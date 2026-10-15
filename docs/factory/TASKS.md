# Execution board — updated 2026-10-15

States: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`. The board reflects **verified work**, not agent intentions. Do one narrow task/PR at a time.

| ID | State | Task | Acceptance / evidence |
|---|---|---|---|
| GOV-001 | DONE | Establish project governance, agent handoff, roadmap and prompt templates | All linked documents created in branch |
| PF-001 | IN_PROGRESS | Read-only local problem preflight + offline tests | Run `python3 -m unittest discover -s tests -v`; verify CLI behavior |
| API-001 | TODO | API client error model, timeout, credential-safe logging | Unit tests for network/HTTP/JSON failures |
| API-002 | TODO | Poll and verify remote package state after build | Mock lifecycle tests + authorized live trial |
| API-003 | TODO | Real pre-sync plan, dry-run and safe re-sync | No unexpected remote writes |
| ING-001 | TODO | Define versioned normalized problem specification | JSON schema + valid/invalid fixtures |
| ING-002 | TODO | Text/Markdown/PDF/image ingestion | Golden fixture + ambiguity report |
| SOL-001 | TODO | Three input modes (no hint / idea / user solution) | Independent oracle tests |
| QA-001 | TODO | Differential+exhaustive runner | Seeded counterexample + resource limits |
| QA-002 | TODO | Boundary/adversarial/mutation testing | Mutant coverage and regression output |
| AG-001 | TODO | Platform-neutral skills and Antigravity subagent integration | Agent handoff passes on at least one sample |
| REP-001 | TODO | Repair loop, impact graph and incremental Polygon update | New edge case → verified revision |

### Immediate next execution task

**PF-001** first. Confirm the unit tests run on Linux and `python3 -m polyup preflight <path>` returns actionable errors without touching Polygon. Address any bugs found in a follow-up patch; mark DONE only with command + result in HANDOFF.

Then **API-001**. Inspect `polyup/api.py` and its callers to preserve API behavior, add explicit network timeout, safe exception semantics and mock-based tests. Do **not** implement unconditional retries of side-effecting `problem.create`, `saveFile`, `commitChanges`, or `buildPackage`.

### Task protocol

Each change: task ID → files changed → tests run + results → risks → PR/commit → HANDOFF updated. Do not mark DONE merely because an agent wrote code.
