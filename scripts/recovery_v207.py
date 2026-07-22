#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Callable, Iterable, Protocol
import urllib.error
import urllib.request
import webbrowser
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


PRODUCT_ID = "fedorinov-rewards-backend"
PRODUCT_NAME = "Награды и награждённые"
TARGET_VERSION = "2.0.7"
SUPPORTED_SOURCE_VERSIONS = {"2.0.5", "2.0.6"}
PACKAGE_ROOT_NAME = "FedorinovRewards_WebPreview"
RECOVERY_MANIFEST_NAME = "manifest.json"
INSTALLATION_POINTER_SCHEMA = 1
RUNTIME_STATE_SCHEMA = 1
TOKEN_LENGTH = 32
MAX_SCAN_DEPTH = 4
MAX_SCAN_DIRECTORIES = 25_000
MAX_PACKAGE_MEMBERS = 20_000
MAX_PACKAGE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
MANAGED_MEDIA_DIRS = ("Source", "SourceMark", "default", "GuideImages")
REQUIRED_DATA_DIRS = ("Source", "SourceMark", "default")
SKIPPED_SCAN_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "backups",
    "database",
    "default",
    "dist",
    "GuideImages",
    "node_modules",
    "Source",
    "SourceMark",
    "updates",
}
REQUIRED_INSTALL_FILES = (
    "start_windows.bat",
    "backend/app/version.py",
    "backend/requirements.txt",
    "scripts/runtime_bootstrap.py",
    "scripts/runtime_server.py",
    ".env",
)


class RecoveryError(RuntimeError):
    pass


class RecoveryCancelled(RecoveryError):
    pass


@dataclass(frozen=True)
class InstallationCandidate:
    install_root: Path
    version: str
    env_path: Path
    data_root: Path
    db_path: Path
    db_size: int
    db_modified: str
    media_count: int
    host: str
    port: int

    def summary(self) -> str:
        return (
            f"Путь: {self.install_root}\n"
            f"Версия: {self.version}\n"
            f"База: {self.db_path.name}, {self.db_size} байт, изменена {self.db_modified}\n"
            f"Файлов media: {self.media_count}"
        )


@dataclass(frozen=True)
class DataFingerprint:
    db_sha256: str
    media_sha256: str
    media_count: int
    media_bytes: int


@dataclass(frozen=True)
class RecoveryPackage:
    version: str
    zip_path: Path
    sha256: str
    size: int
    requirements_sha256: str


@dataclass
class StartedRuntime:
    pid: int
    instance_token: str
    version: str
    build_id: str
    install_root: str
    host: str
    port: int
    state_path: Path
    startup_path: Path | None
    log_path: Path
    process: subprocess.Popen[bytes] | None = None


class RecoveryUI(Protocol):
    def show(self, message: str = "") -> None: ...

    def ask(self, prompt: str) -> str: ...

    def confirm(self, prompt: str) -> bool: ...

    def pick_folder(self) -> Path | None: ...


