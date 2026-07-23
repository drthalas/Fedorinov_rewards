from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time

from .runtime_identity import TOKEN_PATTERN, fetch_runtime_identity


STARTUP_STATE_SCHEMA = 1
STARTUP_HEARTBEAT_SECONDS = 0.25
WINDOWS_REPLACE_TIMEOUT_SECONDS = 0.5
WINDOWS_REPLACE_RETRY_SECONDS = 0.01
WINDOWS_TRANSIENT_REPLACE_ERRORS = {5, 32, 33}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def runtime_startup_path(registry_dir: Path, token: str) -> Path:
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("Invalid runtime instance token.")
    return registry_dir / f"startup-{token}.json"


@dataclass(frozen=True)
class RuntimeStartupSnapshot:
    schema: int
    instance_token: str
    pid: int
    install_root: str
    host: str
    port: int
    expected_version: str
    expected_build_id: str
    stage: str
    previous_stage: str | None
    sequence: int
    started_at: str
    stage_started_at: str
    updated_at: str
    heartbeat_monotonic: float
    error_type: str | None
    error_message: str | None

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> RuntimeStartupSnapshot:
        snapshot = cls(
            schema=int(value.get("schema") or 0),
            instance_token=str(value.get("instance_token") or ""),
            pid=int(value.get("pid") or 0),
            install_root=str(value.get("install_root") or ""),
            host=str(value.get("host") or ""),
            port=int(value.get("port") or 0),
            expected_version=str(value.get("expected_version") or ""),
            expected_build_id=str(value.get("expected_build_id") or ""),
            stage=str(value.get("stage") or ""),
            previous_stage=str(value.get("previous_stage") or "") or None,
            sequence=int(value.get("sequence") or 0),
            started_at=str(value.get("started_at") or ""),
            stage_started_at=str(value.get("stage_started_at") or ""),
            updated_at=str(value.get("updated_at") or ""),
            heartbeat_monotonic=float(value.get("heartbeat_monotonic") or 0.0),
            error_type=str(value.get("error_type") or "") or None,
            error_message=str(value.get("error_message") or "") or None,
        )
        if (
            snapshot.schema != STARTUP_STATE_SCHEMA
            or not TOKEN_PATTERN.fullmatch(snapshot.instance_token)
            or snapshot.pid <= 0
            or not snapshot.stage
            or snapshot.sequence <= 0
            or snapshot.heartbeat_monotonic <= 0
        ):
            raise ValueError("Invalid runtime startup state.")
        return snapshot


def read_runtime_startup(path: Path) -> RuntimeStartupSnapshot | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        return RuntimeStartupSnapshot.from_mapping(value)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_transient_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    deadline = time.monotonic() + WINDOWS_REPLACE_TIMEOUT_SECONDS
    try:
        while True:
            try:
                os.replace(temporary, path)
                return
            except PermissionError as exc:
                if (
                    os.name != "nt"
                    or getattr(exc, "winerror", None) not in WINDOWS_TRANSIENT_REPLACE_ERRORS
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(WINDOWS_REPLACE_RETRY_SECONDS)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class RuntimeStartupReporter:
    def __init__(
        self,
        *,
        path: Path,
        instance_token: str,
        install_root: Path,
        host: str,
        port: int,
        expected_version: str,
        expected_build_id: str,
    ) -> None:
        self.path = path.resolve(strict=False)
        self.instance_token = instance_token
        self.install_root = str(install_root.resolve(strict=False))
        self.host = host
        self.port = int(port)
        self.expected_version = expected_version
        self.expected_build_id = expected_build_id
        self.pid = os.getpid()
        self.started_at = _now_iso()
        self.stage_started_at = self.started_at
        self.stage_name = "child-started"
        self.previous_stage: str | None = None
        self.sequence = 1
        self.error_type: str | None = None
        self.error_message: str | None = None
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._write_locked()
        self._thread = threading.Thread(target=self._heartbeat, name="runtime-startup-heartbeat", daemon=True)
        self._thread.start()

    def _mapping(self) -> dict[str, object]:
        now = _now_iso()
        return {
            "schema": STARTUP_STATE_SCHEMA,
            "instance_token": self.instance_token,
            "pid": self.pid,
            "install_root": self.install_root,
            "host": self.host,
            "port": self.port,
            "expected_version": self.expected_version,
            "expected_build_id": self.expected_build_id,
            "stage": self.stage_name,
            "previous_stage": self.previous_stage,
            "sequence": self.sequence,
            "started_at": self.started_at,
            "stage_started_at": self.stage_started_at,
            "updated_at": now,
            "heartbeat_monotonic": time.monotonic(),
            "error_type": self.error_type,
            "error_message": self.error_message,
        }

    def _write_locked(self) -> None:
        _write_transient_json(self.path, self._mapping())

    def _heartbeat(self) -> None:
        while not self._stopped.wait(STARTUP_HEARTBEAT_SECONDS):
            if self.stage_name == "binding-port":
                identity = fetch_runtime_identity(self.host, self.port, timeout=0.1)
                if (
                    identity
                    and int(identity.get("pid") or 0) == self.pid
                    and str(identity.get("instance_token") or "") == self.instance_token
                ):
                    with self._lock:
                        self.previous_stage = self.stage_name
                        self.stage_name = "identity-ready"
                        self.stage_started_at = _now_iso()
                        self.sequence += 1
                        self._write_locked()
                    self._stopped.set()
                    return
            with self._lock:
                self._write_locked()

    def stage(self, name: str) -> None:
        with self._lock:
            self.previous_stage = self.stage_name
            self.stage_name = name
            self.stage_started_at = _now_iso()
            self.sequence += 1
            self._write_locked()
        print(json.dumps({"event": "runtime-startup", "stage": name, "at": self.stage_started_at}), flush=True)

    def failed(self, exc: BaseException) -> None:
        self._stopped.set()
        self._thread.join(timeout=0.5)
        with self._lock:
            self.previous_stage = self.stage_name
            self.stage_name = "failed"
            self.stage_started_at = _now_iso()
            self.sequence += 1
            self.error_type = exc.__class__.__name__
            self.error_message = (str(exc) or repr(exc))[:1000]
            self._write_locked()

    def stop(self) -> None:
        self._stopped.set()
        self._thread.join(timeout=0.5)

    def remove(self) -> None:
        self.stop()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
