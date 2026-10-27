#!/usr/bin/env python3
"""Keep do-ticket artifact fingerprints honest across a run.

  python ticket_fingerprints.py check   <ticket_dir>
  python ticket_fingerprints.py refresh <ticket_dir> <file> [<file> ...] --reason "<why it was edited>"

Why this exists. A phase stores `fingerprints.<artifact>_sha` in ticket-context.yaml when it ENDS. The run
then keeps editing some artifacts on purpose -- a decision added to plan.md, a removed step in test-cases.md
-- and nothing re-fingerprinted them. On resume the stale-fingerprint sweep (phases/start.md, Phase 0) saw 4 "changed"
files and would have asked 4 times whether to regenerate work that was correct (PROJ-11212). A rule saying
"remember to update the fingerprint" was already in SKILL.md and did not bind, so the edit step now runs this.

refresh  writes the current sha of each named file into `fingerprints:` (inserting the key if missing) and
         leaves the reason as a YAML comment on that line, so a resume can tell a deliberate edit from drift.
check    compares every `<name>_sha` key it can map to a file in the ticket dir with the file on disk.
         Keys with no matching file (projects.yaml, the project index) are listed as `unmapped`, not drift.

Exit codes: 0 no drift (check) / written (refresh) · 3 drift found (check) · 2 usage or file error.
"""
import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

CTX = "ticket-context.yaml"
KEY_LINE_RE = re.compile(r"^(?P<indent>\s+)(?P<key>[a-z0-9_]+_sha)(?P<sfx>_v\d+)?:\s*(?P<val>[0-9a-f]+)(?P<rest>.*)$")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def key_for(file_name: str) -> str:
    # requirements-analysis.md -> requirements_analysis_sha
    return re.sub(r"[^a-z0-9]+", "_", Path(file_name).stem.lower()).strip("_") + "_sha"


def file_for(ticket_dir: Path, key: str):
    stem = key[: -len("_sha")]
    for name in (stem.replace("_", "-"), stem):
        for ext in (".md", ".yaml", ".yml"):
            p = ticket_dir / (name + ext)
            if p.is_file():
                return p
    return None


def fingerprint_block(lines):
    """(start, end) line indexes of the body of the top-level `fingerprints:` block."""
    for i, ln in enumerate(lines):
        if ln.rstrip() == "fingerprints:":
            j = i + 1
            while j < len(lines) and (lines[j].startswith(" ") or not lines[j].strip()):
                j += 1
            return i + 1, j
    return None


def check(ticket_dir: Path) -> int:
    ctx = ticket_dir / CTX
    if not ctx.is_file():
        print(f"ERROR no {CTX} in {ticket_dir}", file=sys.stderr)
        return 2
    lines = ctx.read_text(encoding="utf-8").splitlines()
    block = fingerprint_block(lines)
    if block is None:
        print("no fingerprints block - nothing to check")
        return 0
    drift = 0
    for ln in lines[block[0]:block[1]]:
        m = KEY_LINE_RE.match(ln)
        if not m:
            continue
        key = m.group("key") + (m.group("sfx") or "")
        f = file_for(ticket_dir, m.group("key"))
        if f is None:
            print(f"  unmapped  {key}")
            continue
        now = sha(f)
        stored = m.group("val")
        # A full 64-char sha256 (older runs, other tools) of the same bytes starts with our
        # 16-char form; only the length differs, so compare on the shorter one (PROJ-10837).
        if stored[:len(now)] == now or now[:len(stored)] == stored:
            print(f"  ok        {key:34} {f.name}")
        else:
            drift += 1
            print(f"  DRIFT     {key:34} {f.name}  stored={m.group('val')} now={now}")
    print(f"{'DRIFT' if drift else 'CLEAN'} - {drift} artifact(s) changed since they were fingerprinted")
    return 3 if drift else 0


def refresh(ticket_dir: Path, files, reason: str) -> int:
    ctx = ticket_dir / CTX
    if not ctx.is_file():
        print(f"ERROR no {CTX} in {ticket_dir}", file=sys.stderr)
        return 2
    # read_text() turns CRLF into LF, so it cannot tell which line ending to write back - read the bytes.
    text = ctx.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    block = fingerprint_block(lines)
    if block is None:
        lines.append("fingerprints:")
        block = (len(lines), len(lines))
    stamp = datetime.now().strftime("%Y-%m-%d")
    note = reason.replace("#", "").strip()
    for name in files:
        f = ticket_dir / name
        if not f.is_file():
            print(f"ERROR {name} not found in {ticket_dir}", file=sys.stderr)
            return 2
        key = key_for(name)
        new_line = f"  {key}: {sha(f)}  # refreshed {stamp}: {note}"
        start, end = block
        hit = [i for i in range(start, end) if (m := KEY_LINE_RE.match(lines[i])) and m.group("key") == key and not m.group("sfx")]
        if hit:
            lines[hit[0]] = new_line
        else:
            lines.insert(start, new_line)
            block = (start, end + 1)
        print(f"  refreshed {key} <- {name}")
    ctx.write_text(nl.join(lines) + nl, encoding="utf-8", newline="")
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("ticket_dir", type=Path)
    r = sub.add_parser("refresh")
    r.add_argument("ticket_dir", type=Path)
    r.add_argument("files", nargs="+")
    r.add_argument("--reason", required=True, help="why the artifact was edited after its phase ended")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return check(a.ticket_dir)
    return refresh(a.ticket_dir, a.files, a.reason)


if __name__ == "__main__":
    sys.exit(main())
