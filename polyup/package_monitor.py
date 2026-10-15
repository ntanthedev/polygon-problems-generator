"""Conservative package polling for a newly requested Polygon build.

API reference: https://codeforces.github.io/polygon-misc/API
- problem.buildPackage starts an asynchronous build; it does not confirm completion.
- problem.packages returns Package objects with id, revision, type and state.
- PENDING/RUNNING are intermediate; READY and FAILED are terminal.
- A full build is documented to produce standard, linux and windows types.

Matching against a pre-build snapshot prevents reporting an older READY package
for the same revision as success. If concurrent builds make identity ambiguous,
refuse to assert success rather than silently picking one.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .api import PolygonAPI, PolygonAPIError


KNOWN_TYPES = frozenset({"standard", "linux", "windows"})
TERMINAL_STATES = frozenset({"READY", "FAILED"})
KNOWN_STATES = frozenset({"PENDING", "RUNNING"}) | TERMINAL_STATES


class PackageVerificationError(PolygonAPIError):
    """Raised for unexpected, failed, ambiguous or timed-out package builds."""

    def __init__(self, detail: str):
        super().__init__("problem.buildPackage", "package", detail)


@dataclass(frozen=True)
class VerifiedPackage:
    revision: str
    packages: tuple[dict, ...]
    verified_invocations: bool


def _revision(api: PolygonAPI, problem_id: str) -> str:
    result = api.call("problems.list", id=problem_id)
    if not isinstance(result, list):
        raise PackageVerificationError("problems.list returned a non-list result")
    matches = [
        row for row in result
        if isinstance(row, dict) and str(row.get("id")) == problem_id
    ]
    if len(matches) != 1 or matches[0].get("revision") is None:
        raise PackageVerificationError(
            f"Cannot identify a unique current revision for problem {problem_id}"
        )
    revision = str(matches[0]["revision"])
    if not revision or revision == "None":
        raise PackageVerificationError("Current problem revision is missing")
    return revision


def _packages(api: PolygonAPI, pid: dict) -> list[dict]:
    result = api.call("problem.packages", **pid)
    if not isinstance(result, list):
        raise PackageVerificationError("problem.packages returned a non-list result")
    for row in result:
        if not isinstance(row, dict) or any(
            row.get(key) is None for key in ("id", "revision", "type", "state")
        ):
            raise PackageVerificationError("problem.packages returned a malformed Package")
    return result


def _identity(row: dict) -> tuple[str, str]:
    return str(row["id"]), str(row["type"]).lower()


def build_and_wait(
    api: PolygonAPI,
    pid: dict,
    *,
    full: bool = True,
    verify: bool = True,
    timeout_s: float = 900,
    poll_interval_s: float = 5,
) -> VerifiedPackage:
    """Start one build and confirm its new packages reach READY.

    Raises PolygonAPIError or PackageVerificationError on uncertain outcomes.
    Never retries problem.buildPackage (a non-idempotent write).
    """
    if timeout_s <= 0 or poll_interval_s <= 0:
        raise ValueError("timeout_s and poll_interval_s must be positive")
    problem_id = str(pid["problemId"])
    revision = _revision(api, problem_id)
    previous = {_identity(p) for p in _packages(api, pid)}
    expected = KNOWN_TYPES if full else frozenset({"standard"})
    print(f"Starting package for problem={problem_id}, revision={revision}, "
          f"types={','.join(sorted(expected))}, verify={verify}")
    # Any lost reply here is ambiguous. The API client does NOT retry.
    api.call(
        "problem.buildPackage", **pid,
        full=str(full).lower(), verify=str(verify).lower(),
    )
    deadline = time.monotonic() + timeout_s
    last_summary = None
    while True:
        rows = _packages(api, pid)
        fresh = [
            p for p in rows
            if str(p["revision"]) == revision
            and _identity(p) not in previous
            and str(p["type"]).lower() in expected
        ]
        by_type: dict[str, dict] = {}
        for p in fresh:
            kind = str(p["type"]).lower()
            if kind in by_type and _identity(by_type[kind]) != _identity(p):
                raise PackageVerificationError(
                    f"Multiple newly created {kind} packages for revision={revision}; "
                    "concurrent build is ambiguous"
                )
            if str(p["state"]).upper() not in KNOWN_STATES:
                raise PackageVerificationError(
                    f"Unknown package state for revision={revision}, type={kind}"
                )
            by_type[kind] = p

        summary = tuple(sorted(
            (kind, str(row["state"]).upper()) for kind, row in by_type.items()
        ))
        if summary != last_summary:
            detail = ", ".join(f"{k}:{state}" for k, state in summary) or "not visible yet"
            print(f"  package status: {detail}")
            last_summary = summary

        failed = [
            (kind, row) for kind, row in by_type.items()
            if str(row["state"]).upper() == "FAILED"
        ]
        if failed:
            kind, row = failed[0]
            comment = str(row.get("comment") or "").strip()
            # Avoid dumping entire server logs into terminal.
            comment = " ".join(comment.split())[:300]
            raise PackageVerificationError(
                f"Package FAILED for revision={revision}, type={kind}, "
                f"id={row['id']}: {comment or 'no reason provided'}"
            )

        if expected.issubset(by_type) and all(
            str(by_type[k]["state"]).upper() == "READY" for k in expected
        ):
            print(f"Package build READY for revision={revision}; "
                  f"{'verified build requested' if verify else 'verify disabled'}")
            return VerifiedPackage(
                revision=revision,
                packages=tuple(by_type[k] for k in sorted(expected)),
                verified_invocations=verify,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            missing = sorted(expected - by_type.keys())
            raise PackageVerificationError(
                f"Timed out waiting for new packages for revision={revision}; "
                f"missing={missing}; observed={list(summary)}"
            )
        time.sleep(min(poll_interval_s, remaining))
