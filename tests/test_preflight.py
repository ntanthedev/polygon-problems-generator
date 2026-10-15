"""Tests for the offline, read-only local problem preflight."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from polyup.preflight import inspect_problem, main


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "problem"
        (self.root / "statement").mkdir(parents=True)
        (self.root / "solutions").mkdir()
        (self.root / "generators").mkdir()
        (self.root / "samples").mkdir()
        (self.root / "validator_tests").mkdir()

        (self.root / "statement" / "statement.tex").write_text(
            "=== LEGEND ===\nFind the sum.\n"
            "=== INPUT ===\nTwo integers.\n"
            "=== OUTPUT ===\nTheir sum.\n"
            "=== NOTES ===\nExample.\n",
            encoding="utf-8",
        )
        (self.root / "validator.cpp").write_text("// placeholder", encoding="utf-8")
        (self.root / "checker.cpp").write_text(
            "// Use standard checker: wcmp\n", encoding="utf-8"
        )
        (self.root / "solutions" / "acc.cpp").write_text("// placeholder", encoding="utf-8")
        (self.root / "generators" / "generator.cpp").write_text(
            "/* FreeMarker script:\ngenerator 1 > test1\n*/\n",
            encoding="utf-8",
        )
        (self.root / "samples" / "01.in").write_text("1 2\n", encoding="utf-8")
        (self.root / "samples" / "01.out").write_text("3\n", encoding="utf-8")

    def error_codes(self):
        return {issue["code"] for issue in inspect_problem(self.root)["errors"]}

    def test_complete_structure_passes_with_warnings(self):
        report = inspect_problem(self.root)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["stats"]["samples"], 1)
        self.assertIn("VALIDATOR_TESTS_EMPTY",
                      {i["code"] for i in report["warnings"]})

    def test_missing_mandatory_files_fail(self):
        (self.root / "solutions" / "acc.cpp").unlink()
        (self.root / "samples" / "01.out").unlink()
        self.assertEqual(inspect_problem(self.root)["status"], "FAIL")
        self.assertIn("MISSING_REQUIRED_FILE", self.error_codes())
        self.assertIn("SAMPLE_OUTPUT_MISSING", self.error_codes())

    def test_unparseable_statement_fails(self):
        (self.root / "statement" / "statement.tex").write_text("unstructured text")
        self.assertIn("STATEMENT_SECTION_EMPTY", self.error_codes())

    def test_duplicate_sample_detection(self):
        (self.root / "samples" / "02.in").write_text("1 2\n")
        (self.root / "samples" / "02.out").write_text("3\n")
        self.assertIn("DUPLICATE_SAMPLE", self.error_codes())

    def test_bad_metadata_fails(self):
        (self.root / ".polygon.json").write_text('{"problemId": }')
        self.assertIn("INVALID_POLYGON_METADATA", self.error_codes())

    def test_missing_directory_fails(self):
        result = inspect_problem(self.root / "missing")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["errors"][0]["code"], "PROBLEM_NOT_FOUND")

    def test_cli_json_and_exit_status(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main([str(self.root), "--json"])
        self.assertEqual(rc, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "PASS")
        (self.root / "validator.cpp").unlink()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.root)]), 1)


if __name__ == "__main__":
    unittest.main()
