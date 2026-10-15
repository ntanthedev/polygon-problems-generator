# Roadmap and acceptance contracts

All milestones require reproducible commands/logs. See [TASKS.md](TASKS.md) for current state. Priority: ship narrow, testable vertical slices rather than many half-implemented skills.

## M0 — Project control + offline preflight (P0, initial PR)

- Entry point, charter, architecture, task list, agent rules, handoff and task prompts.
- Read-only `python -m polyup preflight` checks local Polygon problem structure and reports actionable failures.
- `unittest` coverage for valid, missing, malformed and duplicate-sample cases.
- Acceptance: import-free offline command; no Polygon secret needed; nonzero exit on missing mandatory structure.

## M1 — Safe Polygon transport (P0)

- Typed API errors, timeouts, bounded retries **only for safely retryable operations**, structured logs and credential redaction.
- Pre-sync plan/diff, conflict awareness, scoped writes, dry-run that validates real local content.
- Commit → build → poll package → inspect failed/ready/success, verify revision and cautions.
- Acceptance: mocked timeout/HTTP/error/state tests, and one authorized private test-problem integration run. No “Done” before confirmed server completion.

## M2 — Existing-problem ingestion (P0)

- Intake PDFs with text layer, image/scanned PDFs, images, Markdown, raw LaTeX.
- Preserve source artifacts; extract title, statement, input/output, constraints, samples; ambiguity flags and evidence locations.
- Support `statement-only`, `statement+idea`, and `statement+solution` contracts.
- Acceptance: golden test fixture corpus; unknown fields remain unknown, never invented; sample round-trip.

## M3 — Reference solutions and verification (P1)

- Efficient solution, independent brute/oracle, optional user-provided solution; complexity analysis.
- Small exhaustive + targeted differential testing; failure classification; isolated execution.
- Acceptance: counterexamples reproducible, multi-answer cases use checker semantics, no “proved correct” wording.

## M4 — Strong test engine (P1)

- Boundary, adversarial, randomized and maximum-size generator profiles.
- Deterministic seeds, input validator, resource-budgeted executions and mutations.
- Detect WA/TLE/RE/MLE separately; shrink and save regression cases; coverage report with surviving mutants.
- Acceptance: benchmark on varied problem families and inject known faulty solutions to measure caught errors.

## M5 — Agent workflows + repairs (P1)

- Skills and optional Antigravity custom subagents using stable tool contracts.
- Repair existing problem after new WA/counterexample; impact analysis, verification replay and safe resync.
- Acceptance: update only relevant artifacts; no secret leakage; old verified revision retained until replacement verified.

## Later (P2)

Batch input queue, interactive/constructive-specific workflows, UI reports, MCP only if a clear CLI integration gap exists.
