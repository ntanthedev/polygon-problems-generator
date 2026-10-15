"""Polygon API client — handles signing, file uploads, and rate limiting.

Network calls use an explicit connect/read timeout. Failures become
``PolygonAPIError`` (or ``None`` when ``fatal=False`` for HTTP, JSON, and
API-status failures). Requests are not retried: ``problem.create``,
``problem.saveFile``, ``problem.commitChanges``, and ``problem.buildPackage``
are writes and are not treated as idempotent.
"""

import hashlib
import random
import string
import sys
import time

import requests

BASE_URL = "https://polygon.codeforces.com/api"
# Connect, then read. A single hung socket must not stall a sync forever.
DEFAULT_TIMEOUT = (10.0, 60.0)


class PolygonAPIError(Exception):
    """Structured Polygon failure. ``str(error)`` is safe to print."""

    def __init__(
        self,
        method: str,
        kind: str,
        detail: str,
        status_code: int | None = None,
    ):
        self.method = method
        self.kind = kind
        self.detail = detail
        self.status_code = status_code
        super().__init__(f"API error [{method}]: {detail}")


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _make_signature(method: str, params: dict, secret: str, rand: str | None = None) -> str:
    if rand is None:
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    sig_bytes = rand.encode() + b"/" + method.encode() + b"?"
    sig_bytes += b"&".join(
        k.encode() + b"=" + (v if isinstance(v, bytes) else v.encode())
        for k, v in sorted(params.items())
    )
    sig_bytes += b"#" + secret.encode()
    return rand + hashlib.sha512(sig_bytes).hexdigest()


class PolygonAPI:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        delay: float = 0.3,
        timeout: float | tuple[float, float] | None = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.delay = delay
        # None must not disable the timeout; requests treats timeout=None as infinite.
        self.timeout = DEFAULT_TIMEOUT if timeout is None else timeout

    def _secrets(self, *extra: str) -> tuple[str, ...]:
        return (self.api_secret, self.api_key, *extra)

    def _safe(self, text: str, *extra: str) -> str:
        return _redact(text, self._secrets(*extra))

    def _fail(
        self,
        method: str,
        fatal: bool,
        kind: str,
        detail: str,
        status_code: int | None = None,
    ):
        err = PolygonAPIError(method, kind, detail, status_code=status_code)
        if not fatal:
            print(f"  {err}", file=sys.stderr)
            return None
        raise err from None

    def _http_detail(self, resp, *extra: str) -> str:
        extra_text = ""
        try:
            body = resp.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("comment"):
            extra_text = str(body.get("comment"))
        else:
            try:
                extra_text = resp.text or ""
            except (UnicodeError, AttributeError):
                extra_text = ""
        extra_text = _short(self._safe(extra_text, *extra))
        if extra_text:
            return f"HTTP {resp.status_code}: {extra_text}"
        return f"HTTP {resp.status_code}"

    def call(self, method: str, fatal: bool = True, **kwargs):
        params = {k: v for k, v in kwargs.items() if v is not None and k != "_files"}
        params["apiKey"] = self.api_key
        params["time"] = str(int(time.time()))

        files = kwargs.get("_files")
        if files:
            # ponytail: file bytes must be in signature — Polygon verifies them
            for field_name, (_, content) in files.items():
                params[field_name] = content
            params["apiSig"] = _make_signature(method, params, self.api_secret)
            del params["file"]
        else:
            params["apiSig"] = _make_signature(method, params, self.api_secret)
            files = None

        sig = params.get("apiSig", "")
        url = f"{BASE_URL}/{method}"
        try:
            # One attempt only. Do not retry: several methods write remote state.
            if files:
                resp = requests.post(url, data=params, files=files, timeout=self.timeout)
            else:
                resp = requests.post(url, data=params, timeout=self.timeout)
        except requests.RequestException as exc:
            detail = self._safe(f"{type(exc).__name__}: {exc}", sig)
            # Disconnects stay fatal. fatal=False only softens an HTTP/JSON/status
            # refusal from Polygon; returning None here would let clearScript continue.
            return self._fail(method, True, "transport", detail)

        if not resp.ok:
            return self._fail(
                method,
                fatal,
                "http",
                self._http_detail(resp, sig),
                status_code=getattr(resp, "status_code", None),
            )

        try:
            data = resp.json()
        except ValueError:
            return self._fail(method, fatal, "json", "non-JSON response")

        if not isinstance(data, dict):
            return self._fail(method, fatal, "json", "unexpected JSON response")

        if data.get("status") != "OK":
            msg = data.get("comment", data)
            if not isinstance(msg, str):
                msg = str(msg)
            return self._fail(method, fatal, "status", self._safe(msg, sig))

        time.sleep(self.delay)
        if "result" not in data:
            return True
        return data.get("result")
