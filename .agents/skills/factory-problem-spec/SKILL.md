---
name: factory-problem-spec
description: Normalize CP problem statements into V1 structured JSON while preserving uncertainty, with optional user idea or source solution.
---

# Factory V1 problem spec

Read `FACTORY_START_HERE.md`, `docs/factory/PROBLEM_SPEC_V1.md` and `docs/factory/AGENT_RULES.md`.

Follow `factory/schemas/problem-spec.v1.schema.json`. Preserve the original in `source.rawText`, provenance and all samples. Never invent constraints, sum constraints, index bases, testcase count, output policy or sample outputs: use unknown/null and blocking ambiguities. A supplied solution is an untrusted candidate, not an oracle.

Check with `python3 -m factory spec validate <path>`, and after explicit source review use `--ready`. Schema PASS does not imply correctness or permission to publish. Do not invoke Polygon from this skill.
