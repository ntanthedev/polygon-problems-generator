# Session handoff — 2026-10-15

## Repository / branch

- Repository: `ntanthedev/polygon-problems-generator` (fork of `7oSkaaa/polygon-problems-generator`).
- Working branch for initial factory work: `factory/phase-0-governance-preflight-20261015`.
- PR: [#1 (Draft)](https://github.com/ntanthedev/polygon-problems-generator/pull/1), initial Factory M0.
- Base main commit at fork discovery: `0725d8874e41b2d39ba9d6d3b82b24c60887109b`.

## User's goal

Drop an existing programming problem (PDF/images/text) into a workspace; preferably Gemini Pro or another strong model handles ambiguous reasoning, while weaker models can use user-provided idea/solution. Agents should generate statement, validator, checker, independent solutions, generators, strong tests, verify them, and optionally publish to Polygon. Contest creation is manual. Later repair missing edge cases or bad statement without recreating problem. Avoid CHTOJ/VNOJ work.

## Grounded upstream audit

- `.claude/commands/generate-problem.md` requires statement, intended solution, constraints, sample; lacks import-only entry.
- `verify.sh` compiles, samples, ACC/Java/alt, WA detection, ACC-vs-brute (default 1,000); NOT exhaustive or full FreeMarker execution.
- `polyup/api.py` calls signed Polygon requests without explicit timeout.
- `polyup/sync.py` creates or updates by `.polygon.json` problemId, commits and requests package build but does not poll final status.
- `sync-ai-configs.py` regenerates root `AGENTS.md`; prefer `.claude/shared.md` source.
- Existing `originality.py` blocks similar new inventions in some difficulty bands; imported existing tasks must not use that rule blindly.

## Current work and limits

- Governance docs, offline preflight CLI, skill and 7 unit tests implemented on PR #1. **PF-001 DONE** based on GitHub Actions [run 38756769808](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38756769808): `compileall` and tests passed on Python 3.11 and 3.12. GitHub CI is the actual execution evidence; local container clone was blocked by DNS.
- No authorized real Polygon upload has been run; no PDF/vision ingestion implementation yet.
- `python3 -m polyup preflight ...` is intended to inspect local files only and does not validate algorithm correctness.

## Next session

1. Check PR #1 / CI on its latest SHA, inspect `docs/factory/TASKS.md`.
2. Optional: test `python3 -m polyup preflight problems/<name> --json` on a real complete problem folder; it only checks structure.
3. Review and merge PR #1 when satisfied.
4. Start API-001 in a separate small PR: timeouts, structured errors, mocked network tests. Verify no behavior regressions in `sync.py`.
5. After API-001, work toward M1 package polling and ingestion, not UI/contest tooling.

## Reporting contract

Never assume a previous plan was implemented. New session should confirm branch SHA, current file content and actual test outcomes. User may be using a separate coding agent for other projects; avoid unnecessary local coding-model consumption.
