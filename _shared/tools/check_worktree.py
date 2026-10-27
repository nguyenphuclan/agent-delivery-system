#!/usr/bin/env python3
"""Is this worktree safe to build, run and test in -- right now?

Two questions, each one a real failure seen on PROJ-7251 (2026-08-27/28):

1. **Is every repo fresh?**  A base-branch move needs EVERY repo refreshed, not just
   the one being edited. PROJ-11394 spanned two repos, so after rebasing the service
   the worktree still held a shared lib 3 commits behind, and the build failed with
   `CS0117 '<Model>' does not contain '<Member>'` -- a missing-member error that reads
   exactly like your own bug. Measured after that ticket finished: two OTHER repos in
   the same worktree were still 7 and 1 commits behind, silently, because nothing had
   forced them to break.

2. **Are this worktree's services running?**  A live service holds the shared lib dll,
   so the next `dotnet build` of a test project dies with MSB3021/MSB3027. The ports
   come from the `ports:` map in `<worktree_root>/.worktree-meta.yaml` (written by
   worktree-setup Phase 6; it holds the currently active port per service, whether the
   worktree runs on offset or default ports). Pass --ports to override or when there is
   no meta file. A running service is reported, not blocked: it is what you want for an
   API test, and what you do not want for a build.

Exit 0 = safe. Exit 2 = BLOCKED, with the reason named. No exit 1 -- this tool reports
the state of the workspace, never a verdict on your code.

    python check_worktree.py <worktree_root> [--fetch] [--base BRANCH] [--ports 5101,5102]

--base defaults to the active project's `base_branch` (or `branch.main_branch`) in
_config/projects.yaml next to the skills, else `main`.
"""

from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECTS_YAML = Path(__file__).resolve().parents[2] / "_config" / "projects.yaml"
META = ".worktree-meta.yaml"
STALE_FETCH_HOURS = 6


def git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - git missing or hung reads as "cannot tell"
        return ""


def _load_yaml(path: Path):
    try:
        import yaml  # noqa: PLC0415 - optional
    except ImportError:
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except Exception:  # noqa: BLE001 - absent or unparsable reads as "no config"
        return None


def base_branch() -> str:
    """Base branch of the active project; `main` when it cannot be read.

    Accepts both config shapes: a project block with `active: true`, or a top-level
    `active: <name>` that names the block."""
    cfg = _load_yaml(PROJECTS_YAML) if PROJECTS_YAML.exists() else None
    if not isinstance(cfg, dict):
        return "main"
    projects = cfg.get("projects") or {}
    proj = projects.get(cfg.get("active")) if isinstance(cfg.get("active"), str) else None
    if proj is None:
        proj = next((p for p in projects.values() if isinstance(p, dict) and p.get("active") is True), None)
    if not isinstance(proj, dict):
        return "main"
    return str(proj.get("base_branch") or (proj.get("branch") or {}).get("main_branch") or "main")


def meta_ports(root: Path) -> tuple[dict[str, int], str]:
    """service -> active port, from the worktree's own meta file. Returns (ports, note)."""
    path = root / META
    if not path.exists():
        return {}, f"no {META}"
    doc = _load_yaml(path)
    ports: dict[str, int] = {}
    if isinstance(doc, dict) and isinstance(doc.get("ports"), dict):
        for svc, port in doc["ports"].items():
            if str(port).isdigit():
                ports[str(svc)] = int(port)
        return ports, f"{META} (port_mode: {doc.get('port_mode') or '?'})"
    # No PyYAML, or an odd shape: read `ports:` as an inline map or an indented block.
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(r"^ports:\s*\{([^}]*)\}", text, re.M)
    if m:
        body = m.group(1)
    else:
        m = re.search(r"^ports:\s*(?:#.*)?\n((?:[ \t]+.*\n?)+)", text, re.M)
        body = m.group(1) if m else ""
    for svc, port in re.findall(r"([\w.-]+)\s*:\s*(\d{2,5})", body):
        ports[svc] = int(port)
    return ports, META


