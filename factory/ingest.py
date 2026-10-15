"""Safe, provenance-preserving CP statement ingestion (ING-002).

Inputs: UTF-8 TXT/MD/TEX, PDF text layers, or image/PDF pages via an
explicitly enabled multimodal transcriber. Produces a V1 draft spec and
a separate extraction-evidence manifest. NEVER infers mathematical truth
or executes source code. Never calls Polygon.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .spec import ProblemSpecError, SLUG, inspect_spec

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 32
MAX_TRANSCRIPT_CHARS = 2_000_000
MAX_RENDER_BYTES = 14 * 1024 * 1024
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".webp": "image/webp"}
TEXT_KIND = {".txt": "plain-text", ".md": "markdown", ".tex": "latex"}

VISION_PROMPT = (
    "Transcribe this image/page of a competitive programming problem faithfully. "
    "Preserve all mathematical operators, subscripts, constraints, tables and "
    "sample input/output. Respond as UTF-8 plain text with clear heading lines "
    "(Title, Problem Statement, Input, Output, Constraints, Sample Input, Sample "
    "Output) where truly present. Never invent missing sections, sample outputs, "
    "numbers, bounds or an algorithm. For unreadable content write [UNCLEAR: ...]. "
    "Preserve line breaks in samples. Do not solve the problem."
)

class VisionProvider(Protocol):
    model: str
    def transcribe(self, data: bytes, mime_type: str, prompt: str) -> str: ...


@dataclass
class Extracted:
    text: str
    method: str
    segments: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    vision_calls: int = 0


def _read_limited(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ProblemSpecError("Source must be an existing regular non-symlink file")
    size = path.stat().st_size
    if size == 0 or size > MAX_SOURCE_BYTES:
        raise ProblemSpecError(f"Input must be between 1 and {MAX_SOURCE_BYTES} bytes")
    return path.read_bytes()


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ProblemSpecError("Text input must be UTF-8; convert encoding explicitly") from None


def _transcribe(provider: VisionProvider, blob: bytes, mime: str) -> str:
    if len(blob) > MAX_RENDER_BYTES:
        raise ProblemSpecError("Rendered page is too large for inline vision; reduce input size")
    try:
        answer = provider.transcribe(blob, mime, VISION_PROMPT)
    except Exception as exc:
        # Never surface exception payloads: SDK/network errors may contain secrets.
        raise ProblemSpecError(f"Vision provider failed ({type(exc).__name__})") from None
    if not isinstance(answer, str) or not answer.strip():
        raise ProblemSpecError("Vision provider returned no usable transcription")
    if len(answer) > MAX_TRANSCRIPT_CHARS:
        raise ProblemSpecError("Vision transcription exceeds safety limit")
    return answer


def extract_source(path: Path, data: bytes, provider: VisionProvider | None = None) -> Extracted:
    """Read without writing or contacting a provider except by explicit injection."""
    suffix = path.suffix.lower()
    if suffix in TEXT_KIND:
        text = _decode_text(data)
        return Extracted(text, "native-text", [
            {"page": None, "bbox": None, "method": "native-text",
             "text": text, "sourceOffset": 0}
        ])
    if suffix in IMAGE_MIME:
        if provider is None:
            return Extracted("", "not-processed", [],
                             ["Image needs an explicitly selected vision provider"])
        text = _transcribe(provider, data, IMAGE_MIME[suffix])
        return Extracted(text, "vision", [
            {"page": 1, "bbox": None, "method": "vision", "text": text}
        ], ["Model transcription is unverified; check math and samples visually"], 1)
    if suffix != ".pdf":
        raise ProblemSpecError("Unsupported input type (use .txt, .md, .tex, .pdf, .png, .jpg, .webp)")

    try:
        import pymupdf
    except ImportError:
        raise ProblemSpecError("PDF ingestion requires PyMuPDF; install requirements-factory.txt") from None
    if not data.startswith(b"%PDF-"):
        raise ProblemSpecError("Invalid PDF signature")
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise ProblemSpecError("Cannot parse PDF (possibly damaged/encrypted)") from None

    parts = []
    segments = []
    warnings = []
    calls = 0
    try:
        if document.needs_pass:
            raise ProblemSpecError("Encrypted PDF requires an unlocked local copy")
        if document.page_count == 0 or document.page_count > MAX_PAGES:
            raise ProblemSpecError(f"PDF must contain 1–{MAX_PAGES} pages per problem")
        for number, page in enumerate(document, 1):
            blocks = page.get_text("blocks", sort=True)
            page_segments = []
            for item in blocks:
                # PyMuPDF: (x0,y0,x1,y1,text,block_number,block_type)
                if len(item) >= 7 and item[6] == 0 and item[4].strip():
                    page_segments.append({
                        "page": number,
                        "bbox": [round(float(v), 2) for v in item[:4]],
                        "method": "native-text",
                        "text": item[4],
                    })
            native = "\n".join(item["text"] for item in page_segments)
            segments.extend(page_segments)
            if provider is not None:
                # Per-page rendering yields grounded page numbers for model text.
                pix = page.get_pixmap(dpi=160, alpha=False)
                if pix.width * pix.height > 12_000_000:
                    raise ProblemSpecError("PDF page rendering exceeds pixel budget")
                rendered = pix.tobytes("png")
                vision = _transcribe(provider, rendered, "image/png")
                calls += 1
                segments.append({"page": number, "bbox": None, "method": "vision",
                                 "text": vision})
                parts.append(vision)
                if native.strip():
                    warnings.append(f"Page {number}: native extraction retained in evidence; "
                                    "vision transcription selected for draft")
            else:
                parts.append(native)
                if not native.strip():
                    warnings.append(f"Page {number}: no extractable text; use --vision-model "
                                    "to transcribe this scanned page")
                if page.get_images() or page.get_drawings():
                    warnings.append(f"Page {number}: graphics detected; visual review may be required")
            if sum(len(t) for t in parts) > MAX_TRANSCRIPT_CHARS:
                raise ProblemSpecError("Extracted PDF text exceeds safety limit")
    finally:
        document.close()

    if not any(x.strip() for x in parts):
        warnings.append("No textual content extracted; draft remains blocked until vision/review")
    method = "vision" if provider else ("native-text" if any(t.strip() for t in parts) else "not-processed")
    text = "\n\n".join(f"=== PAGE {i} ===\n{page_text}" for i, page_text in enumerate(parts, 1))
    return Extracted(text, method, segments, warnings, calls)


_HEADING = re.compile(
    r"^\s{0,3}(?:(#{1,4})[ \t]+)?"
    r"((?:Title|Problem(?: Statement)?|Statement|Description|Task|Legend|"
    r"Input(?: Format| Specification)?|Output(?: Format| Specification)?|"
    r"Constraints?|Notes?|Explanation|"
    r"(?:Sample|Example)[ \t]+(?:Input|Output)(?:[ \t]*#?[0-9]+)?))"
    r"\s*:?[ \t]*$", re.I
)
_TITLE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$")
_INLINE_TITLE = re.compile(r"^Title:\s*(.+?)\s*$", re.I)
_CODE_FENCE = re.compile(r"^\s*(?:\x60{3,}|~{3,})[^\n]*\n([\s\S]*?)\n?\s*(?:\x60{3,}|~{3,})\s*$")
_SAMPLE_NAME = re.compile(r"^(Sample|Example)\s+(Input|Output)(?:\s*#?([0-9]+))?$", re.I)
_PAGE_HEADER = re.compile(r"^=== PAGE \d+ ===$")


def _strip_sample(text: str) -> str:
    text = text.strip("\r\n")
    m = _CODE_FENCE.match(text)
    if m:
        return m.group(1).strip("\r\n") + "\n"
    return text + ("\n" if text else "")


def _section_key(name: str) -> str:
    name = name.lower()
    if name.startswith(("problem", "statement", "description", "task", "legend")):
        return "legend"
    if name.startswith("input"):
        return "input"
    if name.startswith("output"):
        return "output"
    if name.startswith("constraint"):
        return "constraints"
    if name.startswith("note") or name.startswith("explanation"):
        return "notes"
    if name.startswith("title"):
        return "title"
    return "sample"


def _field_ambiguity(field: str, issue: str) -> dict:
    return {"field": field, "issue": issue, "severity": "blocking", "sourceExcerpt": None}


def normalize_draft(text: str, *, slug: str, kind: str, digest: str,
                    source_path: str, extraction: str, language: str = "und",
                    warnings: list[str] | None = None) -> dict:
    """Conservative section parsing. No semantically verified constraints/samples."""
    title = None
    sections: dict[str, list[str]] = {}
    samples: dict[str, dict[str, str]] = {}
    sample_seen: set[tuple[str, str]] = set()
    sample_duplicates: set[str] = set()
    current = "legend"
    seen_sections = set()
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if _PAGE_HEADER.match(content.strip()):
            continue
        if title is None and (m := _TITLE.match(content)):
            if m.group(1).strip().lower() != "title":
                title = m.group(1).strip()
                continue
        if title is None and (m := _INLINE_TITLE.match(content)):
            title = m.group(1).strip()
            continue
        if m := _HEADING.match(content):
            section = m.group(2).strip()
            sm = _SAMPLE_NAME.match(section)
            if sm:
                index = sm.group(3) or "1"
                direction = sm.group(2).lower()
                if (index, direction) in sample_seen:
                    sample_duplicates.add(index)
                sample_seen.add((index, direction))
                current = f"sample:{index}:{direction}"
            else:
                current = _section_key(section)
                seen_sections.add(current)
            continue
        if current.startswith("sample:"):
            _, index, direction = current.split(":")
            samples.setdefault(index, {}).setdefault(direction, "")
            samples[index][direction] += line
        else:
            sections.setdefault(current, []).append(line)

    def field(key: str) -> str | None:
        contents = "".join(sections.get(key, [])).strip()
        return contents or None

    ambiguities = []
    pairs = []
    for idx in sorted(samples, key=lambda s: int(s)):
        candidate = samples[idx]
        if idx in sample_duplicates:
            ambiguities.append(_field_ambiguity(
                f"statement.samples[{idx}]",
                "Repeated sample headings share an index; manual pairing required"
            ))
            continue
        if "input" in candidate and "output" in candidate:
            pairs.append({
                "input": _strip_sample(candidate["input"]),
                "output": _strip_sample(candidate["output"]),
                "explanation": None,
            })
        else:
            ambiguities.append(_field_ambiguity(
                f"statement.samples[{idx}]",
                f"Sample {idx} is missing {'input' if 'input' not in candidate else 'output'}"
            ))
    constraints = []
    source_constraints = field("constraints")
    if source_constraints:
        for item in source_constraints.splitlines():
            value = re.sub(r"^\s*[-*]\s+", "", item).strip()
            if value:
                is_sum = bool(re.search(r"(?:\bsum\b|∑|\\sum|over all test cases)", value, re.I))
                constraints.append({"expression": value,
                                    "scope": "sum-over-cases" if is_sum else "global",
                                    "sourceExcerpt": item})
        ambiguities.append(_field_ambiguity(
            "statement.constraints", "Constraint scopes and mathematical symbols need review"
        ))
    else:
        ambiguities.append(_field_ambiguity(
            "statement.constraints", "No explicit Constraints section found or extracted"
        ))
    for label in ("title", "legend", "input", "output"):
        if not (title if label == "title" else field(label)):
            ambiguities.append(_field_ambiguity(
                "statement." + label, "Missing or unrecognized " + label + " section"
            ))
    if not pairs:
        ambiguities.append(_field_ambiguity(
            "statement.samples", "No complete sample input/output pair was extracted"
        ))
    ambiguities.append(_field_ambiguity(
        "statement.testCaseMode", "Single vs multiple testcases not independently reviewed"
    ))
    ambiguities.append(_field_ambiguity(
        "statement.outputPolicy", "Exact vs checker/floating answer policy not verified"
    ))
    for warn in warnings or []:
        ambiguities.append(_field_ambiguity("source.extraction", warn))
    for match in re.finditer(r"\[UNCLEAR:[^\]]*\]", text):
        ambiguities.append(_field_ambiguity("source.transcription",
                                           "Unreadable transcription: " + match.group(0)))
    if "interactive" in text.lower():
        ambiguities.append(_field_ambiguity(
            "statement.interactive", "Interactive terminology detected; must be reviewed"
        ))
    spec = {
        "schemaVersion": 1, "slug": slug, "mode": "statement-only",
        "source": {"kind": kind, "path": source_path, "sha256": digest,
                   "rawText": text, "extraction": extraction,
                   "reviewStatus": "pending", "attribution": None},
        "statement": {
            "title": title, "language": language, "legend": field("legend"),
            "input": field("input"), "output": field("output"), "notes": field("notes"),
            "interactive": False, "testCaseMode": "unknown", "outputPolicy": "unknown",
            "timeLimitMs": None, "memoryLimitMb": None,
            "constraints": constraints, "samples": pairs,
        }, "guidance": {}, "ambiguities": ambiguities,
    }
    result = inspect_spec(spec)
    if result["status"] != "PASS":
        raise ProblemSpecError(f"Importer constructed invalid V1 draft: {result['errors']}")
    return spec


def _guidance(spec: dict, *, idea: str | None, solution_name: str | None,
              solution_language: str) -> None:
    if idea is not None:
        if not idea.strip():
            raise ProblemSpecError("User idea cannot be blank")
        spec["guidance"]["idea"] = {"text": idea, "providedBy": "user"}
    if solution_name is not None:
        if solution_language not in {"cpp17", "java21", "python3", "other"}:
            raise ProblemSpecError("Unknown solution language")
        spec["guidance"]["solution"] = {
            "language": solution_language, "providedBy": "user",
            "file": solution_name
        }
        spec["mode"] = "statement+solution"
    elif idea is not None:
        spec["mode"] = "statement+idea"


def ingest_file(path: Path, *, slug: str, dest: Path,
                provider: VisionProvider | None = None, language: str = "und",
                idea: str | None = None, solution_file: Path | None = None,
                solution_language: str = "cpp17") -> dict:
    """Create a new, isolated problem draft directory; refuse existing target.

    On extraction/validation failures, removes only the directory created by
    this invocation. Never modifies source or any existing destination.
    """
    if not SLUG.fullmatch(slug):
        raise ProblemSpecError("Slug must use lowercase letters/underscores, starting with a letter")
    path = Path(path)
    dest = Path(dest)
    if dest.exists() or dest.is_symlink():
        raise ProblemSpecError(f"Destination already exists: {dest}")
    raw = _read_limited(path)
    if path.suffix.lower() not in set(TEXT_KIND) | set(IMAGE_MIME) | {".pdf"}:
        raise ProblemSpecError("Unsupported source suffix")
    if solution_file is not None:
        code = _read_limited(Path(solution_file))
        if len(code) > 2_000_000:
            raise ProblemSpecError("User solution file is too large")
        ext = Path(solution_file).suffix.lower()
        if ext not in {".cpp", ".java", ".py", ".txt"}:
            raise ProblemSpecError("User solution must be a source-code text file")
    else:
        code = None
        ext = ""
    extracted = extract_source(path, raw, provider)
    digest = hashlib.sha256(raw).hexdigest()
    suffix = path.suffix.lower()
    kind = TEXT_KIND.get(suffix, "pdf" if suffix == ".pdf" else "image")
    rel = "source/original" + suffix
    solution_rel = "solutions/user" + ext if code is not None else None
    spec = normalize_draft(extracted.text, slug=slug, kind=kind, digest=digest,
                           source_path=rel, extraction=extracted.method,
                           language=language, warnings=extracted.warnings)
    _guidance(spec, idea=idea, solution_name=solution_rel,
              solution_language=solution_language)
    checked = inspect_spec(spec)
    if checked["status"] != "PASS":
        raise ProblemSpecError(f"Guidance invalid: {checked['errors']}")
    evidence = {
        "evidenceVersion": 1, "source": rel, "sourceSha256": digest,
        "extractor": extracted.method,
        "visionProvider": type(provider).__name__ if provider else None,
        "visionModel": getattr(provider, "model", None) if provider else None,
        "visionCalls": extracted.vision_calls,
        "segments": extracted.segments,
        "warnings": extracted.warnings,
        "note": "Evidence locators indicate extraction positions, not proof of correct OCR"
    }
    dest.mkdir(parents=True, exist_ok=False)
    try:
        (dest / "source").mkdir()
        (dest / rel).write_bytes(raw)
        if code is not None:
            (dest / "solutions").mkdir()
            (dest / solution_rel).write_bytes(code)
        (dest / "spec.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (dest / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        shutil.rmtree(dest)
        raise
    return {"destination": str(dest), "sourceSha256": digest,
            "extraction": extracted.method, "visionCalls": extracted.vision_calls,
            "issues": len(spec["ambiguities"]), "ready": False}
