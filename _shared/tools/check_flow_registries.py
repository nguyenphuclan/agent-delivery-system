#!/usr/bin/env python
"""Flow files are registered in TWO places, updated by hand, at different moments.

`flows/flow_index.yaml` is the machine index. The project's `knowledge.md` FLOWS table is
the routing surface an agent actually reads. Writing a flow and remembering only one of the
two is silent: the flow is still reachable through whichever half was updated, so nothing
feels broken, and the index's `total:` drifts a little further from the truth each time.

Observed 2026-09-11 on one project's docs store: 27 flow files on disk, all 27 in knowledge.md,
only 26 in flow_index.yaml, and `total:` read 24. Three different numbers for one folder.

This is the flows twin of check_skill_frontmatter.py, and it exists for the same reason: the
prose instruction to "spot-check the index" had been in the audit for months and never caught
this. A gate has to be a command with an exit code.

The check DISCOVERS its targets -- every <store>/flows/ under the docs root -- so a project
added later is measured without editing this file. A "store" is one project's docs folder
(`{project_docs}` in the skills; it holds `knowledge.md` and `flows/`). You may also pass a
single store folder directly.

    python check_flow_registries.py <docs_root | project_docs_store>

Exit 0 = every registry agrees. 1 = drift. 2 = cannot measure (say so, never print clean).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def load_index(path: Path) -> tuple[dict | None, str]:
    try:
        import yaml
    except ImportError:
        return None, "pyyaml absent -- cannot read the index, so nothing is proven"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}, ""
    except Exception as e:  # noqa: BLE001
        return None, f"does not parse: {str(e).strip().splitlines()[0][:90]}"


def audit_store(flows_dir: Path) -> tuple[list[str], list[str], int]:
    """Return (problems, notes, files_examined)."""
    store = flows_dir.parent
    problems: list[str] = []
    notes: list[str] = []

    on_disk = {p.name for p in flows_dir.glob("flow_*.md")} - {"flow_index.yaml"}
    if not on_disk:
        return [f"{store.name}: flows/ holds no flow_*.md -- measured nothing"], [], 0

    idx_path = flows_dir / "flow_index.yaml"
    if not idx_path.exists():
        problems.append(f"{store.name}: flows/flow_index.yaml is absent")
        indexed: set[str] = set()
        declared = None
    else:
        doc, err = load_index(idx_path)
        if doc is None:
            return [f"{store.name}: flow_index.yaml {err}"], [], len(on_disk)
        procs = doc.get("procedures") or {}
        indexed = {v.get("file") for v in procs.values() if isinstance(v, dict)}
        indexed.discard(None)
        declared = doc.get("total")
        if declared is not None and declared != len(procs):
            problems.append(
                f"{store.name}: flow_index.yaml says total: {declared}, but it holds {len(procs)} entries")

    for name in sorted(on_disk - indexed):
        problems.append(f"{store.name}: {name} is on disk but NOT in flow_index.yaml")
    for name in sorted(indexed - on_disk):
        problems.append(f"{store.name}: flow_index.yaml points at {name}, which is not on disk")

    kpath = store / "knowledge.md"
    if not kpath.exists():
        notes.append(f"{store.name}: no knowledge.md -- routing table not checked")
    else:
        ktext = kpath.read_text(encoding="utf-8", errors="replace")
        for name in sorted(n for n in on_disk if n not in ktext):
            problems.append(f"{store.name}: {name} is on disk but NOT named in knowledge.md")
        for name in sorted(n for n in indexed if n not in ktext):
            if name in on_disk:
                continue
            problems.append(f"{store.name}: {name} is indexed but NOT named in knowledge.md")

    return problems, notes, len(on_disk)


def main() -> int:
    # Windows consoles default to cp1252 and print the em dashes below as replacement chars.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="docs root that holds the per-project stores, or one store "
                                 "(a folder with flows/ inside)")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"BLOCKED  docs root does not exist: {root}", file=sys.stderr)
        return 2

    if (root / "flows").is_dir():
        stores = [root / "flows"]          # a single store was passed
    else:
        stores = sorted(p for p in root.glob("*/flows") if p.is_dir())
    if not stores:
        print(f"BLOCKED  no <store>/flows/ found under {root} -- this check measured nothing",
              file=sys.stderr)
        return 2

    all_problems: list[str] = []
    all_notes: list[str] = []
    total_files = 0
    for flows_dir in stores:
        p, n, count = audit_store(flows_dir)
        all_problems += p
        all_notes += n
        total_files += count

    scope = f"{len(stores)} store(s), {total_files} flow file(s)"
    print(f"FLOW REGISTRIES  |  {root}  |  {scope}")
    for n in all_notes:
        print(f"  note     {n}")
    for p in all_problems:
        print(f"  DRIFT    {p}")

    if all_problems:
        print(f"\nDRIFT — {len(all_problems)} registry disagreement(s) over {scope}.")
        print("Each one is an index-add or index-prune op. Fix the registry, never the count alone:")
        print("count the entries, then write the number.")
        return 1
    print(f"\nOK — every flow file, index entry and knowledge.md row agrees, across {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
