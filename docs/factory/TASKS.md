# Execution board — updated 2026-10-15 (API-001)

States: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`. The board reflects **verified work**, not agent intentions. Do one narrow task/PR at a time.

| ID | State | Task | Acceptance / evidence |
|---|---|---|---|
| GOV-001 | DONE | Establish project governance, agent handoff, roadmap and prompt templates | All linked documents created in branch |
| PF-001 | DONE | Read-only local problem preflight + offline tests | Run `python3 -m unittest discover -s tests -v`; verify CLI behavior |
| API-001 | DONE | API client error model, timeout, credential-safe logging | Local Python 3.13.0: `python -m unittest discover -s tests -v` → 30 tests OK; `python -m compileall -q polyup tests` exit 0. GitHub Actions NOT_RUN. Live Polygon NOT_RUN |
| API-002 | BLOCKED | Poll and verify remote package state after build | Code + 14 mocked tests PASS (Python 3.11/3.12, CI run 38766107192); live Polygon verification requires explicit permission |
| API-003 | TODO | Real pre-sync plan, dry-run and safe re-sync | No unexpected remote writes |
| ING-001 | TODO | Define versioned normalized problem specification | JSON schema + valid/invalid fixtures |
| ING-002 | TODO | Text/Markdown/PDF/image ingestion | Golden fixture + ambiguity report |
| SOL-001 | TODO | Three input modes (no hint / idea / user solution) | Independent oracle tests |
| QA-001 | TODO | Differential+exhaustive runner | Seeded counterexample + resource limits |
| QA-002 | TODO | Boundary/adversarial/mutation testing | Mutant coverage and regression output |
| AG-001 | TODO | Platform-neutral skills and Antigravity subagent integration | Agent handoff passes on at least one sample |
| REP-001 | TODO | Repair loop, impact graph and incremental Polygon update | New edge case → verified revision |

### Immediate next execution task

**API-002 implementation is ready for review** in stacked PR #2 (based on PR #1), but its real Polygon integration trial remains BLOCKED on explicit user permission. Mocks establish the state machine, not the live API contract. Do not enable autonomous upload until a private test problem is named and permission is given. **API-003** is the next independent development task: safe pre-sync plan/diff and fail-closed remote writes; it should start as a separate PR after review. No unconditional retry of mutating methods.

API-001 contract (on the phase-0 branch; CI for this commit is NOT_RUN until Actions finishes):

- HTTP timeout is `(10.0, 60.0)` connect/read. Passing `timeout=None` still uses that default.
- `PolygonAPIError.kind` is `transport`, `http`, `json`, or `status`. Messages redact the API key, secret, and `apiSig` when those values are at least 4 characters.
- `fatal=False` still returns `None` for HTTP, non-JSON, and non-OK API status, and still prints one stderr line. Transport errors raise even when `fatal=False` (previously an uncaught `requests` exception, not `None`).
- `fatal=True` raises `PolygonAPIError` instead of calling `sys.exit` inside the client. `python -m polyup` and `python -m polyup access` catch it and exit 1.
- No automatic retry. Multipart SHA-512 signing is unchanged: file bytes are in the signature, then the `file` field is removed from the form body.


API-002 CI: [run 38766107192](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38766107192) — `python -m compileall -q polyup tests` plus **44 tests PASS** on Python 3.11 and 3.12. `tests/test_package_monitor.py` contributes 14 tests. Includes stale READY package, state progression, failed build, wrong revision, timeout, duplicate new packages, commit conflict, transport error, and `verify=false` reporting. No Polygon credentials/requests used.

PF-001: GitHub Actions [run 38756769808](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38756769808) confirmed `compileall` + 7 offline unit tests PASS on Python 3.11 and 3.12. That run does not include API-001.

### Task protocol

Each change: task ID → files changed → tests run + results → risks → PR/commit → HANDOFF updated. Do not mark DONE merely because an agent wrote code.
