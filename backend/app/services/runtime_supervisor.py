from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
from typing import Any

from .runtime_identity import (
    LegacyRuntimeRecord,
    RuntimeIdentityError,
    RuntimeInspection,
    RuntimeRecord,
    RuntimeRegistryLock,
    fetch_runtime_identity,
    inspect_legacy_runtime,
    inspect_runtime_record,
    listener_pids,
    python_spawn_target,
    process_snapshot,
    read_runtime_records,
    runtime_build_id,
    runtime_registry_dir,
    runtime_state_path,
)
from .runtime_startup import read_runtime_startup, runtime_startup_path
from ..version import APP_NAME


class RuntimeLifecycleError(RuntimeError):
    def __init__(self, message: str, *, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _read_log_tail(path: Path, line_limit: int = 12) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return " | ".join(line.strip() for line in lines[-line_limit:] if line.strip())[-1800:]


@dataclass(frozen=True)
class StopEvidence:
    pid: int
    process_start_marker: str
    install_root: str
    version: str
    port: int
    instance_token: str
    attempts: int
    elapsed_seconds: float


@dataclass
class StartEvidence:
    pid: int
    install_root: str
    version: str
    build_id: str
    host: str
    port: int
    instance_token: str
    reused: bool
    detection_seconds: float
    termination_seconds: float
    port_release_seconds: float
    readiness_seconds: float
    spawned_at: str | None = None
    identity_seconds: float | None = None
    stopped: list[StopEvidence] = field(default_factory=list)
    log_path: str | None = None
    process: subprocess.Popen[bytes] | None = field(default=None, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "install_root": self.install_root,
            "version": self.version,
            "build_id": self.build_id,
            "host": self.host,
            "port": self.port,
            "instance_token": self.instance_token,
            "reused": self.reused,
            "detection_seconds": self.detection_seconds,
            "termination_seconds": self.termination_seconds,
            "port_release_seconds": self.port_release_seconds,
            "readiness_seconds": self.readiness_seconds,
            "spawned_at": self.spawned_at,
            "identity_seconds": self.identity_seconds,
            "stopped": [evidence.__dict__ for evidence in self.stopped],
            "log_path": self.log_path,
        }


def read_installed_version(install_root: Path) -> str:
    version_path = install_root / "backend" / "app" / "version.py"
    try:
        source = version_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeLifecycleError(f"Не удалось прочитать версию приложения: {exc}") from exc
    for line in source.splitlines():
        if "=" not in line or line.split("=", 1)[0].strip() != "APP_VERSION":
            continue
        value = line.split("=", 1)[1].strip().strip("\"'")
        if value:
            return value
    raise RuntimeLifecycleError("В установленном приложении не найдена APP_VERSION.")


def _port_has_listener(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.12):
            return True
    except OSError:
        return False


class RuntimeSupervisor:
    def __init__(
        self,
        *,
        registry_dir: Path | None = None,
        python_executable: Path | None = None,
        stop_timeout: float = 2.0,
        port_timeout: float = 2.0,
        ready_timeout: float = 5.0,
        startup_timeout: float = 30.0,
    ) -> None:
        self.registry_dir = (registry_dir or runtime_registry_dir()).resolve(strict=False)
        self.python_executable = (python_executable or Path(sys.executable)).expanduser().absolute()
        self.stop_timeout = max(0.1, stop_timeout)
        self.port_timeout = max(0.1, port_timeout)
        self.ready_timeout = max(0.2, ready_timeout)
        self.startup_timeout = max(self.ready_timeout, startup_timeout)
        self._children: dict[int, subprocess.Popen[bytes]] = {}

    def _reap_child(self, pid: int) -> None:
        child = self._children.pop(pid, None)
        if child is None:
            return
        try:
            child.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            self._children[pid] = child

    def _remove_state(self, path: str | Path) -> None:
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass

    def inspect_all(self) -> list[RuntimeInspection]:
        records, invalid = read_runtime_records(self.registry_dir)
        for path in invalid:
            self._remove_state(path)
        inspections: list[RuntimeInspection] = []
        for record in records:
            inspection = inspect_runtime_record(record)
            inspections.append(inspection)
            if not inspection.confirmed and not inspection.healthy:
                self._remove_state(record.state_path)
        return inspections

    @staticmethod
    def _record_matches_requested_runtime(
        record: RuntimeRecord,
        *,
        install_root: Path,
        host: str,
        port: int,
        version: str,
        build_id: str,
    ) -> bool:
        return (
            os.path.normcase(str(Path(record.install_root).resolve(strict=False)))
            == os.path.normcase(str(install_root.resolve(strict=False)))
            and record.host == host
            and record.port == port
            and record.version == version
            and record.build_id == build_id
        )

    @classmethod
    def _matches_requested_runtime(
        cls,
        inspection: RuntimeInspection,
        *,
        install_root: Path,
        host: str,
        port: int,
        version: str,
        build_id: str,
    ) -> bool:
        return (
            inspection.confirmed
            and inspection.healthy
            and cls._record_matches_requested_runtime(
                inspection.record,
                install_root=install_root,
                host=host,
                port=port,
                version=version,
                build_id=build_id,
            )
        )

    @staticmethod
    def _force_kill_pid(pid: int) -> None:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            if result.returncode not in {0, 128}:
                detail = (result.stderr or result.stdout).strip()
                raise RuntimeLifecycleError(f"Не удалось завершить подтверждённый backend PID {pid}: {detail}")
            return
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError as exc:
            raise RuntimeLifecycleError(f"Не удалось завершить подтверждённый backend PID {pid}: {exc}") from exc

    def _wait_process_gone(self, record: RuntimeRecord) -> bool:
        deadline = time.monotonic() + self.stop_timeout
        while time.monotonic() < deadline:
            inspection = inspect_runtime_record(record, health_timeout=0.05)
            if inspection.reason in {"process-not-running", "process-start-time-mismatch"}:
                self._reap_child(record.pid)
                return True
            time.sleep(0.04)
        return False

    def _force_stop_record(self, record: RuntimeRecord) -> StopEvidence:
        started = time.monotonic()
        attempts = 0
        for attempts in (1, 2):
            inspection = inspect_runtime_record(record, health_timeout=0.05)
            if not inspection.confirmed:
                if inspection.reason in {"process-not-running", "process-start-time-mismatch"}:
                    self._remove_state(record.state_path)
                    self._remove_state(runtime_startup_path(self.registry_dir, record.instance_token))
                    return StopEvidence(
                        record.pid,
                        record.process_start_marker,
                        record.install_root,
                        record.version,
                        record.port,
                        record.instance_token,
                        attempts - 1,
                        time.monotonic() - started,
                    )
                raise RuntimeLifecycleError(
                    f"PID {record.pid} больше не подтверждён как backend приложения ({inspection.reason}); процесс не завершён."
                )
            self._force_kill_pid(record.pid)
            if self._wait_process_gone(record):
                self._remove_state(record.state_path)
                self._remove_state(runtime_startup_path(self.registry_dir, record.instance_token))
                return StopEvidence(
                    record.pid,
                    record.process_start_marker,
                    record.install_root,
                    record.version,
                    record.port,
                    record.instance_token,
                    attempts,
                    time.monotonic() - started,
                )
        raise RuntimeLifecycleError(
            f"Подтверждённый backend PID {record.pid} не завершился после двух принудительных попыток."
        )

    def _force_stop_legacy(self, record: LegacyRuntimeRecord) -> StopEvidence:
        started = time.monotonic()
        attempts = 0
        for attempts in (1, 2):
            current = inspect_legacy_runtime(
                install_root=Path(record.install_root),
                host=record.host,
                port=record.port,
                expected_app_name=APP_NAME,
            )
            if current is None:
                snapshot = process_snapshot(record.pid)
                if snapshot is None or snapshot.start_marker != record.process_start_marker:
                    self._reap_child(record.pid)
                    return StopEvidence(
                        record.pid,
                        record.process_start_marker,
                        record.install_root,
                        record.version,
                        record.port,
                        "legacy-command-marker",
                        attempts - 1,
                        time.monotonic() - started,
                    )
                raise RuntimeLifecycleError(
                    f"Legacy PID {record.pid} больше не подтверждён как backend приложения; процесс не завершён."
                )
            if (
                current.pid != record.pid
                or current.process_start_marker != record.process_start_marker
                or current.command_line != record.command_line
                or current.executable != record.executable
                or current.working_directory != record.working_directory
            ):
                raise RuntimeLifecycleError(
                    f"Legacy PID {record.pid} изменил identity перед завершением; процесс не завершён."
                )
            self._force_kill_pid(record.pid)
            deadline = time.monotonic() + self.stop_timeout
            while time.monotonic() < deadline:
                snapshot = process_snapshot(record.pid)
                if snapshot is None or snapshot.start_marker != record.process_start_marker:
                    self._reap_child(record.pid)
                    return StopEvidence(
                        record.pid,
                        record.process_start_marker,
                        record.install_root,
                        record.version,
                        record.port,
                        "legacy-command-marker",
                        attempts,
                        time.monotonic() - started,
                    )
                time.sleep(0.04)
        raise RuntimeLifecycleError(
            f"Подтверждённый legacy backend PID {record.pid} не завершился после двух принудительных попыток."
        )

    def _stop_confirmed_locked(self, inspections: list[RuntimeInspection]) -> list[StopEvidence]:
        evidence: list[StopEvidence] = []
        for inspection in inspections:
            if inspection.confirmed:
                evidence.append(self._force_stop_record(inspection.record))
        return evidence

    def stop_all_confirmed(self) -> list[StopEvidence]:
        with RuntimeRegistryLock(self.registry_dir, timeout=self.startup_timeout + 2.0):
            return self._stop_confirmed_locked(self.inspect_all())

    def _wait_ports_released(self, endpoints: set[tuple[str, int]]) -> float:
        started = time.monotonic()
        deadline = started + self.port_timeout
        while time.monotonic() < deadline:
            if all(not _port_has_listener(host, port) for host, port in endpoints):
                return time.monotonic() - started
            time.sleep(0.04)
        occupied = [f"{host}:{port}" for host, port in sorted(endpoints) if _port_has_listener(host, port)]
        raise RuntimeLifecycleError(
            "Порт не освободился после завершения backend: " + ", ".join(occupied)
        )

    def _spawn_backend(
        self,
        *,
        install_root: Path,
        host: str,
        port: int,
        version: str,
        build_id: str,
    ) -> tuple[subprocess.Popen[bytes], str, Path, Path]:
        install_root = install_root.resolve(strict=False)
        server_script = install_root / "scripts" / "runtime_server.py"
        if not server_script.is_file():
            raise RuntimeLifecycleError(f"Runtime server script not found: {server_script}")
        token = secrets.token_hex(16)
        state_path = runtime_state_path(self.registry_dir, token)
        startup_path = runtime_startup_path(self.registry_dir, token)
        log_dir = self.registry_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"backend-{token}.log"
        spawn_python, spawn_environment = python_spawn_target(self.python_executable)
        command = [
            str(spawn_python),
            str(server_script),
            "--host",
            host,
            "--port",
            str(port),
            "--install-root",
            str(install_root),
            "--instance-token",
            token,
            "--state-path",
            str(state_path),
            "--startup-path",
            str(startup_path),
            "--expected-version",
            version,
            "--expected-build-id",
            build_id,
        ]
        environment = os.environ.copy()
        environment.pop("__PYVENV_LAUNCHER__", None)
        environment.update(
            {
                "APP_HOST": host,
                "APP_PORT": str(port),
                "APP_INSTALL_DIR": str(install_root),
                "APP_RUNTIME_DIR": str(self.registry_dir),
                "APP_RUNTIME_STARTUP_PATH": str(startup_path),
                "PYTHONPYCACHEPREFIX": str(self.registry_dir / "pycache" / build_id),
                "PYTHONUNBUFFERED": "1",
            }
        )
        environment.update(spawn_environment)
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with log_path.open("ab", buffering=0) as output:
            output.write(
                (
                    json.dumps(
                        {
                            "event": "runtime-spawn-request",
                            "at": _now_iso(),
                            "command": command,
                            "cwd": str(install_root),
                            "environment": {
                                key: environment.get(key)
                                for key in (
                                    "APP_HOST",
                                    "APP_PORT",
                                    "APP_INSTALL_DIR",
                                    "APP_RUNTIME_DIR",
                                    "APP_RUNTIME_STARTUP_PATH",
                                    "REWARDS_DATA_DIR",
                                    "REWARDS_DB_PATH",
                                    "READ_ONLY",
                                    "WRITE_MODE",
                                    "PYTHONPYCACHEPREFIX",
                                    "PYTHONDONTWRITEBYTECODE",
                                    "PYTHONUNBUFFERED",
                                    "__PYVENV_LAUNCHER__",
                                )
                            },
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            )
            process = subprocess.Popen(
                command,
                cwd=install_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                start_new_session=False,
            )
            output.write(
                (
                    json.dumps(
                        {
                            "event": "runtime-spawned",
                            "at": _now_iso(),
                            "pid": process.pid,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            )
        self._children[process.pid] = process
        return process, token, state_path, log_path

    @staticmethod
    def _record_mismatches(
        record: RuntimeRecord,
        *,
        process: subprocess.Popen[bytes],
        state_path: Path,
        install_root: Path,
        host: str,
        port: int,
        version: str,
        build_id: str,
    ) -> list[str]:
        expected = {
            "pid": process.pid,
            "state_path": str(state_path.resolve()),
            "install_root": os.path.normcase(str(install_root.resolve())),
            "host": host,
            "port": port,
            "version": version,
            "build_id": build_id,
        }
        actual = {
            "pid": record.pid,
            "state_path": record.state_path,
            "install_root": os.path.normcase(str(Path(record.install_root).resolve(strict=False))),
            "host": record.host,
            "port": record.port,
            "version": record.version,
            "build_id": record.build_id,
        }
        return [
            f"{key}: expected={expected[key]!r}, actual={actual[key]!r}"
            for key in expected
            if expected[key] != actual[key]
        ]

    def _startup_failure(
        self,
        *,
        category: str,
        process: subprocess.Popen[bytes],
        token: str,
        state_path: Path,
        startup_path: Path,
        log_path: Path,
        host: str,
        port: int,
        elapsed: float,
        detail: str = "",
    ) -> RuntimeLifecycleError:
        startup = read_runtime_startup(startup_path)
        records, invalid = read_runtime_records(self.registry_dir)
        record = next((candidate for candidate in records if candidate.instance_token == token), None)
        listeners = sorted(listener_pids(host, port)) if _port_has_listener(host, port) else []
        stage = "startup-state-missing"
        startup_error = ""
        if startup is not None:
            stage = startup.previous_stage if startup.stage == "failed" and startup.previous_stage else startup.stage
            if startup.error_type or startup.error_message:
                startup_error = f"{startup.error_type or 'Error'}: {startup.error_message or ''}".strip()
        registry_status = "present" if record is not None else "absent"
        if state_path in invalid:
            registry_status = "invalid"
        exit_code = process.poll()
        log_tail = _read_log_tail(log_path)
        pieces = [
            f"category={category}",
            f"PID={process.pid}",
            f"exit_code={exit_code if exit_code is not None else 'running'}",
            f"elapsed={elapsed:.3f}s",
            f"stage={stage}",
            f"port={host}:{port}",
            f"listeners={listeners or 'none'}",
            f"registry={registry_status}",
            f"log={log_path}",
        ]
        if detail:
            pieces.append(f"detail={detail}")
        if startup_error:
            pieces.append(f"child_error={startup_error}")
        elif log_tail:
            pieces.append(f"log_tail={log_tail}")
        return RuntimeLifecycleError("Новый backend не запущен: " + "; ".join(pieces) + ".")

    def _wait_ready(
        self,
        *,
        process: subprocess.Popen[bytes],
        token: str,
        state_path: Path,
        install_root: Path,
        host: str,
        port: int,
        version: str,
        build_id: str,
        log_path: Path | None = None,
    ) -> tuple[RuntimeRecord, float]:
        started = time.monotonic()
        hard_deadline = started + self.startup_timeout
        progress_deadline = started + self.ready_timeout
        startup_path = runtime_startup_path(self.registry_dir, token)
        log_path = log_path or self.registry_dir / "logs" / f"backend-{token}.log"
        last_heartbeat = 0.0
        while True:
            now = time.monotonic()
            startup = read_runtime_startup(startup_path)
            if startup is not None:
                startup_mismatch = []
                if startup.instance_token != token:
                    startup_mismatch.append("instance_token")
                if startup.pid != process.pid:
                    startup_mismatch.append("pid")
                if os.path.normcase(startup.install_root) != os.path.normcase(str(install_root.resolve())):
                    startup_mismatch.append("install_root")
                if startup.host != host or startup.port != port:
                    startup_mismatch.append("endpoint")
                if startup.expected_version != version or startup.expected_build_id != build_id:
                    startup_mismatch.append("version/build")
                if startup_mismatch:
                    raise self._startup_failure(
                        category="startup-state-mismatch",
                        process=process,
                        token=token,
                        state_path=state_path,
                        startup_path=startup_path,
                        log_path=log_path,
                        host=host,
                        port=port,
                        elapsed=now - started,
                        detail=", ".join(startup_mismatch),
                    )
                if startup.heartbeat_monotonic > last_heartbeat:
                    last_heartbeat = startup.heartbeat_monotonic
                    progress_deadline = min(hard_deadline, now + self.ready_timeout)

            if process.poll() is not None:
                category = "port-bind-failure" if _port_has_listener(host, port) else "child-crash"
                raise self._startup_failure(
                    category=category,
                    process=process,
                    token=token,
                    state_path=state_path,
                    startup_path=startup_path,
                    log_path=log_path,
                    host=host,
                    port=port,
                    elapsed=now - started,
                )

            records, invalid = read_runtime_records(self.registry_dir)
            if state_path in invalid:
                raise self._startup_failure(
                    category="registry-state-invalid",
                    process=process,
                    token=token,
                    state_path=state_path,
                    startup_path=startup_path,
                    log_path=log_path,
                    host=host,
                    port=port,
                    elapsed=now - started,
                )
            record = next((candidate for candidate in records if candidate.instance_token == token), None)
            if record is not None:
                mismatches = self._record_mismatches(
                    record,
                    process=process,
                    state_path=state_path,
                    install_root=install_root,
                    host=host,
                    port=port,
                    version=version,
                    build_id=build_id,
                )
                if mismatches:
                    raise self._startup_failure(
                        category="registry-identity-mismatch",
                        process=process,
                        token=token,
                        state_path=state_path,
                        startup_path=startup_path,
                        log_path=log_path,
                        host=host,
                        port=port,
                        elapsed=now - started,
                        detail=" | ".join(mismatches),
                    )
                identity = fetch_runtime_identity(host, port, timeout=0.15)
                if identity is not None:
                    inspection = inspect_runtime_record(record, health_timeout=0.2)
                    if inspection.confirmed and inspection.healthy:
                        return record, time.monotonic() - started
                    if inspection.identity is not None:
                        raise self._startup_failure(
                            category="http-identity-mismatch",
                            process=process,
                            token=token,
                            state_path=state_path,
                            startup_path=startup_path,
                            log_path=log_path,
                            host=host,
                            port=port,
                            elapsed=now - started,
                            detail=inspection.reason,
                        )

            if now >= hard_deadline:
                raise self._startup_failure(
                    category="slow-start-hard-limit",
                    process=process,
                    token=token,
                    state_path=state_path,
                    startup_path=startup_path,
                    log_path=log_path,
                    host=host,
                    port=port,
                    elapsed=now - started,
                    detail=f"active startup exceeded {self.startup_timeout:.1f}s",
                )
            if now >= progress_deadline:
                raise self._startup_failure(
                    category="startup-stalled",
                    process=process,
                    token=token,
                    state_path=state_path,
                    startup_path=startup_path,
                    log_path=log_path,
                    host=host,
                    port=port,
                    elapsed=now - started,
                    detail=f"no startup heartbeat within {self.ready_timeout:.1f}s",
                )
            time.sleep(0.05)

    def start_or_reuse(
        self,
        *,
        install_root: Path,
        host: str,
        port: int,
        expected_version: str | None = None,
    ) -> StartEvidence:
        install_root = install_root.resolve(strict=False)
        version = expected_version or read_installed_version(install_root)
        build_id = runtime_build_id(install_root)
        with RuntimeRegistryLock(self.registry_dir, timeout=self.startup_timeout + 2.0):
            detection_started = time.monotonic()
            inspections = self.inspect_all()
            desired = [
                inspection
                for inspection in inspections
                if self._matches_requested_runtime(
                    inspection,
                    install_root=install_root,
                    host=host,
                    port=port,
                    version=version,
                    build_id=build_id,
                )
            ]
            indeterminate = [
                inspection
                for inspection in inspections
                if not inspection.confirmed and inspection.healthy
            ]
            if indeterminate:
                requested = any(
                    self._record_matches_requested_runtime(
                        inspection.record,
                        install_root=install_root,
                        host=host,
                        port=port,
                        version=version,
                        build_id=build_id,
                    )
                    for inspection in indeterminate
                )
                detail = "запрошенного backend" if requested else "другого app-owned backend"
                raise RuntimeLifecycleError(
                    f"Windows временно не подтвердил PID {detail}; registry сохранён, новый backend не запускался.",
                    category="process-inspection-transient",
                )
            confirmed = [inspection for inspection in inspections if inspection.confirmed]
            desired_port_owned = any(
                inspection.record.host == host and inspection.record.port == port for inspection in confirmed
            )
            legacy = None
            if _port_has_listener(host, port) and not desired_port_owned:
                legacy = inspect_legacy_runtime(
                    install_root=install_root,
                    host=host,
                    port=port,
                    expected_app_name=APP_NAME,
                )
                if legacy is None:
                    raise RuntimeLifecycleError(
                        f"Порт {host}:{port} занят посторонним процессом. Посторонний процесс не был завершён."
                    )
            detection_seconds = time.monotonic() - detection_started
            if len(desired) == 1 and len(confirmed) == 1:
                record = desired[0].record
                return StartEvidence(
                    pid=record.pid,
                    install_root=record.install_root,
                    version=record.version,
                    build_id=record.build_id,
                    host=record.host,
                    port=record.port,
                    instance_token=record.instance_token,
                    reused=True,
                    detection_seconds=detection_seconds,
                    termination_seconds=0.0,
                    port_release_seconds=0.0,
                    readiness_seconds=0.0,
                )

            termination_started = time.monotonic()
            stopped = self._stop_confirmed_locked(inspections)
            if legacy is not None:
                stopped.append(self._force_stop_legacy(legacy))
            termination_seconds = time.monotonic() - termination_started
            released_endpoints = {(item.record.host, item.record.port) for item in confirmed}
            if legacy is not None:
                released_endpoints.add((legacy.host, legacy.port))
            if released_endpoints:
                port_release_seconds = self._wait_ports_released(released_endpoints)
            else:
                port_release_seconds = 0.0

            if _port_has_listener(host, port):
                identity = fetch_runtime_identity(host, port, timeout=0.15)
                detail = "другим процессом"
                if identity:
                    detail = "процессом без подтверждённой runtime identity"
                raise RuntimeLifecycleError(
                    f"Порт {host}:{port} занят {detail}. Посторонний процесс не был завершён."
                )

            spawned_at = _now_iso()
            process, token, state_path, log_path = self._spawn_backend(
                install_root=install_root,
                host=host,
                port=port,
                version=version,
                build_id=build_id,
            )
            try:
                record, readiness_seconds = self._wait_ready(
                    process=process,
                    token=token,
                    state_path=state_path,
                    install_root=install_root,
                    host=host,
                    port=port,
                    version=version,
                    build_id=build_id,
                    log_path=log_path,
                )
                # Readiness already proves the HTTP identity. Repeating that short
                # network probe here can misclassify a transient timeout as a failed
                # launch, so the final postcondition is process/registry identity.
                after, invalid_after = read_runtime_records(self.registry_dir)
                if process.poll() is not None or invalid_after or after != [record]:
                    raise RuntimeLifecycleError(
                        "После запуска не подтверждён ровно один backend приложения: "
                        f"process_exit={process.poll()}, records={after}, invalid={invalid_after}."
                    )
            except Exception:
                if process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
                self._reap_child(process.pid)
                self._remove_state(state_path)
                raise

            return StartEvidence(
                pid=record.pid,
                install_root=record.install_root,
                version=record.version,
                build_id=record.build_id,
                host=record.host,
                port=record.port,
                instance_token=record.instance_token,
                reused=False,
                detection_seconds=detection_seconds,
                termination_seconds=termination_seconds,
                port_release_seconds=port_release_seconds,
                readiness_seconds=readiness_seconds,
                spawned_at=spawned_at,
                identity_seconds=readiness_seconds,
                stopped=stopped,
                log_path=str(log_path),
                process=process,
            )

    def stop_token(self, instance_token: str) -> StopEvidence | None:
        with RuntimeRegistryLock(self.registry_dir):
            inspections = self.inspect_all()
            target = next(
                (inspection for inspection in inspections if inspection.record.instance_token == instance_token),
                None,
            )
            if target is None or not target.confirmed:
                return None
            return self._force_stop_record(target.record)


def write_lifecycle_evidence(registry_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    evidence_dir = registry_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / name
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path
