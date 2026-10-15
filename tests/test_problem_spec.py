"""ING-001 specification schema, import adapter and CLI tests (no Polygon calls)."""
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from factory.__main__ import main
from factory.spec import (
    ProblemSpecError,
    from_polygon_folder,
    inspect_spec,
    load_schema,
    parse_json,
)

FIXTURES = Path(__file__).resolve().parent.parent / "factory" / "fixtures"


class SchemaFixturesTests(unittest.TestCase):
    def test_schema_is_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(load_schema())

    def test_all_valid_fixtures_pass_structural_validation(self):
        entries = sorted((FIXTURES / "valid").glob("*.json"))
        self.assertGreaterEqual(len(entries), 4)
        for path in entries:
            with self.subTest(path=path.name):
                report = inspect_spec(parse_json(path.read_text(encoding="utf-8")))
                self.assertEqual(report["status"], "PASS", report["errors"])

    def test_all_invalid_fixtures_fail(self):
        entries = sorted((FIXTURES / "invalid").glob("*.json"))
        self.assertGreaterEqual(len(entries), 5)
        for path in entries:
            with self.subTest(path=path.name):
                report = inspect_spec(parse_json(path.read_text(encoding="utf-8")))
                self.assertEqual(report["status"], "FAIL", path.name)

    def test_ready_fixtures_and_draft_distinction(self):
        for name in ("ready-statement-only.json", "ready-with-idea.json",
                     "ready-with-solution.json"):
            with self.subTest(name=name):
                spec = parse_json((FIXTURES / "valid" / name).read_text())
                self.assertEqual(inspect_spec(spec, ready=True)["status"], "PASS")
        for name in ("draft-incomplete.json", "draft-new-idea.json"):
            with self.subTest(name=name):
                spec = parse_json((FIXTURES / "valid" / name).read_text())
                report = inspect_spec(spec, ready=True)
                self.assertEqual(report["status"], "FAIL")
                self.assertIn("SOURCE_UNREVIEWED", [e["code"] for e in report["errors"]])

    def test_duplicate_json_properties_rejected(self):
        with self.assertRaisesRegex(ProblemSpecError, "Duplicate"):
            parse_json('{"schemaVersion": 1, "schemaVersion": 2}')

    def test_non_object_top_level_rejected(self):
        with self.assertRaisesRegex(ProblemSpecError, "object"):
            parse_json("[]")

    def test_solution_path_traversal_rejected(self):
        spec = parse_json((FIXTURES / "valid" / "ready-with-solution.json").read_text())
        spec["guidance"]["solution"]["file"] = "../secret.cpp"
        report = inspect_spec(spec)
        self.assertIn("UNSAFE_PATH", [x["code"] for x in report["errors"]])

    def test_sample_contents_are_not_normalized_in_schema(self):
        spec = parse_json((FIXTURES / "valid" / "ready-statement-only.json").read_text())
        spec["statement"]["samples"] = [
            {"input": "\r\n1 2\r\n", "output": "  3 \r\n", "explanation": None},
        ]
        self.assertEqual(inspect_spec(spec, ready=True)["status"], "PASS")
        self.assertEqual(spec["statement"]["samples"][0]["input"], "\r\n1 2\r\n")


class FromLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "two_sum"
        (self.root / "statement").mkdir(parents=True)
        (self.root / "samples").mkdir()
        (self.root / "solutions").mkdir()
        self.raw = (
            b"=== TITLE ===\r\n\\textbf{\\Large Two Sum}\r\n"
            b"=== LEGEND ===\r\nAdd two integers.\r\n"
            b"=== INPUT ===\r\nTwo integers a and b.\r\n"
            b"=== OUTPUT ===\r\nTheir sum.\r\n"
            b"=== NOTES ===\r\nExplanation.\r\n"
        )
        (self.root / "statement" / "statement.tex").write_bytes(self.raw)
        (self.root / "samples" / "01.in").write_bytes(b"2 3\r\n")
        (self.root / "samples" / "01.out").write_bytes(b"5\r\n")

    def test_import_is_draft_with_exact_original_bytes_and_samples(self):
        spec = from_polygon_folder(self.root)
        self.assertEqual(spec["mode"], "statement-only")
        self.assertEqual(spec["statement"]["title"], "Two Sum")
        self.assertEqual(spec["source"]["rawText"].encode("utf-8"), self.raw)
        self.assertEqual(spec["source"]["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(spec["statement"]["samples"][0]["input"], "2 3\r\n")
        self.assertEqual(spec["statement"]["samples"][0]["output"], "5\r\n")
        self.assertEqual(spec["source"]["reviewStatus"], "pending")
        self.assertEqual(spec["statement"]["constraints"], [])
        self.assertIn("statement.constraints",
                      [a["field"] for a in spec["ambiguities"]])
        self.assertEqual(inspect_spec(spec)["status"], "PASS")
        self.assertEqual(inspect_spec(spec, ready=True)["status"], "FAIL")
        self.assertFalse((self.root / "spec.json").exists())

    def test_optional_user_idea_and_solution(self):
        (self.root / "notes.txt").write_text("Use long long.\n")
        (self.root / "solutions" / "acc.cpp").write_text("int main() {return 0;}")
        idea = from_polygon_folder(self.root, idea_file="notes.txt")
        self.assertEqual(idea["mode"], "statement+idea")
        self.assertEqual(idea["guidance"]["idea"]["text"], "Use long long.\n")
        sol = from_polygon_folder(self.root, idea="Add", solution_file="solutions/acc.cpp")
        self.assertEqual(sol["mode"], "statement+solution")
        self.assertIn("idea", sol["guidance"])
        self.assertEqual(sol["guidance"]["solution"]["file"], "solutions/acc.cpp")
        self.assertEqual(sol["guidance"]["solution"]["providedBy"], "user")

    def test_missing_output_is_blocking_but_source_retained(self):
        (self.root / "samples" / "01.out").unlink()
        spec = from_polygon_folder(self.root)
        self.assertEqual(spec["statement"]["samples"], [])
        problems = [a["issue"] for a in spec["ambiguities"] if a["severity"] == "blocking"]
        self.assertTrue(any("Sample output missing" in x for x in problems))
        self.assertEqual(spec["source"]["rawText"].encode(), self.raw)

    def test_no_title_never_invented_from_folder_name(self):
        (self.root / "statement" / "statement.tex").write_text(
            "=== LEGEND ===\nSum.\n=== INPUT ===\nTwo numbers.\n"
            "=== OUTPUT ===\nSum of numbers.\n"
        )
        spec = from_polygon_folder(self.root)
        self.assertIsNone(spec["statement"]["title"])
        self.assertIn("statement.title", [x["field"] for x in spec["ambiguities"]])

    def test_solution_path_escape_is_rejected(self):
        with self.assertRaises(ProblemSpecError):
            from_polygon_folder(self.root, solution_file="../secret.cpp")

    def test_unsupported_encoding_is_rejected(self):
        (self.root / "statement" / "statement.tex").write_bytes(b"\xff")
        with self.assertRaisesRegex(ProblemSpecError, "UTF-8"):
            from_polygon_folder(self.root)

    def test_empty_idea_is_not_a_fake_hint(self):
        with self.assertRaisesRegex(ProblemSpecError, "blank"):
            from_polygon_folder(self.root, idea=" \n ")

    def test_cli_validate_json_and_ready(self):
        draft = self.root / "draft.json"
        draft.write_text(json.dumps(from_polygon_folder(self.root)))
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["spec", "validate", str(draft), "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "PASS")
        with redirect_stdout(io.StringIO()):
            rc = main(["spec", "validate", str(draft), "--ready"])
        self.assertEqual(rc, 1)

    def test_cli_import_stdout_is_read_only(self):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = main(["spec", "from-local", str(self.root)])
        self.assertEqual(rc, 0)
        self.assertEqual(parse_json(output.getvalue())["mode"], "statement-only")
        self.assertFalse((self.root / "spec.json").exists())

    def test_cli_output_never_overwrites_existing_file(self):
        output = self.root / "spec.json"
        output.write_text("owned by user\n")
        stderr = io.StringIO()
        with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
            rc = main(["spec", "from-local", str(self.root), "--output", str(output)])
        self.assertEqual(rc, 1)
        self.assertEqual(output.read_text(), "owned by user\n")

    def test_cli_output_is_valid_json(self):
        output = self.root / "spec.json"
        with redirect_stdout(io.StringIO()):
            rc = main(["spec", "from-local", str(self.root),
                       "--idea", "Sum a and b.", "--output", str(output)])
        self.assertEqual(rc, 0)
        self.assertEqual(parse_json(output.read_text())["mode"], "statement+idea")

    def test_does_not_touch_polygon_api(self):
        with mock.patch("polyup.api.requests.post") as post:
            from_polygon_folder(self.root)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
