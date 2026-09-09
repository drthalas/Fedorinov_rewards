from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend.app.services import runtime_identity
from backend.app.services.runtime_identity import RuntimeInspection
from backend.app.services.runtime_supervisor import RuntimeLifecycleError, RuntimeSupervisor


class BootstrapInspectionTests(unittest.TestCase):
    def run_readiness(self, outcomes, *, query_seconds=0.0, timeout=10.0):
        self.clock = 0.0
        self.calls = 0
        with TemporaryDirectory() as directory:
            root = Path(directory)
            supervisor = RuntimeSupervisor(registry_dir=root, ready_timeout=1, startup_timeout=timeout)
            process = Mock(pid=4321)
            process.poll.return_value = None
            record = Mock(instance_token="a" * 32)
            identity = {"pid": process.pid}

            def inspect(*args, **kwargs):
                self.calls += 1
                self.clock += query_seconds
                reason = outcomes[min(self.calls - 1, len(outcomes) - 1)]
                return RuntimeInspection(
                    record, None, reason == "confirmed", reason != "http-mismatch", reason, identity
                )

            def sleep(seconds):
                self.clock += seconds

            def failure(**kwargs):
                self.failure = kwargs
                return RuntimeLifecycleError(kwargs["category"])

            with (
                patch("backend.app.services.runtime_supervisor.time.monotonic", side_effect=lambda: self.clock),
                patch("backend.app.services.runtime_supervisor.time.sleep", side_effect=sleep),
                patch("backend.app.services.runtime_supervisor.read_runtime_startup", return_value=None),
                patch("backend.app.services.runtime_supervisor.read_runtime_records", return_value=([record], [])),
                patch("backend.app.services.runtime_supervisor.fetch_runtime_identity", return_value=identity),
                patch("backend.app.services.runtime_supervisor.inspect_runtime_record", side_effect=inspect),
                patch.object(supervisor, "_record_mismatches", return_value=[]),
                patch.object(supervisor, "_startup_failure", side_effect=failure),
            ):
                return supervisor._wait_ready(
                    process=process, token=record.instance_token, state_path=root / "backend.json",
                    install_root=root, host="127.0.0.1", port=18421, version="test", build_id="b" * 64,
                )

    def test_unavailable_os_query_retries_until_full_identity_is_confirmed(self):
        self.run_readiness(["process-inspection-unavailable", "confirmed"])
        self.assertEqual(self.calls, 2)

    def test_slow_query_is_not_a_stalled_backend_when_exact_http_identity_is_alive(self):
        self.run_readiness(["process-inspection-unavailable", "confirmed"], query_seconds=3)
        self.assertEqual(self.calls, 2)

    def test_http_identity_alone_never_passes_and_has_bounded_distinct_failure(self):
        with self.assertRaisesRegex(RuntimeLifecycleError, "process-inspection-unavailable"):
            self.run_readiness(["process-inspection-unavailable"], query_seconds=3)
        self.assertGreaterEqual(self.failure["elapsed"], 10)
        self.assertLess(self.failure["elapsed"], 13.2)

    def test_confirmed_identity_after_hard_deadline_is_not_accepted(self):
        with self.assertRaisesRegex(RuntimeLifecycleError, "slow-start-hard-limit"):
            self.run_readiness(["confirmed"], query_seconds=11)
        self.assertEqual(self.calls, 1)

    def test_actual_os_mismatches_are_not_retried_even_with_matching_http(self):
        for reason in ("command-line-mismatch", "executable-mismatch", "process-start-time-mismatch",
                       "app-owned-command-marker-mismatch"):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(RuntimeLifecycleError, "http-identity-mismatch"):
                    self.run_readiness([reason, "confirmed"])
                self.assertEqual(self.calls, 1)
                self.assertEqual(self.failure["detail"], reason)

    def test_actual_http_mismatch_is_not_retried(self):
        with self.assertRaisesRegex(RuntimeLifecycleError, "http-identity-mismatch"):
            self.run_readiness(["http-mismatch", "confirmed"])
        self.assertEqual(self.calls, 1)

    @unittest.skipUnless(os.name == "nt", "requires native Windows WMI")
    def test_native_wmi_fallback_matches_native_registration_identity(self):
        native = runtime_identity.current_process_snapshot()
        query = runtime_identity._run_process_query_result

        def wmi_only(command, **kwargs):
            if "Get-CimInstance" in command[-1]:
                return 4, None
            return query(command, **kwargs)

        with patch.object(runtime_identity, "_run_process_query_result", side_effect=wmi_only):
            observed = runtime_identity.process_snapshot(os.getpid())
        self.assertIsNotNone(native)
        self.assertIsNotNone(observed)
        self.assertEqual(observed.pid, native.pid)
        self.assertEqual(observed.start_marker, native.start_marker)
        self.assertEqual(observed.command_line, native.command_line)
        self.assertEqual(os.path.normcase(observed.executable), os.path.normcase(native.executable))


if __name__ == "__main__":
    unittest.main()
