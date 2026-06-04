from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import fnmatch
import json
from pathlib import Path
from shutil import copy2, rmtree
import hashlib
import urllib.error
import urllib.request
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from ..config import Settings
from ..version import APP_VERSION
from .update_checker import check_for_updates


PACKAGE_ROOT_NAME = "FedorinovRewards_WebPreview"
ALLOWED_TOP_LEVEL = {
    ".env.example",
    ".env.windows.example",
    "HELP_RU.md",
    "README.md",
    "backend",
    "deploy",
    "docs",
    "release_notes",
    "scripts",
    "start_windows.bat",
    "start_windows.ps1",
}
FORBIDDEN_EXACT = {".env", ".env.daily-report"}
FORBIDDEN_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "backups",
    "data",
    "database",
    "default",
    "dist",
    "logs",
    "Source",
    "SourceMark",
    "updates",
}
FORBIDDEN_PREFIXES = {
    ("docs", "reports"),
    ("legacy", "_external"),
}
FORBIDDEN_PATTERNS = ("*.sqlite", "*.db", "*.jpg", "*.jpeg", "*.png", "*.pdf", "*.exe", "*.dll", "*.zip")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdatePlan:
    current_version: str
    latest_version: str | None
    update_available: bool
    download_url: str | None
    sha256: str | None
    notes: list[str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parts(path: Path | str) -> tuple[str, ...]:
    return tuple(part for part in Path(path).parts if part not in ("", "."))


def _is_forbidden_relative(relative: Path) -> str | None:
    parts = _parts(relative)
    if not parts:
        return None
    if parts[-1] in FORBIDDEN_EXACT:
        return f"forbidden file: {parts[-1]}"
    if any(part in FORBIDDEN_DIRS for part in parts):
        return "forbidden directory"
    for prefix in FORBIDDEN_PREFIXES:
        if len(parts) >= len(prefix) and parts[: len(prefix)] == prefix:
            return f"forbidden path: {'/'.join(prefix)}"
    if any(fnmatch.fnmatch(parts[-1], pattern) for pattern in FORBIDDEN_PATTERNS):
        return "forbidden file type"
    if parts[0] not in ALLOWED_TOP_LEVEL:
        return f"not an application path: {parts[0]}"
    return None


def validate_package_root(package_root: Path) -> None:
    if not package_root.exists() or not package_root.is_dir():
        raise UpdateError("Некорректный архив обновления: корневая папка пакета не найдена.")
    for path in package_root.rglob("*"):
        relative = path.relative_to(package_root)
        reason = _is_forbidden_relative(relative)
        if reason:
            raise UpdateError(f"Некорректный архив обновления: {relative} ({reason}).")


def find_package_root(extract_dir: Path) -> Path:
    roots = [path for path in extract_dir.iterdir() if path.is_dir()]
    if len(roots) != 1 or roots[0].name != PACKAGE_ROOT_NAME:
        raise UpdateError("Некорректный архив обновления: ожидается папка FedorinovRewards_WebPreview.")
    validate_package_root(roots[0])
    return roots[0]


def download_file(url: str, destination: Path, timeout_seconds: int) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "FedorinovRewardsUpdater/0.1"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=max(1, timeout_seconds)) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Не удалось скачать обновление: {exc}") from exc
    return destination


def verify_zip_sha256(zip_path: Path, expected_sha256: str) -> str:
    actual = sha256_file(zip_path)
    if actual.lower() != str(expected_sha256 or "").strip().lower():
        raise UpdateError("SHA256 скачанного архива не совпадает с latest.json.")
    return actual


def extract_update_zip(zip_path: Path, extract_dir: Path) -> Path:
    if extract_dir.exists():
        rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with ZipFile(zip_path) as archive:
            bad_file = archive.testzip()
            if bad_file:
                raise UpdateError(f"Некорректный архив обновления: повреждён файл {bad_file}.")
            for member in archive.infolist():
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise UpdateError(f"Некорректный архив обновления: небезопасный путь {member.filename}.")
            archive.extractall(extract_dir)
    except BadZipFile as exc:
        raise UpdateError("Некорректный архив обновления: ZIP не читается.") from exc
    return find_package_root(extract_dir)


