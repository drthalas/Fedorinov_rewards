from __future__ import annotations

from contextlib import contextmanager
import hashlib
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.parse
import urllib.request
from zipfile import ZipFile

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import app
from backend.app.services.runtime_identity import (
    APPLICATION_ID,
    RUNTIME_STATE_SCHEMA,
    atomic_write_json,
    fetch_runtime_identity,
    fetch_version_identity,
    inspect_legacy_runtime,
    listener_pids,
    process_snapshot,
    read_runtime_records,
    runtime_build_id,
)
from backend.app.services.runtime_supervisor import RuntimeLifecycleError, RuntimeSupervisor
from backend.app.services.supervised_update import run_supervised_update
from backend.app.services.updater import UpdateError, UpdatePlan, read_update_status


ROOT = Path(__file__).resolve().parents[1]


class QuietFileHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args) -> None:
        return


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def process_is_same(pid: int, start_marker: str) -> bool:
    snapshot = process_snapshot(pid)
    return snapshot is not None and snapshot.start_marker == start_marker


class RuntimeLifecycleTests(unittest.TestCase):
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

    def supervisor(self, **overrides) -> RuntimeSupervisor:
        supervisor = RuntimeSupervisor(
            registry_dir=self.registry,
            python_executable=Path(sys.executable),
            ready_timeout=8,
            **overrides,
        )
        self.supervisors.append(supervisor)
        return supervisor

    def start(self, supervisor: RuntimeSupervisor, port: int):
        return supervisor.start_or_reuse(
            install_root=ROOT,
            host="127.0.0.1",
            port=port,
            expected_version="2.0.6",
        )

    def test_clean_and_repeated_start_leave_one_backend(self) -> None:
        supervisor = self.supervisor()
        port = free_port()
        first = self.start(supervisor, port)
        second = self.start(supervisor, port)

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(second.pid, first.pid)
        confirmed = [item for item in supervisor.inspect_all() if item.confirmed and item.healthy]
        self.assertEqual(len(confirmed), 1)
        identity = fetch_runtime_identity("127.0.0.1", port)
        self.assertEqual(identity["pid"], first.pid)
        self.assertEqual(identity["version"], "2.0.6")
        self.assertEqual(identity["build_id"], runtime_build_id(ROOT))
        self.assertEqual(identity["install_root"], str(ROOT))
        self.assertEqual(identity["instance_token"], first.instance_token)
        self.assertLess(first.detection_seconds, 2.0)
        self.assertLess(first.readiness_seconds, 5.0)
        self.assertLess(second.detection_seconds, 2.0)

    def test_start_does_not_repeat_health_probe_after_readiness(self) -> None:
        supervisor = self.supervisor()
        port = free_port()
        original_wait_ready = supervisor._wait_ready
        original_inspect_all = supervisor.inspect_all
        readiness_complete = False
        post_readiness_inspections = 0

        def wait_ready(**kwargs):
            nonlocal readiness_complete
            result = original_wait_ready(**kwargs)
            readiness_complete = True
            return result

        def inspect_all():
            nonlocal post_readiness_inspections
            if readiness_complete:
                post_readiness_inspections += 1
            return original_inspect_all()

        with (
            patch.object(supervisor, "_wait_ready", side_effect=wait_ready),
            patch.object(supervisor, "inspect_all", side_effect=inspect_all),
        ):
            evidence = self.start(supervisor, port)

        self.assertEqual(post_readiness_inspections, 0)
        identity = fetch_runtime_identity("127.0.0.1", port)
        self.assertIsNotNone(identity)
        self.assertEqual(identity["pid"], evidence.pid)
        self.assertEqual(identity["instance_token"], evidence.instance_token)
        self.assertEqual(identity["build_id"], evidence.build_id)

    def test_backend_uses_writable_build_scoped_bytecode_cache(self) -> None:
        source = (ROOT / "backend" / "app" / "services" / "runtime_supervisor.py").read_text(encoding="utf-8")
        self.assertIn('"PYTHONPYCACHEPREFIX": str(self.registry_dir / "pycache" / build_id)', source)
        self.assertIn('environment.pop("PYTHONDONTWRITEBYTECODE", None)', source)
        self.assertNotIn('"PYTHONDONTWRITEBYTECODE": "1"', source)

    def test_two_confirmed_backends_are_forced_down_before_one_start(self) -> None:
        supervisor = self.supervisor()
        first_port = free_port()
        second_port = free_port()
        previous_root = self.root / "previous-install"
        shutil.copytree(ROOT / "backend", previous_root / "backend", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (previous_root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "runtime_server.py", previous_root / "scripts" / "runtime_server.py")
        spawned = []
        for install_root, port in ((ROOT, first_port), (previous_root.resolve(), second_port)):
            build_id = runtime_build_id(install_root)
            process, token, state_path, _log = supervisor._spawn_backend(
                install_root=install_root,
                host="127.0.0.1",
                port=port,
                version="2.0.6",
                build_id=build_id,
            )
            supervisor._wait_ready(
                process=process,
                token=token,
                state_path=state_path,
                install_root=install_root,
                host="127.0.0.1",
                port=port,
                version="2.0.6",
                build_id=build_id,
            )
            spawned.append((process, process_snapshot(process.pid).start_marker))

        replacement = self.start(supervisor, first_port)
        self.assertEqual(len(replacement.stopped), 2)
        self.assertTrue(all(not process_is_same(process.pid, marker) for process, marker in spawned))
        self.assertEqual(len([item for item in supervisor.inspect_all() if item.confirmed and item.healthy]), 1)
        self.assertLess(replacement.termination_seconds, 2.0)
        for process, _marker in spawned:
            process.wait(timeout=2)

    def test_stale_pid_and_pid_reuse_state_never_trigger_kill(self) -> None:
        snapshot = process_snapshot(os.getpid())
        self.assertIsNotNone(snapshot)
        state = self.registry / "backend-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json"
        atomic_write_json(
            state,
            {
                "application_id": APPLICATION_ID,
                "schema": RUNTIME_STATE_SCHEMA,
                "pid": os.getpid(),
                "process_start_marker": snapshot.start_marker + "-reused",
                "install_root": str(ROOT),
                "executable": snapshot.executable,
                "command_line": snapshot.command_line,
                "host": "127.0.0.1",
                "port": free_port(),
                "version": "2.0.6",
                "build_id": runtime_build_id(ROOT),
                "instance_token": "a" * 32,
                "created_at": "2026-07-21T00:00:00+00:00",
            },
        )
        supervisor = self.supervisor()
        with patch.object(supervisor, "_force_kill_pid") as force_kill:
            self.assertEqual(supervisor.stop_all_confirmed(), [])
        force_kill.assert_not_called()
        self.assertFalse(state.exists())
        self.assertIsNotNone(process_snapshot(os.getpid()))

    def test_unrelated_port_listener_is_not_killed(self) -> None:
        port = free_port()
        fake_server = self.root / "unrelated_server.py"
        fake_server.write_text(
            """from http.server import BaseHTTPRequestHandler, HTTPServer
import json, sys
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'app_name': 'Награды и награждённые', 'version': '2.0.6'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
""",
            encoding="utf-8",
        )
        unrelated = subprocess.Popen(
            [sys.executable, str(fake_server), str(port)],
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                        break
                except OSError:
                    time.sleep(0.02)
            supervisor = self.supervisor()
            with self.assertRaisesRegex(RuntimeLifecycleError, "Посторонний процесс не был завершён"):
                self.start(supervisor, port)
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_confirmed_force_stop_is_bounded(self) -> None:
        supervisor = self.supervisor(stop_timeout=0.8)
        running = self.start(supervisor, free_port())
        started = time.monotonic()
        stopped = supervisor.stop_all_confirmed()
        elapsed = time.monotonic() - started
        self.assertEqual([item.pid for item in stopped], [running.pid])
        self.assertEqual(stopped[0].attempts, 1)
        self.assertLess(elapsed, 2.0)

    def test_launcher_converts_exact_public_v204_style_backend_to_managed_instance(self) -> None:
        install_root = (self.root / "public-v204-install").resolve()
        shutil.copytree(ROOT / "backend", install_root / "backend", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (install_root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "runtime_server.py", install_root / "scripts" / "runtime_server.py")
        (install_root / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
        expected_python = install_root / ".venv" / "bin" / "python"
        port = free_port()
        environment = os.environ.copy()
        environment.update(
            {
                "APP_INSTALL_DIR": str(install_root),
                "APP_HOST": "127.0.0.1",
                "APP_PORT": str(port),
            }
        )
        legacy = subprocess.Popen(
            [
                str(expected_python),
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=install_root,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if fetch_version_identity("127.0.0.1", port, 0.15):
                    break
                time.sleep(0.05)
            legacy_marker = process_snapshot(legacy.pid).start_marker
            legacy_record = inspect_legacy_runtime(
                install_root=install_root,
                host="127.0.0.1",
                port=port,
                expected_app_name="Награды и награждённые",
            )
            self.assertIsNotNone(
                legacy_record,
                msg=f"snapshot={process_snapshot(legacy.pid)!r}; expected_python={expected_python}",
            )
            supervisor = self.supervisor()
            managed = supervisor.start_or_reuse(
                install_root=install_root,
                host="127.0.0.1",
                port=port,
                expected_version="2.0.6",
            )
            self.assertFalse(managed.reused)
            self.assertEqual(len(managed.stopped), 1)
            self.assertEqual(managed.stopped[0].pid, legacy.pid)
            self.assertEqual(managed.stopped[0].instance_token, "legacy-command-marker")
            self.assertFalse(process_is_same(legacy.pid, legacy_marker))
            legacy.wait(timeout=2)
            identity = fetch_runtime_identity("127.0.0.1", port)
            self.assertTrue(identity["managed"])
            self.assertEqual(identity["pid"], managed.pid)
            self.assertLess(managed.detection_seconds, 2.0)
            self.assertLess(managed.termination_seconds, 2.0)
            self.assertLess(managed.port_release_seconds, 2.0)
            self.assertLess(managed.readiness_seconds, 5.0)
        finally:
            if legacy.poll() is None:
                legacy.terminate()
                legacy.wait(timeout=3)

    def test_windows_force_kill_is_exact_pid_not_process_name(self) -> None:
        completed = Mock(returncode=0, stdout="", stderr="")
        with patch("backend.app.services.runtime_supervisor.os.name", "nt"), patch(
            "backend.app.services.runtime_supervisor.subprocess.run",
            return_value=completed,
        ) as run:
            RuntimeSupervisor._force_kill_pid(4312)
        command = run.call_args.args[0]
        self.assertEqual(command, ["taskkill", "/PID", "4312", "/F"])
        self.assertNotIn("/IM", command)
        self.assertNotIn("python.exe", command)

    def test_launchers_and_package_use_bootstrap(self) -> None:
        batch = (ROOT / "start_windows.bat").read_text(encoding="utf-8")
        powershell = (ROOT / "start_windows.ps1").read_text(encoding="utf-8")
        packager = (ROOT / "scripts" / "build_windows_preview_package.py").read_text(encoding="utf-8")
        for launcher in (batch, powershell):
            self.assertIn("runtime_bootstrap.py", launcher)
            self.assertNotIn("-m uvicorn backend.app.main:app", launcher)
            self.assertNotIn("taskkill /IM", launcher)
        self.assertIn('Path("scripts") / "runtime_bootstrap.py"', packager)
        self.assertIn('Path("scripts") / "runtime_server.py"', packager)

    def test_runtime_identity_endpoint_is_local_and_has_no_user_data(self) -> None:
        response = TestClient(app).get("/runtime/identity")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["application_id"], APPLICATION_ID)
        self.assertIn("version", payload)
        self.assertIn("install_root", payload)
        self.assertNotIn("data_dir", payload)
        self.assertNotIn("counts", payload)

    def test_update_route_schedules_external_bootstrap(self) -> None:
        scheduled = {
            "ok": True,
            "scheduled": True,
            "bootstrap_pid": 8100,
            "message": "scheduled",
        }
        with patch("backend.app.routers.updates.schedule_supervised_update", return_value=scheduled) as schedule:
            response = TestClient(app).post(
                "/updates/apply",
                content="confirm_update=true",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["scheduled"])
        schedule.assert_called_once()

    def test_update_frontend_tolerates_bounded_backend_restart(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "update_progress.js").read_text(encoding="utf-8")
        template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn("UPDATE_TIMEOUT_MS", source)
        self.assertIn("/runtime/identity", source)
        self.assertIn("window.location.replace", source)
        self.assertIn("автоматически перезапустится", template)
        self.assertNotIn("после обновления нужно перезапустить", template)


class SupervisedUpdateIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.install_root = self.root / "install"
        self.registry = self.root / "runtime"
        self.data_root = self.root / "data"
        (self.data_root / "database").mkdir(parents=True)
        (self.data_root / "database" / "MyDatabase.sqlite").touch()
        shutil.copytree(ROOT / "backend", self.install_root / "backend", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (self.install_root / "scripts").mkdir()
        for name in ("runtime_server.py", "runtime_bootstrap.py"):
            shutil.copy2(ROOT / "scripts" / name, self.install_root / "scripts" / name)
        self._write_version(self.install_root, "9.0.0")
        self.manifest = self.root / "latest.json"
        self.manifest.write_text('{"version":"9.0.0"}\n', encoding="utf-8")
        handler = lambda *args, **kwargs: QuietFileHandler(*args, directory=str(self.root), **kwargs)
        self.manifest_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.manifest_thread = threading.Thread(target=self.manifest_server.serve_forever, daemon=True)
        self.manifest_thread.start()
        self.manifest_url = f"http://127.0.0.1:{self.manifest_server.server_port}/latest.json"
        self.port = free_port()
        self.environment = patch.dict(
            os.environ,
            {
                "APP_RUNTIME_DIR": str(self.registry),
                "APP_INSTALL_DIR": str(self.install_root),
                "APP_HOST": "127.0.0.1",
                "APP_PORT": str(self.port),
                "REWARDS_DATA_DIR": str(self.data_root),
                "REWARDS_DB_PATH": str(self.data_root / "database" / "MyDatabase.sqlite"),
                "READ_ONLY": "true",
                "WRITE_MODE": "false",
                "UPDATE_CHECK_ENABLED": "true",
                "UPDATE_MANIFEST_URL": self.manifest_url,
            },
        )
        self.environment.start()
        self.supervisor = RuntimeSupervisor(
            registry_dir=self.registry,
            python_executable=Path(sys.executable),
            ready_timeout=8,
        )
        self.settings = Settings(
            rewards_data_dir=self.data_root,
            rewards_db_path=self.data_root / "database" / "MyDatabase.sqlite",
            app_host="127.0.0.1",
            app_port=self.port,
            read_only=True,
            write_mode=False,
            update_check_enabled=True,
            update_manifest_url=self.manifest_url,
            update_timeout_seconds=10,
            app_install_dir=self.install_root,
            update_backup_dir=self.install_root / "updates" / "backups",
            update_download_dir=self.install_root / "updates" / "downloads",
            update_extract_dir=self.install_root / "updates" / "extracted",
        )

    def tearDown(self) -> None:
        try:
            self.supervisor.stop_all_confirmed()
        except RuntimeLifecycleError:
            pass
        self.manifest_server.shutdown()
        self.manifest_server.server_close()
        self.manifest_thread.join(timeout=2)
        self.environment.stop()
        self.temporary.cleanup()

    @staticmethod
    def _write_version(root: Path, version: str) -> None:
        (root / "backend" / "app" / "version.py").write_text(
            f'APP_NAME = "Test"\nAPP_VERSION = "{version}"\nAPP_VERSION_DATE = "2026-07-21"\n',
            encoding="utf-8",
        )

    def _package(self, version: str) -> tuple[Path, str]:
        path = self.root / f"update-{version}.zip"
        with ZipFile(path, "w") as archive:
            archive.writestr(
                "FedorinovRewards_WebPreview/backend/app/version.py",
                f'APP_NAME = "Test"\nAPP_VERSION = "{version}"\nAPP_VERSION_DATE = "2026-07-21"\n',
            )
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def _plan_and_downloader(self, version: str):
        package, checksum = self._package(version)

        def plan_builder(_settings: Settings, current: str) -> UpdatePlan:
            return UpdatePlan(current, version, True, "https://example.test/update.zip", checksum, ["test"])

        def downloader(_url: str, destination: Path, _timeout: int) -> Path:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(package, destination)
            return destination

        return plan_builder, downloader

    @staticmethod
    def no_dependencies(_root: Path, _python: Path) -> float:
        return 0.0

    def _start_old(self):
        return self.supervisor.start_or_reuse(
            install_root=self.install_root,
            host="127.0.0.1",
            port=self.port,
            expected_version="9.0.0",
        )

    def test_managed_http_route_schedules_bootstrap_without_self_deadlock(self) -> None:
        old = self._start_old()
        body = urllib.parse.urlencode({"confirm_update": "true"}).encode("ascii")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/updates/apply",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
        self.assertTrue(result["scheduled"])
        bootstrap_pid = int(result["bootstrap_pid"])
        bootstrap_snapshot = process_snapshot(bootstrap_pid)

        deadline = time.monotonic() + 5
        status = {}
        while time.monotonic() < deadline:
            with opener.open(f"http://127.0.0.1:{self.port}/updates/status", timeout=1) as response:
                status = json.loads(response.read().decode("utf-8"))
            if status.get("status") != "running":
                break
            time.sleep(0.05)
        self.assertEqual(status.get("status"), "success")
        self.assertEqual(fetch_runtime_identity("127.0.0.1", self.port)["pid"], old.pid)
        deadline = time.monotonic() + 3
        while (
            bootstrap_snapshot is not None
            and process_is_same(bootstrap_pid, bootstrap_snapshot.start_marker)
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertFalse(
            bootstrap_snapshot is not None and process_is_same(bootstrap_pid, bootstrap_snapshot.start_marker)
        )

    def test_http_update_replaces_live_backend_and_serves_new_identity(self) -> None:
        package, checksum = self._package("9.0.1")
        self.manifest.write_text(
            json.dumps(
                {
                    "version": "9.0.1",
                    "download_url": package.as_uri(),
                    "sha256": checksum,
                    "notes": ["test"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        old = self._start_old()
        old_marker = process_snapshot(old.pid).start_marker
        body = urllib.parse.urlencode({"confirm_update": "true"}).encode("ascii")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/updates/apply",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            scheduled = json.loads(response.read().decode("utf-8"))
        self.assertTrue(scheduled["scheduled"])
        bootstrap_pid = int(scheduled["bootstrap_pid"])
        bootstrap_snapshot = process_snapshot(bootstrap_pid)

        deadline = time.monotonic() + 20
        identity = None
        status = None
        while time.monotonic() < deadline:
            identity = fetch_runtime_identity("127.0.0.1", self.port, 0.2)
            if identity and identity.get("version") == "9.0.1":
                try:
                    with opener.open(f"http://127.0.0.1:{self.port}/updates/status", timeout=1) as response:
                        status = json.loads(response.read().decode("utf-8"))
                except OSError:
                    status = None
                if status and status.get("status") == "success":
                    break
            time.sleep(0.1)

        self.assertIsNotNone(identity)
        self.assertEqual(identity["version"], "9.0.1")
        self.assertNotEqual(identity["pid"], old.pid)
        self.assertFalse(process_is_same(old.pid, old_marker))
        old.process.wait(timeout=2)
        self.assertEqual(status["status"], "success")
        self.assertEqual(len([item for item in self.supervisor.inspect_all() if item.confirmed and item.healthy]), 1)
        deadline = time.monotonic() + 3
        while (
            bootstrap_snapshot is not None
            and process_is_same(bootstrap_pid, bootstrap_snapshot.start_marker)
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertFalse(
            bootstrap_snapshot is not None and process_is_same(bootstrap_pid, bootstrap_snapshot.start_marker)
        )

    def test_launcher_wait_hands_off_from_forced_old_pid_to_new_backend(self) -> None:
        package, checksum = self._package("9.0.1")
        self.manifest.write_text(
            json.dumps(
                {
                    "version": "9.0.1",
                    "download_url": package.as_uri(),
                    "sha256": checksum,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        launcher_log_path = self.root / "launcher.log"
        launcher_log = launcher_log_path.open("wb")
        launcher = subprocess.Popen(
            [sys.executable, str(self.install_root / "scripts" / "runtime_bootstrap.py"), "start", "--wait"],
            cwd=self.install_root,
            env=os.environ.copy(),
            stdout=launcher_log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 8
            old_identity = None
            while time.monotonic() < deadline:
                old_identity = fetch_runtime_identity("127.0.0.1", self.port, 0.15)
                if old_identity and old_identity.get("version") == "9.0.0":
                    break
                time.sleep(0.05)
            self.assertIsNotNone(old_identity)

            body = urllib.parse.urlencode({"confirm_update": "true"}).encode("ascii")
            request = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/updates/apply",
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            scheduled_result: dict[str, object]
            try:
                with opener.open(request, timeout=3) as response:
                    scheduled_result = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(scheduled_result["scheduled"])
            except http.client.RemoteDisconnected:
                scheduled_result = {"remote_disconnected": True}

            deadline = time.monotonic() + 20
            new_identity = None
            observed_identities: list[dict[str, object]] = []
            while time.monotonic() < deadline:
                new_identity = fetch_runtime_identity("127.0.0.1", self.port, 0.15)
                if new_identity and (not observed_identities or observed_identities[-1] != new_identity):
                    observed_identities.append(new_identity)
                if new_identity and new_identity.get("version") == "9.0.1":
                    break
                time.sleep(0.1)
            if new_identity is None:
                launcher_log.flush()
                diagnostics = {
                    str(path.relative_to(self.root)): path.read_text(encoding="utf-8", errors="replace")
                    for path in sorted(self.root.rglob("*.log"))
                }
                diagnostics["request-result"] = json.dumps(scheduled_result, ensure_ascii=False)
                diagnostics["launcher-returncode"] = json.dumps(launcher.poll())
                old_snapshot = process_snapshot(int(old_identity["pid"]))
                diagnostics["old-process"] = json.dumps(
                    old_snapshot.__dict__ if old_snapshot is not None else None,
                    ensure_ascii=False,
                    default=str,
                )
                records, invalid_records = read_runtime_records(self.registry)
                diagnostics["observed-identities"] = json.dumps(
                    observed_identities, ensure_ascii=False, default=str
                )
                diagnostics["listener-pids"] = json.dumps(sorted(listener_pids("127.0.0.1", self.port)))
                diagnostics["registry-records"] = json.dumps(
                    [record.__dict__ for record in records], ensure_ascii=False, default=str
                )
                diagnostics["invalid-registry-records"] = json.dumps([str(path) for path in invalid_records])
                status_path = self.install_root / "updates" / "update_status.json"
                if status_path.is_file():
                    diagnostics[str(status_path.relative_to(self.root))] = status_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                self.fail(diagnostics)
            self.assertNotEqual(new_identity["pid"], old_identity["pid"])
            time.sleep(0.3)
            self.assertIsNone(launcher.poll())

            self.supervisor.stop_all_confirmed()
            self.assertEqual(launcher.wait(timeout=3), 0)
        finally:
            if launcher.poll() is None:
                launcher.terminate()
                launcher.wait(timeout=3)
            launcher_log.close()

    def test_live_old_backend_is_replaced_by_exact_new_version(self) -> None:
        old = self._start_old()
        old_marker = process_snapshot(old.pid).start_marker
        plan_builder, downloader = self._plan_and_downloader("9.0.1")
        result = run_supervised_update(
            self.settings,
            requester_pid=old.pid,
            current_version="9.0.0",
            supervisor=self.supervisor,
            plan_builder=plan_builder,
            zip_downloader=downloader,
            dependency_installer=self.no_dependencies,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["latest_version"], "9.0.1")
        self.assertNotEqual(result["new_pid"], old.pid)
        self.assertFalse(process_is_same(old.pid, old_marker))
        identity = fetch_runtime_identity("127.0.0.1", self.port)
        self.assertEqual(identity["version"], "9.0.1")
        self.assertEqual(identity["pid"], result["new_pid"])
        self.assertEqual(identity["install_root"], str(self.install_root.resolve()))
        self.assertEqual(read_update_status(self.settings)["status"], "success")
        self.assertTrue(Path(str(result["backup_path"])).is_file())
        timings = result["process_timings"]
        self.assertLess(timings["termination_seconds"], 2.0)
        self.assertLess(timings["port_release_seconds"], 2.0)
        self.assertLess(timings["readiness_seconds"], 5.0)
        self.assertEqual(timings["dependency_seconds"], 0.0)

    def test_update_stops_two_old_install_roots_before_one_new_backend(self) -> None:
        old = self._start_old()
        old_marker = process_snapshot(old.pid).start_marker
        previous_root = (self.root / "previous-install").resolve()
        shutil.copytree(self.install_root, previous_root, ignore=shutil.ignore_patterns("updates", "__pycache__", "*.pyc"))
        previous_port = free_port()
        previous_build_id = runtime_build_id(previous_root)
        process, token, state_path, _log = self.supervisor._spawn_backend(
            install_root=previous_root,
            host="127.0.0.1",
            port=previous_port,
            version="9.0.0",
            build_id=previous_build_id,
        )
        self.supervisor._wait_ready(
            process=process,
            token=token,
            state_path=state_path,
            install_root=previous_root,
            host="127.0.0.1",
            port=previous_port,
            version="9.0.0",
            build_id=previous_build_id,
        )
        previous_marker = process_snapshot(process.pid).start_marker
        plan_builder, downloader = self._plan_and_downloader("9.0.1")

        result = run_supervised_update(
            self.settings,
            requester_pid=old.pid,
            current_version="9.0.0",
            supervisor=self.supervisor,
            plan_builder=plan_builder,
            zip_downloader=downloader,
            dependency_installer=self.no_dependencies,
        )

        self.assertEqual(set(result["old_pids"]), {old.pid, process.pid})
        self.assertFalse(process_is_same(old.pid, old_marker))
        self.assertFalse(process_is_same(process.pid, previous_marker))
        self.assertEqual(len([item for item in self.supervisor.inspect_all() if item.confirmed and item.healthy]), 1)

    def test_failed_new_start_rolls_back_to_one_old_backend(self) -> None:
        old = self._start_old()
        plan_builder, downloader = self._plan_and_downloader("9.0.1")
        real = self.supervisor

        class FailNewOnce:
            python_executable = real.python_executable

            def __init__(self) -> None:
                self.failed = False

            def inspect_all(self):
                return real.inspect_all()

            def stop_all_confirmed(self):
                return real.stop_all_confirmed()

            def start_or_reuse(self, **kwargs):
                if kwargs["expected_version"] == "9.0.1" and not self.failed:
                    self.failed = True
                    raise RuntimeLifecycleError("controlled new-start failure")
                return real.start_or_reuse(**kwargs)

        with self.assertRaisesRegex(UpdateError, "Предыдущая версия восстановлена"):
            run_supervised_update(
                self.settings,
                requester_pid=old.pid,
                current_version="9.0.0",
                supervisor=FailNewOnce(),
                plan_builder=plan_builder,
                zip_downloader=downloader,
                dependency_installer=self.no_dependencies,
            )

        identity = fetch_runtime_identity("127.0.0.1", self.port)
        self.assertEqual(identity["version"], "9.0.0")
        confirmed = [item for item in real.inspect_all() if item.confirmed and item.healthy]
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].record.pid, identity["pid"])
        status = read_update_status(self.settings)
        self.assertEqual(status["status"], "error")
        self.assertIn("Предыдущая версия восстановлена", status["message"])


if __name__ == "__main__":
    unittest.main()
