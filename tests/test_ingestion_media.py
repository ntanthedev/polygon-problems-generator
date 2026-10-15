"""ING-002 image/PDF extraction and mock Gemini tests. No network."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pymupdf

from factory.ingest import ingest_file
from factory.gemini_vision import GeminiVision
from factory.spec import ProblemSpecError


class DummyVision:
    model = "mock-model"
    def __init__(self, text="Input\nx\nOutput\ny\n"):
        self.calls = []
        self.text = text

    def transcribe(self, data, mime_type, prompt):
        self.calls.append((data, mime_type, prompt))
        return self.text


class MultimediaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dest = self.root / "task"

    def ingest(self, path, provider=None):
        return ingest_file(path, slug="task", dest=self.dest, provider=provider)

    def evidence(self):
        return json.loads((self.dest / "evidence.json").read_text())

    def spec(self):
        return json.loads((self.dest / "spec.json").read_text())

    def test_image_offline_generates_blocked_draft(self):
        file = self.root / "image.png"
        file.write_bytes(b"\x89PNG\r\n\x1a\nstub")
        result = self.ingest(file)
        self.assertEqual(result["extraction"], "not-processed")
        self.assertEqual(result["visionCalls"], 0)
        self.assertEqual(self.spec()["source"]["rawText"], "")
        self.assertTrue(self.evidence()["warnings"])

    def test_explicit_image_vision_has_page_evidence(self):
        file = self.root / "image.png"
        content = b"\x89PNG\r\n\x1a\nstub"
        file.write_bytes(content)
        model = DummyVision()
        result = self.ingest(file, model)
        self.assertEqual(result["visionCalls"], 1)
        self.assertEqual(model.calls[0][0], content)
        self.assertEqual(model.calls[0][1], "image/png")
        self.assertEqual(self.evidence()["segments"][0]["page"], 1)
        self.assertEqual(self.spec()["source"]["reviewStatus"], "pending")

    def test_invalid_vision_output_does_not_create_destination(self):
        file = self.root / "picture.jpg"
        file.write_bytes(b"\xff\xd8stub")
        with self.assertRaises(ProblemSpecError):
            self.ingest(file, DummyVision(""))
        self.assertFalse(self.dest.exists())

    def test_native_pdf_page_bbox(self):
        file = self.root / "text.pdf"
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((50, 50), "Input")
        page.insert_text((50, 70), "Two integers.")
        page.insert_text((50, 100), "Output")
        page.insert_text((50, 120), "Sum.")
        file.write_bytes(pdf.tobytes())
        pdf.close()
        result = self.ingest(file)
        self.assertEqual(result["extraction"], "native-text")
        self.assertEqual(self.evidence()["visionCalls"], 0)
        self.assertTrue(any(s["bbox"] for s in self.evidence()["segments"]))
        self.assertEqual(self.spec()["source"]["kind"], "pdf")

    def test_scanned_pdf_no_model_requires_review(self):
        file = self.root / "scan.pdf"
        pdf = pymupdf.open()
        pdf.new_page().draw_rect(pymupdf.Rect(20,20,60,60))
        file.write_bytes(pdf.tobytes())
        pdf.close()
        result = self.ingest(file)
        self.assertEqual(result["extraction"], "not-processed")
        self.assertIn("no extractable text", self.evidence()["warnings"][0])

    def test_scanned_pdf_vision_transcribes_each_page(self):
        file = self.root / "scan.pdf"
        pdf = pymupdf.open()
        pdf.new_page()
        pdf.new_page()
        file.write_bytes(pdf.tobytes())
        pdf.close()
        vision = DummyVision()
        result = self.ingest(file, vision)
        self.assertEqual(result["visionCalls"], 2)
        self.assertEqual(len(vision.calls), 2)
        self.assertEqual([p["page"] for p in self.evidence()["segments"]], [1,2])
        self.assertIn("=== PAGE 2 ===", self.spec()["source"]["rawText"])

    def test_malformed_pdf_cannot_create_partial_target(self):
        file = self.root / "bad.pdf"
        file.write_bytes(b"%PDF-BROKEN")
        with self.assertRaises(ProblemSpecError):
            self.ingest(file)
        self.assertFalse(self.dest.exists())

    def test_gemini_mock_interactions_payload(self):
        client = SimpleNamespace(interactions=SimpleNamespace(
            create=mock.Mock(return_value=SimpleNamespace(output_text="Input\n1"))
        ))
        model = GeminiVision("explicit-model", client=client)
        self.assertEqual(model.transcribe(b"\x89PNG", "image/png", "Transcribe."), "Input\n1")
        payload = client.interactions.create.call_args.kwargs
        self.assertEqual(payload["model"], "explicit-model")
        self.assertEqual(payload["input"][1]["mime_type"], "image/png")
        self.assertEqual(payload["input"][1]["data"], "iVBORw==")

    def test_gemini_no_implicit_credentials(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ProblemSpecError):
                GeminiVision("configured-model")

    def test_gemini_requires_model_name(self):
        with self.assertRaises(ProblemSpecError):
            GeminiVision("", client=object())

if __name__ == "__main__":
    unittest.main()
