# Paste-ready prompts

The agent must always inspect current files and not assume these docs represent executable functionality.

## A. New Codex / Antigravity session — general
> You are implementing `ntanthedev/polygon-problems-generator` Factory. Read `FACTORY_START_HERE.md`, `docs/factory/TASKS.md`, `docs/factory/HANDOFF.md`, `docs/factory/AGENT_RULES.md`, and `.claude/shared.md`. Inspect live source. Work on one ready task (default current task from TASKS). State a short plan, implement only its scope, run the acceptance tests, report observed outcomes, then update TASKS and HANDOFF. Do not create or update Polygon remotely. Never leak credentials. Do not claim tests were run if they were not.

## B. Weaker coding model (Luna / Flash) — API-001 only
> Task API-001 only. Read the handoff and `polyup/api.py`, `polyup/sync.py`, `polyup/__main__.py`. Your assignment: add explicit HTTP connect/read timeouts; catch requests transport/HTTP/non-JSON failures; return or raise structured errors that callers handle; add isolated unittest with mocks. Preserve multipart signing and current `fatal=False` behavior or document and update all affected callers. Do not retry mutating Polygon calls automatically. No work on statement parsing, generators, model orchestration or PDF input. Run `python3 -m unittest discover -s tests -v`; update task/handoff with exact evidence. Do not publish.

## C. Strong model (Gemini Pro / high reasoning) — ingestion design
> Task ING-001 design first, no remote writes. Read Factory charter, architecture, task board and the upstream statement parser. Design a versioned normalized problem schema supporting input from PDF/images/text and optional idea or trusted-looking user code (code is not an oracle). Enumerate mathematical ambiguities, sum constraints, multiple answer semantics, multisets, floating point, samples and provenance. Add JSON-schema plus at least four valid and four invalid fixtures, and a parser adapter preserving source text. Implement only after reviewing edge cases; keep existing Polygon format compatible.

## D. Review a coding-agent PR
> Review only changed files against AGENT_RULES and acceptance criteria in TASKS. Identify reproducible bugs, missing tests, untrusted execution, Polygon API risks and false-success conditions. Classify P0/P1/P2. Report evidence (file/line/command), and give an executable minimal fix plan. Do not change the PR or call Polygon unless explicitly tasked.

## E. Restart with ChatGPT in another conversation
> Continue my AI Polygon Problem Factory fork at `ntanthedev/polygon-problems-generator`. Use the GitHub connector to read `FACTORY_START_HERE.md`, `docs/factory/HANDOFF.md`, `docs/factory/TASKS.md`, `docs/factory/DECISIONS.md`, and relevant source from the **current working branch/PR**, not outdated memory. You are the technical project coordinator; prefer opening small reviewable PRs directly on GitHub. Verify current status, identify the next task, implement/test what is feasible, and give only essential local commands for any remaining real-world verification. Do not ask me to re-explain earlier decisions.

## F. ING-002, any coding model (only after ING-001 review)

> Task ING-002 only. Inspect `factory/spec.py`, `factory/schemas/problem-spec.v1.schema.json`, `docs/factory/PROBLEM_SPEC_V1.md`, `TASKS.md` and `HANDOFF.md`. First implement deterministic UTF-8 text/Markdown → V1 draft with golden fixtures, exact source preservation and explicit ambiguous constraints, then separately add PDF text-layer/page extraction and image/scan input using a configurable multimodal adapter. Never fabricate samples, case count or constraints. Do not execute untrusted solutions or call Polygon. Run complete CI and update handoff with exact outcomes. Build each medium as a distinct task/PR if necessary.

## G. SOL-001 — reference/oracle correctness workflow (next)

> Work **only** on task SOL-001 using the current branch and PR status. Read `FACTORY_START_HERE.md`, `docs/factory/PROBLEM_SPEC_V1.md`, `docs/factory/INGESTION.md`, `docs/factory/TASKS.md`, `docs/factory/HANDOFF.md`, and `docs/factory/AGENT_RULES.md`. Build a safe offline interface that accepts reviewed V1 specs and **optional** user idea or user source solution; never treat supplied code as a trusted oracle. Define independent brute-force/reference verification, sample and constraints checks, explicit failure classifications, resource-bounded untrusted code execution, reproducible seeds and counterexamples. Start with a narrow deterministic feature and mocked golden fixtures; do not use live Polygon or Gemini credentials and do not auto-publish. Update task board and handoff with exact observed test results and open a separate stacked PR.
