# Execution board — updated 2026-10-16 (SOL-LIVE-001 blocked)

States: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`. The board reflects **verified work**, not agent intentions. Do one narrow task/PR at a time.

| ID | State | Task | Acceptance / evidence |
|---|---|---|---|
| GOV-001 | DONE | Establish project governance, agent handoff, roadmap and prompt templates | All linked documents created in branch |
| PF-001 | DONE | Read-only local problem preflight + offline tests | Run `python3 -m unittest discover -s tests -v`; verify CLI behavior |
| API-001 | DONE | API client error model, timeout, credential-safe logging | Local Python 3.13.0: `python -m unittest discover -s tests -v` → 30 tests OK; `python -m compileall -q polyup tests` exit 0. GitHub Actions NOT_RUN. Live Polygon NOT_RUN |
| API-002 | BLOCKED | Poll and verify remote package state after build | Code + 14 mocked tests PASS (Python 3.11/3.12, CI run 38766107192); live Polygon verification requires explicit permission |
| API-003 | DONE | Read-only pre-sync plan, explicit apply/overwrite, revision + local drift guards, strict clearScript | Mocked CI 60 tests PASS (3.11/3.12); real Polygon NOT_RUN |
| API-INT-001 | BLOCKED | Authorized real Polygon integration smoke test for API-001/002/003 | User-specified private problem + explicit approval required |
| ING-001 | DONE | Strict versioned spec, 4 input modes, offline CLI and local Polygon adapter | 5 valid/8 invalid JSON fixtures + Python tests; 83 tests PASS (3.11/3.12), CI run 38772106942 |
| ING-002 | DONE | Offline-first TXT/Markdown/PDF/image drafts, page/bbox evidence, optional Gemini vision adapter | 106 mock/offline tests PASS (3.11/3.12) CI run 38777661492; Gemini live NOT_RUN |
| ING-LIVE-001 | BLOCKED | Live Gemini vision smoke test on a non-sensitive disposable source | User opt-in, available API model and local key required; no external calls made |
| SOL-001 | DONE | Three modes supported by V1 + solve-agent skill, deterministic C++17 candidate/oracle checker, Docker isolation | 136 mocked/offline tests PASS (Python 3.11/3.12); real Docker runtime pending SOL-LIVE-001 |
| SOL-LIVE-001 | BLOCKED | Disposable Docker smoke test for solution runner (no credentials) | 2026-10-16 on this host: Docker Engine 28.5.2 is up, local image `gcc:14` is absent and was not pulled; host is a physical Lenovo ThinkPad, not a disposable VM. Fixture smoke NOT_RUN |
| QA-001 | TODO | Differential+exhaustive runner | Seeded counterexample + resource limits |
| QA-002 | TODO | Boundary/adversarial/mutation testing | Mutant coverage and regression output |
| AG-001 | TODO | Platform-neutral skills and Antigravity subagent integration | Agent handoff passes on at least one sample |
| REP-001 | TODO | Repair loop, impact graph and incremental Polygon update | New edge case → verified revision |

### Immediate next execution task

**API-003 implementation is in [stacked PR #3](https://github.com/ntanthedev/polygon-problems-generator/pull/3)** (on PR #2). ING-002 is implemented on [stacked PR #5](https://github.com/ntanthedev/polygon-problems-generator/pull/5) atop PR #4. CI passes mocked/offline behavior; **live Gemini remains BLOCKED on explicit opt-in**. SOL-001 implemented in [stacked PR #6](https://github.com/ntanthedev/polygon-problems-generator/pull/6) using a deterministic C++17 Docker-backed comparator and model-neutral solve skill; no LLM algorithm-generation service is claimed. Next task: **QA-001** — seeded differential/exhaustive runner and reproducible counterexample minimization. Local Docker smoke SOL-LIVE-001 was attempted on 2026-10-16 and remains BLOCKED: Docker Engine 28.5.2 is running, but `gcc:14` is not installed locally and this host is a physical ThinkPad rather than a disposable VM. Do not pull the image or run the fixture here without a separate approval and a disposable host. Do not enable unattended execution or publishing yet. Review/merge upstream stacked PRs in order before local use. The real Polygon smoke test API-INT-001 remains BLOCKED without an authorized private problem. Existing API implementation has mock CI only, not verified against live Polygon. Do not enable unattended publishing yet. No unconditional retry of mutating API calls.

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

ING-001 evidence: [GitHub Actions run 38772106942](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38772106942) — 83 tests PASS on Python 3.11 + 3.12, compileall PASS. Tests live in `tests/test_problem_spec.py`; [V1 contract](PROBLEM_SPEC_V1.md). Importing with `factory spec from-local` outputs draft only. No real Polygon calls or uploads were made.

ING-002 CI: [run 38777661492](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38777661492) — 106 tests PASS on Python 3.11 and 3.12; later `GeminiVision` exception sanitization and documentation updates require latest-head CI confirmation. No live Gemini or Polygon requests. The model-neutral vision protocol allows alternative providers, but only Gemini Interactions has a concrete adapter in this branch. See [INGESTION.md](INGESTION.md).

SOL-001 CI evidence: [latest GitHub Actions run 38780833767](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38780833767) — **136 tests PASS** on Python 3.11 and 3.12 including symlink/FIFO regression and readiness tests. That run does not execute a real container. Synthetic reproducible addition fixture: `factory/fixtures/solution_smoke/`. Reports show `PASS_ON_TESTS`, not proven correctness. See [SOLUTIONS.md](SOLUTIONS.md).

SOL-LIVE-001 local evidence (2026-10-16, branch `factory/sol-001-reference-check-20261016` at `12e2f705feb067d63802cdeb982986e19cf4f9f8`, before this note):

- `python -m unittest discover -s tests -v` on Python 3.13.0 (Windows): **Ran 136 tests, FAILED (failures=1, errors=2, skipped=1)**. This is not the Linux CI result. The failure is `test_optional_user_idea_and_solution` (idea text keeps `\r\n` on Windows; ING-001, not changed here). The errors are `test_symlink_test_case_refused` and `test_guest_output_symlink_cannot_read_host_file` (`WinError 1314`, this account cannot create symlinks). The skip is `test_guest_fifo_is_rejected_without_blocking` because Windows has no `os.mkfifo`.
- `docker version`: client and engine **28.5.2**, context `desktop-linux`, server OS/Arch `linux/amd64`, Docker Desktop 4.51.0.
- `docker image inspect gcc:14`: **No such image**. Image was not pulled.
- Host probe: computer `THINKPAD`, manufacturer `LENOVO`, model `21ED0069VN`, user `nhatt`. `HypervisorPresent=True` comes from the local virtualization stack on this laptop; it is not a disposable test VM. Checked Polygon/Gemini/OpenAI environment variable names were unset; values were not printed.
- `python -m factory solutions verify factory/fixtures/solution_smoke ...`: **NOT_RUN**. Compile, execution, verdict, timeout, resource limits, container cleanup, and host-execution isolation were not observed on a real container.
