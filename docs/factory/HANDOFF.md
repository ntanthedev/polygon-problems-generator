# Session handoff — 2026-10-15 (API-002 mock implementation)

## Repository / branch

- Repository: `ntanthedev/polygon-problems-generator` (fork of `7oSkaaa/polygon-problems-generator`).
- Working branch for initial factory work: `factory/phase-0-governance-preflight-20261015`.
- PR #1 (Draft): [initial Factory M0 + API-001](https://github.com/ntanthedev/polygon-problems-generator/pull/1).
- API-002 branch: `factory/api-002-package-verification-20261015` based on commit `b30173fee23215ac3e4a4ac42dee93d4f55a639e` from PR #1. Create a stacked PR against the phase-0 branch.
- Base main commit at fork discovery: `0725d8874e41b2d39ba9d6d3b82b24c60887109b`.

## User's goal

Drop an existing programming problem (PDF/images/text) into a workspace; preferably Gemini Pro or another strong model handles ambiguous reasoning, while weaker models can use user-provided idea/solution. Agents should generate statement, validator, checker, independent solutions, generators, strong tests, verify them, and optionally publish to Polygon. Contest creation is manual. Later repair missing edge cases or bad statement without recreating problem. Avoid CHTOJ/VNOJ work.

## Grounded upstream audit

- `.claude/commands/generate-problem.md` requires statement, intended solution, constraints, sample; lacks import-only entry.
- `verify.sh` compiles, samples, ACC/Java/alt, WA detection, ACC-vs-brute (default 1,000); NOT exhaustive or full FreeMarker execution.
- `polyup/api.py` now signs requests as before, posts with an explicit `(10s, 60s)` timeout, and turns transport/HTTP/JSON/status failures into `PolygonAPIError`. It does not retry writes.
- `polyup/sync.py` on API-002 branch now calls `build_and_wait` after commit, captures current revision via `problems.list`, compares pre-build package snapshot, and requires all newly observed packages to reach READY (full build: standard, linux, windows). The `fatal=False` callers still treat `None` as a soft Polygon refusal.
- `sync-ai-configs.py` regenerates root `AGENTS.md`; prefer `.claude/shared.md` source.
- Existing `originality.py` blocks similar new inventions in some difficulty bands; imported existing tasks must not use that rule blindly.

## Current work and limits

- Governance docs, offline preflight CLI, skill and the original 7 unit tests are on PR #1. **PF-001 DONE** based on GitHub Actions [run 38756769808](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38756769808): `compileall` and tests passed on Python 3.11 and 3.12. That run does not include API-001.
- **API-001 is on `factory/phase-0-governance-preflight-20261015` (draft PR #1).** Parent commit: `032ff428bbb4915c29fcd5b64a0e62f7b92901da`. No separate branch was opened.
- Local evidence on Python 3.13.0, from the repo root: `python -m compileall -q polyup tests` exit 0, then `python -m unittest discover -s tests -v` → `Ran 30 tests` `OK` (23 API tests + 7 preflight). Mocks only; no socket to Polygon.
- **NOT_RUN:** GitHub Actions for this diff, `./verify.sh`, and any live Polygon read or write.
- Contract that callers rely on: `fatal=False` returns `None` for HTTP, JSON, and non-OK API status. Transport errors raise `PolygonAPIError` for both `fatal` values. `fatal=True` no longer calls `sys.exit` inside `PolygonAPI.call`; the CLI prints `  API error [...]` and exits 1. Secrets shorter than 4 characters are not redacted.
- No authorized real Polygon upload has been run; no PDF/vision ingestion implementation yet.
- `python -m polyup preflight ...` inspects local files only and does not validate algorithm correctness.


## API-002 mock verification (2026-10-15)

- Code: `polyup/package_monitor.py`, `polyup/config.py`, `polyup/sync.py`, `tests/test_package_monitor.py`.
- GitHub Actions [run 38766107192](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38766107192) confirmed `compileall` and **44 unit tests PASS** (30 inherited + 14 new) on Python 3.11 and 3.12. An initial fixture error on a prior run was corrected before this green run.
- A package whose (id, type) was present before build is never accepted as a new READY package. `problem.buildPackage` is called once; lost-response writes are not retried. Unknown/malformed packages, FAILED, ambiguous concurrent builds, old revision and timeout fail closed. `verify=false` never sets `verified_invocations=true`.
- This assumes the documented `Package` fields and full-build types; **live Polygon run is NOT_RUN**, therefore do not claim real API compatibility or production readiness. Explicit approval and private target required before integration test. Wait deadline defaults to 900 seconds (per-request timeout remains 10/60).
- API-001 followups: short secrets (<4 chars) are not redacted; soft HTTP/status failure of `problem.clearScript` still allows subsequent sync. Track under API-003 before autonomous sync.

## Next session

1. Review PR #1 (base) and stacked PR #2 (API-002), and their CI evidence. Check current branch SHA before editing.
2. API-002 still needs a separately approved live integration trial on a private Polygon problem; until then mark it BLOCKED for end-to-end confirmation.
3. Start API-003 in an isolated branch when ready: fail-closed sync, pre-sync diff, secrets/no unconditional retries.
4. After safe Polygon baseline, proceed ING-001 specification schema. Ingestion/UI remain unimplemented.

## Reporting contract

Never assume a previous plan was implemented. New session should confirm branch SHA, current file content and actual test outcomes. User may be using a separate coding agent for other projects; avoid unnecessary local coding-model consumption.
