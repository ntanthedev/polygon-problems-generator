"""Conservative, read-only pre-sync planning for Polygon.

No remote writes. Polygon's JSON list endpoints expose metadata, not guaranteed
file digests; the plan therefore NEVER claims remote content equality. Existing
problems require explicit overwrite approval at apply time.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from .api import PolygonAPIError
from .parsers import detect_standard_checker, extract_freemarker_script
from .preflight import inspect_problem


class UnsafeSyncError(PolygonAPIError):
    def __init__(self, detail: str):
        super().__init__("sync.preflight", "unsafe", detail)


def _require_list(api, method: str, *, pid: dict | None = None) -> list:
    result = api.call(method, **(pid or {}))
    if not isinstance(result, list):
        raise UnsafeSyncError(f"{method} returned an unexpected response")
    return result


def _remote_identity(api, problem_id: str) -> dict:
    rows = _require_list(api, "problems.list", pid={"id": problem_id})
    matches = [p for p in rows if isinstance(p, dict) and str(p.get("id")) == problem_id]
    if len(matches) != 1 or matches[0].get("revision") is None:
        raise UnsafeSyncError(f"Cannot identify revision for remote problem {problem_id}")
    entry = matches[0]
    if entry.get("deleted") or entry.get("accessType") not in {"OWNER", "WRITE"}:
        raise UnsafeSyncError(f"Problem {problem_id} unavailable or not writable")
    return entry


def _named_entries(entries, context: str, key: str = "name") -> dict:
    if not isinstance(entries, list):
        raise UnsafeSyncError(f"Unexpected response for {context}")
    mapping = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get(key), (str, int)):
            raise UnsafeSyncError(f"Malformed item in {context}")
        name = str(entry[key])
        if name in mapping:
            raise UnsafeSyncError(f"Duplicate {context} key: {name}")
        mapping[name] = entry
    return mapping


def local_fingerprint(root: Path) -> str:
    """Fingerprint local problem inputs (ignore volatile build reports/Polygon ID)."""
    root = Path(root)
    entries = []
    excluded = {".build", ".tests", "reports", "__pycache__", ".git"}
    for path in root.rglob("*"):
        if any(part in excluded for part in path.relative_to(root).parts):
            continue
        if path.name == ".polygon.json" or not path.is_file():
            continue
        if path.is_symlink():
            raise UnsafeSyncError("Symlinks inside problem directory are unsupported")
        relative = path.relative_to(root).as_posix()
        entries.append((relative, hashlib.sha256(path.read_bytes()).hexdigest()))
    packed = json.dumps(sorted(entries), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def assert_local_unchanged(root: Path, plan: dict) -> None:
    if local_fingerprint(root) != plan.get("localFingerprint"):
        raise UnsafeSyncError("Local source files changed since sync planning; re-plan")


def build_sync_plan(problem_dir: Path, api=None, *, include_remote: bool = True) -> dict:
    """Returns a JSON-serializable plan without changing files or remote state."""
    root = Path(problem_dir)
    preflight = inspect_problem(root)
    if preflight["errors"]:
        raise UnsafeSyncError(
            "Local structural preflight FAILED: "
            + "; ".join(f"{i['code']}: {i['message']}" for i in preflight["errors"])
        )

    metadata_path = root / ".polygon.json"
    meta = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    remote_id = str(meta["problemId"]) if meta.get("problemId") else None
    is_existing = bool(remote_id)
    if is_existing and include_remote and api is None:
        raise UnsafeSyncError("Remote metadata read requires authenticated Polygon client")

    local_sources = sorted(
        [root / "validator.cpp", root / "checker.cpp", root / "interactor.cpp"]
        + list((root / "generators").glob("*.cpp"))
    )
    local_sources = [p for p in local_sources if p.is_file()
                     and not (p.name == "checker.cpp"
                              and detect_standard_checker(p))]
    local_solutions = [
        p for p in sorted((root / "solutions").iterdir())
        if p.is_file() and p.suffix in {".cpp", ".java"}
    ]
    sample_inputs = sorted((root / "samples").glob("*.in"))
    generator = root / "generators" / "generator.cpp"
    generator_script = extract_freemarker_script(generator) if generator.exists() else None
    vtests = sorted(p for p in (root / "validator_tests").iterdir() if p.is_file()) \
        if (root / "validator_tests").is_dir() else []
    ctests = sorted((root / "checker_tests").glob("*.in")) \
        if (root / "checker_tests").is_dir() else []

    plan = {
        "problem": root.name,
        "localFingerprint": local_fingerprint(root),
        "mode": "update" if is_existing else "create",
        "problemId": remote_id,
        "remoteRevision": None,
        "remoteInspected": bool(is_existing and include_remote),
        "contentComparison": "metadata-only: remote file contents not hashed",
        "localPreflight": preflight["status"],
        "warnings": [i["message"] for i in preflight["warnings"]],
        "writes": [],
        "remoteConflicts": [],
        "requiresOverwriteApproval": is_existing,
    }
    if not is_existing:
        plan["writes"].append({"operation": "problem.create", "target": root.name})
    if is_existing and not include_remote:
        plan["warnings"].append("Remote state not read; apply forbidden until inspected")

    sources = solutions = statements = tests = vremote = cremote = {}
    if is_existing and include_remote:
        entry = _remote_identity(api, remote_id)
        plan["remoteRevision"] = str(entry["revision"])
        wc = entry.get("workingCopyRevision")
        # Different working-copy revision is evidence someone may have staged
        # changes. Do not discard their changes by updating the working copy.
        if wc is not None and str(wc) != str(entry["revision"]):
            raise UnsafeSyncError(
                f"Remote working copy revision {wc} differs from committed "
                f"revision {entry['revision']}; manual review required"
            )
        pid = {"problemId": remote_id}
        info = api.call("problem.info", **pid)
        if not isinstance(info, dict):
            raise UnsafeSyncError("problem.info returned malformed data")
        remote_files = api.call("problem.files", **pid)
        if not isinstance(remote_files, dict):
            raise UnsafeSyncError("problem.files returned malformed data")
        sources = _named_entries(remote_files.get("sourceFiles"), "sourceFiles")
        solutions = _named_entries(_require_list(api, "problem.solutions", pid=pid),
                                   "solutions")
        statements = api.call("problem.statements", **pid)
        if not isinstance(statements, dict):
            raise UnsafeSyncError("problem.statements returned malformed data")
        tests = _named_entries(_require_list(
            api, "problem.tests", pid={"problemId": remote_id, "testset": "tests",
                                      "noInputs": "true"}
        ), "tests", key="index")
        vremote = _named_entries(
            _require_list(api, "problem.validatorTests", pid=pid), "validatorTests", key="index"
        )
        cremote = _named_entries(
            _require_list(api, "problem.checkerTests", pid=pid), "checkerTests", key="index"
        )
        if len(vremote) > len(vtests):
            raise UnsafeSyncError(
                "Remote has more validator tests than local; no documented "
                "deleteValidatorTest API. Resolve manually before sync."
            )
        if len(cremote) > len(ctests):
            raise UnsafeSyncError(
                "Remote has more checker tests than local; cannot safely delete extras."
            )
        # All the following are potential overwrites, even when names differ:
        # updateInfo/clearScript/saveStatement etc. Metadata is not exact content.
        plan["warnings"].append(
            "Existing Polygon content will be changed. Remote list metadata "
            "cannot prove source/solution/test equality."
        )
        for fld, target in [("timeLimit", "time_limit_ms"), ("memoryLimit", "memory_limit_mb")]:
            if fld in info:
                plan["warnings"].append(
                    f"Remote {fld} currently {info[fld]}; compare local CLI configuration before apply"
                )
    else:
        plan["warnings"].append("New problem: remote identity will be created only during --apply")

    def add(operation: str, name: str, exists: bool = False, size: int | None = None):
        status = "possibly-overwrite" if exists else "create-or-update"
        step = {"operation": operation, "target": name, "classification": status}
        if size is not None:
            step["localBytes"] = size
        plan["writes"].append(step)
        if exists:
            plan["remoteConflicts"].append({"operation": operation, "target": name})

    add("problem.updateWorkingCopy", "working-copy", is_existing)
    add("problem.updateInfo", "limits+mode", is_existing)
    stmt_path = root / "statement" / "statement.tex"
    add("problem.saveStatement", "statement.tex",
        bool(statements), stmt_path.stat().st_size)
    if (root / "statement" / "tutorial.tex").is_file():
        add("problem.saveGeneralTutorial", "tutorial.tex", is_existing)
    for path in local_sources:
        add("problem.saveFile", path.name, path.name in sources, path.stat().st_size)
    for path in local_solutions:
        add("problem.saveSolution", path.name, path.name in solutions,
            path.stat().st_size)
    for index, path in enumerate(vtests, 1):
        add("problem.saveValidatorTest", str(index), str(index) in vremote, path.stat().st_size)
    for index, path in enumerate(ctests, 1):
        add("problem.saveCheckerTest", str(index), str(index) in cremote, path.stat().st_size)
    # Includes both script clearing (a destructive remote operation) and re-uploading samples.
    add("problem.clearScript", "tests", is_existing or bool(tests))
    for index, path in enumerate(sample_inputs, 1):
        add("problem.saveTest", f"{index}: {path.name}", str(index) in tests, path.stat().st_size)
    if generator_script:
        add("problem.saveScript", "tests (FreeMarker)", is_existing)
    add("problem.commitChanges", "revision", is_existing)
    plan["writes"].append({"operation": "problem.buildPackage", "target": "full",
                           "classification": "new-build"})
    return plan


def assert_remote_unchanged(api, plan: dict) -> None:
    """Re-check committed and working-copy revisions before writes/commit.

    This is a best-effort guard, NOT an atomic Polygon compare-and-swap.
    """
    if plan["mode"] != "update":
        return
    entry = _remote_identity(api, str(plan["problemId"]))
    if str(entry["revision"]) != plan["remoteRevision"]:
        raise UnsafeSyncError("Remote committed revision changed since the plan; re-plan")
    wc = entry.get("workingCopyRevision")
    if wc is not None and str(wc) != str(entry["revision"]):
        raise UnsafeSyncError("Remote working copy diverged; refusing to overwrite")
