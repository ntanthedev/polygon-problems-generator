# Agent operating rules — mandatory

Read `FACTORY_START_HERE.md`, `TASKS.md`, `HANDOFF.md` and relevant upstream source before edits.

1. **Use a task ID.** Work on one scoped task. Propose file-level changes, acceptance criteria and dependency risks. Avoid unrelated refactors.
2. **Evidence first.** Never state that tests, Polygon API calls or builds passed unless you actually saw the result. Distinguish `NOT_RUN`, `PASS`, `FAIL`, `BLOCKED`.
3. **Never assume an imported statement is correct.** Preserve original, do not silently add constraints, change math symbols or manufacture samples. Flag ambiguity with exact source references.
4. **Solutions from the user are hypotheses.** Verify against small exhaustive tests/independent brute or checker. Distinguish oracle failure from candidate failure.
5. **No credential exposure.** Do not echo `POLYGON_API_SECRET`, upload .env, write passwords to logs or send private statements to novelty APIs by default.
6. **Sandbox untrusted code.** Validator, checker, generator and solutions may execute arbitrary code. Enforce CPU/memory/time limits and default network denial before remote automation.
7. **Remote writes are explicit.** No Polygon create, delete, overwrite, grant-access or package publish without permission and target scope. `preflight` is read-only.
8. **Retries must be idempotent.** Read operations can be retried with limits; ambiguous failed writes require reconciliation before reattempt.
9. **Regression preservation.** A bug fix should add a minimized counterexample, preserve prior passing tests and rerun impacted verification.
10. **Honest delivery.** Do not claim the entire end-to-end pipeline is ready. Record implementation vs proposal. Update `TASKS.md` + `HANDOFF.md` before ending.
11. **Agent budget.** Route difficult algorithm proofs and ambiguity to a strong reasoning model; offer implementation-only, idea-assisted, solution-assisted tasks to less capable models.
12. **Do not edit generated `AGENTS.md` alone.** Upstream script `sync-ai-configs.py` generates it from `.claude/shared.md`; align changes with source of truth.

Format completion as: task ID; summary; changed files; commands actually run; observed results; known gaps; next ready task.
