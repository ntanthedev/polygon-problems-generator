# SOL-001 — Solution candidate / oracle agreement

**Status:** implemented in stacked SOL-001 branch (mocked/offline CI). Live Docker execution and any real Polygon run are **not yet validated**.

## Goal and modes

The Factory supports three inputs from the V1 spec:

| Input mode | What the reasoning agent does | What SOL-001 verifies |
|---|---|---|
| `statement-only` | Derive an efficient candidate and an independently reasoned small-domain oracle | Compare both on reviewed samples and supplied cases |
| `statement+idea` | Challenge the proposed algorithm, implement candidate and separately derive oracle | Do not treat the idea as correctness evidence |
| `statement+solution` | Start from user-provided C++17 code as an untrusted candidate; derive a separate brute/reference oracle | Compare candidate against oracle, not itself |

**No API generates algorithms automatically yet.** The agent skill below supplies the reasoning workflow; the CLI supplies deterministic execution and diagnostics. Agent conclusions need independent review. Model families can be switched without changing file formats.

## CLI

Prerequisites: Python 3.11+, installed `requirements-factory.txt`, and Docker installed with a **locally available** `gcc:14` image. The tool **never** downloads an image or compiles directly on the host. Docker daemon access must be restricted to a trusted administrator account. Use a disposable environment for unfamiliar code.

```bash
# Just the pure Python tests (no Docker required)
python3 -m unittest discover -s tests -v

# Check Docker locally (no image pull)
docker image inspect gcc:14

# Review the spec first
python3 -m factory spec validate problems/my_problem/spec.json --ready

# Compare your candidate with an independently written oracle
python3 -m factory solutions verify problems/my_problem \
  --candidate problems/my_problem/solutions/acc.cpp \
  --oracle problems/my_problem/solutions/brute.cpp \
  --tests-dir problems/my_problem/regression \
  --report problems/my_problem/reports/solution-check.json
```

If the V1 spec has `mode=statement+solution` with a valid `guidance.solution.file`, `--candidate` may be omitted. A test directory is optional; each `*.in` may have a matching `*.out`, otherwise the oracle determines expected output. Any unpaired `*.out`, symlinked input, oversized case, unreadable source or unreviewed spec fails closed.

The `--report` flag creates a **new** file exclusively; existing reports are never overwritten. Without that flag the JSON report prints to stdout. The report includes input/source hashes, per-case verdict, and first known failure; it does not serialize solution source code or user secrets.

## Meaning of verdicts

- `PASS_ON_TESTS`: token-level candidate output equals oracle on every supplied case, and oracle matched each known expected sample/output. **This is not a proof**; even two independent implementations can share a bug.
- `FAIL`: candidate differs or exits abnormally on one or more cases. Case-specific `WA`, `TLE`, `RE`, `MLE`, `OLE`.
- `ORACLE_ERROR`: oracle crashed/timed out or disagreed with a supplied expected output, so the candidate cannot be graded reliably.
- `COMPILE_ERROR`, `ORACLE_COMPILE_ERROR`: compilation did not succeed. Exit code is nonzero.
- `BLOCKED`: spec not reviewed, outputPolicy unsupported, runner unavailable, invalid input/config etc. Execution does not proceed.

V1 only supports reviewed **non-interactive exact/token-comparison** output. A checker-specific, floating-point tolerance, constructive, or interactive problem must use a specialized runner in a future task. Blank lines/trailing whitespace are ignored by `bytes.split()`; spelling and case remain exact.

## Docker isolation policy

The `DockerRunner` uses:

- `--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`.
- Non-root UID/GID, memory/pid/CPU limits, a temporary `/tmp` and limited outputs.
- Read-only input/source/binary mounts; only isolated temporary compilation and output folders are writable.
- Explicit command arguments, no concatenated user-controlled shell fragments.
- Wall-time limits and best-effort explicit container kill on timeout.
- `--pull=never`; a missing image must be installed deliberately.

**Limitation:** Docker is not a perfect adversarial-code sandbox, and access to the host Docker daemon is privileged. There is no guarantee against kernel/container escape or denial-of-service. For unknown code, prefer a disposable VM with a restricted Docker daemon, no host secrets, and no external network. CI mocks enforce command construction and result handling, not the host's actual containment.

## Reproducible demo

A self-contained synthetic example is stored in `factory/fixtures/solution_smoke/`. Use it only after deciding to run Docker code locally:

```bash
python3 -m factory solutions verify factory/fixtures/solution_smoke \
  --oracle factory/fixtures/solution_smoke/oracle.cpp \
  --tests-dir factory/fixtures/solution_smoke/cases
```

Expected verdict: `PASS_ON_TESTS` for a small integer-addition fixture. The oracle/candidate use different code, but this synthetic demo is **not** evidence that the general mathematical problem is solved correctly. Untrusted code must remain isolated.

## Acceptance / next tasks

- CI tests: source/spec guards, stale/mismatched oracle outputs, compilation failures, WA/TLE/RE/MLE/OLE, sample and extra cases, CLI errors and Docker policy.
- **Local Docker smoke:** `SOL-LIVE-001` pending real compilation/runtime test on disposable fixture, followed by cross-platform review. Do not claim the runner is fully verified without this.
- **QA-001:** seeded exhaustive/targeted case generation, safe brute-domain contracts and reproducible counterexample shrinking.
- **AG-001:** orchestrator invocation, model routing and explicit reviewer steps.
- **API-INT-001:** Polygon remote integration remains separate and blocked on user approval.