def listening(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--fetch", action="store_true",
                    help="git fetch each repo first (slower, but the freshness answer is only "
                         "as good as the ref it reads)")
    ap.add_argument("--base", help="base branch to compare against (default: from projects.yaml, else main)")
    ap.add_argument("--ports", help="comma-separated ports of this worktree's services "
                                    "(default: the ports: map in .worktree-meta.yaml)")
    args = ap.parse_args()

    root: Path = args.root.resolve()
    if not root.is_dir():
        print(f"BLOCKED  no such worktree: {root}", file=sys.stderr)
        return 2

    base = args.base or base_branch()
    repos = sorted(p for p in root.iterdir() if (p / ".git").exists())
    if not repos:
        print(f"BLOCKED  {root} contains no git repos", file=sys.stderr)
        return 2

    print(f"WORKTREE CHECK  {root}\n  base branch: {base}  ·  repos: {len(repos)}\n")
    blocks: list[str] = []

    # ---- 1. freshness -----------------------------------------------------
    print("1. repo freshness")
    if args.fetch:
        for r in repos:
            git(r, "fetch", "origin", base, "--quiet")
    stale_refs = []
    behind_any = False
    unreadable = 0
    for r in repos:
        fh = r / ".git" / "FETCH_HEAD"
        if not args.fetch and fh.exists():
            age_h = (time.time() - fh.stat().st_mtime) / 3600
            if age_h > STALE_FETCH_HOURS:
                stale_refs.append(f"{r.name} ({age_h:.0f}h)")
        n = git(r, "rev-list", "--count", f"HEAD..origin/{base}")
        cnt = int(n) if n.isdigit() else None
        if cnt is None:
            print(f"   ?      {r.name:<32} cannot read origin/{base}")
            unreadable += 1
        elif cnt == 0:
            print(f"   ok     {r.name:<32} up to date")
        else:
            print(f"   BEHIND {r.name:<32} {cnt} commit(s) behind origin/{base}")
            behind_any = True
    if behind_any:
        blocks.append("a repo is behind the base branch -- refresh EVERY repo, not just the one "
                      "you are editing; a cross-repo ticket breaks the build from the other side")
    if unreadable == len(repos):
        blocks.append(f"no repo could read origin/{base} -- freshness measured nothing "
                      "(wrong --base, or never fetched; try --fetch)")
    if stale_refs:
        print(f"   note   remote refs not fetched recently: {', '.join(stale_refs[:4])}"
              f"{' …' if len(stale_refs) > 4 else ''}  -> re-run with --fetch to trust this section")

    # ---- 2. running services ---------------------------------------------
    print("\n2. this worktree's services")
    if args.ports:
        try:
            ports = {f"port{i}": int(p) for i, p in enumerate(args.ports.split(","), 1) if p.strip()}
        except ValueError:
            print(f"BLOCKED  --ports must be comma-separated numbers: {args.ports}", file=sys.stderr)
            return 2
        source = "--ports"
    else:
        ports, source = meta_ports(root)
    if not ports:
        print(f"   n/a    {source}, and no --ports given -- running services not checked")
    else:
        up = sorted((svc, p) for svc, p in ports.items() if listening(p))
        print(f"   from   {source}: {len(ports)} port(s)")
        if up:
            print(f"   UP     {len(up)} service(s) listening: "
                  + ", ".join(f"{svc}:{p}" for svc, p in up))
            print("   note   a live service holds the shared lib dll -> a test-project build will "
                  "hit MSB3021. Stop the services before building tests.")
        else:
            print("   ok     none running; safe to build")

    print("\nNOT CHECKED  the dev DB is shared by every checkout and nothing guards it -- a worktree "
          "isolates source and ports, not any DB. Assert on ids you created, never on 'the newest row'.")

    if blocks:
        print("\nBLOCKED")
        for b in blocks:
            print(f"  - {b}")
        return 2
    print("\nPASS — worktree is safe to build, run and test in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
