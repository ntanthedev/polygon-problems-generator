# Execution board — updated 2026-10-15 (API-003)

States: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`. The board reflects **verified work**, not agent intentions. Do one narrow task/PR at a time.

| ID | State | Task | Acceptance / evidence |
|---|---|---|---|
| GOV-001 | DONE | Establish project governance, agent handoff, roadmap and prompt templates | All linked documents created in branch |
| PF-001 | DONE | Read-only local problem preflight + offline tests | Run `python3 -m unittest discover -s tests -v`; verify CLI behavior |
| API-001 | DONE | API client error model, timeout, credential-safe logging | Local Python 3.13.0: `python -m unittest discover -s tests -v` → 30 tests OK; `python -m compileall -q polyup tests` exit 0. GitHub Actions NOT_RUN. Live Polygon NOT_RUN |
| API-002 | BLOCKED | Poll and verify remote package state after build | Code + 14 mocked tests PASS (Python 3.11/3.12, CI run 38766107192); live Polygon verification requires explicit permission |
| API-003 | DONE | Read-only pre-sync plan, explicit apply/overwrite, revision + local drift guards, strict clearScript | Mocked CI 60 tests PASS (3.11/3.12); real Polygon NOT_RUN |
| API-INT-001 | BLOCKED | Authorized real Polygon integration smoke test for API-001/002/003 | User-specified private problem + explicit approval required |
| ING-001 | TODO | Define versioned normalized problem specification | JSON schema + valid/invalid fixtures |
| ING-002 | TODO | Text/Markdown/PDF/image ingestion | Golden fixture + ambiguity report |
| SOL-001 | TODO | Three input modes (no hint / idea / user solution) | Independent oracle tests |
| QA-001 | TODO | Differential+exhaustive runner | Seeded counterexample + resource limits |
| QA-002 | TODO | Boundary/adversarial/mutation testing | Mutant coverage and regression output |
| AG-001 | TODO | Platform-neutral skills and Antigravity subagent integration | Agent handoff passes on at least one sample |
| REP-001 | TODO | Repair loop, impact graph and incremental Polygon update | New edge case → verified revision |

### Immediate next execution task

**API-003 implementation is in [stacked PR #3](https://github.com/ntanthedev/polygon-problems-generator/pull/3)** (on PR #2). Next independent development task: **ING-001 — versioned normalized problem specification**, supporting statement-only / statement+idea / statement+solution. The real Polygon smoke test API-INT-001 remains BLOCKED without an authorized private problem. Existing API implementation has mock CI only, not verified against live Polygon. Do not enable unattended publishing yet. No unconditional retry of mutating API calls.

API-001 contract (CI validated on [PR #1](https://github.com/ntanthedev/polygon-problems-generator/pull/1)):

- HTTP timeout is `(10.0, 60.0)` connect/read. Passing `timeout=None` still uses that default.
- `PolygonAPIError.kind` is `transport`, `http`, `json`, or `status`. API-003 also redacts short credentials (any nonempty value); extremely short values may over-redact log text.
- `fatal=False` still returns `None` for HTTP, non-JSON, and non-OK API status, and still prints one stderr line. Transport errors raise even when `fatal=False` (previously an uncaught `requests` exception, not `None`).
- `fatal=True` raises `PolygonAPIError` instead of calling `sys.exit` inside the client. `python -m polyup` and `python -m polyup access` catch it and exit 1.
- No automatic retry. Multipart SHA-512 signing is unchanged: file bytes are in the signature, then the `file` field is removed from the form body.


API-003 CI: [run 38769146390](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38769146390) — 60 mocked/offline tests PASS on Python 3.11 + 3.12; documentation and one completion-text tweak followed this run. Defaults to read-only plan; `--apply` required to write, `--allow-overwrite` for existing problem. Remote metadata list is not exact content diff; existing overwrites are explicitly opt-in. Revision guard is best-effort (not atomic). `problem.clearScript` is fatal on refusal. Live Polygon NOT_RUN.

API-002 CI: [run 38766107192](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38766107192) — `python -m compileall -q polyup tests` plus **44 tests PASS** on Python 3.11 and 3.12. `tests/test_package_monitor.py` contributes 14 tests. Includes stale READY package, state progression, failed build, wrong revision, timeout, duplicate new packages, commit conflict, transport error, and `verify=false` reporting. No Polygon credentials/requests used.

PF-001: GitHub Actions [run 38756769808](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38756769808) confirmed `compileall` + 7 offline unit tests PASS on Python 3.11 and 3.12. That run does not include API-001.

### Task protocol

Each change: task ID → files changed → tests run + results → risks → PR/commit → HANDOFF updated. Do not mark DONE merely because an agent wrote code.
