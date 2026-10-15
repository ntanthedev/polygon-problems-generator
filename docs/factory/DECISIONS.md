# Decision log (ADR-lite)

## 2026-10-15 — D001: Fork, do not rewrite
**Decision:** Extend the user's fork of `7oSkaaa/polygon-problems-generator`, preserving upstream format and Polygon importer until a replacement is tested. **Reason:** Keeps existing testlib/agent and Polygon mapping work.

## 2026-10-15 — D002: Assistant-owned GitHub PRs, user-run local tests
**Decision:** Prefer a reviewable feature branch/PR from ChatGPT; user pulls and performs real toolchain or Polygon tests. **Reason:** saves local model quota and avoids claiming inaccessible private environment success. Main branch remains untouched pending merge.

## 2026-10-15 — D003: Optional idea or source solution
**Decision:** Accept full problem alone, full problem plus idea, or full problem plus solution. A supplied solution is not automatically authoritative. **Reason:** allows Flash/Luna to implement narrow work and Pro-level models to focus on uncertain reasoning.

## 2026-10-15 — D004: Skills + deterministic tools first
**Decision:** Keep model-neutral Markdown contracts and local CLI; use custom subagents as orchestration, not as test verdicts. MCP and UI are deferred until needed. **Reason:** simpler to test and usable in Codex/Antigravity.

## 2026-10-15 — D005: Explicit remote publish boundary
**Decision:** Local analysis/preflight/verification may run automatically; creating/updating Polygon requires explicit target and approval. **Reason:** remote writes are durable; ambiguous statements must not become quietly published tasks.

## 2026-10-15 — D006: Traceable evidence and no false assurance
**Decision:** Track command output, source revision, seeds, exact errors and package state. **Reason:** model consensus/random tests do not prove correctness.

Changes to any decision must add an entry with date, rationale, consequences and impacted tasks.
