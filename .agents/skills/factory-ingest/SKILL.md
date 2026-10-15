---
name: factory-ingest
description: Import competitive programming statements from TXT/Markdown/PDF/images into evidence-backed V1 drafts, with optionally user-provided algorithms or source code.
---

# Factory ingestion

Read `docs/factory/INGESTION.md`, `docs/factory/PROBLEM_SPEC_V1.md`, and `docs/factory/AGENT_RULES.md`.

1. Prefer offline `python3 -m factory ingest SOURCE --slug SLUG --dest problems/SLUG`. Do not invoke `polyup --apply`.
2. Inspect `spec.json` plus `evidence.json`. Identify unknown or ambiguous constraints, testcase mode, checker/output semantics, OCR math, and missing samples; **never fill them from guesses**.
3. For images or PDF scans, `--vision-model MODEL_ID` transmits source pages to an external provider. Only use it when the user has explicitly consented to that disclosure and provided local credentials.
4. Any `guidance.idea` or `guidance.solution` supplied by the user is untrusted until independent verification.
5. Use `python3 -m factory spec validate problems/SLUG/spec.json`. Mark ready only after real review. Never claim schema PASS means a solution or Polygon package is correct.
