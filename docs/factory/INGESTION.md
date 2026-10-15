# ING-002 — Source ingestion (TXT, Markdown, PDF and images)

This is an **offline-first draft importer**. It never contacts Polygon or executes code. It copies the original file unchanged, records its SHA-256, and creates a V1 `spec.json` plus `evidence.json`.

## Install and run

```bash
python3 -m pip install -r requirements-factory.txt

# Native text or Markdown: no keys and no network
python3 -m factory ingest ./inputs/task.md --slug task_one --dest problems/task_one

# PDF with selectable text: native extraction + page/bbox evidence, no cloud call
python3 -m factory ingest ./inputs/task.pdf --slug task_two --dest problems/task_two

# Optional user algorithm / reference source; only copied, NEVER executed
python3 -m factory ingest ./inputs/task.txt --slug task_three --dest problems/task_three \
  --idea "Use prefix sums" --solution-file ./my_solution.cpp

# Inspect the draft and review required fields
python3 -m factory spec validate problems/task_two/spec.json --json
python3 -m factory spec validate problems/task_two/spec.json --ready
```

**The last `--ready` check is expected to fail initially.** Information from external documents is not silently trusted or declared reviewed. Source, constraint scope, test count, answer checker policy, mathematical glyphs and example I/O require confirmation. This is **not** an algorithm-correctness check.

## Explicit, opt-in Gemini transcription

Install only if you want to send pages to Google's Gemini API:

```bash
python3 -m pip install -r requirements-vision.txt
export GEMINI_API_KEY='YOUR_KEY_IN_YOUR_LOCAL_SHELL'
python3 -m factory ingest ./inputs/scan.pdf --slug task_scan \
  --dest problems/task_scan --vision-model YOUR_AVAILABLE_GEMINI_MODEL_ID
```

The shell variable is local and **must never be committed**. Choose an actual multimodal model available to your API account; the tool deliberately does not pin Pro/Flash versions. No Gemini call occurs without `--vision-model`. All text/PDF/image imports create a pending-review draft; model transcription is not accepted automatically. No real Gemini calls were made by repository CI; API functionality was checked with mocks.

PDF `--vision-model` renders **every page** to PNG at 160 dpi and sends each page separately. This preserves page numbering in `evidence.json` but may incur substantial API cost. For PDF native-text extraction without vision, evidence includes text blocks and `bbox: [x0,y0,x1,y1]` in PDF points. Pages with empty text or graphics are flagged for manual inspection. An image without vision creates a blocked draft rather than manufacturing a statement.

## Output directory (new path only)

```text
problems/task_one/
  source/
    original.md
  spec.json         # V1 contract, pending review, explicit ambiguities
  evidence.json     # source hash, extractor, PDF page boxes or vision transcripts
  solutions/user.cpp # only when --solution-file supplied
```

The importer refuses to overwrite an existing destination and does not modify input files. File extension and size caps apply; a single task's PDF is limited to 32 pages and 20 MiB, with page rendering/transcription limits. Split large workbooks into separate problem files.

## Extraction guarantees and limitations

- Markdown/text: UTF-8 bytes are preserved in `source/original`; `source.rawText` retains the original decoded string (including CRLF).
- PDF: the original PDF binary is preserved; `source.rawText` contains **extracted text**, not the literal binary PDF. The evidence includes source hash and page locations.
- Images/PDF scans: model text is a **transcription proposal**, not authoritative source. Formulas, diagrams, tables, subscripts and sample whitespace need review.
- Conservative section recognizer supports titles, Input, Output, Constraints, Notes, and numbered Sample Input/Output headings in common Markdown/plain-text forms. It does not cover every contest PDF layout or infer hidden constraints. Missing/unpaired samples are blocking ambiguities.
- `constraints[].scope` is provisional for plain listed constraints; anything potentially cumulative (e.g. sum over tests) requires review. `testCaseMode` and `outputPolicy` are always `unknown` until reviewed.
- Vision calls can incur charges and transmit private statement pages to the provider. Verify redistribution permissions/source privacy first.
- The tool does **not** generate solutions/tests, mark `--ready` automatically, create Polygon problems, or auto-publish.

## References

- [PyMuPDF extraction blocks and coordinates](https://pymupdf.readthedocs.io/en/latest/app1.html)
- [Google Gemini image understanding](https://ai.google.dev/gemini-api/docs/image-understanding) and [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview.md)

## Next engineering task

SOL-001 should consume `spec.json`, optional `guidance.idea` and `guidance.solution`, then produce independent correctness evidence. Separately, run one explicitly approved, non-sensitive image/PDF through the Gemini adapter to verify real API compatibility (ING-LIVE-001); do not assert this from mock tests.
