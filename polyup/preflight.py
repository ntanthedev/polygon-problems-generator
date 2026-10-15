"""Read-only structural preflight for a local Polygon problem.

This does NOT compile or execute untrusted problem code and does not call Polygon.
It is a prerequisite checklist, not a correctness or upload verification tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .parsers import extract_freemarker_script, parse_statement


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def inspect_problem(problem_dir: Path) -> dict:
    """Return an actionable JSON-serializable structural report; never write files."""
    root = Path(problem_dir)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    stats = {"samples": 0, "validator_tests": 0}

    if not root.is_dir():
        errors.append(_issue("PROBLEM_NOT_FOUND", f"Problem directory does not exist: {root}"))
        return {"problem": str(root), "status": "FAIL", "errors": errors,
                "warnings": warnings, "stats": stats}

    required = {
        "statement/statement.tex": "Polygon statement",
        "validator.cpp": "input validator",
        "checker.cpp": "checker (or standard-checker marker)",
        "generators/generator.cpp": "test generator",
        "solutions/acc.cpp": "accepted reference solution",
    }
    for rel, label in required.items():
        if not (root / rel).is_file():
            errors.append(_issue("MISSING_REQUIRED_FILE", f"Missing {label}: {rel}"))

    statement = root / "statement" / "statement.tex"
    if statement.is_file():
        try:
            parts = parse_statement(statement)
            for section in ("legend", "input", "output"):
                if not parts.get(section, "").strip():
                    errors.append(_issue(
                        "STATEMENT_SECTION_EMPTY",
                        f"statement/statement.tex: missing or unparseable {section} section",
                    ))
        except (UnicodeError, OSError) as exc:
            errors.append(_issue("STATEMENT_UNREADABLE", f"Cannot read statement: {exc}"))

    generator = root / "generators" / "generator.cpp"
    if generator.is_file():
        try:
            if not extract_freemarker_script(generator):
                errors.append(_issue(
                    "GENERATOR_SCRIPT_MISSING",
                    "generators/generator.cpp: expected FreeMarker script comment not found",
                ))
        except (UnicodeError, OSError) as exc:
            errors.append(_issue("GENERATOR_UNREADABLE", f"Cannot read generator: {exc}"))

    sample_dir = root / "samples"
    sample_inputs = sorted(sample_dir.glob("*.in")) if sample_dir.is_dir() else []
    stats["samples"] = len(sample_inputs)
    if not sample_inputs:
        errors.append(_issue("SAMPLES_MISSING", "At least one samples/*.in + *.out pair is required"))

    sample_hashes: dict[str, str] = {}
    for input_path in sample_inputs:
        output_path = input_path.with_suffix(".out")
        if not output_path.is_file():
            errors.append(_issue("SAMPLE_OUTPUT_MISSING", f"No corresponding output for {input_path.name}"))
        else:
            try:
                if output_path.stat().st_size == 0:
                    warnings.append(_issue("SAMPLE_OUTPUT_EMPTY", f"{output_path.name} is empty; confirm intentionally"))
            except OSError as exc:
                errors.append(_issue("SAMPLE_UNREADABLE", f"Cannot inspect {output_path.name}: {exc}"))
        try:
            content = input_path.read_bytes()
            if not content:
                warnings.append(_issue("SAMPLE_INPUT_EMPTY", f"{input_path.name} is empty; confirm intentionally"))
            digest = hashlib.sha256(content).hexdigest()
            if digest in sample_hashes:
                errors.append(_issue("DUPLICATE_SAMPLE", f"{input_path.name} duplicates {sample_hashes[digest]}"))
            else:
                sample_hashes[digest] = input_path.name
        except OSError as exc:
            errors.append(_issue("SAMPLE_UNREADABLE", f"Cannot read {input_path.name}: {exc}"))

    if sample_dir.is_dir():
        names = {path.stem for path in sample_inputs}
        for orphan in sorted(sample_dir.glob("*.out")):
            if orphan.stem not in names:
                warnings.append(_issue("ORPHAN_SAMPLE_OUTPUT", f"{orphan.name} has no matching .in"))

    vtest_dir = root / "validator_tests"
    if vtest_dir.is_dir():
        stats["validator_tests"] = sum(path.is_file() for path in vtest_dir.iterdir())
    if stats["validator_tests"] == 0:
        warnings.append(_issue("VALIDATOR_TESTS_EMPTY", "Add valid_* and invalid_* validator tests"))

    metadata = root / ".polygon.json"
    if metadata.is_file():
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not data.get("problemId"):
                errors.append(_issue("INVALID_POLYGON_METADATA", ".polygon.json must contain problemId"))
        except (ValueError, UnicodeError, OSError) as exc:
            errors.append(_issue("INVALID_POLYGON_METADATA", f"Cannot parse .polygon.json: {exc}"))

    return {
        "problem": str(root),
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def _resolve_problem(arg: str) -> Path:
    direct = Path(arg).expanduser()
    if direct.exists() or direct.is_absolute() or "/" in arg or "\\" in arg:
        return direct
    return Path(__file__).resolve().parent.parent / "problems" / arg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m polyup preflight",
        description="Read-only structural check; does not access Polygon or execute programs",
    )
    parser.add_argument("problem", help="Problem name under problems/, or explicit directory path")
    parser.add_argument("--json", action="store_true", help="Print machine-readable report")
    args = parser.parse_args(argv)
    report = inspect_problem(_resolve_problem(args.problem))

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Preflight {report['status']}: {report['problem']}")
        print(f"Samples: {report['stats']['samples']}; "
              f"validator tests: {report['stats']['validator_tests']}")
        for issue in report["errors"]:
            print(f"  ERROR [{issue['code']}] {issue['message']}")
        for issue in report["warnings"]:
            print(f"  WARN  [{issue['code']}] {issue['message']}")
        if report["status"] == "PASS":
            print("Structure looks complete. This does NOT verify algorithm correctness.")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
