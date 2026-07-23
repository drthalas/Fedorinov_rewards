from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request


APPLICATION_ID = "fedorinov-rewards-backend"
RUNTIME_STATE_SCHEMA = 1
TOKEN_PATTERN = re.compile(r"^[a-f0-9]{32}$")
BUILD_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
PROCESS_QUERY_TIMEOUT_SECONDS = 1.5
# A cold PowerShell + CIM startup can exceed the generic process-query bound.
WINDOWS_PROCESS_QUERY_TIMEOUT_SECONDS = 3.0
WINDOWS_FILETIME_UNIX_EPOCH = 116_444_736_000_000_000
BUILD_ID_EXTRA_FILES = (
    Path("backend/requirements.txt"),
    Path("scripts/runtime_bootstrap.py"),
    Path("scripts/runtime_server.py"),
    Path("start_windows.bat"),
    Path("start_windows.ps1"),
)


class RuntimeIdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    start_marker: str
    executable: str
    command_line: str


@dataclass(frozen=True)
class RuntimeRecord:
    application_id: str
    schema: int
    pid: int
    process_start_marker: str
    install_root: str
    executable: str
    command_line: str
    host: str
    port: int
    version: str
    build_id: str
    instance_token: str
    created_at: str
    state_path: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any], state_path: Path) -> RuntimeRecord:
        record = cls(
            application_id=str(value.get("application_id") or ""),
            schema=int(value.get("schema") or 0),
            pid=int(value.get("pid") or 0),
            process_start_marker=str(value.get("process_start_marker") or ""),
            install_root=str(value.get("install_root") or ""),
            executable=str(value.get("executable") or ""),
            command_line=str(value.get("command_line") or ""),
            host=str(value.get("host") or ""),
            port=int(value.get("port") or 0),
            version=str(value.get("version") or ""),
            build_id=str(value.get("build_id") or ""),
            instance_token=str(value.get("instance_token") or ""),
            created_at=str(value.get("created_at") or ""),
            state_path=str(state_path.resolve()),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if self.application_id != APPLICATION_ID or self.schema != RUNTIME_STATE_SCHEMA:
            raise RuntimeIdentityError("Runtime state belongs to an unsupported application or schema.")
        if self.pid <= 0 or not self.process_start_marker:
            raise RuntimeIdentityError("Runtime state has no valid process identity.")
        if not self.install_root or not self.executable or not self.command_line:
            raise RuntimeIdentityError("Runtime state is missing executable or install-root identity.")
        if self.host not in LOCAL_HOSTS or not 1 <= self.port <= 65535:
            raise RuntimeIdentityError("Runtime state is not bound to a supported local endpoint.")
        if not self.version or not BUILD_ID_PATTERN.fullmatch(self.build_id):
            raise RuntimeIdentityError("Runtime state has no valid version or build identity.")
        if not TOKEN_PATTERN.fullmatch(self.instance_token):
            raise RuntimeIdentityError("Runtime state has no valid instance token.")


@dataclass(frozen=True)
class RuntimeInspection:
    record: RuntimeRecord
    snapshot: ProcessSnapshot | None
    confirmed: bool
    healthy: bool
    reason: str
    identity: dict[str, Any] | None = None


@dataclass(frozen=True)
class LegacyRuntimeRecord:
    pid: int
    process_start_marker: str
    install_root: str
    executable: str
    command_line: str
    working_directory: str | None
    host: str
    port: int
    version: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _normalized_path(value: str | Path) -> str:
    resolved = str(Path(value).expanduser().resolve(strict=False))
    return os.path.normcase(resolved)


def runtime_build_id(install_root: Path) -> str:
    root = install_root.resolve(strict=False)
    digest = hashlib.sha256()
    app_root = root / "backend" / "app"
    app_files = (
        path.relative_to(root)
        for path in app_root.rglob("*")
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    for relative in sorted({*app_files, *BUILD_ID_EXTRA_FILES}, key=lambda path: path.as_posix()):
        path = root / relative
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def runtime_registry_dir() -> Path:
    configured = os.getenv("APP_RUNTIME_DIR", "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser().resolve(strict=False)
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA", "").strip()
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return (Path(base) / "FedorinovRewards" / "runtime").resolve(strict=False)
    return (Path.home() / ".fedorinov_rewards" / "runtime").resolve(strict=False)


def runtime_state_path(registry_dir: Path, token: str) -> Path:
    if not TOKEN_PATTERN.fullmatch(token):
        raise RuntimeIdentityError("Invalid runtime instance token.")
    return registry_dir / f"backend-{token}.json"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _run_process_query(
    command: list[str],
    *,
    timeout: float = PROCESS_QUERY_TIMEOUT_SECONDS,
) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def process_snapshot(pid: int) -> ProcessSnapshot | None:
    if pid <= 0:
        return None
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            return None
        expression = (
            f'$p = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}"; '
            'if ($null -eq $p) { exit 3 }; '
            '$p | Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine | ConvertTo-Json -Compress'
        )
        raw = _run_process_query(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", expression],
            timeout=WINDOWS_PROCESS_QUERY_TIMEOUT_SECONDS,
        )
        if not raw:
            return None
        try:
            value = json.loads(raw)
            return ProcessSnapshot(
                pid=int(value["ProcessId"]),
                start_marker=str(value["CreationDate"]),
                executable=str(value.get("ExecutablePath") or ""),
                command_line=str(value.get("CommandLine") or ""),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    process_status = _run_process_query(["ps", "-p", str(pid), "-o", "stat="])
    if process_status and process_status.startswith("Z"):
        return None
    start_marker = _run_process_query(["ps", "-p", str(pid), "-o", "lstart="])
    command_line = _run_process_query(["ps", "-p", str(pid), "-o", "command="])
    executable = _run_process_query(["ps", "-p", str(pid), "-o", "comm="])
    if not start_marker or not command_line:
        return None
    return ProcessSnapshot(
        pid=pid,
        start_marker=start_marker,
        executable=executable or "",
        command_line=command_line,
    )


def _windows_filetime_start_marker(high: int, low: int) -> str:
    filetime = (int(high) << 32) | int(low)
    unix_milliseconds = (filetime - WINDOWS_FILETIME_UNIX_EPOCH) // 10_000
    return f"/Date({unix_milliseconds})/"


def _current_windows_process_snapshot() -> ProcessSnapshot | None:
    import ctypes
    from ctypes import wintypes

    class FileTime(ctypes.Structure):
        _fields_ = (("low", wintypes.DWORD), ("high", wintypes.DWORD))

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetCommandLineW.argtypes = ()
        kernel32.GetCommandLineW.restype = wintypes.LPWSTR

        creation = FileTime()
        exit_time = FileTime()
        kernel_time = FileTime()
        user_time = FileTime()
        if not kernel32.GetProcessTimes(
            kernel32.GetCurrentProcess(),
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        command_line = str(kernel32.GetCommandLineW() or "")
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    if not command_line:
        return None
    return ProcessSnapshot(
        pid=os.getpid(),
        start_marker=_windows_filetime_start_marker(creation.high, creation.low),
        executable=str(Path(sys.executable).resolve()),
        command_line=command_line,
    )


def current_process_snapshot() -> ProcessSnapshot | None:
    if os.name == "nt":
        return _current_windows_process_snapshot()
    return process_snapshot(os.getpid())


def prepare_legacy_windows_process_inspection(expected: ProcessSnapshot) -> None:
    observed = process_snapshot(expected.pid)
    if observed is None:
        raise RuntimeIdentityError("Legacy Windows process inspection did not become ready.")
    if observed.start_marker != expected.start_marker or observed.command_line != expected.command_line:
        raise RuntimeIdentityError("Legacy Windows process inspection returned a different process identity.")
    if (
        expected.executable
        and observed.executable
        and _normalized_path(observed.executable) != _normalized_path(expected.executable)
    ):
        raise RuntimeIdentityError("Legacy Windows process inspection returned a different executable.")


def register_current_runtime(
    *,
    install_root: Path,
    host: str,
    port: int,
    version: str,
    build_id: str,
    instance_token: str,
    state_path: Path,
    prepare_legacy_inspection: bool = False,
) -> RuntimeRecord:
    snapshot = current_process_snapshot()
    if snapshot is None:
        raise RuntimeIdentityError("Cannot inspect the backend process being registered.")
    if prepare_legacy_inspection:
        prepare_legacy_windows_process_inspection(snapshot)
    record = RuntimeRecord(
        application_id=APPLICATION_ID,
        schema=RUNTIME_STATE_SCHEMA,
        pid=snapshot.pid,
        process_start_marker=snapshot.start_marker,
        install_root=str(Path(install_root).resolve()),
        executable=snapshot.executable or str(Path(sys.executable).resolve()),
        command_line=snapshot.command_line,
        host=host,
        port=int(port),
        version=version,
        build_id=build_id,
        instance_token=instance_token,
        created_at=_now_iso(),
        state_path=str(state_path.resolve()),
    )
    record.validate()
    atomic_write_json(state_path, {key: value for key, value in asdict(record).items() if key != "state_path"})
    os.environ["APP_PROCESS_START_MARKER"] = record.process_start_marker
    os.environ["APP_BUILD_ID"] = record.build_id
    return record


def remove_runtime_state(state_path: Path, *, pid: int, instance_token: str) -> bool:
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if int(value.get("pid") or 0) != pid or str(value.get("instance_token") or "") != instance_token:
        return False
    try:
        state_path.unlink()
    except FileNotFoundError:
        return False
    return True


def read_runtime_records(registry_dir: Path) -> tuple[list[RuntimeRecord], list[Path]]:
    records: list[RuntimeRecord] = []
    invalid: list[Path] = []
    if not registry_dir.exists():
        return records, invalid
    for path in sorted(registry_dir.glob("backend-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise RuntimeIdentityError("Runtime state is not an object.")
            records.append(RuntimeRecord.from_mapping(value, path))
        except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeIdentityError):
            invalid.append(path)
    return records, invalid


def fetch_runtime_identity(host: str, port: int, timeout: float = 0.35) -> dict[str, Any] | None:
    if host not in LOCAL_HOSTS:
        return None
    request = urllib.request.Request(
        f"http://{host}:{port}/runtime/identity",
        headers={"Accept": "application/json", "Cache-Control": "no-store"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=max(0.05, timeout)) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        exc.close()
        return None
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def fetch_version_identity(host: str, port: int, timeout: float = 0.35) -> dict[str, Any] | None:
    if host not in LOCAL_HOSTS:
        return None
    request = urllib.request.Request(
        f"http://{host}:{port}/version",
        headers={"Accept": "application/json", "Cache-Control": "no-store"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=max(0.05, timeout)) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        exc.close()
        return None
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def listener_pids(host: str, port: int) -> set[int]:
    if host not in LOCAL_HOSTS or not 1 <= port <= 65535:
        return set()
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            return set()
        expression = (
            f"@(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue "
            "| Select-Object -ExpandProperty OwningProcess -Unique) | ConvertTo-Json -Compress"
        )
        raw = _run_process_query(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", expression],
            timeout=WINDOWS_PROCESS_QUERY_TIMEOUT_SECONDS,
        )
        if not raw:
            return set()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return set()
        values = value if isinstance(value, list) else [value]
        result: set[int] = set()
        for item in values:
            try:
                pid = int(item)
            except (TypeError, ValueError):
                continue
            if pid > 0:
                result.add(pid)
        return result

    lsof = shutil.which("lsof") or "/usr/sbin/lsof"
    raw = _run_process_query([lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    if not raw:
        return set()
    result: set[int] = set()
    for line in raw.splitlines():
        try:
            result.add(int(line.strip()))
        except ValueError:
            continue
    return result


def process_working_directory(pid: int) -> str | None:
    if pid <= 0 or os.name == "nt":
        return None
    proc_path = Path("/proc") / str(pid) / "cwd"
    if proc_path.exists():
        try:
            return str(proc_path.resolve(strict=True))
        except OSError:
            return None
    lsof = shutil.which("lsof") or "/usr/sbin/lsof"
    raw = _run_process_query([lsof, "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
    if not raw:
        return None
    for line in raw.splitlines():
        if line.startswith("n") and len(line) > 1:
            return str(Path(line[1:]).resolve(strict=False))
    return None


def inspect_legacy_runtime(
    *,
    install_root: Path,
    host: str,
    port: int,
    expected_app_name: str,
) -> LegacyRuntimeRecord | None:
    pids = listener_pids(host, port)
    if len(pids) != 1:
        return None
    pid = next(iter(pids))
    snapshot = process_snapshot(pid)
    if snapshot is None:
        return None

    root = install_root.resolve(strict=False)
    if os.name == "nt":
        expected_python = root / ".venv" / "Scripts" / "python.exe"
    else:
        expected_python = root / ".venv" / "bin" / "python"
    expected_python_text = str(expected_python.absolute())
    executable_matches = bool(
        snapshot.executable
        and expected_python.exists()
        and _normalized_path(snapshot.executable) == _normalized_path(expected_python)
    )
    command_uses_expected_python = expected_python_text in snapshot.command_line
    working_directory = process_working_directory(pid)
    working_directory_matches = bool(
        working_directory
        and _normalized_path(working_directory) == _normalized_path(root)
    )
    required_command_markers = (
        "-m uvicorn",
        "backend.app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    )
    if not (executable_matches or command_uses_expected_python or working_directory_matches):
        return None
    if any(marker not in snapshot.command_line for marker in required_command_markers):
        return None

    version_identity = fetch_version_identity(host, port, timeout=0.25)
    if not version_identity or str(version_identity.get("app_name") or "") != expected_app_name:
        return None
    version = str(version_identity.get("version") or "").strip()
    if not version:
        return None
    return LegacyRuntimeRecord(
        pid=pid,
        process_start_marker=snapshot.start_marker,
        install_root=str(root),
        executable=snapshot.executable,
        command_line=snapshot.command_line,
        working_directory=working_directory,
        host=host,
        port=port,
        version=version,
    )


def _identity_matches(record: RuntimeRecord, value: dict[str, Any] | None) -> bool:
    if not value or not value.get("managed"):
        return False
    expected = {
        "application_id": record.application_id,
        "pid": record.pid,
        "process_start_marker": record.process_start_marker,
        "install_root": _normalized_path(record.install_root),
        "host": record.host,
        "port": record.port,
        "version": record.version,
        "build_id": record.build_id,
        "instance_token": record.instance_token,
    }
    actual = {
        "application_id": str(value.get("application_id") or ""),
        "pid": int(value.get("pid") or 0),
        "process_start_marker": str(value.get("process_start_marker") or ""),
        "install_root": _normalized_path(str(value.get("install_root") or ".")),
        "host": str(value.get("host") or ""),
        "port": int(value.get("port") or 0),
        "version": str(value.get("version") or ""),
        "build_id": str(value.get("build_id") or ""),
        "instance_token": str(value.get("instance_token") or ""),
    }
    return actual == expected


def inspect_runtime_record(record: RuntimeRecord, health_timeout: float = 0.2) -> RuntimeInspection:
    snapshot = process_snapshot(record.pid)
    if snapshot is None:
        return RuntimeInspection(record, None, False, False, "process-not-running")
    if snapshot.start_marker != record.process_start_marker:
        return RuntimeInspection(record, snapshot, False, False, "process-start-time-mismatch")
    if snapshot.command_line != record.command_line:
        return RuntimeInspection(record, snapshot, False, False, "command-line-mismatch")
    if record.executable and snapshot.executable and _normalized_path(snapshot.executable) != _normalized_path(record.executable):
        return RuntimeInspection(record, snapshot, False, False, "executable-mismatch")

    command = snapshot.command_line
    required_markers = ("runtime_server.py", record.instance_token, record.install_root, str(record.port))
    if any(marker not in command for marker in required_markers):
        return RuntimeInspection(record, snapshot, False, False, "app-owned-command-marker-mismatch")

    identity = fetch_runtime_identity(record.host, record.port, timeout=health_timeout)
    healthy = _identity_matches(record, identity)
    return RuntimeInspection(record, snapshot, True, healthy, "confirmed" if healthy else "confirmed-unresponsive", identity)


def current_runtime_identity(*, version: str, install_root: Path, host: str, port: int) -> dict[str, Any]:
    token = os.getenv("APP_INSTANCE_TOKEN", "").strip()
    state_value = os.getenv("APP_RUNTIME_STATE_PATH", "").strip()
    start_marker = os.getenv("APP_PROCESS_START_MARKER", "").strip()
    build_id = os.getenv("APP_BUILD_ID", "").strip()
    managed = bool(TOKEN_PATTERN.fullmatch(token) and BUILD_ID_PATTERN.fullmatch(build_id) and state_value and start_marker)
    return {
        "application_id": APPLICATION_ID,
        "managed": managed,
        "pid": os.getpid(),
        "process_start_marker": start_marker if managed else None,
        "install_root": str(Path(install_root).resolve()),
        "host": host,
        "port": int(port),
        "version": version,
        "build_id": build_id if managed else runtime_build_id(install_root),
        "instance_token": token if managed else None,
    }


class RuntimeRegistryLock(AbstractContextManager["RuntimeRegistryLock"]):
    def __init__(self, registry_dir: Path, timeout: float = 3.0) -> None:
        self.registry_dir = registry_dir
        self.timeout = max(0.1, timeout)
        self._handle = None

    def __enter__(self) -> RuntimeRegistryLock:
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        path = self.registry_dir / "lifecycle.lock"
        self._handle = path.open("a+b")
        if path.stat().st_size == 0:
            self._handle.write(b"0")
            self._handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    self._handle.seek(0)
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise RuntimeIdentityError("Another launcher or updater operation is already running.")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