def create_app_backup(settings: Settings) -> Path:
    install_dir = settings.app_install_dir
    if not install_dir.exists() or not install_dir.is_dir():
        raise UpdateError(f"Папка приложения не найдена: {install_dir}")
    settings.update_backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = settings.update_backup_dir / f"app_backup_{timestamp}.zip"
    with ZipFile(backup_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(install_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(install_dir)
            if _is_forbidden_relative(relative):
                continue
            archive.write(path, relative)
    return backup_path


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy2(source, destination)


def copy_package_files(package_root: Path, install_dir: Path) -> int:
    copied = 0
    for source in sorted(package_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(package_root)
        reason = _is_forbidden_relative(relative)
        if reason:
            raise UpdateError(f"Небезопасный файл обновления: {relative} ({reason}).")
        _copy_file(source, install_dir / relative)
        copied += 1
    return copied


def restore_backup(backup_path: Path, install_dir: Path) -> None:
    with ZipFile(backup_path) as archive:
        for member in archive.infolist():
            relative = Path(member.filename)
            if relative.is_absolute() or ".." in relative.parts or _is_forbidden_relative(relative):
                continue
            destination = install_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                output.write(source.read())


def write_update_log(settings: Settings, entry: dict[str, object]) -> Path:
    log_path = settings.app_install_dir / "updates" / "update_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": datetime.now().isoformat(timespec="seconds"), **entry}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return log_path


def build_update_plan(settings: Settings, current_version: str = APP_VERSION) -> UpdatePlan:
    manifest = check_for_updates(settings, current_version=current_version)
    if manifest.get("error"):
        raise UpdateError(str(manifest["error"]))
    return UpdatePlan(
        current_version=str(manifest.get("current_version") or current_version),
        latest_version=str(manifest.get("latest_version") or "") or None,
        update_available=bool(manifest.get("update_available")),
        download_url=str(manifest.get("download_url") or "") or None,
        sha256=str(manifest.get("sha256") or "") or None,
        notes=[str(note) for note in manifest.get("notes") or []],
    )


def apply_update(
    settings: Settings,
    dry_run: bool = False,
    current_version: str = APP_VERSION,
    zip_downloader=download_file,
) -> dict[str, object]:
    if not settings.update_check_enabled:
        raise UpdateError("Проверка обновлений выключена.")

    plan = build_update_plan(settings, current_version=current_version)
    result: dict[str, object] = {
        "ok": False,
        "dry_run": dry_run,
        "current_version": plan.current_version,
        "latest_version": plan.latest_version,
        "update_available": plan.update_available,
        "download_url": plan.download_url,
        "backup_path": None,
        "copied_files": 0,
        "message": "",
    }
    if not plan.update_available:
        result["message"] = "Обновлений нет. Установлена актуальная версия."
        result["ok"] = True
        return result
    if not plan.download_url or not plan.sha256:
        raise UpdateError("В latest.json нет download_url или sha256.")

    if dry_run:
        result["ok"] = True
        result["message"] = "Доступно обновление. Dry-run: файлы приложения не изменены."
        return result

    settings.update_download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = settings.update_download_dir / f"FedorinovRewards_WebPreview_v{plan.latest_version}.zip"
    zip_downloader(plan.download_url, zip_path, settings.update_timeout_seconds)
    verified_sha = verify_zip_sha256(zip_path, plan.sha256)
    package_root = extract_update_zip(zip_path, settings.update_extract_dir)
    backup_path = create_app_backup(settings)

    try:
        copied = copy_package_files(package_root, settings.app_install_dir)
    except Exception as exc:
        try:
            restore_backup(backup_path, settings.app_install_dir)
        except Exception as rollback_exc:
            raise UpdateError(f"Обновление не удалось, rollback тоже не завершился: {rollback_exc}") from exc
        raise UpdateError(f"Обновление не удалось, текущая версия восстановлена из backup: {exc}") from exc

    result.update(
        {
            "ok": True,
            "sha256": verified_sha,
            "backup_path": str(backup_path),
            "copied_files": copied,
            "message": "Обновление установлено. Закройте окно запуска и запустите start_windows.bat снова.",
        }
    )
    write_update_log(settings, result)
    return result
