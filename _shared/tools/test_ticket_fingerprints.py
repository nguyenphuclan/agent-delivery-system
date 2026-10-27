"""Tests for ticket_fingerprints.py. Run: python test_ticket_fingerprints.py (exit 0 = all passed)."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ticket_fingerprints as tf  # noqa: E402

CTX = """ticket_id: T-1
fingerprints:
  projects_yaml_sha: 765620f78a408b6c
  plan_sha: {plan}
  test_cases_sha: {tc}
phases_run:
  - {{phase: plan}}
"""


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "plan.md").write_text("plan v1", encoding="utf-8")
        (self.d / "test-cases.md").write_text("tc v1", encoding="utf-8")
        (self.d / "ticket-context.yaml").write_text(
            CTX.format(plan=tf.sha(self.d / "plan.md"), tc=tf.sha(self.d / "test-cases.md")), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = tf.check(self.d)
        return code, out.getvalue()

    def test_clean_when_nothing_changed(self):
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("unmapped  projects_yaml_sha", out)

    def test_full_length_sha_of_the_same_file_is_not_drift(self):
        # PROJ-10837: a run (and older tickets) stored the full 64-char sha256; the tool
        # stores 16. Same file, same hash -- only the length differs -- must read as clean.
        import hashlib
        full = hashlib.sha256((self.d / "plan.md").read_bytes()).hexdigest()
        ctx = self.d / "ticket-context.yaml"
        ctx.write_text(ctx.read_text(encoding="utf-8").replace(tf.sha(self.d / "plan.md"), full), encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_edit_after_phase_is_drift(self):
        (self.d / "plan.md").write_text("plan v2 - decision added", encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, 3)
        self.assertIn("DRIFT     plan_sha", out)

    def test_refresh_clears_drift_and_keeps_the_reason(self):
        (self.d / "plan.md").write_text("plan v2 - decision added", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(tf.refresh(self.d, ["plan.md"], "D7 decision recorded"), 0)
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        ctx = (self.d / "ticket-context.yaml").read_text(encoding="utf-8")
        self.assertIn("# refreshed", ctx)
        self.assertIn("D7 decision recorded", ctx)
        self.assertEqual(ctx.count("plan_sha:"), 1)

    def test_refresh_inserts_a_missing_key_inside_the_block(self):
        (self.d / "blast-radius.md").write_text("counts", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            tf.refresh(self.d, ["blast-radius.md"], "new artifact")
        lines = (self.d / "ticket-context.yaml").read_text(encoding="utf-8").splitlines()
        start, end = tf.fingerprint_block(lines)
        self.assertTrue(any("blast_radius_sha:" in ln for ln in lines[start:end]))
        self.assertIn("phases_run:", lines)

    def test_refresh_keeps_crlf_files_crlf(self):
        p = self.d / "ticket-context.yaml"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        with redirect_stdout(io.StringIO()):
            tf.refresh(self.d, ["plan.md"], "x")
        raw = p.read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
