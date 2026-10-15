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
  spec.json               # version 1 normalization, source evidence, unknowns and hints
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
- `python -m factory ingest SOURCE --slug SLUG --dest problems/SLUG`: **implemented**, offline draft creation; optional Gemini transcriber only with `--vision-model`.
- `factory audit ...`, `factory repair ...`: **proposed**, not implemented.
- `python -m polyup <problem>`: **inherited**, side-effectful upload; remains opt-in.

Polygon credentials stay in a local environment/.env, never in prompts, commits, logs, reports or model tool outputs. Remote writes require user-approved target and scope.

## Dependency graph for later repairs

- Statement constraints → validator, generator, solutions, stress budget, performance bench.
- Input format → validator, generator, samples, solutions, parser.
- Checker policy → checker tests, oracle comparison, solution verdicts.
- Generator/testset → uniqueness, validator, full invocations, new package.
- Only editorial spelling → render/review statement; no need to rewrite algorithms.

Model output is **proposed code or claims**; local and Polygon verification provide independent evidence.

## ING-001: versioned interchange contract

`factory/schemas/problem-spec.v1.schema.json` defines the stable boundary between multimodal ingestion, reasoning agents, test engineering and Polygon serialization. Existing `polyup` does not yet read `spec.json` (backward compatibility). Provenance, literal constraints with scopes, samples, testcase semantics, output/checker policy and optional ideas/solutions are explicit; see [V1 contract](PROBLEM_SPEC_V1.md).

## ING-002 ingestion boundary

`factory/ingest.py` creates an isolated new problem folder, copies the original source unchanged, and outputs a draft V1 spec plus `evidence.json` (extractor, source checksum, PDF page/text bbox or vision transcript, warnings). This sidecar deliberately stores provenance without changing V1 schema. For PDFs, `rawText` is extracted text and SHA-256 authenticates the original binary. For images/scans without an opted-in transcriber, draft remains blocked. See [INGESTION.md](INGESTION.md).

`factory/gemini_vision.py` is one implementation of the `VisionProvider` protocol. It requires an explicit model and local API key and uses Google's Interactions API. Provider responses are untrusted: a subsequent review stage must resolve constraints, checker semantics and sample ambiguity. No Polygon publish is triggered by ingestion.

## SOL-001 — candidate vs independent oracle

`factory/solution_check.py` consumes a reviewed V1 `spec.json` and C++17 candidate and oracle sources; both may come from agent workflows, but the oracle cannot simply be the candidate itself. It checks source SHA difference, oracle agreement with expected outputs, then candidate vs oracle, preserving verdicts/hashes. This proves only tested agreement.

`factory/docker_runner.py` is the required execution backend, compiled/run without host fallback and with nonroot Docker restrictions. Docker daemon access itself remains privileged, so unknown code should be executed in a disposable VM. The model-neutral agent instructions are in `factory-solve`. End-to-end agent subagent orchestration remains AG-001, not SOL-001; proof reasoning isn't mechanically verified by the script. See [SOLUTIONS.md](SOLUTIONS.md).
