from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import platform
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

from ..config import Settings
from .audit import log_action


class PersonFilesError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveResult:
    path: Path
    filename: str
    files_count: int
    size_bytes: int


FORBIDDEN_ARCHIVE_PARTS = {".env", ".venv", "backups", "database", "logs", "archives", "Source", "SourceMark"}
FORBIDDEN_ARCHIVE_SUFFIXES = {".zip", ".exe", ".dll"}


def safe_person_folder(settings: Settings, person_id: int) -> Path:
    if person_id <= 0:
        raise PersonFilesError("Некорректный id кавалера")
    root = settings.rewards_data_dir.resolve()
    folder = (settings.rewards_data_dir / "Source" / str(person_id)).resolve()
    try:
        folder.relative_to(root)
    except ValueError as exc:
        raise PersonFilesError("Каталог кавалера находится вне папки данных") from exc
    return folder


def person_folder_status(settings: Settings, person_id: int) -> tuple[Path, bool]:
    folder = safe_person_folder(settings, person_id)
    return folder, folder.exists() and folder.is_dir()


def open_person_folder(settings: Settings, person_id: int, opener=None) -> Path:
    folder, exists = person_folder_status(settings, person_id)
    if not exists:
        raise PersonFilesError("Каталог кавалера не найден.")
    opener = opener or _default_opener
    opener(folder)
    return folder


def archive_person_folder(settings: Settings, person_id: int, fio: str) -> ArchiveResult:
    folder, exists = person_folder_status(settings, person_id)
    if not exists:
        raise PersonFilesError("Каталог кавалера не найден.")
    files = [path for path in folder.rglob("*") if path.is_file() and _allowed_archive_member(path, folder)]
    if not files:
        raise PersonFilesError("В каталоге кавалера нет файлов для архивации.")

    archive_dir = (settings.rewards_data_dir / "archives").resolve()
    root = settings.rewards_data_dir.resolve()
    try:
        archive_dir.relative_to(root)
    except ValueError as exc:
        raise PersonFilesError("Папка архивов находится вне папки данных") from exc
    archive_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{_safe_filename(fio)}_{person_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    archive_path = archive_dir / filename
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(folder).as_posix())

    result = ArchiveResult(
        path=archive_path,
        filename=filename,
        files_count=len(files),
        size_bytes=archive_path.stat().st_size,
    )
    log_action("person_folder_archived", "person", person_id, {"archive_filename": filename, "files": len(files)})
    return result


def _default_opener(path: Path) -> None:
    system = platform.system().lower()
    if system == "windows" and hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if system == "darwin":
        subprocess.run(["open", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path)], check=False)


def _safe_filename(value: str) -> str:
    text = re.sub(r"\s+", "_", str(value or "").strip())
    text = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_.-]+", "_", text).strip("._")
    return text[:80] or "person"


def _allowed_archive_member(path: Path, folder: Path) -> bool:
    relative = path.relative_to(folder)
    parts = set(relative.parts)
    if parts.intersection(FORBIDDEN_ARCHIVE_PARTS):
        return False
    if path.suffix.lower() in FORBIDDEN_ARCHIVE_SUFFIXES:
        return False
    return True
