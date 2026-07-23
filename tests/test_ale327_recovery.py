from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from backend.app.services.runtime_supervisor import RuntimeLifecycleError
from scripts import (
    build_recovery_package,
    check_recovery_package_safety,
    recovery_v206,
    recovery_v207,
    runtime_bootstrap,
    runtime_server,
)


ROOT = Path(__file__).resolve().parents[1]


class ScriptedUI:
    def __init__(self, *, answers: list[str] | None = None, confirmations: list[bool] | None = None, folder=None):
        self.answers = list(answers or [])
        self.confirmations = list(confirmations or [])
        self.folder = folder
        self.messages: list[str] = []

    def show(self, message: str = "") -> None:
        self.messages.append(message)

    def ask(self, _prompt: str) -> str:
        return self.answers.pop(0)

    def confirm(self, _prompt: str) -> bool:
        return self.confirmations.pop(0)

    def pick_folder(self) -> Path | None:
        return self.folder


class Ale327RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _install(self, name: str, *, version: str = "2.0.5") -> recovery_v206.InstallationCandidate:
        install = self.root / name
        data = self.root / f"{name}-data"
        for relative in recovery_v206.REQUIRED_INSTALL_FILES:
            path = install / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")
        (install / "backend/app/version.py").write_text(
            f'APP_NAME = "{recovery_v206.PRODUCT_NAME}"\nAPP_VERSION = "{version}"\nAPP_VERSION_DATE = "2026-07-22"\n',
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "backend/requirements.txt", install / "backend/requirements.txt")
        shutil.copy2(ROOT / "scripts/runtime_server.py", install / "scripts/runtime_server.py")
        shutil.copy2(ROOT / "scripts/runtime_bootstrap.py", install / "scripts/runtime_bootstrap.py")
        for dirname in ("database", "Source", "SourceMark", "default"):
            (data / dirname).mkdir(parents=True)
        (data / "database/MyDatabase.sqlite").write_bytes(b"owner database")
        (data / "Source/1").mkdir()
        (data / "Source/1/photo.jpg").write_bytes(b"owner photo")
        (install / ".env").write_text(
            f"REWARDS_DATA_DIR={data}\nAPP_HOST=127.0.0.1\nAPP_PORT=18080\n",
            encoding="utf-8",
        )
        candidate = recovery_v206.validate_installation(
            install,
            supported_versions=recovery_v206.SUPPORTED_SOURCE_VERSIONS,
        )
        self.assertIsNotNone(candidate)
        return candidate

    def _new_package_root(self) -> Path:
        package = self.root / "package"
        (package / "backend/app").mkdir(parents=True)
        (package / "backend/app/version.py").write_text(
            f'APP_NAME = "{recovery_v206.PRODUCT_NAME}"\nAPP_VERSION = "2.0.6"\nAPP_VERSION_DATE = "2026-07-22"\n',
            encoding="utf-8",
        )
        (package / "backend/requirements.txt").parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "backend/requirements.txt", package / "backend/requirements.txt")
        (package / "new-only.txt").write_text("new\n", encoding="utf-8")
        return package

    def _package(self) -> recovery_v206.RecoveryPackage:
        path = self.root / "main.zip"
        path.write_bytes(b"package")
        return recovery_v206.RecoveryPackage(
            "2.0.6",
            path,
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            recovery_v206.sha256_file(ROOT / "backend/requirements.txt"),
        )

    @staticmethod
    def _runtime(candidate, version: str) -> recovery_v206.StartedRuntime:
        return recovery_v206.StartedRuntime(
            pid=9012,
            instance_token="a" * 32,
            version=version,
            build_id="b" * 64,
            install_root=str(candidate.install_root),
            host=candidate.host,
            port=candidate.port,
            state_path=Path("state.json"),
            startup_path=Path("startup.json") if version == "2.0.6" else None,
            log_path=Path("runtime.log"),
        )

    def test_public_v205_legacy_argv_derives_app_owned_startup_path(self) -> None:
        token = "a" * 32
        registry = self.root / "runtime"
        state = registry / f"backend-{token}.json"
        args = runtime_server._parser().parse_args(
            [
                "--host", "127.0.0.1", "--port", "8080", "--install-root", str(ROOT),
                "--instance-token", token, "--state-path", str(state),
                "--expected-version", "2.0.6", "--expected-build-id", "b" * 64,
            ]
        )
        self.assertIsNone(args.startup_path)
        with patch.dict(os.environ, {"APP_RUNTIME_DIR": str(registry)}):
            resolved_state, startup = runtime_server._resolve_runtime_paths(args.state_path, None, token)
        self.assertEqual(resolved_state, state.resolve(strict=False))
        self.assertEqual(startup, (registry / f"startup-{token}.json").resolve(strict=False))

    def test_public_v205_legacy_runtime_preloads_before_identity_publication(self) -> None:
        source = (ROOT / "scripts/runtime_server.py").read_text(encoding="utf-8")

        preload = source.index('reporter.stage("preloading-legacy-server")')
        register = source.index('reporter.stage("registering-identity")')
        regular_load = source.index('reporter.stage("loading-server")')

        self.assertLess(preload, register)
        self.assertLess(register, regular_load)
        self.assertIn("if legacy_runtime_contract:", source[preload - 80:preload])

    def test_runtime_paths_reject_wrong_state_or_explicit_startup(self) -> None:
        token = "a" * 32
        registry = self.root / "runtime"
        with patch.dict(os.environ, {"APP_RUNTIME_DIR": str(registry)}), self.assertRaisesRegex(
            RuntimeError, "state path mismatch"
        ):
            runtime_server._resolve_runtime_paths(registry / "backend-wrong.json", None, token)
        state = registry / f"backend-{token}.json"
        with patch.dict(os.environ, {"APP_RUNTIME_DIR": str(registry)}), self.assertRaisesRegex(
            RuntimeError, "startup path mismatch"
        ):
            runtime_server._resolve_runtime_paths(state, registry / "other.json", token)
        with patch.dict(os.environ, {"APP_RUNTIME_DIR": str(self.root / "other-runtime")}), self.assertRaisesRegex(
            RuntimeError, "registry path mismatch"
        ):
            runtime_server._resolve_runtime_paths(state, None, token)

    def test_exactly_one_official_pointer_wins_over_bounded_scan(self) -> None:
        official = self._install("official")
        self._install("other")
        pointer = self.root / "installation.json"
        pointer.write_text(
            json.dumps(
                {
                    "application_id": recovery_v206.PRODUCT_ID,
                    "schema": recovery_v206.INSTALLATION_POINTER_SCHEMA,
                    "install_root": str(official.install_root),
                }
            ),
            encoding="utf-8",
        )
        candidates, source = recovery_v206.discover_installations(
            pointer_path=pointer,
            registry_dir=self.root / "empty-runtime",
            scan_roots=[self.root],
        )
        self.assertEqual(source, "official-pointer")
        self.assertEqual([item.install_root for item in candidates], [official.install_root])

    def test_multiple_installations_require_explicit_number_and_confirmation(self) -> None:
        first = self._install("copy-a")
        second = self._install("copy-b")
        ui = ScriptedUI(answers=["2"], confirmations=[True])
        selected = recovery_v206.select_installation([first, second], ui)
        self.assertEqual(selected.install_root, second.install_root)
        self.assertIn(str(first.install_root), "\n".join(ui.messages))
        self.assertIn(str(second.install_root), "\n".join(ui.messages))

    def test_multiple_installations_reject_zero_instead_of_selecting_last(self) -> None:
        first = self._install("copy-zero-a")
        second = self._install("copy-zero-b")
        ui = ScriptedUI(answers=["0"])
        with self.assertRaises(recovery_v206.RecoveryCancelled):
            recovery_v206.select_installation([first, second], ui)

    def test_no_installation_uses_picker_and_invalid_selection_has_no_mutation(self) -> None:
        invalid = self.root / "not-an-install"
        invalid.mkdir()
        before = list(invalid.iterdir())
        ui = ScriptedUI(folder=invalid)
        with self.assertRaises(recovery_v206.RecoveryCancelled):
            recovery_v206.select_installation([], ui)
        self.assertEqual(list(invalid.iterdir()), before)

    def test_picker_validates_and_confirms_exact_installation(self) -> None:
        candidate = self._install("picked")
        ui = ScriptedUI(folder=candidate.install_root, confirmations=[True])
        selected = recovery_v206.select_installation([], ui)
        self.assertEqual(selected.install_root, candidate.install_root)

    def test_v207_native_picker_cancel_does_not_open_second_dialog(self) -> None:
        completed = recovery_v207.subprocess.CompletedProcess([], 0, stdout="", stderr="")

        with (
            patch.object(recovery_v207.os, "name", "nt"),
            patch.object(recovery_v207.shutil, "which", return_value="powershell.exe"),
            patch.object(recovery_v207.subprocess, "run", return_value=completed) as run,
        ):
            selected = recovery_v207.ConsoleUI().pick_folder()

        self.assertIsNone(selected)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_program_install_rejects_symlink_destination(self) -> None:
        selected = self._install("symlink-install")
        package_root = self._new_package_root()
        outside = self.root / "outside-version.py"
        outside.write_text("outside\n", encoding="utf-8")
        version_path = selected.install_root / "backend/app/version.py"
        version_path.unlink()
        version_path.symlink_to(outside)
        with self.assertRaisesRegex(recovery_v206.RecoveryError, "за пределы|недопустимую ссылку"):
            recovery_v206.create_verified_backup(
                selected,
                package_root,
                recovery_v206.fingerprint_data(selected),
            )
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")

    def test_stalled_candidate_is_terminated_before_rollback(self) -> None:
        selected = self._install("stalled-candidate")

        class FakeProcess:
            pid = 9123
            returncode = None
            terminated = False
            killed = False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            def kill(self):
                self.killed = True
                self.returncode = -9

            def wait(self, timeout=None):
                return self.returncode

        process = FakeProcess()
        with patch.object(recovery_v206, "_runtime_build_id", return_value="b" * 64), patch.object(
            recovery_v206.subprocess, "Popen", return_value=process
        ):
            with self.assertRaisesRegex(recovery_v206.RecoveryError, "startup-stalled"):
                recovery_v206.start_runtime(
                    selected,
                    self.root / "runtime-stalled",
                    expected_version="2.0.6",
                    include_startup_path=True,
                    timeout=0,
                )
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)

    def test_transaction_updates_only_selected_install_and_preserves_data(self) -> None:
        selected = self._install("selected")
        neighbor = self._install("neighbor")
        package_root = self._new_package_root()
        package = self._package()
        neighbor_version_before = (neighbor.install_root / "backend/app/version.py").read_bytes()
        data_before = recovery_v206.fingerprint_data(selected)
        pointer = self.root / "pointer.json"
        runtime = self._runtime(selected, "2.0.6")

        def fake_start(candidate, _registry, *, expected_version, include_startup_path):
            self.assertEqual(candidate.install_root, selected.install_root)
            self.assertEqual(expected_version, "2.0.6")
            self.assertTrue(include_startup_path)
            return runtime

        identity = {
            "pid": runtime.pid,
            "instance_token": runtime.instance_token,
            "version": runtime.version,
            "build_id": runtime.build_id,
            "install_root": runtime.install_root,
            "host": runtime.host,
            "port": runtime.port,
        }
        with patch.object(recovery_v206, "_run_internal_stop", return_value={"stopped": []}), patch.object(
            recovery_v206, "_fetch_identity", return_value=identity
        ), patch.dict(os.environ, {"APP_INSTALLATION_POINTER": str(pointer)}):
            result = recovery_v206.run_recovery_transaction(
                selected,
                package,
                package_root,
                registry_dir=self.root / "runtime",
                start_fn=fake_start,
                repeat_fn=lambda *_args: {"reused": True},
            )

        self.assertTrue(result["ok"])
        self.assertIn('APP_VERSION = "2.0.6"', (selected.install_root / "backend/app/version.py").read_text())
        self.assertTrue((selected.install_root / "new-only.txt").is_file())
        self.assertEqual(recovery_v206.fingerprint_data(selected), data_before)
        self.assertEqual((neighbor.install_root / "backend/app/version.py").read_bytes(), neighbor_version_before)
        self.assertTrue(pointer.is_file())

    def test_candidate_failure_restores_v205_and_removes_new_files(self) -> None:
        selected = self._install("rollback")
        package_root = self._new_package_root()
        package = self._package()
        old_version_bytes = (selected.install_root / "backend/app/version.py").read_bytes()
        data_before = recovery_v206.fingerprint_data(selected)
        calls: list[str] = []

        def fake_start(candidate, _registry, *, expected_version, include_startup_path):
            calls.append(expected_version)
            if expected_version == "2.0.6":
                raise recovery_v206.RecoveryError("forced candidate failure")
            self.assertFalse(include_startup_path)
            return self._runtime(candidate, expected_version)

        with patch.object(recovery_v206, "_run_internal_stop", return_value={"stopped": []}):
            with self.assertRaisesRegex(recovery_v206.RecoveryError, "Предыдущая v2.0.5 восстановлена"):
                recovery_v206.run_recovery_transaction(
                    selected,
                    package,
                    package_root,
                    registry_dir=self.root / "runtime",
                    start_fn=fake_start,
                )
        self.assertEqual(calls, ["2.0.6", "2.0.5"])
        self.assertEqual((selected.install_root / "backend/app/version.py").read_bytes(), old_version_bytes)
        self.assertFalse((selected.install_root / "new-only.txt").exists())
        self.assertEqual(recovery_v206.fingerprint_data(selected), data_before)

    def test_recovery_builder_and_safety_enforce_five_expected_members(self) -> None:
        dist = self.root / "dist"
        dist.mkdir()
        main_zip = dist / "FedorinovRewards_WebPreview_v2.0.6.zip"
        with ZipFile(main_zip, "w") as archive:
            archive.writestr("FedorinovRewards_WebPreview/backend/app/version.py", 'APP_VERSION = "2.0.6"\n')
            archive.writestr(
                "FedorinovRewards_WebPreview/backend/requirements.txt",
                (ROOT / "backend/requirements.txt").read_bytes(),
            )
            archive.writestr("FedorinovRewards_WebPreview/start_windows.bat", "@echo off\n")
        with patch.object(build_recovery_package, "DIST_ROOT", dist):
            result = build_recovery_package.build_recovery_package("2.0.6", main_package=main_zip)
        recovery_zip = Path(result["zip_path"])
        safety = check_recovery_package_safety.check_recovery_package(recovery_zip)
        self.assertTrue(safety["safe"])
        self.assertEqual(safety["members"], 5)
        with ZipFile(recovery_zip) as archive:
            self.assertEqual(
                {name for name in archive.namelist() if not name.endswith("/")},
                check_recovery_package_safety.ROOT_FILES | check_recovery_package_safety.SERVICE_FILES,
            )

    def test_v207_bootstrap_is_ascii_crlf_and_parser_minimal(self) -> None:
        dist = self.root / "dist-v207"
        dist.mkdir()
        main_zip = dist / "FedorinovRewards_WebPreview_v2.0.7.zip"
        with ZipFile(main_zip, "w") as archive:
            archive.writestr(
                "FedorinovRewards_WebPreview/backend/app/version.py",
                f'APP_NAME = "{recovery_v207.PRODUCT_NAME}"\nAPP_VERSION = "2.0.7"\n',
            )
            archive.writestr(
                "FedorinovRewards_WebPreview/backend/requirements.txt",
                (ROOT / "backend/requirements.txt").read_bytes(),
            )
            archive.writestr("FedorinovRewards_WebPreview/start_windows.bat", "@echo off\n")
        with patch.object(build_recovery_package, "DIST_ROOT", dist):
            result = build_recovery_package.build_recovery_package("2.0.7", main_package=main_zip)
        recovery_zip = Path(result["zip_path"])
        safety = check_recovery_package_safety.check_recovery_package(recovery_zip)
        self.assertTrue(safety["safe"])
        with ZipFile(recovery_zip) as archive:
            names = {name for name in archive.namelist() if not name.endswith("/")}
            self.assertEqual(
                names,
                check_recovery_package_safety.expected_root_files("2.0.7")
                | check_recovery_package_safety.expected_service_files("2.0.7"),
            )
            bootstrap = archive.read("ВОССТАНОВИТЬ_И_ЗАПУСТИТЬ_2.0.7.bat")
            manifest = json.loads(archive.read("service/manifest.json"))
        self.assertTrue(bootstrap.isascii())
        self.assertFalse(bootstrap.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(bootstrap.count(b"\n"), bootstrap.count(b"\r\n"))
        self.assertNotIn(b"(", bootstrap)
        self.assertNotIn(b")", bootstrap)
        self.assertNotIn(b"chcp", bootstrap.lower())
        self.assertEqual(manifest["supported_source_versions"], ["2.0.5", "2.0.6"])

    def test_v207_accepts_only_supported_recovery_sources(self) -> None:
        for version in ("2.0.5", "2.0.6"):
            install = self._install(f"supported-{version}")
            (install.install_root / "backend/app/version.py").write_text(
                f'APP_NAME = "{recovery_v207.PRODUCT_NAME}"\nAPP_VERSION = "{version}"\n',
                encoding="utf-8",
            )
            candidate = recovery_v207.validate_installation(
                install.install_root,
                supported_versions=recovery_v207.SUPPORTED_SOURCE_VERSIONS,
            )
            self.assertIsNotNone(candidate)
        unsupported = self._install("unsupported")
        (unsupported.install_root / "backend/app/version.py").write_text(
            f'APP_NAME = "{recovery_v207.PRODUCT_NAME}"\nAPP_VERSION = "2.0.4"\n',
            encoding="utf-8",
        )
        self.assertIsNone(
            recovery_v207.validate_installation(
                unsupported.install_root,
                supported_versions=recovery_v207.SUPPORTED_SOURCE_VERSIONS,
            )
        )

    def test_v207_cancel_precedes_backup_and_all_mutation(self) -> None:
        selected = self._install("cancel-before-mutation")
        (selected.install_root / "backend/app/version.py").write_text(
            f'APP_NAME = "{recovery_v207.PRODUCT_NAME}"\nAPP_VERSION = "2.0.6"\n',
            encoding="utf-8",
        )
        selected = recovery_v207.validate_installation(
            selected.install_root,
            supported_versions=recovery_v207.SUPPORTED_SOURCE_VERSIONS,
        )
        self.assertIsNotNone(selected)
        ui = ScriptedUI(confirmations=[False])
        before = {
            str(path.relative_to(selected.install_root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in selected.install_root.rglob("*")
            if path.is_file()
        }
        with self.assertRaises(recovery_v207.RecoveryCancelled):
            recovery_v207.select_installation([selected], ui)
        after = {
            str(path.relative_to(selected.install_root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in selected.install_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_runtime_bootstrap_machine_json_is_cp1252_safe_and_round_trips_cyrillic(self) -> None:
        payload = {"install_root": r"C:\Users\Alex\Desktop\Проверка восстановления"}

        encoded = runtime_bootstrap._machine_json(payload)

        encoded.encode("cp1252")
        self.assertTrue(encoded.isascii())
        self.assertEqual(json.loads(encoded), payload)

    def test_runtime_bootstrap_retries_only_typed_process_inspection_transient(self) -> None:
        expected = object()

        class FakeSupervisor:
            calls = 0

            def start_or_reuse(self, **_kwargs):
                self.calls += 1
                if self.calls < runtime_bootstrap.PROCESS_INSPECTION_RETRY_ATTEMPTS:
                    raise RuntimeLifecycleError(
                        "strict HTTP identity healthy; Windows inspection transient",
                        category="process-inspection-transient",
                    )
                return expected

        supervisor = FakeSupervisor()
        result = runtime_bootstrap._start_or_reuse_with_retry(
            supervisor,
            install_root=self.root,
            host="127.0.0.1",
            port=18080,
            expected_version="2.0.7",
        )

        self.assertIs(result, expected)
        self.assertEqual(supervisor.calls, runtime_bootstrap.PROCESS_INSPECTION_RETRY_ATTEMPTS)

    def test_v207_recovery_uses_base_process_without_losing_venv_identity(self) -> None:
        venv_root = self.root / "Windows recovery venv"
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

        executable, environment = recovery_v207._windows_runtime_python_spawn(venv_python)

        self.assertEqual(executable, base_python.absolute())
        self.assertEqual(environment, {"__PYVENV_LAUNCHER__": str(venv_python.absolute())})

    def test_v207_stop_verifies_live_child_after_empty_internal_stop(self) -> None:
        selected = self._install("empty-internal-stop")

        class FakeProcess:
            pid = 9123
            returncode = None
            terminated = False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.returncode = -15

            def kill(self):
                self.returncode = -9

            def wait(self, timeout=None):
                return self.returncode

        process = FakeProcess()
        runtime = recovery_v207.StartedRuntime(
            pid=process.pid,
            instance_token="a" * 32,
            version="2.0.7",
            build_id="b" * 64,
            install_root=str(selected.install_root),
            host=selected.host,
            port=selected.port,
            state_path=self.root / "state.json",
            startup_path=self.root / "startup.json",
            log_path=self.root / "runtime.log",
            process=process,
        )
        identity = {
            "pid": runtime.pid,
            "instance_token": runtime.instance_token,
            "version": runtime.version,
            "build_id": runtime.build_id,
            "install_root": runtime.install_root,
            "host": runtime.host,
            "port": runtime.port,
        }

        with patch.object(recovery_v207, "_run_internal_stop", return_value={"stopped": []}), patch.object(
            recovery_v207, "_fetch_identity", side_effect=[identity, None]
        ):
            recovery_v207._stop_started_runtime(selected, self.root / "runtime", runtime)

        self.assertTrue(process.terminated)
        self.assertEqual(process.poll(), -15)

    def test_v207_stop_does_not_kill_child_when_http_identity_changed(self) -> None:
        selected = self._install("mismatched-stop-identity")

        class FakeProcess:
            pid = 9124
            returncode = None
            terminated = False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True

            def kill(self):
                self.terminated = True

            def wait(self, timeout=None):
                return self.returncode

        process = FakeProcess()
        runtime = recovery_v207.StartedRuntime(
            pid=process.pid,
            instance_token="a" * 32,
            version="2.0.7",
            build_id="b" * 64,
            install_root=str(selected.install_root),
            host=selected.host,
            port=selected.port,
            state_path=self.root / "state.json",
            startup_path=self.root / "startup.json",
            log_path=self.root / "runtime.log",
            process=process,
        )
        mismatched = {
            "pid": runtime.pid + 1,
            "instance_token": runtime.instance_token,
            "version": runtime.version,
            "build_id": runtime.build_id,
            "install_root": runtime.install_root,
            "host": runtime.host,
            "port": runtime.port,
        }

        with patch.object(recovery_v207, "_run_internal_stop", return_value={"stopped": []}), patch.object(
            recovery_v207, "_fetch_identity", return_value=mismatched
        ), self.assertRaisesRegex(recovery_v207.RecoveryError, "identity"):
            recovery_v207._stop_started_runtime(selected, self.root / "runtime", runtime)

        self.assertFalse(process.terminated)

    def test_v207_rollback_retries_only_public_v205_self_inspection_crash(self) -> None:
        selected = self._install("v205-self-inspection-retry")
        restored = self._runtime(selected, "2.0.5")
        attempts = 0

        def start_fn(*_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise recovery_v207.RecoveryError(
                    "Новая версия не запустилась: child-crash; "
                    "Cannot inspect the backend process being registered."
                )
            return restored

        with patch.object(recovery_v207, "_port_has_listener", return_value=False):
            result = recovery_v207._start_restored_runtime(
                selected,
                self.root / "runtime",
                start_fn=start_fn,
            )

        self.assertIs(result, restored)
        self.assertEqual(attempts, 3)

    def test_v207_rollback_does_not_retry_other_child_crash(self) -> None:
        selected = self._install("other-child-crash")
        attempts = 0

        def start_fn(*_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            raise recovery_v207.RecoveryError("Новая версия не запустилась: child-crash; import failed")

        with patch.object(recovery_v207, "_port_has_listener", return_value=False), self.assertRaisesRegex(
            recovery_v207.RecoveryError, "import failed"
        ):
            recovery_v207._start_restored_runtime(
                selected,
                self.root / "runtime",
                start_fn=start_fn,
            )

        self.assertEqual(attempts, 1)

    def test_v207_repeat_launch_decodes_utf8_failure_without_masking_it(self) -> None:
        selected = self._install("utf8-repeat-failure")
        runtime = self._runtime(selected, "2.0.7")
        completed = recovery_v207.subprocess.CompletedProcess(
            [],
            1,
            stdout="",
            stderr="Не удалось строго подтвердить runtime",
        )

        with patch.object(recovery_v207.subprocess, "run", return_value=completed) as run:
            with self.assertRaisesRegex(recovery_v207.RecoveryError, "строго подтвердить runtime"):
                recovery_v207.verify_repeat_launch(selected, self.root / "runtime", runtime)

        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")


if __name__ == "__main__":
    unittest.main()
