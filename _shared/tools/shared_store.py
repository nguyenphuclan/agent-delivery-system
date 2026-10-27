"""Safe reads and writes for the stores that SEVERAL Claude sessions share.

Why this exists: `observations.md` (and any other append-mostly log the skills keep) is written
by whichever session happens to be running. On 2026-09-18 two sessions overlapped. Session A
read observations.md, worked for a few minutes, then rewrote the file from its own stale copy --
and everything session B had appended in between was gone. Nothing errored. The drain simply
reported a smaller number than it should have, and nobody could tell.

The bug is READ-MODIFY-WRITE without a lock, so that is what this module removes. The lock is
a plain file created atomically in a lock folder (default `~/.claude/locks`, override with the
CLAUDE_LOCK_DIR environment variable). A stale lock is one whose pid is gone, and clearing it
says so out loud. A live holder is waited for, never killed.

    from shared_store import append_lines, rewrite, fingerprint

    append_lines(OBS, ["2026-09-18 | git | ... | 1"], label="learn")

    def drain(text):                      # receives the CURRENT file, never your snapshot
        return "\\n".join(l for l in text.split("\\n") if keep(l))
    rewrite(OBS, drain, label="promote-observations")

Rules this module enforces for you:
  * the callback in `rewrite` is handed a FRESH read taken INSIDE the lock;
  * writes are atomic (temp file in the same folder + os.replace), so a crash mid-write
    cannot leave a half file;
  * BOM and CRLF are preserved exactly -- this store has lost data to both before;
  * `append_lines` skips lines already present, so a retry cannot double-write.

Stdlib only. Works on Windows and POSIX.
"""

import io
import json
import os
import hashlib
import tempfile
import threading
import time
from contextlib import contextmanager

__all__ = ["lock", "append_lines", "rewrite", "read_text", "fingerprint", "LockTimeout"]

_STALE_AFTER_S = 30 * 60          # a held lock older than this, whose pid is gone, is stale


class LockTimeout(RuntimeError):
    pass


def _lock_dir():
    d = os.environ.get("CLAUDE_LOCK_DIR") or os.path.expanduser("~/.claude/locks")
    os.makedirs(d, exist_ok=True)
    return d


def _pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if os.name == "nt":
        import subprocess
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _lock_path(name):
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    return os.path.join(_lock_dir(), "store-%s.lock" % safe)


@contextmanager
def lock(name, label="unnamed", timeout_s=120):
    """Machine-wide lock for one store. Waits; never kills the holder."""
    path = _lock_path(name)
    deadline = time.time() + timeout_s
    announced = False

    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({
                "pid": os.getpid(), "label": label, "at": time.time(),
            }).encode("utf-8"))
            os.close(fd)
            break
        except FileExistsError:
            holder = {}
            try:
                with io.open(path, encoding="utf-8") as f:
                    holder = json.loads(f.read() or "{}")
            except Exception:
                holder = {}
            # An empty holder is usually a lock being written right now (created, not yet
            # filled). Age it by the file's mtime, never by "at = 0", or a live lock looks
            # decades old and gets cleared under its owner.
            try:
                born = float(holder.get("at") or os.path.getmtime(path))
            except OSError:
                continue  # the holder released it between our two calls; try again
            age = time.time() - born
            if not _pid_alive(holder.get("pid")) and age > 5:
                # Say it out loud. A lock that clears silently hides a crash loop.
                if _clear_stale(path, holder):
                    print("  cleared stale store lock '%s' from '%s' (pid %s is gone, %.0fs old)"
                          % (name, holder.get("label"), holder.get("pid"), age))
                continue
            if age > _STALE_AFTER_S:
                print("  WARNING: store lock '%s' held by live pid %s for %.0f min"
                      % (name, holder.get("pid"), age / 60.0))
            if time.time() >= deadline:
                raise LockTimeout(
                    "waited %ds for store '%s', still held by '%s' (pid %s). Nothing was written."
                    % (timeout_s, name, holder.get("label"), holder.get("pid")))
            if not announced:
                print("  waiting for store '%s' held by '%s'..." % (name, holder.get("label")))
                announced = True
            time.sleep(0.4)

    try:
        yield
    finally:
        _release(path)


def _clear_stale(path, holder):
    """Remove a dead holder's lock without removing a live one by mistake.

    Two waiters can see the same stale lock. If both simply delete it, the second delete can
    land on the FRESH lock the first waiter just created, and two writers then run at once.
    So move the file aside atomically first (only one waiter can win the rename), then check
    that what was moved is the stale holder we judged. If it is not, put it back."""
    tomb = "%s.stale-%d-%d" % (path, os.getpid(), threading.get_ident())
    try:
        os.rename(path, tomb)
    except OSError:
        return False  # another waiter cleared it first, or the holder released it
    moved = {}
    try:
        with io.open(tomb, encoding="utf-8") as f:
            moved = json.loads(f.read() or "{}")
    except Exception:
        moved = {}
    if (moved.get("pid"), moved.get("at")) != (holder.get("pid"), holder.get("at")):
        try:
            os.rename(tomb, path)  # it was a live lock; give it back
            return False
        except OSError:
            pass
    _release(tomb)
    return True


