"""Offline ING-002 text import and safety regression tests."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from factory.__main__ import main
from factory.ingest import ingest_file
from factory.spec import ProblemSpecError, inspect_spec

SOURCE = (
    "# Addition Task\r\n## Problem Statement\r\nAdd a and b.\r\n"
    "## Input\r\nTwo integers a and b.\r\n## Output\r\nTheir sum.\r\n"
    "## Constraints\r\n- 1 <= a,b <= 100\r\n"
    "## Sample Input\r\n~~~\r\n2 3\r\n~~~\r\n"
    "## Sample Output\r\n~~~\r\n5\r\n~~~\r\n"
)

class ImportTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "problem.md"
        self.source.write_bytes(SOURCE.encode())
        self.dest = self.root / "new_problem"

    def run_import(self, **kwargs):
        return ingest_file(self.source, slug="new_problem", dest=self.dest, **kwargs)

    def spec(self):
        return json.loads((self.dest / "spec.json").read_text())

    def test_markdown_preserves_original_bytes(self):
        self.run_import()
        spec = self.spec()
        self.assertEqual((self.dest / "source" / "original.md").read_bytes(), SOURCE.encode())
        self.assertEqual(spec["source"]["rawText"], SOURCE)
        self.assertEqual(spec["source"]["sha256"], hashlib.sha256(SOURCE.encode()).hexdigest())
        self.assertEqual(spec["statement"]["title"], "Addition Task")
        self.assertEqual(spec["statement"]["samples"],
                         [{"input":"2 3\n","output":"5\n","explanation":None}])
        self.assertEqual(spec["statement"]["testCaseMode"], "unknown")
        self.assertEqual(inspect_spec(spec)["status"], "PASS")
        self.assertEqual(inspect_spec(spec, ready=True)["status"], "FAIL")

    def test_constraints_require_review(self):
        self.run_import()
        spec = self.spec()
        self.assertEqual(spec["statement"]["constraints"][0]["expression"], "1 <= a,b <= 100")
        self.assertIn("statement.constraints", [a["field"] for a in spec["ambiguities"]])

    def test_numbered_samples(self):
        self.source = self.root / "plain.txt"
        self.source.write_text("Title: Test\nProblem Statement\nX\nInput\nx\nOutput\nx\n"
                               "Sample Input 1\n1\nSample Output 1\n1\n"
                               "Sample Input 2\n2\nSample Output 2\n2\n")
        self.run_import()
        self.assertEqual([x["input"] for x in self.spec()["statement"]["samples"]],
                         ["1\n","2\n"])

    def test_unpaired_sample(self):
        self.source.write_text("# X\n## Sample Input\n7\n")
        self.run_import()
        spec = self.spec()
        self.assertFalse(spec["statement"]["samples"])
        self.assertTrue(any("missing output" in a["issue"] for a in spec["ambiguities"]))

    def test_no_hallucinated_sections(self):
        self.source.write_text("A short unstructured paragraph.")
        self.run_import()
        spec = self.spec()
        self.assertIsNone(spec["statement"]["title"])
        self.assertIsNone(spec["statement"]["output"])
        self.assertFalse(spec["statement"]["samples"])

    def test_user_idea_and_solution_are_copied(self):
        solution = self.root / "user.cpp"
        solution.write_bytes(b"int main(){return 0;}")
        self.run_import(idea="Sort first", solution_file=solution)
        spec = self.spec()
        self.assertEqual(spec["mode"], "statement+solution")
        self.assertEqual(spec["guidance"]["idea"]["text"], "Sort first")
        self.assertEqual((self.dest / "solutions" / "user.cpp").read_bytes(), solution.read_bytes())

    def test_existing_destination_kept(self):
        self.dest.mkdir()
        (self.dest / "mine").write_text("keep")
        with self.assertRaises(ProblemSpecError):
            self.run_import()
        self.assertEqual((self.dest / "mine").read_text(), "keep")

    def test_invalid_slug_and_binary_input(self):
        with self.assertRaises(ProblemSpecError):
            ingest_file(self.source, slug="../oops", dest=self.dest)
        self.source.write_bytes(b"\xff")
        with self.assertRaises(ProblemSpecError):
            self.run_import()
        self.assertFalse(self.dest.exists())

    def test_cli_offline_no_polygon(self):
        with mock.patch("polyup.api.requests.post") as post, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["ingest", str(self.source), "--slug", "new_problem",
                                   "--dest", str(self.dest)]), 0)
        post.assert_not_called()

    def test_cli_refuses_existing_destination(self):
        self.dest.mkdir()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["ingest", str(self.source), "--slug", "new_problem",
                                   "--dest", str(self.dest)]), 1)

if __name__ == "__main__":
    unittest.main()
