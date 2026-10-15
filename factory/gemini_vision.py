"""Opt-in Gemini image transcription adapter.

Only constructed when the user passes --vision-model; never auto-uploads
private source or echoes credentials. Uses Google's Interactions API for
inline images (documented at ai.google.dev/gemini-api/docs/image-understanding).
"""
from __future__ import annotations

import base64
import os

from .spec import ProblemSpecError


class GeminiVision:
    def __init__(self, model: str, *, client=None):
        if not isinstance(model, str) or not model.strip():
            raise ProblemSpecError("An explicit Gemini model ID is required")
        self.model = model.strip()
        if client is not None:
            self.client = client
            return
        if not os.environ.get("GEMINI_API_KEY"):
            raise ProblemSpecError(
                "GEMINI_API_KEY is missing; use offline mode or set it locally"
            )
        try:
            from google import genai
        except ImportError:
            raise ProblemSpecError(
                "Install requirements-vision.txt for Gemini transcription"
            ) from None
        # Key is read from local environment by SDK, not logged or serialized.
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def transcribe(self, data: bytes, mime_type: str, prompt: str) -> str:
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ProblemSpecError("GeminiVision only accepts image pages")
        response = self.client.interactions.create(
            model=self.model,
            input=[
                {"type": "text", "text": prompt},
                {"type": "image",
                 "data": base64.b64encode(data).decode("ascii"),
                 "mime_type": mime_type},
            ]
        )
        result = getattr(response, "output_text", None)
        if not isinstance(result, str) or not result.strip():
            raise ProblemSpecError("Gemini returned an empty transcription")
        return result