def _release(path):
    """Delete the lock file. On Windows the delete fails while any other process or thread
    has the file open -- a waiter reading the holder's name is enough. Swallowing that
    error once left a lock owned by a LIVE pid on disk forever, and every later writer
    timed out. So retry, and say so if it still cannot be removed."""
    last = None
    for attempt in range(50):
        try:
            os.unlink(path)
            return
        except FileNotFoundError:
            return
        except PermissionError as e:
            last = e
            time.sleep(0.02 * (attempt + 1))
        except OSError as e:
            last = e
            break
    print("  WARNING: could not release store lock %s: %s" % (path, last))


def _read_raw(path):
    if not os.path.exists(path):
        return b""
    return io.open(path, "rb").read()


def _decode(raw):
    bom = raw[:3] == b"\xef\xbb\xbf"
    crlf = b"\r\n" in raw
    return raw.decode("utf-8-sig"), bom, crlf


def _write_atomic(path, text, bom, crlf):
    body = text.replace("\r\n", "\n")
    if crlf:
        body = body.replace("\n", "\r\n")
    data = (b"\xef\xbb\xbf" if bom else b"") + body.encode("utf-8")
    folder = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-store-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        # Windows refuses the rename while ANY handle is open on either side -- an indexer or
        # an on-access virus scanner grabs the temp file the moment we close it.
        # It clears in milliseconds, so retry. Measured 10/150 writes hitting this without it.
        last = None
        for attempt in range(40):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as e:
                last = e
                time.sleep(0.02 * (attempt + 1))
        raise OSError("could not replace %s after 40 tries: %s" % (path, last))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_text(path):
    """Plain read. No lock -- only for reporting, never as the input to a write."""
    return _decode(_read_raw(path))[0]


def append_lines(path, lines, label="unnamed", store=None, timeout_s=120):
    """Append under lock. Re-reads first, so a concurrent append is never clobbered.
    Lines already present are skipped -- a retry cannot double-write.
    Returns the lines it actually wrote.

    FLAT LINE LOGS ONLY. The skip-if-present rule compares WHOLE LINES against the whole file,
    so it cannot tell "this line is a duplicate" from "this line repeats elsewhere by nature".
    Feed it a structured block and it silently drops the lines that are not unique -- a YAML
    entry loses its `service:`, `port_main:` and even `note: >` keys if any of those strings
    appear in another entry, and what lands is an orphan text block that no longer parses.
    Observed 2026-09-29 on a shared YAML action index.

    For anything with repeated keys or required ordering -- YAML entries, tables, sections --
    use `rewrite()` and place the block yourself. Then PARSE THE FILE BACK and assert your
    content is there; the drop is silent and append_lines reports success either way.

    Second trap from the same run: `lines` must be a LIST. Passing a string makes Python
    iterate it character by character and write one character per line."""
    store = store or os.path.basename(path)
    with lock(store, label, timeout_s):
        raw = _read_raw(path)
        text, bom, crlf = _decode(raw)
        have = set(l.strip() for l in text.replace("\r\n", "\n").split("\n") if l.strip())
        new = [l for l in lines if l.strip() and l.strip() not in have]
        if not new:
            return []
        sep = "" if (text.endswith("\n") or not text) else "\n"
        _write_atomic(path, text + sep + "\n".join(new) + "\n", bom, crlf)
        return new


def rewrite(path, fn, label="unnamed", store=None, timeout_s=120):
    """Read-modify-write under lock. `fn` receives the CURRENT text, read inside the lock,
    and returns the new text. This is the only safe way to DRAIN a shared store."""
    store = store or os.path.basename(path)
    with lock(store, label, timeout_s):
        raw = _read_raw(path)
        text, bom, crlf = _decode(raw)
        out = fn(text)
        if out is None:
            raise ValueError("rewrite callback returned None -- refusing to blank %s" % path)
        if out == text:
            return False
        _write_atomic(path, out, bom, crlf)
        return True


def fingerprint(*parts, length=12):
    """Content id for an entry, so the SAME case transported twice is detectable no matter
    what position or sequence number it got. Positional ids collide across sessions."""
    h = hashlib.sha256()
    for p in parts:
        h.update(" ".join(str(p or "").split()).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:length]
