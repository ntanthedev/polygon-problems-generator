# Project charter

## Goal

Build a reliable, agent-driven pipeline: **existing problem (PDF/images/text) or brief idea + optional solution → structured statement → validator/checker/solutions/generator/tests → local verification → optional Polygon sync and verified package**. Contest creation is explicitly out of scope.

## Input modes

| Mode | Provided | Agent responsibility |
|---|---|---|
| `statement-only` | Existing statement, limits, sample I/O | Derive algorithm + independent oracle |
| `statement+idea` | Above + algorithmic idea | Validate the idea; generate robust implementation and oracle |
| `statement+solution` | Above + user's source code | Treat solution as an untrusted candidate until tested; derive independent checks |
| `new-idea` | A problem idea and intended algorithm | Reuse upstream invention pipeline; originality screening may apply |

A weak/cheap model (e.g. Flash or Luna) must be able to execute constrained implementation tasks when the user supplies an algorithm or solution. A stronger model is preferred for ambiguous statements, proofs, and independent review, but no component assumes a particular model name or provider.

## V1 scope

Non-interactive, deterministic-output competitive programming problems in C++17 with testlib validators, generators, and Polygon-compatible statements. Additional languages and interactive/constructive/output-only problems are later extensions with separate contracts.

## Non-goals / boundaries

- No CHTOJ/VNOJ integration or automatic contest creation.
- No assertion that random testing proves correctness.
- No automatic overwrite of existing remote Polygon content without an explicit publish mode/permission.
- No sending private PDFs or problem text to third-party originality/search services by default.
- Respect provenance and redistribution rights for imported statements.

## Definition of done

A task is DONE only when its acceptance checks are executed and recorded. A problem is PUBLISH-VERIFIED only when Polygon reports a completed verified package on the intended revision and warnings/errors are examined; a successful HTTP API response is insufficient.
