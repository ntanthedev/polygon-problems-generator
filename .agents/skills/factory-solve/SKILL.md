---
name: factory-solve
description: Analyze a reviewed CP problem, optionally use a user idea or source solution, generate independently reasoned oracle and candidate, and test them safely through Factory.
---

# Factory solve / independent review workflow

Read `docs/factory/SOLUTIONS.md`, `docs/factory/PROBLEM_SPEC_V1.md`, `docs/factory/AGENT_RULES.md`, and `docs/factory/HANDOFF.md`. Inspect the **current** `spec.json`; never use guesses to clear a pending review or missing constraints. Do not upload to Polygon.

## Modes

- **Statement only:** use a strong reasoning model to derive a performant C++17 candidate with proof sketch, constraints analysis and a logically independent brute/reference solver. Explicitly challenge proof and edge cases.
- **Statement + user idea:** treat idea as a hypothesis, question its invariants/complexity, independently derive oracle, then implement candidate. A weaker coding model can be used only when the idea is concrete enough to implement; do not infer unprovided facts.
- **Statement + user solution:** preserve source unchanged; use it as candidate. Independently design an oracle without copying its implementation. Run review and compare, including against original samples.

## Mandatory safety gates

1. Run `python3 -m factory spec validate problems/SLUG/spec.json --ready`. A draft with blocking ambiguities needs review before execution.
2. Reject multiple-valid-output/checker, floating-point tolerance, constructive/interactive cases until specialized checker support exists. Current token comparator is valid **only** for reviewed exact-output.
3. Put separately designed C++17 candidate and oracle in named files. Use **small inputs** for brute-force oracle; no assertion of algorithm correctness from a passing test.
4. Run `python3 -m factory solutions verify problems/SLUG --candidate ... --oracle ... --tests-dir ...` with Docker in an appropriate disposable VM. Never run untrusted C++ code on the host; no Docker means stop, not fall back.
5. If the oracle fails a known sample, stop and investigate the oracle/statement before grading candidate. If candidate fails, report the seed/input case and expected-vs-actual evidence. Preserve regression inputs.
6. Save structured report, exact source hashes, which cases executed, verdict. Report `PASS_ON_TESTS`, not “proven correct.” The reporter always sets `oracleIsProvenCorrect=false`.
7. Keep all remote Polygon writes explicitly gated. No automatic secret transmission. Update `TASKS.md` + `HANDOFF.md` with commands actually executed.

For hard algorithmic questions, request stronger model review instead of asserting a weak model found a valid proof. Agent role separation is a workflow convention; it does not guarantee independent reasoning unless separately verified.
