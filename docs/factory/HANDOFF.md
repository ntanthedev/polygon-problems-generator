# Session handoff — 2026-10-16 (SOL-001 candidate/oracle verification)

## Repository / branch

- Repository: `ntanthedev/polygon-problems-generator` (fork of `7oSkaaa/polygon-problems-generator`).
- Working branch for initial factory work: `factory/phase-0-governance-preflight-20261015`.
- PR #1 (Draft): [initial Factory M0 + API-001](https://github.com/ntanthedev/polygon-problems-generator/pull/1).
- API-002 branch: `factory/api-002-package-verification-20261015` based on commit `b30173fee23215ac3e4a4ac42dee93d4f55a639e` from PR #1. Stacked PR: [#2 (Draft)](https://github.com/ntanthedev/polygon-problems-generator/pull/2), targeting the phase-0 branch.
- API-003 branch: `factory/api-003-safe-sync-20261015` stacked on API-002 branch; Stacked PR: [#3 (Draft)](https://github.com/ntanthedev/polygon-problems-generator/pull/3), targeting API-002 branch.
- ING-001 branch: `factory/ing-001-problem-spec-v1-20261015`, stacked on API-003. [stacked PR #4 (Draft)](https://github.com/ntanthedev/polygon-problems-generator/pull/4), targeting the API-003 branch.
- ING-002 branch: `factory/ing-002-multimodal-ingestion-20261016`; [stacked PR #5 (Draft)](https://github.com/ntanthedev/polygon-problems-generator/pull/5) targeting ING-001 branch.
- SOL-001 branch: `factory/sol-001-reference-check-20261016` stacked on ING-002 [PR #5](https://github.com/ntanthedev/polygon-problems-generator/pull/5); new PR #6 to be created.
- Base main commit at fork discovery: `0725d8874e41b2d39ba9d6d3b82b24c60887109b`.

## User's goal

Drop an existing programming problem (PDF/images/text) into a workspace; preferably Gemini Pro or another strong model handles ambiguous reasoning, while weaker models can use user-provided idea/solution. Agents should generate statement, validator, checker, independent solutions, generators, strong tests, verify them, and optionally publish to Polygon. Contest creation is manual. Later repair missing edge cases or bad statement without recreating problem. Avoid CHTOJ/VNOJ work.

## Grounded upstream audit

- `.claude/commands/generate-problem.md` requires statement, intended solution, constraints, sample; lacks import-only entry.
- `verify.sh` compiles, samples, ACC/Java/alt, WA detection, ACC-vs-brute (default 1,000); NOT exhaustive or full FreeMarker execution.
- `polyup/api.py` now signs requests as before, posts with an explicit `(10s, 60s)` timeout, and turns transport/HTTP/JSON/status failures into `PolygonAPIError`. It does not retry writes.
- `polyup/sync.py` on API-003 branch calls `build_and_wait` after commit; API-003 adds read-only plans, explicit `--apply`/`--allow-overwrite`, preflight, local fingerprint, best-effort remote revision checks, strict clearScript, stale-test blocks and fail-on-hard cautions. API-002 package-monitor CI is still mock-only.
- `sync-ai-configs.py` regenerates root `AGENTS.md`; prefer `.claude/shared.md` source.
- Existing `originality.py` blocks similar new inventions in some difficulty bands; imported existing tasks must not use that rule blindly.

## Current work and limits

- Governance docs, offline preflight CLI, skill and the original 7 unit tests are on PR #1. **PF-001 DONE** based on GitHub Actions [run 38756769808](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38756769808): `compileall` and tests passed on Python 3.11 and 3.12. That run does not include API-001.
- **API-001 is on `factory/phase-0-governance-preflight-20261015` (draft PR #1).** Parent commit: `032ff428bbb4915c29fcd5b64a0e62f7b92901da`. No separate branch was opened.
- Local evidence on Python 3.13.0, from the repo root: `python -m compileall -q polyup tests` exit 0, then `python -m unittest discover -s tests -v` → `Ran 30 tests` `OK` (23 API tests + 7 preflight). Mocks only; no socket to Polygon.
- **NOT_RUN:** `./verify.sh` and any real Polygon read or write. The API-001 diff has since passed CI as part of PR #1 / subsequent branches.
- Contract that callers rely on: `fatal=False` returns `None` for HTTP, JSON, and non-OK API status. Transport errors raise `PolygonAPIError` for both `fatal` values. `fatal=True` no longer calls `sys.exit` inside `PolygonAPI.call`; the CLI prints `  API error [...]` and exits 1. API-003 now redacts any nonempty configured secret, including values shorter than four characters.
- No authorized real Polygon upload has been run; no PDF/vision ingestion implementation yet.
- `python -m polyup preflight ...` inspects local files only and does not validate algorithm correctness.


## API-002 mock verification (2026-10-15)

- Code: `polyup/package_monitor.py`, `polyup/config.py`, `polyup/sync.py`, `tests/test_package_monitor.py`.
- GitHub Actions [run 38766107192](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38766107192) confirmed `compileall` and **44 unit tests PASS** (30 inherited + 14 new) on Python 3.11 and 3.12. An initial fixture error on a prior run was corrected before this green run.
- A package whose (id, type) was present before build is never accepted as a new READY package. `problem.buildPackage` is called once; lost-response writes are not retried. Unknown/malformed packages, FAILED, ambiguous concurrent builds, old revision and timeout fail closed. `verify=false` never sets `verified_invocations=true`.
- This assumes the documented `Package` fields and full-build types; **live Polygon run is NOT_RUN**, therefore do not claim real API compatibility or production readiness. Explicit approval and private target required before integration test. Wait deadline defaults to 900 seconds (per-request timeout remains 10/60).
- API-001 followups: short secrets (<4 chars) are not redacted; soft HTTP/status failure of `problem.clearScript` still allows subsequent sync. Track under API-003 before autonomous sync.


## API-003 safe sync (2026-10-15)

- Branch `factory/api-003-safe-sync-20261015` stacked on API-002; source files: `polyup/sync_plan.py`, `polyup/__main__.py`, `polyup/sync.py`, `polyup/api.py`, `tests/test_sync_plan.py` plus updated inherited tests.
- GitHub Actions [run 38769146390](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38769146390): **60 tests PASS on Python 3.11 + 3.12**, Python compileall succeeded. More code/doc-only commits followed; check latest SHA CI before merge.
- `python -m polyup <problem>` defaults to a read-only JSON plan. Existing remote problems need Polygon API credentials to READ metadata even for planning. New problem plans require no Polygon credentials. Nothing is written until `--apply`; an existing problem also needs `--allow-overwrite`.
- `--dry-run --apply` is rejected. `sync_plan.py` rejects structural preflight failures, remote read errors, unexpected response shapes, remote permissions missing, differing working-copy revision, excess validator/checker tests; it reads source/solution/statement/test metadata and labels content comparison **metadata-only**.
- Rechecks remote committed revision and local SHA-256 manifest/fingerprint before writing and before commit. Not atomic: concurrent remote or local writes between checks can still race. No undo/rollback after a partial remote upload. Always restrict direct edits while syncing.
- `problem.clearScript` now throws on HTTP/API rejection rather than letting subsequent tests upload, and unsupported `problem.deleteValidatorTest` calls were removed. Explicit access failures and Polygon HARD cautions now fail closed.
- No real Polygon integration performed. **Do not claim production-ready remote synchronization.** API-INT-001 needs user permission, private target, and reconciliation testing of partial failures.

## Next session

1. Review PR #1 (base) → PR #2 (API-002) → PR #3 (API-003), CI and staged code. Rebase/retarget stacked PRs only after the base merges.
2. API-INT-001 still requires a separately approved live integration trial on a user-specified private Polygon problem; do not call Polygon yet.
3. Next coding task: **QA-001**. Add seeded/exhaustive/differential test-generation budgets and minimized reproducible counterexamples atop SOL-001. Real Docker smoke SOL-LIVE-001 remains outstanding.
4. API-003 limitations: metadata-only remote comparisons, best-effort (non-atomic) revision guard and no rollback. These require integration review before unattended writes.

## Reporting contract

Never assume a previous plan was implemented. New session should confirm branch SHA, current file content and actual test outcomes. User may be using a separate coding agent for other projects; avoid unnecessary local coding-model consumption.

## ING-001 delivery (2026-10-15)

- `factory/schemas/problem-spec.v1.schema.json`: strict JSON Schema Draft 2020-12 (`schemaVersion=1`), fields for provenance, exact text, optional user-provided idea or solution, scoped constraints including sums, samples, test-case mode, output policy, ambiguous values, time/memory limits.
- `factory/spec.py` + CLI `python -m factory spec`: structure validation, `--ready` review gate, `from-local` adapter reading existing Polygon statement.tex + samples while preserving original UTF-8 bytes/CRLF and SHA-256. It **does not guess** constraints, algorithms, testcase mode or checker equivalence.
- 5 valid + 8 invalid fixtures, unit tests, `requirements-factory.txt`, CI extension for Python 3.11/3.12 and a model-neutral `.agents/skills/factory-problem-spec/SKILL.md`.
- Read [PROBLEM_SPEC_V1.md](PROBLEM_SPEC_V1.md). No calls to Polygon; no PDF/image ingestion yet. Do not confuse `--ready` with proof of correctness or Polygon publication readiness.
- Upcoming ING-002 must preserve the same schema and capture text/region provenance; it is NOT implemented here.

## ING-002 delivery (2026-10-16)

- [PR #5](https://github.com/ntanthedev/polygon-problems-generator/pull/5) stacked on PR #4; files `factory/ingest.py`, `factory/gemini_vision.py`, `factory/__main__.py`, `tests/test_ingestion.py`, `tests/test_ingestion_media.py`, `docs/factory/INGESTION.md`, `.agents/skills/factory-ingest/SKILL.md`, `requirements-vision.txt`, `requirements-factory.txt`, CI workflow.
- Offline command: `python3 -m factory ingest path/to/problem.pdf --slug simple_problem --dest problems/simple_problem`. Creates new directory only; stores **original file bytes**, SHA256, draft `spec.json`, and `evidence.json`. Optional `--idea` and `--solution-file` copy guidance without execution.
- TXT/MD: native UTF-8 preservation and conservative section parser. PDF: PyMuPDF native text-block extraction with page coordinates. Scanned PDF/image: no text means blocked draft by default. **Explicit** `--vision-model MODEL_ID` uses Gemini Interactions API for per-page PNG transcription; local key needed. Every vision transcript remains pending review; no invented constraints or auto-READY.
- Safety: no remote Polygon activity, no direct file overwrite, 20 MiB input and 32-page budget, model/page render caps, sanitized provider errors. Input source paths and user source code should remain under user control.
- CI [run 38777661492](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38777661492): **106 tests PASS** on Python 3.11 and 3.12. Latest code CI confirmed on Python 3.11 and 3.12. Vision tests use MOCK, not an actual Gemini API key or live model.
- No claim that generic PDFs with complex columns/tables are transcribed perfectly; final review must inspect `evidence.json` and source. Algorithm solving, generator creation and end-to-end Polygon publishing are future tasks.
- **Next SOL-001**: issue scoped tasks for a strong reasoning model (derive oracle), or weaker model with user-provided idea/code. **ING-LIVE-001** requires separate opt-in to send a disposable non-sensitive source through Gemini and verify SDK/model behavior.

## SOL-001 delivery (2026-10-16)

- Branch `factory/sol-001-reference-check-20261016` on top of PR #5. Added `factory/solution_check.py` (reviewed V1 spec, optional user code, C++17 candidate/oracle agreements, sample and extra cases, verdicts WA/TLE/RE/MLE/OLE/oracle failures, source/input hashes), `factory/docker_runner.py` (Docker-only compilation/execution with read-only/networkless nonroot containers, CPU/memory/pid/time/file caps, symlink/FIFO-resistant guest output), CLI `factory solutions verify`, tests, synthetic fixture, and `.agents/skills/factory-solve/SKILL.md`.
- Guidance for three modes: statement-only → derive candidate/oracle; statement+idea → challenge untrusted idea; statement+solution → treat user source as candidate and derive oracle separately. **No automatic LLM reasoning runtime has been added**: only agent skill and deterministic tools.
- Result `PASS_ON_TESTS` means agreement on a limited input corpus, not proof. Runner accepts reviewed `outputPolicy=exact` noninteractive tasks only, and marks `oracleIsProvenCorrect=false`.
- Mock/offline CI [run 38779624746](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38779624746) passed 132 tests for Python 3.11/3.12. Later commits added readiness gate and output symlink/FIFO hardening; **confirm latest SHA CI** before merge.
- No real Docker container compilation/execution performed. `SOL-LIVE-001` awaits a disposable local VM + preapproved locally available gcc Docker image; no secrets/Polygon involved. Test fixture and instructions in [SOLUTIONS.md](SOLUTIONS.md).
- QA-001 next: generate small-domain systematic/random case corpora with explicit oracle resource budgets, seeded reproducibility, counterexample minimizing, saved regressions. Keep checker-specific tasks deferred.
