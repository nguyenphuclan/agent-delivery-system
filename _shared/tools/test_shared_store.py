"""Proof that shared_store actually prevents the loss it claims to prevent.

A guard that has never gone red is unproven. Each check below runs the SAME scenario twice:
once with a naive read-modify-write (what promote-observations did on 2026-09-18) and once
through shared_store. The naive run must LOSE data, or the test says so and fails -- because a
scenario that cannot reproduce the bug proves nothing about the fix.

    python test_shared_store.py
"""

import io
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared_store import append_lines, rewrite, read_text, fingerprint  # noqa: E402

FAILURES = []


def check(name, ok, detail="", detail_on_pass=""):
    # Show the failure note only on failure. A PASS line carrying the failure's explanation
    # is the same misleading shape this whole module exists to stamp out.
    note = detail_on_pass if ok else detail
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  -- " + note) if note else ""))
    if not ok:
        FAILURES.append(name)


def fresh(tmp, body=""):
    p = os.path.join(tmp, "store.md")
    io.open(p, "w", encoding="utf-8", newline="\n").write(body)
    return p


# --------------------------------------------------------------------------
# 1. the real bug: a slow drain rewrites from a stale snapshot
# --------------------------------------------------------------------------
def naive_drain(path, hold_s):
    text = io.open(path, encoding="utf-8").read()          # read
    time.sleep(hold_s)                                      # ... work ...
    keep = [l for l in text.split("\n") if "DROP" not in l]
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(keep))


def naive_append(path, line, wait_s):
    time.sleep(wait_s)
    text = io.open(path, encoding="utf-8").read()
    if not text.endswith("\n") and text:
        text += "\n"
    io.open(path, "w", encoding="utf-8", newline="\n").write(text + line + "\n")


def scenario_lost_update(tmp, safe):
    path = fresh(tmp, "keep-1\nDROP-me\nkeep-2\n")
    late = "APPENDED-BY-OTHER-SESSION"

    if safe:
        t1 = threading.Thread(target=rewrite, args=(
            path,
            lambda t: (time.sleep(0.8) or "\n".join(l for l in t.split("\n") if "DROP" not in l)),
        ), kwargs={"label": "drainer"})
        t2 = threading.Thread(target=lambda: (time.sleep(0.2), append_lines(path, [late], label="appender")))
    else:
        t1 = threading.Thread(target=naive_drain, args=(path, 0.8))
        t2 = threading.Thread(target=naive_append, args=(path, late, 0.2))

    t1.start(); t2.start(); t1.join(); t2.join()
    body = read_text(path)
    return (late in body), ("DROP" not in body), body


# --------------------------------------------------------------------------
# 2. many appends at once
# --------------------------------------------------------------------------
def scenario_concurrent_appends(tmp, safe, writers=6, each=25):
    path = fresh(tmp, "")
    expected = ["w%d-line%d" % (w, i) for w in range(writers) for i in range(each)]

    def work(w):
        for i in range(each):
            line = "w%d-line%d" % (w, i)
            if safe:
                append_lines(path, [line], label="w%d" % w)
            else:
                naive_append(path, line, 0)

    ts = [threading.Thread(target=work, args=(w,)) for w in range(writers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    have = set(l.strip() for l in read_text(path).split("\n") if l.strip())
    missing = [e for e in expected if e not in have]
    return len(expected), len(missing)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        print("1. slow drain + concurrent append (the 2026-09-18 bug)")
        n_kept, n_dropped, _ = scenario_lost_update(tmp, safe=False)
        check("naive read-modify-write LOSES the concurrent append (must be red)",
              not n_kept,
              "the append SURVIVED -- the scenario did not reproduce the bug, so the safe run below proves nothing",
              detail_on_pass="append lost, as it was on 2026-09-18")
        s_kept, s_dropped, body = scenario_lost_update(tmp, safe=True)
        check("shared_store.rewrite keeps the concurrent append", s_kept, repr(body[:60]))
        check("shared_store.rewrite still did its own job (DROP removed)", s_dropped)

        print("2. six writers appending at once")
        total, missing = scenario_concurrent_appends(tmp, safe=False)
        check("naive append loses lines under contention (must be red)",
              missing > 0, "lost %d/%d" % (missing, total))
        total, missing = scenario_concurrent_appends(tmp, safe=True)
        check("shared_store.append_lines loses nothing", missing == 0,
              "lost %d/%d" % (missing, total))

        print("3. housekeeping")
        p = fresh(tmp, "a\n")
        wrote = append_lines(p, ["a", "b"], label="t")
        check("append_lines skips a line already present", wrote == ["b"], repr(wrote))

        crlf = os.path.join(tmp, "crlf.md")
        io.open(crlf, "wb").write(b"\xef\xbb\xbfone\r\ntwo\r\n")
        append_lines(crlf, ["three"], label="t")
        raw = io.open(crlf, "rb").read()
        check("BOM preserved", raw.startswith(b"\xef\xbb\xbf"))
        check("CRLF preserved", b"three\r\n" in raw, repr(raw[-14:]))

        try:
            rewrite(p, lambda t: None, label="t")
            check("rewrite refuses a None callback", False)
        except ValueError:
            check("rewrite refuses a None callback", True)

        check("fingerprint ignores whitespace",
              fingerprint("a  b", "c") == fingerprint(" a b ", "c"))
        check("fingerprint separates fields",
              fingerprint("ab", "c") != fingerprint("a", "bc"))

    print()
    if FAILURES:
        print("FAILED: " + ", ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
