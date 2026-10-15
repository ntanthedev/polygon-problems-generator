"""SOL-001 deterministic candidate/oracle checks; mocked isolation, no network/Docker required."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from factory.__main__ import main
from factory.solution_check import (
    Case, Execution, get_cases, resolve_candidate, verify_candidate,
)
from factory.docker_runner import DockerRunner, _read_guest_file
from factory.spec import ProblemSpecError, parse_json

FIXTURE = Path(__file__).resolve().parent.parent / "factory/fixtures/valid/ready-statement-only.json"


class FakeRunner:
    def __init__(self, *, oracle=None, candidate=None, builds=None):
        self.outputs = {
            "oracle": list(oracle if oracle is not None else [Execution("OK", b"5\n")]),
            "candidate": list(candidate if candidate is not None else [Execution("OK", b"5\n")]),
        }
        self.builds = builds or {}
        self.calls = []

    def build(self, path, role):
        self.calls.append(("build", role))
        return self.builds.get(role, Execution("OK"))

    def run(self, role, data, timeout):
        self.calls.append(("run", role, data, timeout))
        if not self.outputs[role]:
            raise AssertionError("Unexpected extra run")
        return self.outputs[role].pop(0)


class SolutionCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = self.root / "candidate.cpp"
        self.oracle = self.root / "oracle.cpp"
        self.candidate.write_text("int main(){return 0;}\n")
        self.oracle.write_text("int main(){return 1;}\n")
        self.spec = parse_json(FIXTURE.read_text())

    def check(self, runner=None, **kwargs):
        return verify_candidate(
            self.spec, candidate=self.candidate, oracle=self.oracle,
            runner=runner or FakeRunner(), **kwargs
        )

    def test_candidate_agrees_on_sample_without_claiming_proof(self):
        result = self.check()
        self.assertEqual(result["verdict"], "PASS_ON_TESTS")
        self.assertFalse(result["oracleIsProvenCorrect"])
        self.assertFalse(result["oracleIndependentConfirmed"])
        self.assertEqual(result["caseCount"], 1)
        self.assertEqual(result["cases"][0]["verdict"], "PASS")
        self.assertEqual(len(result["candidateSha256"]), 64)

    def test_exact_output_ignores_whitespace_only(self):
        self.assertEqual(self.check(FakeRunner(
            oracle=[Execution("OK", b"5\n")],
            candidate=[Execution("OK", b"  5 \r\n")]
        ))["verdict"], "PASS_ON_TESTS")

    def test_wrong_answer_is_detected(self):
        report = self.check(FakeRunner(candidate=[Execution("OK", b"6\n")]))
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["cases"][0]["verdict"], "WA")
        self.assertEqual(len(report["cases"][0]["oracleOutputSha256"]), 64)

    def test_oracle_wrong_on_sample_is_not_candidate_wa(self):
        runner = FakeRunner(oracle=[Execution("OK", b"99\n")])
        out = self.check(runner)
        self.assertEqual(out["verdict"], "ORACLE_ERROR")
        self.assertEqual(out["cases"][0]["verdict"], "ORACLE_SAMPLE_MISMATCH")
        self.assertNotIn("candidate", [call[1] for call in runner.calls if call[0] == "run"])

    def test_oracle_crash_stops_comparison(self):
        out = self.check(FakeRunner(oracle=[Execution("RE", detail="crash")]))
        self.assertEqual(out["verdict"], "ORACLE_ERROR")
        self.assertEqual(out["cases"][0]["verdict"], "ORACLE_RE")

    def test_candidate_tle_re_mle_ole_are_distinct(self):
        for status in ("TLE", "RE", "MLE", "OLE"):
            with self.subTest(status=status):
                out = self.check(FakeRunner(candidate=[Execution(status, detail="hit")]))
                self.assertEqual(out["verdict"], "FAIL")
                self.assertEqual(out["cases"][0]["verdict"], status)

    def test_candidate_compile_failure(self):
        runner = FakeRunner(builds={"candidate": Execution("COMPILE_ERROR", detail="syntax")})
        out = self.check(runner)
        self.assertEqual(out["verdict"], "COMPILE_ERROR")
        self.assertIn("syntax", out["buildError"]["detail"])
        self.assertFalse(any(c[0] == "run" for c in runner.calls))

    def test_oracle_compile_failure(self):
        out = self.check(FakeRunner(builds={
            "oracle": Execution("COMPILE_ERROR", detail="brute broken")
        }))
        self.assertEqual(out["verdict"], "ORACLE_COMPILE_ERROR")

    def test_unreviewed_spec_is_rejected_before_compile(self):
        self.spec["source"]["reviewStatus"] = "pending"
        runner = FakeRunner()
        with self.assertRaisesRegex(ProblemSpecError, "SOURCE_UNREVIEWED"):
            self.check(runner)
        self.assertEqual(runner.calls, [])

    def test_unknown_testcase_mode_is_rejected(self):
        self.spec["statement"]["testCaseMode"] = "unknown"
        with self.assertRaisesRegex(ProblemSpecError, "UNRESOLVED_SEMANTICS"):
            self.check()

    def test_checker_floats_interactive_are_not_misgraded(self):
        for mode in ("checker", "floating-point", "interactive"):
            with self.subTest(mode=mode):
                self.spec["statement"]["outputPolicy"] = mode
                with self.assertRaises(ProblemSpecError):
                    self.check()
                self.spec["statement"]["outputPolicy"] = "exact"

    def test_identical_sources_cannot_pass_as_independent_oracle(self):
        self.oracle.write_bytes(self.candidate.read_bytes())
        with self.assertRaisesRegex(ProblemSpecError, "identical"):
            self.check()

    def test_timeout_validation(self):
        for timeout in (0, 0.01, 31):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ProblemSpecError):
                    self.check(timeout_s=timeout)

    def test_extra_tests_and_expected_outputs(self):
        testdir = self.root / "tests"
        testdir.mkdir()
        (testdir / "01.in").write_text("4 9\n")
        (testdir / "01.out").write_text("13\n")
        result = self.check(FakeRunner(
            oracle=[Execution("OK", b"5\n"), Execution("OK", b"13\n")],
            candidate=[Execution("OK", b"5\n"), Execution("OK", b"13\n")]
        ), test_dir=testdir)
        self.assertEqual(result["verdict"], "PASS_ON_TESTS")
        self.assertEqual(result["caseCount"], 2)
        self.assertEqual([i["name"] for i in result["cases"]], ["sample:1", "test:01.in"])

    def test_extra_test_without_expected_uses_oracle(self):
        testdir = self.root / "tests"
        testdir.mkdir()
        (testdir / "01.in").write_text("4 9\n")
        report = self.check(FakeRunner(
            oracle=[Execution("OK", b"5\n"), Execution("OK", b"13\n")],
            candidate=[Execution("OK", b"5\n"), Execution("OK", b"12\n")]
        ), test_dir=testdir)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["cases"][1]["verdict"], "WA")

    def test_oracle_must_match_extra_expected_output(self):
        testdir = self.root / "tests"
        testdir.mkdir()
        (testdir / "01.in").write_text("2 2\n")
        (testdir / "01.out").write_text("4\n")
        report = self.check(FakeRunner(
            oracle=[Execution("OK", b"5\n"), Execution("OK", b"9\n")],
            candidate=[Execution("OK", b"5\n")]
        ), test_dir=testdir)
        self.assertEqual(report["verdict"], "ORACLE_ERROR")
        self.assertEqual(report["cases"][1]["verdict"], "ORACLE_EXPECTED_MISMATCH")

    def test_orphan_expected_output_refused(self):
        folder = self.root / "cases"
        folder.mkdir()
        (folder / "01.out").write_text("1\n")
        with self.assertRaisesRegex(ProblemSpecError, "Orphan"):
            get_cases(self.spec, folder)

    def test_symlink_test_case_refused(self):
        folder = self.root / "cases"
        folder.mkdir()
        (folder / "01.in").symlink_to(self.candidate)
        with self.assertRaisesRegex(ProblemSpecError, "regular"):
            get_cases(self.spec, folder)

    def test_oversized_case_refused(self):
        folder = self.root / "cases"
        folder.mkdir()
        (folder / "01.in").write_bytes(b"x" * (256 * 1024 + 1))
        with self.assertRaisesRegex(ProblemSpecError, "exceeds"):
            get_cases(self.spec, folder)

    def test_default_candidate_from_user_provided_solution(self):
        folder = self.root / "example"
        (folder / "solutions").mkdir(parents=True)
        (folder / "solutions" / "mine.cpp").write_text("int main(){}")
        self.spec["guidance"]["solution"] = {
            "language": "cpp17", "providedBy": "user", "file": "solutions/mine.cpp"
        }
        self.spec["mode"] = "statement+solution"
        self.assertEqual(
            resolve_candidate(folder, self.spec), folder / "solutions" / "mine.cpp"
        )

    def test_missing_candidate_requires_explicit_source(self):
        with self.assertRaisesRegex(ProblemSpecError, "No candidate"):
            resolve_candidate(self.root, self.spec)

    def test_cli_draft_rejected_before_docker_setup(self):
        folder = self.root / "draft"
        folder.mkdir()
        self.spec["source"]["reviewStatus"] = "pending"
        (folder / "spec.json").write_text(json.dumps(self.spec))
        with mock.patch("factory.docker_runner.DockerRunner") as docker:
            stderr = io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                rc = main(["solutions", "verify", str(folder),
                           "--candidate", str(self.candidate),
                           "--oracle", str(self.oracle)])
        self.assertEqual(rc, 1)
        self.assertIn("SOURCE_UNREVIEWED", stderr.getvalue())
        docker.assert_not_called()

    def test_cli_fails_closed_without_docker(self):
        folder = self.root / "problem"
        folder.mkdir()
        (folder / "spec.json").write_text(json.dumps(self.spec))
        with mock.patch("factory.docker_runner.shutil.which", return_value=None):
            stderr = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                rc = main(["solutions", "verify", str(folder),
                           "--candidate", str(self.candidate),
                           "--oracle", str(self.oracle)])
        self.assertEqual(rc, 1)
        self.assertIn("Docker is required", stderr.getvalue())


class DockerPolicyTests(unittest.TestCase):
    def test_nonexistent_docker_does_not_fallback_to_host(self):
        with mock.patch("factory.docker_runner.shutil.which", return_value=None):
            with self.assertRaisesRegex(ProblemSpecError, "Docker is required"):
                with DockerRunner():
                    pass

    def test_image_inspection_happens_without_pulling(self):
        with mock.patch("factory.docker_runner.shutil.which", return_value="/usr/bin/docker"), \
             mock.patch("factory.docker_runner.subprocess.run", return_value=mock.Mock(returncode=1)) as run:
            with self.assertRaisesRegex(ProblemSpecError, "pull it manually"):
                with DockerRunner():
                    pass
        self.assertEqual(run.call_args.args[0][:3], ["docker", "image", "inspect"])

    def test_guest_output_symlink_cannot_read_host_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            secret = base / "secret"
            secret.write_text("HOST_PRIVATE_SECRET")
            link = base / "guest_stdout"
            link.symlink_to(secret)
            with self.assertRaisesRegex(ProblemSpecError, "Unsafe"):
                _read_guest_file(link, 128)
            self.assertEqual(secret.read_text(), "HOST_PRIVATE_SECRET")

    def test_guest_regular_file_read_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guest_stdout"
            path.write_bytes(b"abcdef")
            content, size = _read_guest_file(path, 3)
            self.assertEqual(content, b"abc")
            self.assertEqual(size, 6)

    def test_invalid_image_name_refused(self):
        with self.assertRaises(ProblemSpecError):
            DockerRunner("gcc:14; echo hostile")

    def test_isolation_options_present_in_docker_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "source").mkdir()
            (path / "out").mkdir()
            runner = DockerRunner()
            runner.root = path
            with mock.patch("factory.docker_runner.subprocess.run",
                            return_value=mock.Mock(returncode=0)) as cmd:
                runner._docker("test", [(path / "source", "/source", True),
                                        (path / "out", "/out", False)],
                               "echo safe", 1, memory="256m")
            args = cmd.call_args.args[0]
            for item in ("--network", "none", "--read-only", "--cap-drop",
                         "ALL", "--pids-limit", "--memory", "--user",
                         "--security-opt", "no-new-privileges", "--pull=never"):
                self.assertIn(item, args)
            self.assertNotIn("privileged", args)


if __name__ == "__main__":
    unittest.main()
