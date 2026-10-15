"""Normalized programming-problem specification v1.

The JSON Schema is the source of truth for structure. Additional "ready" checks
are deliberately separate: a structurally valid draft can contain unknowns.

No LLM calls, compilation, source execution, Polygon API traffic, or file writes
are performed by validation or conversion.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from polyup.parsers import parse_statement

SCHEMA_FILE = Path(__file__).resolve().parent / "schemas" / "problem-spec.v1.schema.json"
SLUG = re.compile(r"^[a-z][a-z_]*$")
TITLE = re.compile(r"\\textbf\{\\Large\s+(.+?)\}", re.DOTALL)
EXPLICIT_TITLE = re.compile(r"^===\s*TITLE\s*===\s*\n(.*?)(?=^===|\Z)", re.I | re.M | re.S)


class ProblemSpecError(ValueError):
    """Unusable user input or unsafe source path; no side effects."""


def _json_no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProblemSpecError(f"Duplicate JSON property: {key}")
        result[key] = value
    return result


def parse_json(text: str) -> dict:
    try:
        result = json.loads(text, object_pairs_hook=_json_no_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ProblemSpecError(f"Invalid JSON: {exc.msg} at line {exc.lineno}") from None
    if not isinstance(result, dict):
        raise ProblemSpecError("Top-level specification must be a JSON object")
    return result


def load_schema() -> dict:
    schema = parse_json(SCHEMA_FILE.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _safe_relative_path(value: str) -> bool:
    """Portable, project-relative POSIX source path; no escaping the project."""
    if not value or "\\" in value or "\0" in value or value.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    components = value.split("/")
    return all(part not in ("", ".", "..") for part in components)


def inspect_spec(data: dict, *, ready: bool = False) -> dict:
    """Return deterministic diagnostics, never mutate the specification."""
    errors = []
    warnings = []
    validator = Draft202012Validator(load_schema())
    for error in sorted(validator.iter_errors(data), key=lambda e: (list(map(str, e.absolute_path)), e.message)):
        location = "$" + "".join(f"[{json.dumps(p)}]" for p in error.absolute_path)
        errors.append({"code": "SCHEMA", "path": location, "message": error.message})

    if errors:
        return {"status": "FAIL", "errors": errors, "warnings": warnings,
                "schemaVersion": data.get("schemaVersion")}

    src = data["source"]
    if src["path"] is not None and not _safe_relative_path(src["path"]):
        errors.append({"code": "UNSAFE_PATH", "path": "$.source.path",
                       "message": "Source path must be a safe project-relative POSIX path"})

    solution = data["guidance"].get("solution")
    if solution and "file" in solution and not _safe_relative_path(solution["file"]):
        errors.append({"code": "UNSAFE_PATH", "path": "$.guidance.solution.file",
                       "message": "Solution file must be a safe project-relative POSIX path"})

    if ready:
        if src["reviewStatus"] != "verified":
            errors.append({"code": "SOURCE_UNREVIEWED", "path": "$.source.reviewStatus",
                           "message": "Human or independent review of source is required"})
        for field in ("title", "legend", "input", "output"):
            val = data["statement"][field]
            if not isinstance(val, str) or not val.strip():
                errors.append({"code": "INCOMPLETE_STATEMENT", "path": "$.statement." + field,
                               "message": field + " must be nonempty for ready mode"})
        if not data["statement"]["constraints"]:
            errors.append({"code": "CONSTRAINTS_UNREVIEWED", "path": "$.statement.constraints",
                           "message": "Explicit reviewed constraints are required for test generation"})
        if not data["statement"]["samples"]:
            errors.append({"code": "SAMPLES_MISSING", "path": "$.statement.samples",
                           "message": "At least one sample input/output pair is required"})
        for field in ("testCaseMode", "outputPolicy"):
            if data["statement"][field] == "unknown":
                errors.append({"code": "UNRESOLVED_SEMANTICS",
                               "path": "$.statement." + field,
                               "message": field + " must be explicitly reviewed"})
        if data["statement"]["interactive"]:
            errors.append({"code": "INTERACTIVE_UNSUPPORTED", "path": "$.statement.interactive",
                           "message": "Interactive problems require a future specialized workflow"})
        for index, sample in enumerate(data["statement"]["samples"]):
            if not sample["input"]:
                warnings.append({"code": "EMPTY_SAMPLE_INPUT", "path": f"$.statement.samples[{index}].input",
                                 "message": "Confirm an empty sample input is intentional"})
            if not sample["output"]:
                warnings.append({"code": "EMPTY_SAMPLE_OUTPUT", "path": f"$.statement.samples[{index}].output",
                                 "message": "Confirm an empty sample output is intentional"})
        for item in data["ambiguities"]:
            if item["severity"] == "blocking":
                errors.append({"code": "UNRESOLVED_AMBIGUITY", "path": item["field"],
                               "message": item["issue"]})
    else:
        if src["reviewStatus"] != "verified":
            warnings.append({"code": "SOURCE_UNREVIEWED", "path": "$.source.reviewStatus",
                             "message": "Source text not yet reviewed"})
        if not data["statement"]["constraints"]:
            warnings.append({"code": "CONSTRAINTS_UNREVIEWED", "path": "$.statement.constraints",
                             "message": "No reviewed constraints provided"})
        if not data["statement"]["samples"]:
            warnings.append({"code": "SAMPLES_MISSING", "path": "$.statement.samples",
                             "message": "No sample pairs provided"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors,
            "warnings": warnings, "schemaVersion": data["schemaVersion"]}


def _read_source_bytes(path: Path) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
        return raw, raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ProblemSpecError(f"Source is not UTF-8: {path.name}") from None
    except OSError as exc:
        raise ProblemSpecError(f"Cannot read {path.name}: {exc}") from exc


def _inside_dir(root: Path, path: str) -> Path:
    if not _safe_relative_path(path):
        raise ProblemSpecError("File path must be project-relative and must not contain '..'")
    target = (root / path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        raise ProblemSpecError("File path escapes the problem directory") from None
    if not target.is_file():
        raise ProblemSpecError(f"File not found: {path}")
    return target


def from_polygon_folder(root: Path, *, idea: str | None = None,
                        idea_file: str | None = None,
                        solution_file: str | None = None,
                        solution_language: str = "cpp17") -> dict:
    """Convert existing local Polygon statement+samples to a V1 **draft**.

    Preserve the original LaTeX verbatim in source.rawText. Never invent
    constraints, silent sample outputs or an algorithm.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ProblemSpecError(f"Problem folder not found: {root}")
    if not SLUG.fullmatch(root.name):
        raise ProblemSpecError("Problem folder must use snake_case letters and underscores")
    if idea is not None and idea_file is not None:
        raise ProblemSpecError("Specify either idea or idea_file, not both")
    stmt_path = _inside_dir(root, "statement/statement.tex")
    raw, original = _read_source_bytes(stmt_path)
    try:
        parts = parse_statement(stmt_path)
    except (UnicodeError, OSError) as exc:
        raise ProblemSpecError(f"Unable to parse statement: {exc}") from exc

    match = TITLE.search(original)
    title = match.group(1).strip() if match else None
    if title is None:
        alt = EXPLICIT_TITLE.search(original)
        if alt:
            title = alt.group(1).strip() or None

    samples = []
    ambiguities = []
    sample_dir = root / "samples"
    files = sorted(sample_dir.glob("*.in")) if sample_dir.is_dir() else []
    for inp in files:
        out = inp.with_suffix(".out")
        if not out.is_file():
            ambiguities.append({"field": f"statement.samples.{inp.name}",
                                "issue": "Sample output missing; original input was not altered.",
                                "severity": "blocking", "sourceExcerpt": None})
            continue
        _, iv = _read_source_bytes(inp)
        _, ov = _read_source_bytes(out)
        samples.append({"input": iv, "output": ov, "explanation": None})

    if sample_dir.is_dir():
        for out in sorted(sample_dir.glob("*.out")):
            if not out.with_suffix(".in").is_file():
                ambiguities.append({"field": f"statement.samples.{out.name}",
                                    "issue": "Orphan sample output not paired with input.",
                                    "severity": "advisory", "sourceExcerpt": None})
    if not samples:
        ambiguities.append({"field": "statement.samples",
                            "issue": "No complete sample input/output pair was supplied.",
                            "severity": "blocking", "sourceExcerpt": None})
    for field in ("legend", "input", "output"):
        if not parts[field].strip():
            ambiguities.append({"field": "statement." + field,
                                "issue": f"Missing or unparseable statement {field}.",
                                "severity": "blocking", "sourceExcerpt": None})
    if title is None:
        ambiguities.append({"field": "statement.title",
                            "issue": "Original source has no explicit title; folder name is not treated as proof.",
                            "severity": "blocking", "sourceExcerpt": None})
    ambiguities.append({"field": "statement.constraints",
                        "issue": "Constraints were not extracted by a verified parser. Review original Input/Legend before generating tests.",
                        "severity": "blocking", "sourceExcerpt": None})
    guidance = {}
    if idea_file is not None:
        idea = _read_source_bytes(_inside_dir(root, idea_file))[1]
    if idea is not None:
        if not idea.strip():
            raise ProblemSpecError("Provided idea cannot be blank")
        guidance["idea"] = {"text": idea, "providedBy": "user"}
    if solution_file is not None:
        _inside_dir(root, solution_file)
        guidance["solution"] = {"language": solution_language, "providedBy": "user",
                                "file": solution_file}
    mode = "statement+solution" if solution_file is not None else (
        "statement+idea" if idea is not None else "statement-only"
    )
    spec = {
        "schemaVersion": 1,
        "slug": root.name,
        "mode": mode,
        "source": {"kind": "polygon-tex", "path": "statement/statement.tex",
                   "sha256": hashlib.sha256(raw).hexdigest(),
                   "rawText": original, "extraction": "native-text",
                   "reviewStatus": "pending", "attribution": None},
        "statement": {"title": title, "language": "en",
                      "legend": parts["legend"].strip() or None,
                      "input": parts["input"].strip() or None,
                      "output": parts["output"].strip() or None,
                      "notes": parts["notes"].strip() or None,
                      "interactive": bool(parts["interaction"].strip()),
                      "testCaseMode": "unknown", "outputPolicy": "unknown",
                      "timeLimitMs": None, "memoryLimitMb": None,
                      "constraints": [], "samples": samples},
        "guidance": guidance,
        "ambiguities": ambiguities,
    }
    report = inspect_spec(spec)
    if report["status"] != "PASS":
        raise ProblemSpecError("Adapter produced invalid draft: " + str(report["errors"]))
    return spec
