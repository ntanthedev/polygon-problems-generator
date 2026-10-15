"""Package build lifecycle tests. Mocked Polygon; no credentials or sockets."""
import unittest
from unittest import mock

from polyup.api import PolygonAPIError
from polyup.config import SyncConfig
from polyup.package_monitor import PackageVerificationError, build_and_wait
from polyup.sync import _commit_and_build


def pkg(typ, state, *, rev=4, ident=101, comment=""):
    return {"id": ident, "revision": rev, "type": typ, "state": state,
            "comment": comment}


class FakeAPI:
    def __init__(self, snapshots, *, revision=4, fail_build=None):
        self.snapshots = list(snapshots)
        self.revision = revision
        self.fail_build = fail_build
        self.calls = []

    def call(self, method, **params):
        self.calls.append((method, params))
        if method == "problems.list":
            return [{"id": 7, "revision": self.revision}]
        if method == "problem.packages":
            if not self.snapshots:
                raise AssertionError("Unexpected extra polling")
            return self.snapshots.pop(0)
        if method == "problem.buildPackage":
            if self.fail_build:
                raise self.fail_build
            return True
        if method == "problem.commitChanges":
            return {"committed": True, "conflictOccurred": False}
        raise AssertionError(f"Unexpected method {method}")


class FakeClock:
    def __init__(self):
        self.current = 0.0
    def monotonic(self):
        return self.current
    def sleep(self, seconds):
        self.current += seconds


def _run(api, **kwargs):
    clock = FakeClock()
    with mock.patch("polyup.package_monitor.time.monotonic", clock.monotonic), \
         mock.patch("polyup.package_monitor.time.sleep", clock.sleep):
        return build_and_wait(api, {"problemId": "7"}, **kwargs)


class PackageMonitorTests(unittest.TestCase):
    def test_standard_build_pending_running_ready(self):
        api = FakeAPI([
            [pkg("standard", "READY", ident=12)],  # old baseline
            [pkg("standard", "READY", ident=12)],  # old READY must not pass
            [pkg("standard", "READY", ident=12), pkg("standard", "PENDING")],
            [pkg("standard", "READY", ident=12), pkg("standard", "RUNNING")],
            [pkg("standard", "READY", ident=12), pkg("standard", "READY")],
        ])
        result = _run(api, full=False, poll_interval_s=1)
        self.assertEqual(result.revision, "4")
        self.assertTrue(result.verified_invocations)
        self.assertEqual(len(result.packages), 1)
        self.assertEqual(result.packages[0]["id"], 101)
        self.assertEqual(
            [name for name, _ in api.calls].count("problem.buildPackage"), 1
        )
        self.assertEqual(
            [params for name, params in api.calls if name == "problem.buildPackage"][0],
            {"problemId": "7", "full": "false", "verify": "true"},
        )

    def test_full_build_waits_for_all_three_types(self):
        baseline = [pkg("standard", "READY", ident=99)]
        partial = [pkg("standard", "READY"), pkg("linux", "RUNNING")]
        ready = [pkg(k, "READY") for k in ("standard", "linux", "windows")]
        api = FakeAPI([baseline, partial, ready])
        res = _run(api, full=True)
        self.assertEqual({p["type"] for p in res.packages},
                         {"standard", "linux", "windows"})

    def test_failed_build_stops_immediately(self):
        api = FakeAPI([[], [pkg("standard", "FAILED", comment="compile fail")]])
        with self.assertRaisesRegex(PackageVerificationError, "compile fail"):
            _run(api, full=False)

    def test_old_ready_package_does_not_false_pass(self):
        old = [pkg("standard", "READY", ident=100)]
        api = FakeAPI([old, old, old])
        with self.assertRaisesRegex(PackageVerificationError, "Timed out"):
            _run(api, full=False, timeout_s=2, poll_interval_s=1)

    def test_other_revision_is_not_a_success(self):
        api = FakeAPI([[], [pkg("standard", "READY", rev=3, ident=110)], []])
        with self.assertRaisesRegex(PackageVerificationError, "Timed out"):
            _run(api, full=False, timeout_s=1, poll_interval_s=1)

    def test_build_transport_exception_never_retried(self):
        api = FakeAPI([[]], fail_build=PolygonAPIError(
            "problem.buildPackage", "transport", "lost response"
        ))
        with self.assertRaises(PolygonAPIError):
            _run(api, full=False)
        self.assertEqual(
            [name for name, _ in api.calls].count("problem.buildPackage"), 1
        )

    def test_new_concurrent_packages_ambiguous(self):
        api = FakeAPI([[], [pkg("standard", "READY", ident=101),
                            pkg("standard", "READY", ident=102)]])
        with self.assertRaisesRegex(PackageVerificationError, "ambiguous"):
            _run(api, full=False)

    def test_no_verify_flag_cannot_be_mislabeled_verified(self):
        api = FakeAPI([[], [pkg("standard", "READY")]])
        out = _run(api, full=False, verify=False)
        self.assertFalse(out.verified_invocations)
        params = next(params for name, params in api.calls if name == "problem.buildPackage")
        self.assertEqual(params["verify"], "false")

    def test_unexpected_or_malformed_packages_fail_closed(self):
        for result in (None, {}, [{"id": 5}], [{"id": 5, "revision": 4,
                    "state": "BROKEN", "type": "standard"}]):
            with self.subTest(result=result):
                api = FakeAPI([[], result])
                with self.assertRaises(PackageVerificationError):
                    _run(api, full=False)

    def test_missing_revision_fails_before_build(self):
        api = FakeAPI([], revision=None)
        with self.assertRaises(PackageVerificationError):
            _run(api, full=False)
        self.assertNotIn("problem.buildPackage", [c[0] for c in api.calls])

    def test_invalid_poll_config_has_no_side_effects(self):
        api = FakeAPI([])
        with self.assertRaises(ValueError):
            _run(api, timeout_s=0)
        self.assertEqual(api.calls, [])

    def test_commit_conflict_prevents_build(self):
        api = FakeAPI([])
        def call(method, **kwargs):
            api.calls.append((method, kwargs))
            return {"committed": False, "conflictOccurred": True}
        api.call = call
        with self.assertRaisesRegex(PackageVerificationError, "conflict"):
            _commit_and_build(api, {"problemId": "7"}, SyncConfig())
        self.assertEqual([x[0] for x in api.calls], ["problem.commitChanges"])

    def test_sync_uses_verification_and_polling(self):
        api = FakeAPI([[], [pkg("standard", "READY"),
                             pkg("linux", "READY"), pkg("windows", "READY")]])
        clock = FakeClock()
        cfg = SyncConfig(package_timeout_seconds=2, package_poll_seconds=1)
        with mock.patch("polyup.package_monitor.time.monotonic", clock.monotonic), \
             mock.patch("polyup.package_monitor.time.sleep", clock.sleep):
            _commit_and_build(api, {"problemId": "7"}, cfg)
        self.assertEqual(
            [x[0] for x in api.calls].count("problem.buildPackage"), 1
        )
        self.assertEqual(
            [x[0] for x in api.calls].count("problem.packages"), 2
        )

    def test_sync_no_build_does_not_query_packages(self):
        api = FakeAPI([])
        _commit_and_build(api, {"problemId": "7"}, SyncConfig(build_package=False))
        self.assertEqual([x[0] for x in api.calls], ["problem.commitChanges"])


if __name__ == "__main__":
    unittest.main()
