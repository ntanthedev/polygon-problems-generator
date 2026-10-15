"""Offline, mocked tests for the conservative Polygon sync plan."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from polyup.api import PolygonAPI, PolygonAPIError
from polyup.config import SyncConfig
from polyup.sync import _sync_tests, sync_problem
from polyup.sync_plan import (
    UnsafeSyncError, assert_remote_unchanged, build_sync_plan,
)


class FakeReadAPI:
    def __init__(self, *, revision=4, working_copy=None, validator_tests=None,
                 checker_tests=None, source_files=None, tests=None, status="WRITE"):
        self.revision = revision
        self.working_copy = working_copy
        self.validator_tests = validator_tests if validator_tests is not None else []
        self.checker_tests = checker_tests if checker_tests is not None else []
        self.source_files = source_files if source_files is not None else [
            {"name": "validator.cpp", "length": 10, "modificationTimeSeconds": 0}
        ]
        self.tests = tests if tests is not None else []
        self.status = status
        self.calls = []

    def call(self, method, **kwargs):
        self.calls.append((method, kwargs))
        if method == "problems.list":
            row = {"id": 7, "revision": self.revision, "accessType": self.status,
                   "deleted": False}
            if self.working_copy is not None:
                row["workingCopyRevision"] = self.working_copy
            return [row]
        if method == "problem.info":
            return {"timeLimit": 1000, "memoryLimit": 256}
        if method == "problem.files":
            return {"sourceFiles": self.source_files, "resourceFiles": [], "auxFiles": []}
        if method == "problem.solutions":
            return [{"name": "acc.cpp", "length": 12}]
        if method == "problem.statements":
            return {"english": {"name": "Example"}}
        if method == "problem.tests":
            return self.tests
        if method == "problem.validatorTests":
            return self.validator_tests
        if method == "problem.checkerTests":
            return self.checker_tests
        raise AssertionError("Unexpected read/write call " + method)


class SyncPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "sample"
        for directory in ("statement", "solutions", "generators", "samples",
                          "validator_tests"):
            (self.root / directory).mkdir(parents=True)
        (self.root / "statement" / "statement.tex").write_text(
            "=== LEGEND ===\nCalculate sum.\n"
            "=== INPUT ===\nTwo numbers.\n"
            "=== OUTPUT ===\nSum of both.\n")
        (self.root / "validator.cpp").write_text("#include <testlib.h>\n")
        (self.root / "checker.cpp").write_text("// Use standard checker: wcmp\n")
        (self.root / "solutions" / "acc.cpp").write_text("int main() {}")
        (self.root / "generators" / "generator.cpp").write_text(
            "/* FreeMarker script:\ngenerator 1 > t1\n*/\n")
        (self.root / "samples" / "01.in").write_text("1 2\n")
        (self.root / "samples" / "01.out").write_text("3\n")

    def make_existing(self):
        (self.root / ".polygon.json").write_text('{"problemId": 7}\n')

    def test_create_plan_is_read_only_and_has_operations(self):
        plan = build_sync_plan(self.root)
        self.assertEqual(plan["mode"], "create")
        self.assertFalse(plan["remoteInspected"])
        self.assertEqual(plan["writes"][0]["operation"], "problem.create")
        self.assertIn("metadata-only", plan["contentComparison"])
        self.assertIn("problem.saveSolution", [x["operation"] for x in plan["writes"]])
        self.assertFalse((self.root / ".polygon.json").exists())

    def test_existing_plan_reads_only_metadata_and_flags_overwrites(self):
        self.make_existing()
        api = FakeReadAPI(tests=[{"index": 1, "manual": True}])
        plan = build_sync_plan(self.root, api)
        self.assertEqual(plan["remoteRevision"], "4")
        self.assertTrue(plan["requiresOverwriteApproval"])
        self.assertGreater(len(plan["remoteConflicts"]), 0)
        self.assertIn("problem.saveFile", [p["operation"] for p in plan["writes"]])
        self.assertIn("problem.tests", [name for name, _ in api.calls])
        self.assertTrue(set(name for name, _ in api.calls).issubset({
            "problems.list", "problem.info", "problem.files", "problem.solutions",
            "problem.statements", "problem.tests", "problem.validatorTests",
            "problem.checkerTests"
        }))

    def test_dirty_working_copy_blocks(self):
        self.make_existing()
        with self.assertRaisesRegex(UnsafeSyncError, "working copy revision"):
            build_sync_plan(self.root, FakeReadAPI(working_copy=5))

    def test_missing_permissions_blocks(self):
        self.make_existing()
        with self.assertRaisesRegex(UnsafeSyncError, "not writable"):
            build_sync_plan(self.root, FakeReadAPI(status="READ"))

    def test_unknown_revision_blocks(self):
        self.make_existing()
        with self.assertRaisesRegex(UnsafeSyncError, "Cannot identify revision"):
            build_sync_plan(self.root, FakeReadAPI(revision=None))

    def test_remote_extra_validator_tests_block(self):
        self.make_existing()
        api = FakeReadAPI(validator_tests=[
            {"index": 1}, {"index": 2}
        ])
        with self.assertRaisesRegex(UnsafeSyncError, "more validator tests"):
            build_sync_plan(self.root, api)

    def test_local_preflight_fails_before_api_reads(self):
        self.make_existing()
        (self.root / "solutions" / "acc.cpp").unlink()
        api = FakeReadAPI()
        with self.assertRaisesRegex(UnsafeSyncError, "Local structural preflight"):
            build_sync_plan(self.root, api)
        self.assertFalse(api.calls)

    def test_revision_guard_detects_external_commit(self):
        self.make_existing()
        api = FakeReadAPI()
        plan = build_sync_plan(self.root, api)
        assert_remote_unchanged(api, plan)
        api.revision = 5
        with self.assertRaisesRegex(UnsafeSyncError, "changed"):
            assert_remote_unchanged(api, plan)

    def test_update_requires_overwrite_before_any_remote_write(self):
        self.make_existing()
        api = FakeReadAPI()
        plan = build_sync_plan(self.root, api)
        count = len(api.calls)
        with self.assertRaisesRegex(UnsafeSyncError, "allow-overwrite"):
            sync_problem(self.root, api, SyncConfig(), plan=plan)
        self.assertEqual(len(api.calls), count)

    def test_dry_run_does_not_write(self):
        self.make_existing()
        api = FakeReadAPI()
        plan = build_sync_plan(self.root, api)
        count = len(api.calls)
        with redirect_stdout(io.StringIO()):
            result = sync_problem(self.root, api, dry_run=True, plan=plan)
        self.assertEqual(result, plan)
        self.assertEqual(len(api.calls), count)

    def test_clear_script_refusal_stops_before_test_writes(self):
        class RefusingAPI:
            def __init__(self):
                self.calls = []
            def call(self, method, **kwargs):
                self.calls.append((method, kwargs))
                if method == "problem.clearScript":
                    raise PolygonAPIError(method, "status", "rejected")
                raise AssertionError("Must not proceed to saveTest")
        api = RefusingAPI()
        with self.assertRaisesRegex(PolygonAPIError, "rejected"):
            with redirect_stdout(io.StringIO()):
                _sync_tests(api, {"problemId": "7"}, self.root)
        self.assertEqual([x[0] for x in api.calls], ["problem.clearScript"])
        self.assertNotIn("fatal", api.calls[0][1])

    def test_short_credentials_are_redacted(self):
        with mock.patch("polyup.api.requests.post", side_effect=__import__(
                "requests").ConnectionError("leaked a bc")):
            with self.assertRaises(PolygonAPIError) as err:
                PolygonAPI("a", "bc", delay=0).call("problem.info")
        self.assertNotIn(" bc", str(err.exception))
        self.assertIn("[REDACTED]", str(err.exception))

    def test_local_change_after_plan_blocks_before_write(self):
        self.make_existing()
        api = FakeReadAPI()
        plan = build_sync_plan(self.root, api)
        original = len(api.calls)
        (self.root / "solutions" / "acc.cpp").write_text("int main(){return 2;}")
        with self.assertRaisesRegex(UnsafeSyncError, "Local source files changed"):
            sync_problem(self.root, api, plan=plan, allow_overwrite=True)
        self.assertEqual(len(api.calls), original)

    def test_dry_run_and_apply_cannot_be_combined(self):
        from polyup.__main__ import main
        with mock.patch("polyup.__main__.sys.argv", [
            "polyup", "sample", "--dry-run", "--apply"
        ]), mock.patch("polyup.__main__._api") as api_factory, \
             redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exited:
                main()
        self.assertEqual(exited.exception.code, 2)
        api_factory.assert_not_called()

    def test_cli_default_is_plan_only_and_no_credential_for_new(self):
        from polyup.__main__ import main
        with mock.patch("polyup.__main__.sys.argv", ["polyup", "sample"]), \
             mock.patch("polyup.__main__._problem_dir", return_value=self.root), \
             mock.patch("polyup.__main__.collect_access", return_value={}), \
             mock.patch("polyup.__main__._api") as api_factory, \
             mock.patch("polyup.__main__.sync_problem") as upload:
            with redirect_stdout(io.StringIO()):
                main()
        api_factory.assert_not_called()
        upload.assert_not_called()

    def test_cli_existing_apply_needs_opt_in(self):
        from polyup.__main__ import main
        self.make_existing()
        api = FakeReadAPI()
        stderr = io.StringIO()
        with mock.patch("polyup.__main__.sys.argv", ["polyup", "sample", "--apply"]), \
             mock.patch("polyup.__main__._problem_dir", return_value=self.root), \
             mock.patch("polyup.__main__.collect_access", return_value={}), \
             mock.patch("polyup.__main__._api", return_value=api), \
             mock.patch("polyup.__main__.sync_problem") as upload:
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exit:
                    main()
        self.assertEqual(exit.exception.code, 1)
        self.assertIn("allow-overwrite", stderr.getvalue())
        upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
