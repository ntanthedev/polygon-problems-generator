"""Mocked Polygon API client tests. No network and no real credentials."""
import hashlib
import io
import tempfile
import traceback
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import requests

from polyup.api import (
    BASE_URL,
    PolygonAPI,
    PolygonAPIError,
    _make_signature,
)
from polyup.config import SyncConfig
from polyup.sync import _sync_access, _sync_validator_tests

SECRET = "super-secret-value"
KEY = "polygon-api-key-123"


def _response(payload, status_code=200, text=None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 400
    resp.json.return_value = payload
    if text is None and not isinstance(payload, str):
        text = str(payload)
    resp.text = text if text is not None else payload
    return resp


class SignatureTests(unittest.TestCase):
    def test_string_params_match_sha512_layout(self):
        payload = b"abc123/problem.info?a=x=y&b=1#s3cret"
        sig = _make_signature(
            "problem.info",
            {"b": "1", "a": "x=y"},
            "s3cret",
            rand="abc123",
        )
        self.assertEqual(sig, "abc123" + hashlib.sha512(payload).hexdigest())

    def test_file_bytes_are_signed_raw(self):
        payload = b"abc123/problem.saveFile?apiKey=k&file=\xff\xfe#s3cret"
        sig = _make_signature(
            "problem.saveFile",
            {"file": b"\xff\xfe", "apiKey": "k"},
            "s3cret",
            rand="abc123",
        )
        self.assertEqual(sig, "abc123" + hashlib.sha512(payload).hexdigest())


class PolygonAPITests(unittest.TestCase):
    def setUp(self):
        self.api = PolygonAPI(KEY, SECRET, delay=0)

    def _patch_post(self, side_effect=None, return_value=None):
        patcher = mock.patch("polyup.api.requests.post")
        post = patcher.start()
        self.addCleanup(patcher.stop)
        if side_effect is not None:
            post.side_effect = side_effect
        else:
            post.return_value = return_value
        return post

    def test_success_returns_result_and_default_timeout(self):
        post = self._patch_post(return_value=_response({"status": "OK", "result": {"id": 9}}))
        with mock.patch("polyup.api.time.time", return_value=1_700_000_000.9):
            with mock.patch("polyup.api.time.sleep") as sleep:
                result = self.api.call("problem.create", name="demo", skipped=None)
        self.assertEqual(result, {"id": 9})
        sleep.assert_called_once_with(0)
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], f"{BASE_URL}/problem.create")
        self.assertEqual(kwargs["timeout"], (10.0, 60.0))
        self.assertNotIn("files", kwargs)
        data = kwargs["data"]
        self.assertNotIn("skipped", data)
        self.assertEqual(data["apiKey"], KEY)
        self.assertEqual(data["time"], "1700000000")
        self.assertEqual(data["name"], "demo")
        self.assertNotIn(SECRET, repr(data))
        signed = {k: v for k, v in data.items() if k != "apiSig"}
        expected = _make_signature("problem.create", signed, SECRET, rand=data["apiSig"][:6])
        self.assertEqual(data["apiSig"], expected)

    def test_missing_result_returns_true(self):
        self._patch_post(return_value=_response({"status": "OK"}))
        with mock.patch("polyup.api.time.sleep") as sleep:
            self.assertIs(self.api.call("problem.commitChanges"), True)
        sleep.assert_called_once_with(0)

    def test_timeout_none_stays_explicit(self):
        api = PolygonAPI(KEY, SECRET, delay=0, timeout=None)
        post = self._patch_post(return_value=_response({"status": "OK", "result": 1}))
        with mock.patch("polyup.api.time.sleep"):
            api.call("problem.info")
        self.assertEqual(post.call_args.kwargs["timeout"], (10.0, 60.0))

    def test_custom_timeout_is_forwarded(self):
        api = PolygonAPI(KEY, SECRET, delay=0, timeout=(1.5, 2.5))
        post = self._patch_post(return_value=_response({"status": "OK", "result": 1}))
        with mock.patch("polyup.api.time.sleep"):
            api.call("problem.info")
        self.assertEqual(post.call_args.kwargs["timeout"], (1.5, 2.5))

        api.timeout = 7
        with mock.patch("polyup.api.time.sleep"):
            api.call("problem.info")
        self.assertEqual(post.call_args.kwargs["timeout"], 7)

    def test_connection_error_is_structured_and_not_retried(self):
        leaked = {}

        def boom(url, data=None, **kwargs):
            leaked["sig"] = data["apiSig"]
            raise requests.ConnectionError(f"down {SECRET} {data['apiSig']}")

        post = self._patch_post(side_effect=boom)
        with mock.patch("polyup.api.time.sleep") as sleep:
            with self.assertRaises(PolygonAPIError) as caught:
                try:
                    self.api.call("problem.create", name="demo")
                except PolygonAPIError:
                    rendered = traceback.format_exc()
                    self.assertNotIn(SECRET, rendered)
                    self.assertNotIn(leaked["sig"], rendered)
                    raise
        err = caught.exception
        self.assertEqual(err.kind, "transport")
        self.assertIsNone(err.status_code)
        self.assertNotIn(SECRET, str(err))
        self.assertNotIn(leaked["sig"], str(err))
        self.assertIn("[REDACTED]", str(err))
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_timeout_is_transport_error(self):
        post = self._patch_post(side_effect=requests.Timeout("read timed out"))
        with mock.patch("polyup.api.time.sleep") as sleep:
            with self.assertRaises(PolygonAPIError) as caught:
                self.api.call("problem.buildPackage")
        self.assertEqual(caught.exception.kind, "transport")
        self.assertIn("Timeout", caught.exception.detail)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_transport_error_is_not_softened_by_fatal_false(self):
        self._patch_post(side_effect=requests.ConnectionError("reset"))
        with self.assertRaises(PolygonAPIError) as caught:
            self.api.call("problem.clearScript", fatal=False, testset="tests")
        self.assertEqual(caught.exception.kind, "transport")
        self.assertEqual(caught.exception.method, "problem.clearScript")

    def test_mutating_methods_post_once(self):
        methods = (
            "problem.create",
            "problem.saveFile",
            "problem.commitChanges",
            "problem.buildPackage",
        )
        for method in methods:
            with self.subTest(method=method):
                post = mock.Mock(side_effect=requests.ConnectionError("down"))
                with mock.patch("polyup.api.requests.post", post):
                    with self.assertRaises(PolygonAPIError):
                        self.api.call(method, name="x")
                self.assertEqual(post.call_count, 1)

    def test_http_error_raises_and_redacts(self):
        body = SECRET + ("A" * 500)
        resp = _response({"ignored": True}, status_code=503, text=body)
        resp.json.side_effect = ValueError("not json")
        post = self._patch_post(return_value=resp)
        with mock.patch("polyup.api.time.sleep") as sleep:
            with self.assertRaises(PolygonAPIError) as caught:
                self.api.call("problem.saveFile")
        err = caught.exception
        self.assertEqual(err.kind, "http")
        self.assertEqual(err.status_code, 503)
        self.assertIn("HTTP 503", err.detail)
        self.assertNotIn(SECRET, str(err))
        self.assertIn("[REDACTED]", err.detail)
        self.assertLess(len(err.detail), 400)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_http_error_fatal_false_returns_none(self):
        resp = _response(
            {"status": "FAILED", "comment": f"nope {SECRET}"},
            status_code=400,
        )
        self._patch_post(return_value=resp)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = self.api.call("problem.setAccess", fatal=False, login="alice")
        self.assertIsNone(result)
        text = stderr.getvalue()
        self.assertIn("API error [problem.setAccess]: HTTP 400:", text)
        self.assertNotIn(SECRET, text)
        self.assertIn("[REDACTED]", text)

    def test_non_json_uses_legacy_detail(self):
        resp = _response({}, text=f"<html>{SECRET}</html>")
        resp.json.side_effect = requests.exceptions.JSONDecodeError(
            "Expecting value", f"<html>{SECRET}</html>", 0
        )
        self._patch_post(return_value=resp)
        with self.assertRaises(PolygonAPIError) as caught:
            self.api.call("problem.info")
        self.assertEqual(caught.exception.kind, "json")
        self.assertEqual(caught.exception.detail, "non-JSON response")
        self.assertNotIn(SECRET, str(caught.exception))

    def test_non_json_fatal_false_returns_none_without_body(self):
        resp = _response({}, text=f"<html>{SECRET}</html>")
        resp.json.side_effect = ValueError("Expecting value")
        self._patch_post(return_value=resp)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = self.api.call("problem.cautions", fatal=False)
        self.assertIsNone(result)
        text = stderr.getvalue()
        self.assertIn("API error [problem.cautions]: non-JSON response", text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("<html>", text)

    def test_unexpected_json_type(self):
        resp = _response(["not", "an", "object"])
        self._patch_post(return_value=resp)
        with self.assertRaises(PolygonAPIError) as caught:
            self.api.call("problem.info")
        self.assertEqual(caught.exception.kind, "json")
        self.assertEqual(caught.exception.detail, "unexpected JSON response")

    def test_api_status_error(self):
        self._patch_post(return_value=_response(
            {"status": "FAILED", "comment": f"exists {SECRET}"}
        ))
        with mock.patch("polyup.api.time.sleep") as sleep:
            with self.assertRaises(PolygonAPIError) as caught:
                self.api.call("problem.create", name="demo")
        self.assertEqual(caught.exception.kind, "status")
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIn("exists [REDACTED]", str(caught.exception))
        sleep.assert_not_called()

    def test_api_status_fatal_false_returns_none(self):
        self._patch_post(return_value=_response({"status": "FAILED", "comment": "denied"}))
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = self.api.call(
                "problem.deleteValidatorTest", fatal=False, testIndex="3"
            )
        self.assertIsNone(result)
        self.assertIn("API error [problem.deleteValidatorTest]: denied", stderr.getvalue())

    def test_missing_status_is_an_error(self):
        self._patch_post(return_value=_response({}))
        with self.assertRaises(PolygonAPIError) as caught:
            self.api.call("problem.info")
        self.assertEqual(caught.exception.kind, "status")

    def test_multipart_signs_file_and_strips_it_from_form(self):
        content = b"int main(){return 0;}\xff"
        resp = _response({"status": "OK"})
        post = self._patch_post(return_value=resp)
        with mock.patch("polyup.api.time.time", return_value=10):
            with mock.patch("polyup.api.time.sleep"):
                result = self.api.call(
                    "problem.saveFile",
                    type="source",
                    name="acc.cpp",
                    _files={"file": ("acc.cpp", content)},
                )
        self.assertIs(result, True)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://polygon.codeforces.com/api/problem.saveFile")
        self.assertEqual(kwargs["timeout"], (10.0, 60.0))
        self.assertEqual(kwargs["files"], {"file": ("acc.cpp", content)})
        data = kwargs["data"]
        self.assertNotIn("file", data)
        self.assertNotIn(SECRET, repr(data))
        signed = {k: v for k, v in data.items() if k != "apiSig"}
        signed["file"] = content
        expected = _make_signature(
            "problem.saveFile", signed, SECRET, rand=data["apiSig"][:6]
        )
        self.assertEqual(data["apiSig"], expected)
        self.assertEqual(post.call_count, 1)


class CallerContractTests(unittest.TestCase):
    def test_cli_sync_exits_on_api_error_without_traceback(self):
        from polyup.__main__ import main

        err = PolygonAPIError("problem.create", "status", "name already used")
        stderr = io.StringIO()
        with mock.patch("polyup.__main__.sys.argv", ["polyup", "demo"]):
            with mock.patch("polyup.__main__._problem_dir", return_value=Path(".")):
                with mock.patch("polyup.__main__.collect_access", return_value={}):
                    with mock.patch("polyup.__main__._api", return_value=object()):
                        with mock.patch("polyup.__main__.sync_problem", side_effect=err):
                            with redirect_stderr(stderr):
                                with self.assertRaises(SystemExit) as caught:
                                    main()
        self.assertEqual(caught.exception.code, 1)
        text = stderr.getvalue()
        self.assertIn("  API error [problem.create]: name already used", text)
        self.assertNotIn("Traceback", text)

    def test_cli_access_exits_on_api_error(self):
        from polyup.__main__ import _access_cmd

        err = PolygonAPIError("problem.accesses", "transport", "ConnectionError: down")
        stderr = io.StringIO()
        with mock.patch("polyup.__main__._problem_dir", return_value=Path(".")):
            with mock.patch("polyup.__main__._problem_id", return_value="15"):
                with mock.patch("polyup.__main__._api", return_value=object()):
                    with mock.patch("polyup.__main__.list_accesses", side_effect=err):
                        with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                            with self.assertRaises(SystemExit) as caught:
                                _access_cmd(["demo", "--list"])
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("API error [problem.accesses]: ConnectionError: down", stderr.getvalue())

    def test_validator_delete_stops_when_api_returns_none(self):
        class FakeAPI:
            def __init__(self):
                self.calls = []

            def call(self, method, fatal=True, **kwargs):
                self.calls.append((method, fatal, kwargs.get("testIndex")))
                if method == "problem.deleteValidatorTest":
                    return None
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vdir = root / "validator_tests"
            vdir.mkdir()
            (vdir / "valid_1.in").write_text("1\n", encoding="utf-8")
            (vdir / "invalid_2.in").write_text("x\n", encoding="utf-8")
            api = FakeAPI()
            with redirect_stdout(io.StringIO()):
                _sync_validator_tests(api, {"problemId": "1"}, root)
        deletes = [c for c in api.calls if c[0] == "problem.deleteValidatorTest"]
        self.assertEqual(deletes, [("problem.deleteValidatorTest", False, "3")])

    def test_set_access_treats_none_as_failure(self):
        class FakeAPI:
            def call(self, method, fatal=True, **kwargs):
                if method == "problem.setAccess":
                    return None
                if method == "problem.accesses":
                    return []
                raise AssertionError(method)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            _sync_access(
                FakeAPI(),
                {"problemId": "1"},
                SyncConfig(access={"alice": "WRITE"}, grant_access=True),
            )
        self.assertIn("setAccess failed for alice (WRITE)", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
