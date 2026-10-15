"""Deterministic C++17 candidate-vs-oracle checks for reviewed V1 problems.

This never calls an LLM/Polygon. It refuses to execute code without an injected
runner; the production runner is an isolated Docker container. Matching all
tested cases is not a mathematical proof of correctness or oracle independence.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .spec import ProblemSpecError, _inside_dir, inspect_spec

MAX_INPUT_BYTES = 256 * 1024
MAX_TEST_FILES = 200


@dataclass(frozen=True)
class Execution:
    status: str
    output: bytes = b""
    detail: str = ""


class IsolatedRunner(Protocol):
    def build(self, source: Path, role: str) -> Execution: ...
    def run(self, role: str, data: bytes, timeout_s: float) -> Execution: ...


@dataclass(frozen=True)
class Case:
    name: str
    input_data: bytes
    expected: bytes | None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_safely(file: Path, *, allow_empty: bool = False) -> bytes:
    if file.is_symlink() or not file.is_file():
        raise ProblemSpecError(f"Not a regular file: {file}")
    if file.stat().st_size > MAX_INPUT_BYTES:
        raise ProblemSpecError(f"Input/output file exceeds {MAX_INPUT_BYTES} bytes: {file.name}")
    data = file.read_bytes()
    if not allow_empty and not data:
        raise ProblemSpecError(f"Empty input file: {file.name}")
    return data


def get_cases(spec: dict, test_dir: Path | None = None) -> list[Case]:
    cases = []
    for i, sample in enumerate(spec["statement"]["samples"], 1):
        try:
            inp = sample["input"].encode("utf-8")
            out = sample["output"].encode("utf-8")
        except UnicodeError:
            raise ProblemSpecError(f"Invalid UTF-8 sample #{i}") from None
        if len(inp) > MAX_INPUT_BYTES or len(out) > MAX_INPUT_BYTES:
            raise ProblemSpecError(f"Sample #{i} is too large")
        cases.append(Case(f"sample:{i}", inp, out))
    if test_dir is not None:
        folder = Path(test_dir)
        if folder.is_symlink() or not folder.is_dir():
            raise ProblemSpecError("Test directory must be an existing regular directory")
        names = sorted(folder.glob("*.in"))
        if len(names) > MAX_TEST_FILES:
            raise ProblemSpecError(f"At most {MAX_TEST_FILES} extra test inputs are allowed")
        inputs = {p.stem for p in names}
        for out in folder.glob("*.out"):
            if out.stem not in inputs:
                raise ProblemSpecError(f"Orphan expected output {out.name}")
        for path in names:
            inp = _read_safely(path)
            exp_path = path.with_suffix(".out")
            expected = _read_safely(exp_path, allow_empty=True) if exp_path.exists() or exp_path.is_symlink() else None
            cases.append(Case(f"test:{path.name}", inp, expected))
    return cases


def _token_equal(left: bytes, right: bytes) -> bool:
    """Only for reviewed exact-output problems: whitespace-separated tokens."""
    return left.split() == right.split()


def resolve_candidate(problem_dir: Path, spec: dict, override: Path | None = None) -> Path:
    if override is not None:
        return Path(override).resolve(strict=True)
    source = spec["guidance"].get("solution")
    if not source or "file" not in source:
        raise ProblemSpecError(
            "No candidate file: supply --candidate, or add guidance.solution.file"
        )
    if source["language"] != "cpp17":
        raise ProblemSpecError("SOL-001 currently supports C++17 source files only")
    return _inside_dir(Path(problem_dir), source["file"])


def verify_candidate(
    spec: dict, *, candidate: Path, oracle: Path, runner: IsolatedRunner,
    test_dir: Path | None = None, timeout_s: float = 2.0,
) -> dict:
    """Run a reviewed exact-output statement against an independent oracle.

    The oracle is user/agent supplied and not intrinsically trusted; samples
    must agree with it first. No inferred correctness or mutations.
    """
    report = inspect_spec(spec, ready=True)
    if report["status"] != "PASS":
        raise ProblemSpecError(
            "Spec not ready: " + "; ".join(f"{x['code']}: {x['message']}" for x in report["errors"])
        )
    stmt = spec["statement"]
    if stmt["outputPolicy"] != "exact" or stmt["interactive"]:
        raise ProblemSpecError(
            "SOL-001 supports reviewed non-interactive exact/token output only; "
            "floating/checker output needs a checker-aware runner"
        )
    if not (0.1 <= timeout_s <= 30):
        raise ProblemSpecError("Per-case timeout must be between 0.1 and 30 seconds")
    candidate = Path(candidate)
    oracle = Path(oracle)
    left = _read_safely(candidate)
    right = _read_safely(oracle)
    if candidate.suffix.lower() != ".cpp" or oracle.suffix.lower() != ".cpp":
        raise ProblemSpecError("Only C++17 .cpp files are supported")
    if _sha(left) == _sha(right):
        raise ProblemSpecError(
            "Candidate and oracle have identical contents; supply independently derived implementations"
        )
    cases = get_cases(spec, test_dir)
    if not cases:
        raise ProblemSpecError("No samples/tests available")
    result = {
        "specSchemaVersion": 1, "slug": spec["slug"],
        "candidateSha256": _sha(left), "oracleSha256": _sha(right),
        "caseCount": len(cases), "verdict": "BLOCKED",
        "oracleIsProvenCorrect": False,
        "oracleIndependentConfirmed": False,
        "scope": "exact-output token comparison on supplied cases only",
        "cases": [],
    }
    for role, src in (("oracle", oracle), ("candidate", candidate)):
        build = runner.build(src, role)
        if build.status != "OK":
            result["verdict"] = "ORACLE_COMPILE_ERROR" if role == "oracle" else "COMPILE_ERROR"
            result["buildError"] = {"role": role, "status": build.status,
                                    "detail": build.detail[:512]}
            return result
    failures = False
    for case in cases:
        oracle_result = runner.run("oracle", case.input_data, timeout_s)
        data = {"name": case.name, "inputSha256": _sha(case.input_data)}
        if oracle_result.status != "OK":
            data["verdict"] = "ORACLE_" + oracle_result.status
            data["detail"] = oracle_result.detail[:512]
            result["cases"].append(data)
            result["verdict"] = "ORACLE_ERROR"
            return result
        if case.expected is not None and not _token_equal(oracle_result.output, case.expected):
            data["verdict"] = "ORACLE_SAMPLE_MISMATCH" if case.name.startswith("sample:") else "ORACLE_EXPECTED_MISMATCH"
            data["oracleOutputSha256"] = _sha(oracle_result.output)
            result["cases"].append(data)
            result["verdict"] = "ORACLE_ERROR"
            return result
        candidate_result = runner.run("candidate", case.input_data, timeout_s)
        if candidate_result.status != "OK":
            data["verdict"] = candidate_result.status
            data["detail"] = candidate_result.detail[:512]
            failures = True
        elif not _token_equal(candidate_result.output, oracle_result.output):
            data["verdict"] = "WA"
            data["candidateOutputSha256"] = _sha(candidate_result.output)
            data["oracleOutputSha256"] = _sha(oracle_result.output)
            failures = True
        else:
            data["verdict"] = "PASS"
        result["cases"].append(data)
    result["verdict"] = "FAIL" if failures else "PASS_ON_TESTS"
    return result
