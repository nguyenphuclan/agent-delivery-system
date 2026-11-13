#!/usr/bin/env python
"""Tests for check_flow_registries.py -- the business-flow half (2026-10-28).

Run: python test_check_flow_registries.py
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_flow_registries as cfr  # noqa: E402

PROC = "procedures:\n  a:\n    file: flow_a.md\ntotal: 1\n"
BF = """flows:
  gdpr-clearing: {health: degraded}
  role-delete: {health: ok}
indexes:
  by_keyword:
    gdpr: [gdpr-clearing]
  by_health:
    ok: [role-delete]
    degraded: [gdpr-clearing]
summary:
  flows_registered: 2
"""


class BusinessFlowTests(unittest.TestCase):
    def run_check(self, files: dict[str, str]) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as root:
            store = Path(root) / "proj"
            base = {"flows/flow_a.md": "# a\n", "knowledge.md": "flow_a.md\n",
                    "flows/flow_index.yaml": PROC + "business_flows_ref: flows/business_flows.yaml\n",
                    "flows/business_flows.yaml": BF}
            base.update(files)
            for rel, text in base.items():
                if text is None:
                    continue
                p = store / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            out = io.StringIO()
            argv, sys.argv = sys.argv, ["check_flow_registries.py", root]
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    code = cfr.main()
            finally:
                sys.argv = argv
            return code, out.getvalue()

    def test_clean_store_passes_and_counts_business_flows(self):
        code, out = self.run_check({})
        self.assertEqual(code, 0, out)
        self.assertIn("2 business flow(s)", out)

    def test_no_business_flows_is_a_note_not_drift(self):
        code, out = self.run_check({"flows/flow_index.yaml": PROC, "flows/business_flows.yaml": None})
        self.assertEqual(code, 0, out)
        self.assertIn("no business flows", out)

    def test_ref_to_missing_file_is_drift(self):
        code, out = self.run_check({"flows/business_flows.yaml": None})
        self.assertEqual(code, 1, out)
        self.assertIn("not on disk", out)

    def test_file_without_ref_is_drift(self):
        code, out = self.run_check({"flows/flow_index.yaml": PROC + "business_flows_ref: flows/other.yaml\n",
                                    "flows/other.yaml": BF})
        self.assertEqual(code, 1, out)
        self.assertIn("does not point at it", out)

    def test_index_naming_unknown_flow_is_drift(self):
        code, out = self.run_check({"flows/business_flows.yaml": BF.replace("gdpr: [gdpr-clearing]", "gdpr: [gdpr-x]")})
        self.assertEqual(code, 1, out)
        self.assertIn("'gdpr-x', which is not a flow", out)

    def test_count_mismatch_is_drift(self):
        code, out = self.run_check({"flows/business_flows.yaml": BF.replace("flows_registered: 2", "flows_registered: 3"),
                                    "_index.yaml": "artifacts:\n  business_flows: {flow_count: 5}\n"})
        self.assertEqual(code, 1, out)
        self.assertIn("flows_registered: 3", out)
        self.assertIn("flow_count is 5", out)

    def test_concern_naming_unknown_flow_is_drift(self):
        code, out = self.run_check({"flows/_concerns.yaml": "concerns:\n  - {id: c-001, related_flows: [nope]}\n"})
        self.assertEqual(code, 1, out)
        self.assertIn("c-001", out)

    def test_legacy_flow_index_holding_flows_is_its_own_business_file(self):
        with tempfile.TemporaryDirectory() as root:
            flows = Path(root) / "flows"
            flows.mkdir()
            (flows / "flow_index.yaml").write_text(BF, encoding="utf-8")
            self.assertEqual(cfr.business_flows_path(Path(root)), flows / "flow_index.yaml")


if __name__ == "__main__":
    unittest.main(verbosity=1)