class ConsoleUI:
    def show(self, message: str = "") -> None:
        print(message, flush=True)

    def ask(self, prompt: str) -> str:
        return input(prompt).strip()

    def confirm(self, prompt: str) -> bool:
        answer = self.ask(f"{prompt} Введите ДА для продолжения: ")
        return answer.casefold() == "да"

    def pick_folder(self) -> Path | None:
        if os.name == "nt":
            powershell = shutil.which("powershell.exe") or shutil.which("powershell")
            if powershell:
                expression = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                    "$d.Description = 'Выберите папку, из которой обычно запускается программа'; "
                    "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $d.SelectedPath }"
                )
                result = subprocess.run(
                    [powershell, "-NoProfile", "-STA", "-Command", expression],
                    text=True,
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
                selected = result.stdout.strip()
                if result.returncode == 0 and selected:
                    return Path(selected)
        try:
            import tkinter
            from tkinter import filedialog

            root = tkinter.Tk()
            root.withdraw()
            selected = filedialog.askdirectory(title="Выберите папку, из которой обычно запускается программа")
            root.destroy()
            return Path(selected) if selected else None
        except Exception:
            return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_path(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def _read_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def _version_metadata(path: Path) -> tuple[str, str]:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise RecoveryError(f"Не удалось проверить версию программы: {exc}") from exc
    values: dict[str, str] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id not in {"APP_NAME", "APP_VERSION"}:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            values[node.targets[0].id] = node.value.value
    return values.get("APP_NAME", ""), values.get("APP_VERSION", "")


def _resolve_env_path(raw: str, install_root: Path) -> Path:
    expanded = os.path.expandvars(raw).strip()
    path = Path(expanded).expanduser()
    if not path.is_absolute():
        path = install_root / path
    return path.resolve(strict=False)


def _media_files(data_root: Path) -> list[Path]:
    files: list[Path] = []
    for name in MANAGED_MEDIA_DIRS:
        root = data_root / name
        if not root.is_dir():
            continue
        files.extend(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    return sorted(set(files), key=lambda path: path.relative_to(data_root).as_posix().casefold())


def validate_installation(
    install_root: Path,
    *,
    supported_versions: set[str] | None = None,
) -> InstallationCandidate | None:
    root = install_root.expanduser().resolve(strict=False)
    if not root.is_dir() or root.is_symlink():
        return None
    if any(not (root / relative).is_file() or (root / relative).is_symlink() for relative in REQUIRED_INSTALL_FILES):
        return None
    try:
        app_name, version = _version_metadata(root / "backend/app/version.py")
        if app_name != PRODUCT_NAME:
            return None
        if supported_versions is not None and version not in supported_versions:
            return None
        environment = _read_assignments(root / ".env")
        configured_install = environment.get("APP_INSTALL_DIR", "").strip()
        if configured_install and _normalized_path(_resolve_env_path(configured_install, root)) != _normalized_path(root):
            return None
        data_value = environment.get("REWARDS_DATA_DIR", "").strip()
        if not data_value or data_value.casefold() == r"c:\path\to\rewards".casefold():
            return None
        data_root = _resolve_env_path(data_value, root)
        db_value = environment.get("REWARDS_DB_PATH", "").strip()
        db_path = _resolve_env_path(db_value, root) if db_value else data_root / "database" / "MyDatabase.sqlite"
        if not data_root.is_dir() or not db_path.is_file() or db_path.is_symlink():
            return None
        if any(not (data_root / name).is_dir() for name in REQUIRED_DATA_DIRS):
            return None
        host = environment.get("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return None
        port = int(environment.get("APP_PORT", "8080").strip() or "8080")
        if not 1 <= port <= 65535:
            return None
        stat = db_path.stat()
        media_count = len(_media_files(data_root))
    except (OSError, UnicodeError, ValueError, RecoveryError):
        return None
    return InstallationCandidate(
        install_root=root,
        version=version,
        env_path=root / ".env",
        data_root=data_root,
        db_path=db_path.resolve(strict=False),
        db_size=stat.st_size,
        db_modified=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        media_count=media_count,
        host=host,
        port=port,
    )


def runtime_registry_dir() -> Path:
    configured = os.getenv("APP_RUNTIME_DIR", "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser().resolve(strict=False)
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    else:
        base = Path.home() / ".fedorinov_rewards"
        return (base / "runtime").resolve(strict=False)
    return (base / "FedorinovRewards" / "runtime").resolve(strict=False)


def installation_pointer_path() -> Path:
    configured = os.getenv("APP_INSTALLATION_POINTER", "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser().resolve(strict=False)
    configured_runtime = os.getenv("APP_RUNTIME_DIR", "").strip()
    if configured_runtime:
        return (Path(os.path.expandvars(configured_runtime)).expanduser().resolve(strict=False).parent / "installation.json")
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return (base / "FedorinovRewards" / "installation.json").resolve(strict=False)
    return (Path.home() / ".fedorinov_rewards" / "installation.json").resolve(strict=False)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def official_pointer_roots(
    *,
    pointer_path: Path | None = None,
    registry_dir: Path | None = None,
) -> list[Path]:
    roots: list[Path] = []
    pointer = _read_json(pointer_path or installation_pointer_path())
    if (
        pointer
        and pointer.get("application_id") == PRODUCT_ID
        and int(pointer.get("schema") or 0) == INSTALLATION_POINTER_SCHEMA
        and pointer.get("install_root")
    ):
        roots.append(Path(str(pointer["install_root"])))

    registry = registry_dir or runtime_registry_dir()
    if registry.is_dir():
        for state_path in sorted(registry.glob("backend-*.json")):
            value = _read_json(state_path)
            if (
                value
                and value.get("application_id") == PRODUCT_ID
                and int(value.get("schema") or 0) == RUNTIME_STATE_SCHEMA
                and value.get("install_root")
            ):
                roots.append(Path(str(value["install_root"])))
    return _dedupe_paths(roots)


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.expanduser().resolve(strict=False)
        key = _normalized_path(resolved)
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def default_scan_roots() -> list[Path]:
    configured = os.getenv("FEDORINOV_RECOVERY_SCAN_ROOTS", "").strip()
    if configured:
        return _dedupe_paths(Path(item) for item in configured.split(os.pathsep) if item.strip())
    roots = [Path.home() / name for name in ("Desktop", "Documents", "Downloads")]
    for value in (os.getenv("LOCALAPPDATA"), os.getenv("APPDATA")):
        if value:
            roots.append(Path(value) / "FedorinovRewards")
    return _dedupe_paths(path for path in roots if path.is_dir())


def bounded_installation_scan(
    scan_roots: Iterable[Path],
    *,
    max_depth: int = MAX_SCAN_DEPTH,
    max_directories: int = MAX_SCAN_DIRECTORIES,
) -> list[InstallationCandidate]:
    found: list[InstallationCandidate] = []
    seen: set[str] = set()
    visited = 0
    for scan_root in _dedupe_paths(scan_roots):
        queue: list[tuple[Path, int]] = [(scan_root, 0)]
        while queue:
            current, depth = queue.pop(0)
            visited += 1
            if visited > max_directories:
                raise RecoveryError("Поиск остановлен: превышен безопасный предел проверяемых папок.")
            marker = current / "start_windows.bat"
            if marker.is_file():
                candidate = validate_installation(current, supported_versions=SUPPORTED_SOURCE_VERSIONS)
                if candidate is not None:
                    key = _normalized_path(candidate.install_root)
                    if key not in seen:
                        seen.add(key)
                        found.append(candidate)
                    continue
            if depth >= max_depth:
                continue
            try:
                children = sorted(
                    (
                        path
                        for path in current.iterdir()
                        if path.is_dir() and not path.is_symlink() and path.name not in SKIPPED_SCAN_NAMES
                    ),
                    key=lambda path: path.name.casefold(),
                )
            except OSError:
                continue
            queue.extend((child, depth + 1) for child in children)
    return sorted(found, key=lambda item: str(item.install_root).casefold())


def discover_installations(
    *,
    pointer_path: Path | None = None,
    registry_dir: Path | None = None,
    scan_roots: Iterable[Path] | None = None,
) -> tuple[list[InstallationCandidate], str]:
    pointer_candidates = [
        candidate
        for root in official_pointer_roots(pointer_path=pointer_path, registry_dir=registry_dir)
        if (candidate := validate_installation(root, supported_versions=SUPPORTED_SOURCE_VERSIONS)) is not None
    ]
    pointer_candidates = list({_normalized_path(item.install_root): item for item in pointer_candidates}.values())
    if len(pointer_candidates) == 1:
        return pointer_candidates, "official-pointer"

    scanned = bounded_installation_scan(scan_roots if scan_roots is not None else default_scan_roots())
    combined = {
        _normalized_path(item.install_root): item
        for item in [*pointer_candidates, *scanned]
    }
    return sorted(combined.values(), key=lambda item: str(item.install_root).casefold()), "bounded-scan"


def select_installation(candidates: list[InstallationCandidate], ui: RecoveryUI) -> InstallationCandidate:
    selected: InstallationCandidate | None = None
    if len(candidates) == 1:
        selected = candidates[0]
        ui.show("Найдена одна установка:\n" + selected.summary())
    elif len(candidates) > 1:
        ui.show("Найдено несколько установок. Выберите папку, из которой обычно запускаете программу:")
        for index, candidate in enumerate(candidates, 1):
            ui.show(f"\n{index}.\n{candidate.summary()}")
        answer = ui.ask("Введите номер установки: ")
        try:
            index = int(answer)
            if not 1 <= index <= len(candidates):
                raise ValueError
            selected = candidates[index - 1]
        except (ValueError, IndexError):
            raise RecoveryCancelled("Установка не выбрана. Изменения не выполнялись.")
    else:
        ui.show("Установка автоматически не найдена. Выберите папку, из которой обычно запускаете программу.")
        chosen = ui.pick_folder()
        if chosen is None:
            raise RecoveryCancelled("Папка не выбрана. Изменения не выполнялись.")
        selected = validate_installation(chosen, supported_versions=SUPPORTED_SOURCE_VERSIONS)
        if selected is None:
            raise RecoveryCancelled(
                "Выбранная папка не является поддерживаемой установкой v2.0.5/v2.0.6. "
                "Изменения не выполнялись."
            )

    ui.show("\nБудет обновлена только эта установка:\n" + selected.summary())
    if not ui.confirm("Проверьте полный путь и подтвердите обновление."):
        raise RecoveryCancelled("Пользователь отменил восстановление. Изменения не выполнялись.")
    return selected


def fingerprint_data(candidate: InstallationCandidate) -> DataFingerprint:
    media_digest = hashlib.sha256()
    count = 0
    total_bytes = 0
    for path in _media_files(candidate.data_root):
        relative = path.relative_to(candidate.data_root).as_posix()
        size = path.stat().st_size
        checksum = sha256_file(path)
        media_digest.update(relative.encode("utf-8"))
        media_digest.update(b"\0")
        media_digest.update(str(size).encode("ascii"))
        media_digest.update(b"\0")
        media_digest.update(checksum.encode("ascii"))
        media_digest.update(b"\n")
        count += 1
        total_bytes += size
    return DataFingerprint(
        db_sha256=sha256_file(candidate.db_path),
        media_sha256=media_digest.hexdigest(),
        media_count=count,
        media_bytes=total_bytes,
    )


def load_recovery_package(service_dir: Path) -> RecoveryPackage:
    manifest_path = service_dir / RECOVERY_MANIFEST_NAME
    value = _read_json(manifest_path)
    if not value:
        raise RecoveryError("Служебный manifest восстановления отсутствует или повреждён.")
    try:
        version = str(value["version"])
        filename = str(value["package_filename"])
        expected_sha = str(value["package_sha256"]).lower()
        expected_size = int(value["package_size"])
        requirements_sha = str(value["requirements_sha256"]).lower()
    except (KeyError, TypeError, ValueError) as exc:
        raise RecoveryError("Служебный manifest восстановления неполный.") from exc
    if version != TARGET_VERSION:
        raise RecoveryError(f"Recovery package version mismatch: {version} != {TARGET_VERSION}")
    package_path = (service_dir / filename).resolve(strict=False)
    if package_path.parent != service_dir.resolve(strict=False) or not package_path.is_file():
        raise RecoveryError("Основной пакет v2.0.7 не найден в recovery-архиве.")
    actual_size = package_path.stat().st_size
    actual_sha = sha256_file(package_path)
    if actual_size != expected_size or actual_sha != expected_sha:
        raise RecoveryError("Основной пакет v2.0.7 повреждён: размер или SHA256 не совпадает.")
    return RecoveryPackage(version, package_path, actual_sha, actual_size, requirements_sha)


def _safe_zip_parts(name: str) -> tuple[str, ...]:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
        raise RecoveryError(f"Небезопасный путь в пакете: {name}")
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if any(part == ".." or part.endswith((" ", ".")) or ":" in part for part in parts):
        raise RecoveryError(f"Небезопасный путь в пакете: {name}")
    return parts


def _zip_is_special(member: ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0xFFFF
    file_type = mode & 0o170000
    return bool(file_type and file_type not in {0o040000, 0o100000})


def validate_and_extract_package(package: RecoveryPackage, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    seen: set[tuple[str, ...]] = set()
    total = 0
    try:
        with ZipFile(package.zip_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_PACKAGE_MEMBERS:
                raise RecoveryError("В основном пакете слишком много файлов.")
            if archive.testzip():
                raise RecoveryError("Основной пакет v2.0.7 повреждён.")
            for member in members:
                parts = _safe_zip_parts(member.filename)
                if not parts:
                    continue
                if parts[0] != PACKAGE_ROOT_NAME:
                    raise RecoveryError("Основной пакет имеет неизвестную корневую папку.")
                relative = parts[1:]
                if not relative:
                    continue
                folded = tuple(part.casefold() for part in relative)
                if folded in seen or _zip_is_special(member):
                    raise RecoveryError("Основной пакет содержит дублирующий или специальный файл.")
                seen.add(folded)
                if member.file_size > MAX_PACKAGE_MEMBER_BYTES:
                    raise RecoveryError("Основной пакет содержит слишком большой файл.")
                total += member.file_size
                if total > MAX_PACKAGE_BYTES:
                    raise RecoveryError("Основной пакет превышает безопасный размер.")
                target = destination.joinpath(*relative)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except BadZipFile as exc:
        raise RecoveryError("Основной пакет v2.0.7 не является корректным ZIP.") from exc

    required = [destination / path for path in REQUIRED_INSTALL_FILES if path != ".env"]
    if any(not path.is_file() for path in required):
        raise RecoveryError("В основном пакете отсутствуют обязательные файлы программы.")
    app_name, version = _version_metadata(destination / "backend/app/version.py")
    if app_name != PRODUCT_NAME or version != package.version:
        raise RecoveryError("Версия или product marker основного пакета не совпадает.")
    if sha256_file(destination / "backend/requirements.txt") != package.requirements_sha256:
        raise RecoveryError("Закреплённые зависимости основного пакета не совпадают с manifest.")
    return destination


def _package_files(package_root: Path) -> list[Path]:
    return sorted(path for path in package_root.rglob("*") if path.is_file() and not path.is_symlink())


def _safe_program_path(install_root: Path, relative: Path | str) -> Path:
    root = install_root.resolve(strict=False)
    destination = root / Path(relative)
    try:
        destination.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise RecoveryError(f"Program path выходит за пределы выбранной установки: {relative}") from exc
    current = destination
    while current != root:
        if current.is_symlink():
            raise RecoveryError(f"Program path содержит недопустимую ссылку: {relative}")
        current = current.parent
    return destination


def create_verified_backup(
    candidate: InstallationCandidate,
    package_root: Path,
    data_before: DataFingerprint,
) -> tuple[Path, dict[str, dict[str, object]]]:
    entries: dict[str, dict[str, object]] = {}
    for source in _package_files(package_root):
        relative = source.relative_to(package_root).as_posix()
        destination = _safe_program_path(candidate.install_root, relative)
        if destination.is_file() and not destination.is_symlink():
            entries[relative] = {
                "existed": True,
                "sha256": sha256_file(destination),
                "size": destination.stat().st_size,
            }
        else:
            entries[relative] = {"existed": False, "sha256": None, "size": 0}

    backup_dir = candidate.install_root / "updates" / "recovery_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"program_v{candidate.version}_{timestamp}_{secrets.token_hex(4)}.zip"
    backup_manifest = {
        "schema": 1,
        "application_id": PRODUCT_ID,
        "install_root": str(candidate.install_root),
        "source_version": candidate.version,
        "created_at": _now_iso(),
        "data_fingerprint": data_before.__dict__,
        "files": entries,
    }
    with ZipFile(backup_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("__recovery_manifest__.json", json.dumps(backup_manifest, ensure_ascii=False, sort_keys=True))
        for relative, metadata in entries.items():
            if metadata["existed"]:
                archive.write(candidate.install_root / relative, relative)

    with ZipFile(backup_path) as archive:
        if archive.testzip():
            raise RecoveryError("Созданный backup программы повреждён.")
        stored = json.loads(archive.read("__recovery_manifest__.json").decode("utf-8"))
        if stored != backup_manifest:
            raise RecoveryError("Manifest созданного backup не совпадает.")
        for relative, metadata in entries.items():
            if metadata["existed"] and hashlib.sha256(archive.read(relative)).hexdigest() != metadata["sha256"]:
                raise RecoveryError(f"Backup не прошёл проверку файла {relative}.")
    return backup_path, entries


def install_program_files(package_root: Path, install_root: Path) -> int:
    copied = 0
    for source in _package_files(package_root):
        relative = source.relative_to(package_root)
        destination = _safe_program_path(install_root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256_file(source) != sha256_file(destination):
            raise RecoveryError(f"Не удалось проверить установленный файл {relative.as_posix()}.")
        copied += 1
    return copied


def restore_program_files(
    backup_path: Path,
    install_root: Path,
    entries: dict[str, dict[str, object]],
) -> None:
    with ZipFile(backup_path) as archive:
        if archive.testzip():
            raise RecoveryError("Backup программы повреждён; автоматическое восстановление остановлено.")
        for relative, metadata in entries.items():
            destination = _safe_program_path(install_root, relative)
            if metadata["existed"]:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(relative) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if sha256_file(destination) != metadata["sha256"]:
                    raise RecoveryError(f"Rollback не проверил восстановленный файл {relative}.")
            elif destination.exists():
                if destination.is_file() and not destination.is_symlink():
                    destination.unlink()
                else:
                    raise RecoveryError(f"Rollback остановлен на неожиданном пути {relative}.")


def _target_python(install_root: Path) -> Path:
    candidates = (
        install_root / ".venv" / "Scripts" / "python.exe",
        install_root / ".venv" / "bin" / "python",
    )
    return next((path for path in candidates if path.is_file()), Path(sys.executable))


def _run_internal_stop(candidate: InstallationCandidate, registry_dir: Path) -> dict[str, object]:
    command = [
        str(_target_python(candidate.install_root)),
        str(Path(__file__).resolve()),
        "--internal-stop",
        "--install-root",
        str(candidate.install_root),
        "--registry-dir",
        str(registry_dir),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(registry_dir / "pycache" / "recovery-stop"),
        }
    )
    result = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=30, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RecoveryError(detail[-1] if detail else "Не удалось безопасно остановить backend выбранной установки.")
    try:
        return json.loads(result.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RecoveryError("Backend выбранной установки не вернул подтверждение остановки.") from exc


def _internal_stop(install_root: Path, registry_dir: Path) -> int:
    sys.path.insert(0, str(install_root.resolve(strict=False)))
    from backend.app.services.runtime_identity import inspect_runtime_record, read_runtime_records
    from backend.app.services.runtime_supervisor import RuntimeSupervisor

    root_key = _normalized_path(install_root)
    records, invalid = read_runtime_records(registry_dir)
    inspections = [inspect_runtime_record(record) for record in records]
    confirmed = [item for item in inspections if item.confirmed]
    ambiguous_selected = [
        item
        for item in inspections
        if _normalized_path(item.record.install_root) == root_key
        and not item.confirmed
        and item.reason not in {"process-not-running", "process-start-time-mismatch"}
    ]
    if ambiguous_selected:
        raise RecoveryError("Backend выбранной установки не удалось строго подтвердить; процессы не завершались.")
    supervisor = RuntimeSupervisor(registry_dir=registry_dir)
    stopped: list[dict[str, object]] = []
    for inspection in confirmed:
        if _normalized_path(inspection.record.install_root) != root_key:
            continue
        evidence = supervisor.stop_token(inspection.record.instance_token)
        if evidence is None:
            raise RecoveryError("Backend изменился во время подтверждения; восстановление остановлено.")
        stopped.append(evidence.__dict__)
    untouched_other = sum(1 for item in confirmed if _normalized_path(item.record.install_root) != root_key)
    print(
        json.dumps(
            {
                "ok": True,
                "stopped": stopped,
                "untouched_other_backends": untouched_other,
                "invalid_records": len(invalid),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _runtime_build_id(install_root: Path) -> str:
    command = [
        str(_target_python(install_root)),
        "-c",
        (
            "from pathlib import Path; "
            "from backend.app.services.runtime_identity import runtime_build_id; "
            "print(runtime_build_id(Path('.').resolve()))"
        ),
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        command,
        cwd=install_root,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    build_id = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if result.returncode != 0 or len(build_id) != 64:
        raise RecoveryError("Не удалось вычислить build identity выбранной установки.")
    return build_id


def _runtime_environment(
    candidate: InstallationCandidate,
    registry_dir: Path,
    *,
    build_id: str = "bootstrap",
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(_read_assignments(candidate.env_path))
    environment.update(
        {
            "APP_INSTALL_DIR": str(candidate.install_root),
            "APP_HOST": candidate.host,
            "APP_PORT": str(candidate.port),
            "APP_RUNTIME_DIR": str(registry_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(registry_dir / "pycache" / build_id),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def _fetch_identity(host: str, port: int, timeout: float = 0.3) -> dict[str, object] | None:
    request = urllib.request.Request(
        f"http://{host}:{port}/runtime/identity",
        headers={"Accept": "application/json", "Cache-Control": "no-store"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _port_has_listener(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.1):
            return True
    except OSError:
        return False


def _runtime_record(path: Path) -> dict[str, object] | None:
    value = _read_json(path)
    if not value or value.get("application_id") != PRODUCT_ID or int(value.get("schema") or 0) != RUNTIME_STATE_SCHEMA:
        return None
    return value


def _terminate_spawned_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _identity_mismatches(
    identity: dict[str, object],
    *,
    pid: int,
    token: str,
    version: str,
    build_id: str,
    candidate: InstallationCandidate,
) -> list[str]:
    expected = {
        "pid": pid,
        "instance_token": token,
        "version": version,
        "build_id": build_id,
        "install_root": _normalized_path(candidate.install_root),
        "host": candidate.host,
        "port": candidate.port,
    }
    actual = {
        "pid": int(identity.get("pid") or 0),
        "instance_token": str(identity.get("instance_token") or ""),
        "version": str(identity.get("version") or ""),
        "build_id": str(identity.get("build_id") or ""),
        "install_root": _normalized_path(str(identity.get("install_root") or "")),
        "host": str(identity.get("host") or ""),
        "port": int(identity.get("port") or 0),
    }
    return [key for key in expected if expected[key] != actual[key]]


def start_runtime(
    candidate: InstallationCandidate,
    registry_dir: Path,
    *,
    expected_version: str,
    include_startup_path: bool,
    timeout: float = 45.0,
) -> StartedRuntime:
    build_id = _runtime_build_id(candidate.install_root)
    token = secrets.token_hex(TOKEN_LENGTH // 2)
    state_path = registry_dir / f"backend-{token}.json"
    startup_path = registry_dir / f"startup-{token}.json" if include_startup_path else None
    log_dir = registry_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"recovery-backend-{token}.log"
    command = [
        str(_target_python(candidate.install_root)),
        str(candidate.install_root / "scripts" / "runtime_server.py"),
        "--host",
        candidate.host,
        "--port",
        str(candidate.port),
        "--install-root",
        str(candidate.install_root),
        "--instance-token",
        token,
        "--state-path",
        str(state_path),
    ]
    if startup_path is not None:
        command.extend(["--startup-path", str(startup_path)])
    command.extend(["--expected-version", expected_version, "--expected-build-id", build_id])
    environment = _runtime_environment(candidate, registry_dir, build_id=build_id)
    environment["APP_RUNTIME_STATE_PATH"] = str(state_path)
    if startup_path is not None:
        environment["APP_RUNTIME_STARTUP_PATH"] = str(startup_path)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with log_path.open("ab", buffering=0) as output:
        process = subprocess.Popen(
            command,
            cwd=candidate.install_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )

    deadline = time.monotonic() + timeout
    last_stage = "startup-state-missing"
    try:
        while time.monotonic() < deadline:
            if startup_path is not None:
                startup = _read_json(startup_path)
                if startup:
                    last_stage = str(startup.get("stage") or last_stage)
            if process.poll() is not None:
                category = "port-bind-failure" if _port_has_listener(candidate.host, candidate.port) else "child-crash"
                tail = " | ".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])[-1200:]
                raise RecoveryError(
                    f"Новая версия не запустилась: {category}; exit={process.returncode}; stage={last_stage}; {tail}"
                )
            record = _runtime_record(state_path)
            identity = _fetch_identity(candidate.host, candidate.port)
            if record and identity:
                mismatches = _identity_mismatches(
                    identity,
                    pid=process.pid,
                    token=token,
                    version=expected_version,
                    build_id=build_id,
                    candidate=candidate,
                )
                record_mismatches = _identity_mismatches(
                    record,
                    pid=process.pid,
                    token=token,
                    version=expected_version,
                    build_id=build_id,
                    candidate=candidate,
                )
                if not mismatches and not record_mismatches:
                    return StartedRuntime(
                        process.pid,
                        token,
                        expected_version,
                        build_id,
                        str(candidate.install_root),
                        candidate.host,
                        candidate.port,
                        state_path,
                        startup_path,
                        log_path,
                        process,
                    )
                raise RecoveryError(
                    "Новая версия вернула неверную runtime identity: "
                    + ", ".join(sorted(set([*mismatches, *record_mismatches])))
                )
            time.sleep(0.08)
        raise RecoveryError(f"Новая версия не подтвердила запуск: startup-stalled; stage={last_stage}.")
    except BaseException:
        _terminate_spawned_process(process)
        raise


def verify_repeat_launch(candidate: InstallationCandidate, registry_dir: Path, runtime: StartedRuntime) -> dict[str, object]:
    command = [
        str(_target_python(candidate.install_root)),
        str(candidate.install_root / "scripts" / "runtime_bootstrap.py"),
        "start",
    ]
    result = subprocess.run(
        command,
        cwd=candidate.install_root,
        env=_runtime_environment(candidate, registry_dir, build_id=runtime.build_id),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise RecoveryError("Повторный штатный запуск завершился ошибкой.")
    try:
        evidence = json.loads(result.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RecoveryError("Повторный штатный запуск не вернул runtime identity.") from exc
    expected = {
        "pid": runtime.pid,
        "instance_token": runtime.instance_token,
        "version": runtime.version,
        "build_id": runtime.build_id,
        "install_root": runtime.install_root,
        "host": runtime.host,
        "port": runtime.port,
        "reused": True,
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        raise RecoveryError("Повторный штатный запуск не переиспользовал точный подтверждённый backend.")
    return evidence


def _stop_started_runtime(candidate: InstallationCandidate, registry_dir: Path, runtime: StartedRuntime | None) -> None:
    try:
        _run_internal_stop(candidate, registry_dir)
        return
    except RecoveryError:
        if runtime is None or runtime.process is None or runtime.process.poll() is not None:
            raise
        identity = _fetch_identity(runtime.host, runtime.port)
        if identity is None or _identity_mismatches(
            identity,
            pid=runtime.pid,
            token=runtime.instance_token,
            version=runtime.version,
            build_id=runtime.build_id,
            candidate=candidate,
        ):
            raise
        runtime.process.kill()
        runtime.process.wait(timeout=5)


def write_installation_pointer(candidate: InstallationCandidate, version: str) -> Path:
    path = installation_pointer_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "application_id": PRODUCT_ID,
        "schema": INSTALLATION_POINTER_SCHEMA,
        "install_root": str(candidate.install_root),
        "version": version,
        "updated_at": _now_iso(),
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def run_recovery_transaction(
    candidate: InstallationCandidate,
    package: RecoveryPackage,
    package_root: Path,
    *,
    registry_dir: Path | None = None,
    start_fn: Callable[..., StartedRuntime] = start_runtime,
    repeat_fn: Callable[[InstallationCandidate, Path, StartedRuntime], dict[str, object]] = verify_repeat_launch,
) -> dict[str, object]:
    registry = (registry_dir or runtime_registry_dir()).resolve(strict=False)
    data_before = fingerprint_data(candidate)
    env_before = sha256_file(candidate.env_path)
    backup_path, entries = create_verified_backup(candidate, package_root, data_before)
    old_runtime: StartedRuntime | None = None
    new_runtime: StartedRuntime | None = None
    mutation_started = False
    try:
        stop_result = _run_internal_stop(candidate, registry)
        mutation_started = True
        copied = install_program_files(package_root, candidate.install_root)
        app_name, installed_version = _version_metadata(candidate.install_root / "backend/app/version.py")
        if app_name != PRODUCT_NAME or installed_version != package.version:
            raise RecoveryError("Установленная программная часть не подтверждает версию v2.0.7.")
        if sha256_file(candidate.install_root / "backend/requirements.txt") != package.requirements_sha256:
            raise RecoveryError("Установленные закреплённые зависимости не совпадают с recovery manifest.")
        new_runtime = start_fn(
            candidate,
            registry,
            expected_version=package.version,
            include_startup_path=True,
        )
        identity = _fetch_identity(candidate.host, candidate.port, timeout=0.5)
        if identity is None or _identity_mismatches(
            identity,
            pid=new_runtime.pid,
            token=new_runtime.instance_token,
            version=package.version,
            build_id=new_runtime.build_id,
            candidate=candidate,
        ):
            raise RecoveryError("HTTP identity новой версии не подтверждена.")
        data_after = fingerprint_data(candidate)
        if data_after != data_before or sha256_file(candidate.env_path) != env_before:
            raise RecoveryError("Проверка данных после запуска не совпала; запускается rollback.")
        repeat = repeat_fn(candidate, registry, new_runtime)
        pointer = write_installation_pointer(candidate, package.version)
        return {
            "ok": True,
            "source_version": candidate.version,
            "target_version": package.version,
            "install_root": str(candidate.install_root),
            "backup_path": str(backup_path),
            "copied_files": copied,
            "stopped": stop_result.get("stopped", []),
            "new_runtime": {
                "pid": new_runtime.pid,
                "instance_token": new_runtime.instance_token,
                "version": new_runtime.version,
                "build_id": new_runtime.build_id,
                "install_root": new_runtime.install_root,
                "host": new_runtime.host,
                "port": new_runtime.port,
            },
            "repeat_launch": repeat,
            "data_before": data_before.__dict__,
            "data_after": data_after.__dict__,
            "installation_pointer": str(pointer),
        }
    except Exception as exc:
        if not mutation_started:
            raise
        rollback_errors: list[str] = []
        try:
            if new_runtime is not None:
                _stop_started_runtime(candidate, registry, new_runtime)
            else:
                _run_internal_stop(candidate, registry)
        except Exception as stop_exc:
            rollback_errors.append(f"stop: {stop_exc}")
        try:
            restore_program_files(backup_path, candidate.install_root, entries)
        except Exception as restore_exc:
            rollback_errors.append(f"restore: {restore_exc}")
        try:
            restored_name, restored_version = _version_metadata(candidate.install_root / "backend/app/version.py")
            if restored_name != PRODUCT_NAME or restored_version != candidate.version:
                raise RecoveryError("Восстановленная версия не совпадает с исходной.")
            old_runtime = start_fn(
                candidate,
                registry,
                expected_version=candidate.version,
                include_startup_path=False,
            )
        except Exception as start_exc:
            rollback_errors.append(f"restart: {start_exc}")
        try:
            if fingerprint_data(candidate) != data_before or sha256_file(candidate.env_path) != env_before:
                raise RecoveryError("DB/media/.env изменились во время неудачного восстановления.")
        except Exception as data_exc:
            rollback_errors.append(f"data: {data_exc}")
        if rollback_errors:
            raise RecoveryError(
                f"Восстановление v2.0.7 не удалось ({exc}); rollback требует помощи: " + " | ".join(rollback_errors)
            ) from exc
        raise RecoveryError(
            f"Восстановление v2.0.7 не удалось. Предыдущая v{candidate.version} восстановлена и запущена; данные сохранены."
        ) from exc


def run_recovery(service_dir: Path, ui: RecoveryUI | None = None) -> dict[str, object]:
    interface = ui or ConsoleUI()
    package = load_recovery_package(service_dir.resolve(strict=False))
    registry = runtime_registry_dir()
    candidates, source = discover_installations(registry_dir=registry)
    interface.show(f"Источник выбора установки: {source}.")
    candidate = select_installation(candidates, interface)
    interface.show("Проверяем пакет и создаём безопасную staging-копию...")
    with tempfile.TemporaryDirectory(prefix="FedorinovRewards-Recovery-") as tmpdir:
        package_root = validate_and_extract_package(package, Path(tmpdir) / "package")
        result = run_recovery_transaction(candidate, package, package_root, registry_dir=registry)
    interface.show("Восстановление завершено. Версия 2.0.7 запущена, база и фотографии сохранены.")
    webbrowser.open(f"http://{candidate.host}:{candidate.port}")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe one-time Fedorinov Rewards v2.0.7 recovery.")
    parser.add_argument("--service-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--internal-stop", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--install-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--registry-dir", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.internal_stop:
            if args.install_root is None or args.registry_dir is None:
                raise RecoveryError("Internal stop requires install root and registry dir.")
            return _internal_stop(args.install_root.resolve(strict=False), args.registry_dir.resolve(strict=False))
        run_recovery(args.service_dir)
        return 0
    except RecoveryCancelled as exc:
        print(str(exc))
        return 2
    except Exception as exc:
        print(f"Восстановление остановлено: {exc}", file=sys.stderr)
        print("Ничего не удаляйте. Сделайте фотографию этого окна и отправьте Александру.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
