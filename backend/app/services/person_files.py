from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
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


@dataclass(frozen=True)
class ArchiveBytesResult:
    content: bytes
    filename: str
    files_count: int
    size_bytes: int


FORBIDDEN_ARCHIVE_PARTS = {".env", ".venv", "backups", "database", "logs", "archives", "Source", "SourceMark"}
FORBIDDEN_ARCHIVE_SUFFIXES = {".zip", ".exe", ".dll"}
ALLOWED_PERSON_FOLDER_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


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


def person_folder_image_items(
    settings: Settings,
    person_id: int,
    known_paths: list[object] | tuple[object, ...] | None = None,
) -> list[dict[str, str]]:
    folder, exists = person_folder_status(settings, person_id)
    if not exists:
        return []

    root = settings.rewards_data_dir.resolve()
    known_absolute_paths = _known_absolute_paths(settings, known_paths or [])
    items: list[dict[str, str]] = []
    seen = set(known_absolute_paths)
    for path in sorted(folder.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or not _allowed_person_folder_image(path, folder):
            continue
        relative_to_person = path.relative_to(folder)
        if relative_to_person.parts and relative_to_person.parts[0].casefold() == "materials":
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        seen.add(resolved)
        items.append({"label": f"Дополнительное фото: {path.name}", "path": relative})
    return items


def archive_person_folder(settings: Settings, person_id: int, fio: str, target_path: Path | None = None) -> ArchiveResult:
    folder, exists = person_folder_status(settings, person_id)
    if not exists:
        raise PersonFilesError("Каталог кавалера не найден.")
    files = [path for path in folder.rglob("*") if path.is_file() and _allowed_archive_member(path, folder)]
    if not files:
        raise PersonFilesError("В каталоге кавалера нет файлов для архивации.")

    if target_path is None:
        archive_dir = (settings.rewards_data_dir / "archives").resolve()
        root = settings.rewards_data_dir.resolve()
        try:
            archive_dir.relative_to(root)
        except ValueError as exc:
            raise PersonFilesError("Папка архивов находится вне папки данных") from exc
        archive_dir.mkdir(parents=True, exist_ok=True)
        filename = person_archive_filename(fio, person_id)
        archive_path = archive_dir / filename
    else:
        archive_path = target_path.resolve()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        filename = archive_path.name
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


def archive_person_folder_bytes(settings: Settings, person_id: int, fio: str) -> ArchiveBytesResult:
    folder, exists = person_folder_status(settings, person_id)
    if not exists:
        raise PersonFilesError("Каталог кавалера не найден.")
    files = [path for path in folder.rglob("*") if path.is_file() and _allowed_archive_member(path, folder)]
    if not files:
        raise PersonFilesError("В каталоге кавалера нет файлов для архивации.")

    filename = person_archive_filename(fio, person_id)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(folder).as_posix())
    content = buffer.getvalue()
    log_action("person_folder_archived", "person", person_id, {"archive_filename": filename, "files": len(files)})
    return ArchiveBytesResult(
        content=content,
        filename=filename,
        files_count=len(files),
        size_bytes=len(content),
    )


def person_archive_filename(fio: str, person_id: int) -> str:
    return f"{_safe_filename(fio)}_{person_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"


def _default_opener(path: Path) -> None:
    system = platform.system().lower()
    if system == "windows" and hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if system == "darwin":
        subprocess.run(["open", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path)], check=False)


def _known_absolute_paths(settings: Settings, paths: list[object] | tuple[object, ...]) -> set[Path]:
    root = settings.rewards_data_dir.resolve()
    known: set[Path] = set()
    for raw_path in paths:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        normalized = raw_path.strip().replace("\\", "/")
        candidate = Path(normalized)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            parts = candidate.parts
            if not parts:
                continue
            if parts[0] not in {"Source", "SourceMark", "default"}:
                for index, part in enumerate(parts):
                    if part in {"Source", "SourceMark", "default"}:
                        candidate = Path(*parts[index:])
                        break
                else:
                    continue
            resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        known.add(resolved)
    return known


def _allowed_person_folder_image(path: Path, folder: Path) -> bool:
    try:
        relative = path.relative_to(folder)
    except ValueError:
        return False
    if any(part.startswith(".") for part in relative.parts):
        return False
    if path.suffix.lower() not in ALLOWED_PERSON_FOLDER_IMAGE_SUFFIXES:
        return False
    return True


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
