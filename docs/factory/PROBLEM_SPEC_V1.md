# Normalized Problem Specification v1 (ING-001)

This is a **model-independent contract**: a strong model can solve independently, while a smaller model can implement using a supplied idea or solution. Schema validity does not imply that mathematics, algorithms, or test cases are correct.

## Artifacts

- [Strict JSON Schema](../../factory/schemas/problem-spec.v1.schema.json) — Draft 2020-12; schemaVersion = 1.
- [Fixture corpus](../../factory/fixtures/) — valid and invalid cases for each supported input mode.
- [Spec validator and adapter](../../factory/spec.py) and [CLI](../../factory/__main__.py).
- [Offline unit tests](../../tests/test_problem_spec.py).

## Input modes

| `mode` | Required guidance | Behavior |
|---|---|---|
| `statement-only` | None | Solve from statement independently |
| `statement+idea` | `guidance.idea` | Check user idea and implement |
| `statement+solution` | `guidance.solution` | Verify untrusted user code independently |
| `new-idea` | `guidance.idea` | Author an original task from concept |

`statement+solution` may include an additional optional `guidance.idea`. A solution has language, providedBy, and **exactly one** of `file` (safe project-relative) or `code` (inline). User solutions are candidates, not proven oracles.

## Provenance and non-hallucination

- `source.kind`: polygon-tex, plain-text, markdown, latex, image, pdf, docx, idea.
- `source.path`, `sha256`, `rawText`, `extraction`, `reviewStatus` and `attribution` preserve evidence. When a local .tex file is imported, rawText is UTF-8 decoded without altering original CRLF; SHA-256 hashes original bytes.
- `statement.testCaseMode`: single/multiple/unknown. No implicit multi-test default.
- `statement.outputPolicy`: exact/checker/floating-point/interactive/unknown. For multiple valid outputs, a semantic checker will be needed; do not run bytewise `diff`.
- `statement.constraints[]`: literal expression + scope per-case/per-file/sum-over-cases/global + sourceExcerpt (nullable). `n <= 200000` is not the same as `sum(n) <= 200000`.
- `statement.timeLimitMs` and `memoryLimitMb` can be null if not provided. Do not invent limits.
- `statement.samples[]` contains literal input/output texts; preserve whitespace and newline form. If a sample output is missing, add a blocking ambiguity, not a fabricated value.
- `ambiguities[]` tracks `field`, `issue`, `severity` blocking/advisory, and `sourceExcerpt`. An agent may set a source to `reviewStatus=verified` only after an actual review step.

## Two validation levels

**Draft structural validation** accepts unknown or incomplete sections so the OCR/text extraction workflow can progress.

~~~bash
python3 -m factory spec validate problems/<name>/spec.json --json
~~~

**Ready validation** additionally requires: reviewed source; non-empty title/legend/input/output; at least one reviewed constraint and sample; testcase and output semantics known; no blocking ambiguity; non-interactive V1.

~~~bash
python3 -m factory spec validate problems/<name>/spec.json --ready
~~~

Neither level runs solutions, proves correctness or uploads to Polygon. The flag `--ready` means ready for the **next test-generation/solution-agent stage**, not Polygon publication.

## Converting existing local Polygon problem

Install dependencies:

~~~bash
python3 -m pip install -r requirements-factory.txt
python3 -m unittest discover -s tests -v
~~~

Examples (read-only default):

~~~bash
python3 -m factory spec from-local problems/<name>
python3 -m factory spec from-local problems/<name> --idea-file hints/idea.txt --output problems/<name>/spec.json
python3 -m factory spec from-local problems/<name> --solution-file solutions/acc.cpp --output problems/<name>/spec.json
~~~

`--output` creates a file exclusively and refuses to overwrite an existing spec. The adapter requires only a statement.tex file and optionally samples; no Polygon credentials. Constraints, testcase count and answer policy are **not guessed** from source. Every converted spec starts as a draft with explicit unknowns and pending review. Fill it from evidence manually or with a reviewing agent; then validate with `--ready`.

## Next step

ING-002 will add text/Markdown/PDF/image ingestion into this same schema. Prioritize source evidence and faithful transcription, with page/region OCR provenance and ambiguity reporting. SOL-001 will use optional ideas/solutions without assuming their correctness.
