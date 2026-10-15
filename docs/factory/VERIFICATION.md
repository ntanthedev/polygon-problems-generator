# Verification strategy

## Mandatory result vocabulary

`PASS`: actual executed check passed. `FAIL`: check executed and failed. `NOT_RUN`: check not executed. `BLOCKED`: cannot execute (state why). Distinguish local from remote verification.

## Layers

| Layer | Checks | Evidence |
|---|---|---|
| Structural preflight (M0) | statement sections, required source files, samples, duplicate samples, metadata syntax | CLI JSON/text report and exit code |
| Upstream local smoke | `./verify.sh problems/<name>` | compiled components, sample agreement, small stress |
| Reference correctness (M3) | independent brute on small exhaustive/random; checker-aware comparison | seed, source SHA, minimized counterexample |
| Test quality (M4) | targeted adversarial profiles, mutation score and survivors, max performance | per-mutant verdict and testcase mapping |
| Polygon official (M1) | commit, verified build, final package state, warnings, revision consistency | remote result, package ID and status |

## Non-negotiable pitfalls

- Sample output may differ textually while being checker-equivalent.
- Brute runtime limits must be separate from optimized solution limits.
- Generator duplicates are not always caught by static extraction of FreeMarker fragments.
- Wrong-answer code should have an actual demonstrable counterexample; adding a flawed solver alone is not evidence.
- Network errors after a write leave remote state uncertain until reconciled.
- `problem.buildPackage` returning OK is NOT a finished successful package.

## Local M0 test commands

~~~bash
python3 -m unittest discover -s tests -v
python3 -m polyup preflight problems/<name> --json
~~~

These checks do not compile solution code. Avoid reporting the problem as correct when only preflight passed.

## API-002 — package lifecycle, mocked (2026-10-15)

The `build_and_wait` integration captures the current revision from `problems.list`, the `problem.packages` snapshot before the build, and only accepts *new* packages matching the revision. The documented states are `PENDING`, `RUNNING`, `READY`, `FAILED`. For a full build, it checks standard/linux/windows. `READY` is only labeled invocation-verified if the upload requested `verify=true`. Tests use a fake API; **real Polygon behavior is NOT_RUN**. CI: [run 38766107192](https://github.com/ntanthedev/polygon-problems-generator/actions/runs/38766107192).

Remaining caution: concurrent builds that become indistinguishable by Polygon package metadata cannot be unambiguously attributed without stronger server correlation. The poller fails closed on duplicate new IDs per type but cannot independently establish authorship of a single new same-revision build. Restrict concurrent operations during an authorized integration test.
