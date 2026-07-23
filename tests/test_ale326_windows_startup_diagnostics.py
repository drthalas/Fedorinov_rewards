from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import MagicMock, patch

from backend.app.services import runtime_identity
from backend.app.services import runtime_startup
from backend.app.services.runtime_identity import fetch_runtime_identity, runtime_build_id
from backend.app.services.runtime_supervisor import RuntimeLifecycleError, RuntimeSupervisor
from backend.app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class WindowsStartupDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = self.root / "runtime"
        self.data_root = self.root / "data"
        (self.data_root / "database").mkdir(parents=True)
        (self.data_root / "database" / "MyDatabase.sqlite").touch()
        self.environment = patch.dict(
            os.environ,
            {
                "APP_RUNTIME_DIR": str(self.registry),
                "REWARDS_DATA_DIR": str(self.data_root),
                "REWARDS_DB_PATH": str(self.data_root / "database" / "MyDatabase.sqlite"),
                "READ_ONLY": "true",
                "WRITE_MODE": "false",
                "UPDATE_CHECK_ENABLED": "false",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        self.environment.start()
        self.supervisors: list[RuntimeSupervisor] = []

    def tearDown(self) -> None:
        for supervisor in reversed(self.supervisors):
            try:
                supervisor.stop_all_confirmed()
            except RuntimeLifecycleError:
                pass
        self.environment.stop()
        self.temporary.cleanup()

    def _copy_install(self, name: str) -> Path:
        install_root = self.root / name
        shutil.copytree(
            ROOT / "backend",
            install_root / "backend",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (install_root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "runtime_server.py", install_root / "scripts" / "runtime_server.py")
        return install_root.resolve()

    @staticmethod
    def _replace_server_source(install_root: Path, marker: str, replacement: str) -> None:
        path = install_root / "scripts" / "runtime_server.py"
        source = path.read_text(encoding="utf-8")
        if marker not in source:
            raise AssertionError(f"Runtime server marker not found: {marker!r}")
        path.write_text(source.replace(marker, replacement, 1), encoding="utf-8")

    def _supervisor(self, *, ready_timeout: float = 0.25, startup_timeout: float = 2.0) -> RuntimeSupervisor:
        supervisor = RuntimeSupervisor(
            registry_dir=self.registry,
            python_executable=Path(sys.executable),
            ready_timeout=ready_timeout,
            startup_timeout=startup_timeout,
        )
        self.supervisors.append(supervisor)
        return supervisor

    @staticmethod
    def _start(supervisor: RuntimeSupervisor, install_root: Path, port: int):
        return supervisor.start_or_reuse(
            install_root=install_root,
            host="127.0.0.1",
            port=port,
            expected_version=APP_VERSION,
        )

    def test_delayed_windows_style_start_uses_progress_and_strict_identity(self) -> None:
        install_root = self._copy_install("Windows Package Федоринов Rewards")
        marker = '        from backend.app.main import app\n\n        reporter.stage("binding-port")'
        replacement = (
            '        from backend.app.main import app\n'
            '        __import__("time").sleep(0.75)\n\n'
            '        reporter.stage("binding-port")'
        )
        self._replace_server_source(install_root, marker, replacement)
        supervisor = self._supervisor(ready_timeout=0.4, startup_timeout=2.0)

        evidence = self._start(supervisor, install_root, free_port())

        self.assertGreater(evidence.readiness_seconds, 0.7)
        self.assertLess(evidence.readiness_seconds, 2.0)
        identity = fetch_runtime_identity(evidence.host, evidence.port)
        self.assertIsNotNone(identity)
        self.assertEqual(identity["pid"], evidence.pid)
        self.assertEqual(identity["instance_token"], evidence.instance_token)
        self.assertEqual(identity["build_id"], evidence.build_id)
        self.assertEqual(identity["install_root"], str(install_root))
        log = Path(str(evidence.log_path)).read_text(encoding="utf-8")
        launch = json.loads(log.splitlines()[0])
        spawned = json.loads(log.splitlines()[1])
        self.assertEqual(launch["cwd"], str(install_root))
        self.assertEqual(launch["command"][0], str(Path(sys.executable).absolute()))
        self.assertIn(str(install_root / "scripts" / "runtime_server.py"), launch["command"])
        self.assertEqual(spawned["pid"], evidence.pid)
        self.assertEqual(evidence.identity_seconds, evidence.readiness_seconds)
        self.assertIn('"stage": "loading-server"', log)
        self.assertIn('"stage": "binding-port"', log)

    def test_pre_registry_version_failure_reports_exact_stage(self) -> None:
        install_root = self._copy_install("wrong-version")
        supervisor = self._supervisor(ready_timeout=0.4, startup_timeout=2.0)

        with self.assertRaises(RuntimeLifecycleError) as raised:
            supervisor.start_or_reuse(
                install_root=install_root,
                host="127.0.0.1",
                port=free_port(),
                expected_version="9.9.9",
            )

        message = str(raised.exception)
        self.assertIn("category=child-crash", message)
        self.assertIn("stage=validating-version", message)
        self.assertIn("registry=absent", message)
        self.assertIn(f"Runtime version mismatch: {APP_VERSION} != 9.9.9", message)

    def test_startup_crash_surfaces_exit_stage_traceback_and_log(self) -> None:
        install_root = self._copy_install("crash-install")
        marker = '        reporter.stage("binding-port")'
        replacement = (
            '        raise RuntimeError("controlled Windows startup crash")\n\n'
            '        reporter.stage("binding-port")'
        )
        self._replace_server_source(install_root, marker, replacement)
        supervisor = self._supervisor(ready_timeout=0.4, startup_timeout=2.0)

        with self.assertRaises(RuntimeLifecycleError) as raised:
            self._start(supervisor, install_root, free_port())

        message = str(raised.exception)
        self.assertIn("category=child-crash", message)
        self.assertIn("exit_code=1", message)
        self.assertIn("stage=loading-server", message)
        self.assertIn("RuntimeError: controlled Windows startup crash", message)
        self.assertIn("log=", message)
        logs = list((self.registry / "logs").glob("backend-*.log"))
        self.assertEqual(len(logs), 1)
        log = logs[0].read_text(encoding="utf-8")
        self.assertIn("Traceback", log)
        self.assertIn("controlled Windows startup crash", log)

    def test_port_bind_failure_is_distinct_and_unrelated_listener_survives(self) -> None:
        install_root = self._copy_install("bind-install")
        supervisor = self._supervisor(ready_timeout=0.4, startup_timeout=2.0)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = int(listener.getsockname()[1])
            build_id = runtime_build_id(install_root)
            process, token, state_path, log_path = supervisor._spawn_backend(
                install_root=install_root,
                host="127.0.0.1",
                port=port,
                version=APP_VERSION,
                build_id=build_id,
            )
            with self.assertRaises(RuntimeLifecycleError) as raised:
                supervisor._wait_ready(
                    process=process,
                    token=token,
                    state_path=state_path,
                    install_root=install_root,
                    host="127.0.0.1",
                    port=port,
                    version=APP_VERSION,
                    build_id=build_id,
                    log_path=log_path,
                )
            process.wait(timeout=3)
            self.assertGreaterEqual(listener.fileno(), 0)

        message = str(raised.exception)
        self.assertIn("category=port-bind-failure", message)
        self.assertIn(f"port=127.0.0.1:{port}", message)
        self.assertIn("stage=binding-port", message)

    def test_registry_identity_mismatch_is_rejected_without_waiting_for_timeout(self) -> None:
        install_root = self._copy_install("registry-mismatch")
        marker = '        reporter.stage("loading-server")'
        replacement = (
            '        value = json.loads(args.state_path.read_text(encoding="utf-8"))\n'
            '        value["port"] = args.port + 1\n'
            '        args.state_path.write_text(json.dumps(value), encoding="utf-8")\n\n'
            '        reporter.stage("loading-server")'
        )
        self._replace_server_source(install_root, marker, replacement)
        supervisor = self._supervisor(ready_timeout=0.5, startup_timeout=2.0)
        started = time.monotonic()

        with self.assertRaises(RuntimeLifecycleError) as raised:
            self._start(supervisor, install_root, free_port())

        self.assertLess(time.monotonic() - started, 1.5)
        message = str(raised.exception)
        self.assertIn("category=registry-identity-mismatch", message)
        self.assertIn("port: expected=", message)

    def test_missing_startup_state_reports_stall_instead_of_confirmed_unresponsive(self) -> None:
        install_root = self._copy_install("missing-startup-state")
        marker = "    args = _parser().parse_args(argv)\n"
        replacement = '    args = _parser().parse_args(argv)\n    __import__("time").sleep(2)\n'
        self._replace_server_source(install_root, marker, replacement)
        supervisor = self._supervisor(ready_timeout=0.25, startup_timeout=1.0)

        with self.assertRaises(RuntimeLifecycleError) as raised:
            self._start(supervisor, install_root, free_port())

        message = str(raised.exception)
        self.assertIn("category=startup-stalled", message)
        self.assertIn("stage=startup-state-missing", message)
        self.assertNotIn("confirmed-unresponsive", message)

    def test_active_heartbeat_has_a_separate_hard_limit(self) -> None:
        install_root = self._copy_install("hard-limit")
        marker = '        from backend.app.main import app\n\n        reporter.stage("binding-port")'
        replacement = (
            '        from backend.app.main import app\n'
            '        __import__("time").sleep(2)\n\n'
            '        reporter.stage("binding-port")'
        )
        self._replace_server_source(install_root, marker, replacement)
        supervisor = self._supervisor(ready_timeout=0.5, startup_timeout=0.9)
        started = time.monotonic()

        with self.assertRaises(RuntimeLifecycleError) as raised:
            self._start(supervisor, install_root, free_port())

        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.85)
        self.assertLess(elapsed, 1.8)
        self.assertIn("category=slow-start-hard-limit", str(raised.exception))
        self.assertIn("stage=loading-server", str(raised.exception))

    def test_build_scoped_cache_is_written_outside_install_root(self) -> None:
        install_root = self._copy_install("cache-install")
        supervisor = self._supervisor(ready_timeout=1.0, startup_timeout=3.0)

        evidence = self._start(supervisor, install_root, free_port())

        cache_root = self.registry / "pycache" / evidence.build_id
        self.assertTrue(any(cache_root.rglob("*.pyc")))
        self.assertFalse(any(install_root.rglob("*.pyc")))
        launch = json.loads(Path(str(evidence.log_path)).read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(
            Path(launch["environment"]["PYTHONPYCACHEPREFIX"]).resolve(),
            cache_root.resolve(),
        )
        self.assertIsNone(launch["environment"]["PYTHONDONTWRITEBYTECODE"])
        startup_path = self.registry / f"startup-{evidence.instance_token}.json"
        self.assertTrue(startup_path.is_file())

        stopped = supervisor.stop_token(evidence.instance_token)

        self.assertIsNotNone(stopped)
        self.assertFalse(startup_path.exists())

    def test_windows_process_snapshot_allows_measured_cold_cim_start(self) -> None:
        payload = json.dumps(
            {
                "ProcessId": 4321,
                "CreationDate": "20260723020405.123456-420",
                "ExecutablePath": r"C:\Python311\python.exe",
                "CommandLine": r'"C:\Python311\python.exe" scripts\runtime_server.py',
            }
        )
        observed_timeouts: list[float] = []

        def simulated_cold_query(*args, timeout: float, **kwargs):
            observed_timeouts.append(timeout)
            if timeout < 1.623:
                raise subprocess.TimeoutExpired(args[0], timeout)
            return subprocess.CompletedProcess(args[0], 0, stdout=payload, stderr="")

        with (
            patch.object(runtime_identity.os, "name", "nt"),
            patch.object(runtime_identity.shutil, "which", return_value=r"C:\Windows\powershell.exe"),
            patch.object(runtime_identity.subprocess, "run", side_effect=simulated_cold_query),
        ):
            snapshot = runtime_identity.process_snapshot(4321)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.pid, 4321)
        self.assertEqual(snapshot.executable, r"C:\Python311\python.exe")
        self.assertEqual(observed_timeouts, [runtime_identity.WINDOWS_PROCESS_QUERY_TIMEOUT_SECONDS])
        self.assertGreater(
            runtime_identity.WINDOWS_PROCESS_QUERY_TIMEOUT_SECONDS,
            runtime_identity.PROCESS_QUERY_TIMEOUT_SECONDS,
        )

    def test_windows_process_snapshot_retries_only_transient_cim_failure(self) -> None:
        payload = json.dumps(
            {
                "ProcessId": 4321,
                "CreationDate": "20260723020405.123456-420",
                "ExecutablePath": r"C:\Python311\python.exe",
                "CommandLine": r'"C:\Python311\python.exe" scripts\runtime_server.py',
            }
        )
        outcomes = [
            subprocess.CompletedProcess([], 4, stdout="", stderr="Invalid class"),
            subprocess.CompletedProcess([], 0, stdout=payload, stderr=""),
        ]

        with (
            patch.object(runtime_identity.os, "name", "nt"),
            patch.object(runtime_identity.shutil, "which", return_value=r"C:\Windows\powershell.exe"),
            patch.object(runtime_identity.subprocess, "run", side_effect=outcomes) as query,
        ):
            snapshot = runtime_identity.process_snapshot(4321)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.pid, 4321)
        self.assertEqual(query.call_count, 2)
        self.assertIn('$ErrorActionPreference = "Stop"', query.call_args_list[0].args[0][-1])

    def test_windows_process_snapshot_does_not_retry_definitive_absence(self) -> None:
        missing = subprocess.CompletedProcess([], 3, stdout="", stderr="")

        with (
            patch.object(runtime_identity.os, "name", "nt"),
            patch.object(runtime_identity.shutil, "which", return_value=r"C:\Windows\powershell.exe"),
            patch.object(runtime_identity.subprocess, "run", return_value=missing) as query,
        ):
            snapshot = runtime_identity.process_snapshot(4321)

        self.assertIsNone(snapshot)
        query.assert_called_once()

    def test_windows_process_snapshot_uses_wmi_after_cim_provider_failures(self) -> None:
        payload = json.dumps(
            {
                "ProcessId": 4321,
                "CreationDate": "20260723020405.123456-420",
                "ExecutablePath": r"C:\Python311\python.exe",
                "CommandLine": r'"C:\Python311\python.exe" scripts\runtime_server.py',
            }
        )
        outcomes = [
            *[
                subprocess.CompletedProcess([], 4, stdout="", stderr="Invalid class")
                for _ in range(runtime_identity.WINDOWS_PROCESS_QUERY_ATTEMPTS)
            ],
            subprocess.CompletedProcess([], 0, stdout=payload, stderr=""),
        ]

        with (
            patch.object(runtime_identity.os, "name", "nt"),
            patch.object(runtime_identity.shutil, "which", return_value=r"C:\Windows\powershell.exe"),
            patch.object(runtime_identity.subprocess, "run", side_effect=outcomes) as query,
        ):
            snapshot = runtime_identity.process_snapshot(4321)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.pid, 4321)
        self.assertEqual(
            query.call_count,
            runtime_identity.WINDOWS_PROCESS_QUERY_ATTEMPTS
            + runtime_identity.WINDOWS_PROCESS_FALLBACK_ATTEMPTS,
        )
        self.assertIn("Get-WmiObject", query.call_args.args[0][-1])

    def test_windows_process_snapshot_preserves_cyrillic_command_line(self) -> None:
        command_line = (
            r'C:\Python311\python.exe "C:\Users\Alex\Desktop\Проверка восстановления'
            r'\scripts\runtime_server.py"'
        )
        payload = json.dumps(
            {
                "ProcessId": 4321,
                "CreationDate": "20260723020405.123456-420",
                "ExecutablePath": r"C:\Python311\python.exe",
                "CommandLine": command_line,
            },
            ensure_ascii=False,
        )

        with (
            patch.object(runtime_identity.os, "name", "nt"),
            patch.object(runtime_identity.shutil, "which", return_value=r"C:\Windows\powershell.exe"),
            patch.object(
                runtime_identity.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, stdout=payload, stderr=""),
            ) as query,
        ):
            snapshot = runtime_identity.process_snapshot(4321)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.command_line, command_line)
        self.assertEqual(query.call_args.kwargs["encoding"], "utf-8")
        self.assertIn("[Console]::OutputEncoding", query.call_args.args[0][-1])

    def test_current_windows_snapshot_records_actual_process_image(self) -> None:
        kernel32 = MagicMock()
        kernel32.GetCurrentProcess.return_value = 123
        kernel32.GetCommandLineW.return_value = (
            r'"C:\Python311\python.exe" C:\App\scripts\runtime_server.py'
        )

        def get_process_times(_handle, creation, _exit_time, _kernel_time, _user_time):
            creation._obj.low = 123
            creation._obj.high = 456
            return True

        def query_process_image(_handle, _flags, image_buffer, image_length):
            image_buffer.value = r"C:\Python311\python.exe"
            image_length._obj.value = len(image_buffer.value)
            return True

        kernel32.GetProcessTimes.side_effect = get_process_times
        kernel32.QueryFullProcessImageNameW.side_effect = query_process_image

        with (
            patch.object(ctypes, "WinDLL", return_value=kernel32, create=True),
            patch.object(runtime_identity.os, "getpid", return_value=4321),
            patch.object(runtime_identity.sys, "executable", r"C:\App\.venv\Scripts\python.exe"),
        ):
            snapshot = runtime_identity._current_windows_process_snapshot()

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.pid, 4321)
        self.assertEqual(snapshot.executable, r"C:\Python311\python.exe")
        self.assertNotEqual(snapshot.executable, runtime_identity.sys.executable)

    def test_windows_venv_backend_spawn_uses_base_process_with_venv_identity(self) -> None:
        venv_root = self.root / "Windows venv с пробелами"
        venv_python = venv_root / "Scripts" / "python.exe"
        base_python = self.root / "Python311" / "python.exe"
        venv_python.parent.mkdir(parents=True)
        base_python.parent.mkdir(parents=True)
        venv_python.touch()
        base_python.touch()
        (venv_root / "pyvenv.cfg").write_text(
            f"home = {base_python.parent}\n"
            "include-system-site-packages = false\n"
            "version = 3.11.9\n"
            f"executable = {base_python}\n",
            encoding="utf-8",
        )

        executable, environment = runtime_identity._windows_venv_spawn_target(venv_python)

        self.assertEqual(executable, base_python.absolute())
        self.assertEqual(environment, {"__PYVENV_LAUNCHER__": str(venv_python.absolute())})

    def test_windows_venv_backend_spawn_falls_back_for_invalid_config(self) -> None:
        venv_python = self.root / "incomplete-venv" / "Scripts" / "python.exe"
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()

        executable, environment = runtime_identity._windows_venv_spawn_target(venv_python)

        self.assertEqual(executable, venv_python.absolute())
        self.assertEqual(environment, {})

    def test_windows_current_process_identity_avoids_powershell_cim(self) -> None:
        snapshot = runtime_identity.ProcessSnapshot(
            pid=os.getpid(),
            start_marker="/Date(1784786473577)/",
            executable=r"C:\Python311\python.exe",
            command_line=r'"C:\Python311\python.exe" scripts\runtime_server.py',
        )

        with (
            patch.object(runtime_identity.os, "name", "nt"),
            patch.object(runtime_identity, "_current_windows_process_snapshot", return_value=snapshot),
            patch.object(
                runtime_identity,
                "process_snapshot",
                side_effect=AssertionError("self-registration must not launch PowerShell/CIM"),
            ),
        ):
            result = runtime_identity.current_process_snapshot()

        self.assertEqual(result, snapshot)

    def test_windows_native_marker_matches_powershell_json_epoch_format(self) -> None:
        unix_milliseconds = 1_784_786_473_577
        filetime = (
            runtime_identity.WINDOWS_FILETIME_UNIX_EPOCH
            + unix_milliseconds * 10_000
            + 9_999
        )

        marker = runtime_identity._windows_filetime_start_marker(
            filetime >> 32,
            filetime & 0xFFFFFFFF,
        )

        self.assertEqual(marker, f"/Date({unix_milliseconds})/")

    def test_legacy_windows_probe_requires_the_same_process_identity(self) -> None:
        expected = runtime_identity.ProcessSnapshot(
            pid=4321,
            start_marker="/Date(1784786473577)/",
            executable=r"C:\Python311\python.exe",
            command_line=r'"C:\Python311\python.exe" scripts\runtime_server.py',
        )

        with patch.object(runtime_identity, "process_snapshot", return_value=expected) as query:
            runtime_identity.prepare_legacy_windows_process_inspection(expected)

        query.assert_called_once_with(expected.pid)

    def test_legacy_windows_probe_rejects_identity_mismatch(self) -> None:
        expected = runtime_identity.ProcessSnapshot(
            pid=4321,
            start_marker="/Date(1784786473577)/",
            executable=r"C:\Python311\python.exe",
            command_line=r'"C:\Python311\python.exe" scripts\runtime_server.py',
        )
        mismatched = runtime_identity.ProcessSnapshot(
            pid=4321,
            start_marker="/Date(1784786473578)/",
            executable=expected.executable,
            command_line=expected.command_line,
        )

        with (
            patch.object(runtime_identity, "process_snapshot", return_value=mismatched),
            self.assertRaises(runtime_identity.RuntimeIdentityError),
        ):
            runtime_identity.prepare_legacy_windows_process_inspection(expected)

    def test_windows_listener_lookup_uses_same_bounded_query_budget(self) -> None:
        with (
            patch.object(runtime_identity.os, "name", "nt"),
            patch.object(runtime_identity.shutil, "which", return_value=r"C:\Windows\powershell.exe"),
            patch.object(runtime_identity, "_run_process_query", return_value="[4321]") as query,
        ):
            listeners = runtime_identity.listener_pids("127.0.0.1", 8080)

        self.assertEqual(listeners, {4321})
        self.assertEqual(
            query.call_args.kwargs["timeout"],
            runtime_identity.WINDOWS_PROCESS_QUERY_TIMEOUT_SECONDS,
        )

    def test_windows_startup_state_retries_transient_replace_denial(self) -> None:
        real_replace = os.replace
        attempts = 0

        def transient_replace(source, destination):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                error = PermissionError("controlled Windows sharing denial")
                error.winerror = 5
                raise error
            real_replace(source, destination)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "startup-token.json"
            with (
                patch.object(runtime_startup.os, "name", "nt"),
                patch.object(runtime_startup.os, "replace", side_effect=transient_replace),
            ):
                runtime_startup._write_transient_json(path, {"stage": "binding-port"})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"stage": "binding-port"})
            self.assertEqual(attempts, 3)
            self.assertFalse(any(path.parent.glob(".startup-token.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
