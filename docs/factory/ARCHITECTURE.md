# Target architecture (proposal, not all implemented)

## Separation of concerns

- **Agent layer**: read/normalize problems, reason about solutions, design adversarial cases, diagnose failures. Skills explain procedures; subagents provide isolated reasoning; neither substitutes for tests.
- **Core deterministic engine**: schema validation, compile/run sandbox, differential stress, metamorphic tests, mutation-based coverage, counterexample shrinking, reports.
- **Polygon adapter**: signed API transport, local↔remote identity, per-component diff/sync, verification/polling, revision and package manifest.
- **State layer**: versioned `problem.json`, reproducible seeds, immutable source attachments, `verification.json`, `.polygon.json` (private mapping metadata only, never credentials).

## Proposed per-problem layout

~~~text
problems/<slug>/
  source/                 # immutable origin files and attribution
  spec.json               # normalized constraints and input/output contract
  statement/statement.tex # existing Polygon parser contract
  statement/tutorial.tex
  solutions/{acc,acc_alt,brute,wa}.cpp
  generators/generator.cpp
  validator.cpp
  checker.cpp
  samples/*.in + *.out
  validator_tests/
  regression/             # minimal counterexamples with provenance
  reports/verification.json
  .polygon.json           # remote problemId; never API secrets
~~~

V1 extensions **must not break** the existing upstream `problems/<slug>/` layout. Introduce schema versioning when `spec.json` is implemented.

## States and transitions

`INGESTED → SPEC_REVIEWED → SOLVED → TESTED → LOCAL_VERIFIED → READY_TO_SYNC → SYNCING → POLYGON_VERIFIED`

Failures transition to `NEEDS_REPAIR` with a structured issue record. No automatic transition to `POLYGON_VERIFIED` based on an API request alone. Re-running a stage should be safe; every generated artifact should keep a reproducible seed or source reference.

## API/CLI direction

- `python -m polyup preflight <problem>`: **implemented**, read-only structural checks.
- `factory import ...`, `factory audit ...`, `factory repair ...`: **proposed**, not implemented.
- `python -m polyup <problem>`: **inherited**, side-effectful upload; remains opt-in.

Polygon credentials stay in a local environment/.env, never in prompts, commits, logs, reports or model tool outputs. Remote writes require user-approved target and scope.

## Dependency graph for later repairs

- Statement constraints → validator, generator, solutions, stress budget, performance bench.
- Input format → validator, generator, samples, solutions, parser.
- Checker policy → checker tests, oracle comparison, solution verdicts.
- Generator/testset → uniqueness, validator, full invocations, new package.
- Only editorial spelling → render/review statement; no need to rewrite algorithms.

Model output is **proposed code or claims**; local and Polygon verification provide independent evidence.
