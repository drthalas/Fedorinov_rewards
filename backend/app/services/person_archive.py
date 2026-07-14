from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ..config import Settings
from ..repositories.persons import get_person, list_person_rewards, person_photo_items
from .audit import log_action
from .booklets import BookletError, generate_person_archive_profile_pdf
from .media import resolve_media
from .person_files import (
    FORBIDDEN_ARCHIVE_PARTS,
    FORBIDDEN_ARCHIVE_SUFFIXES,
    PersonFilesError,
    person_archive_filename,
    person_folder_status,
)


PROFILE_ARCHIVE_NAME = "Профиль кавалера.pdf"
PHOTO_ARCHIVE_DIR = "Фотографии"
DOCUMENT_ARCHIVE_DIR = "Документы"
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})


class PersonArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class PersonArchiveResult:
    content: bytes
    filename: str
    files_count: int
    size_bytes: int
    entries: tuple[str, ...]
    missing_media: tuple[str, ...]


def build_person_archive(settings: Settings, person_id: int) -> PersonArchiveResult:
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise PersonArchiveError("Награжденный не найден.")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    material_entries, missing_media = _person_material_entries(settings, person_id, person, rewards)
    try:
        profile_pdf = generate_person_archive_profile_pdf(settings, person_id)
    except BookletError as exc:
        raise PersonArchiveError(f"Не удалось сформировать PDF-профиль: {exc}") from exc

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(f"{PHOTO_ARCHIVE_DIR}/", b"")
        archive.writestr(f"{DOCUMENT_ARCHIVE_DIR}/", b"")
        for archive_name, path in material_entries:
            archive.write(path, archive_name)
        archive.writestr(PROFILE_ARCHIVE_NAME, profile_pdf)

    entries = tuple([archive_name for archive_name, _ in material_entries] + [PROFILE_ARCHIVE_NAME])
    content = buffer.getvalue()
    filename = person_archive_filename(str(person.get("fio") or ""), person_id)
    log_action(
        "person_archive_prepared",
        "person",
        person_id,
        {"archive_filename": filename, "files": len(entries), "missing_media": len(missing_media)},
    )
    return PersonArchiveResult(
        content=content,
        filename=filename,
        files_count=len(entries),
        size_bytes=len(content),
        entries=entries,
        missing_media=tuple(missing_media),
    )


def save_person_archive(settings: Settings, person_id: int, target_path: Path) -> PersonArchiveResult:
    result = build_person_archive(settings, person_id)
    archive_path = target_path.resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(result.content)
    return result


def _person_material_entries(
    settings: Settings,
    person_id: int,
    person: dict[str, object],
    rewards: list[dict[str, object]],
) -> tuple[list[tuple[str, Path]], list[str]]:
    data_root = settings.rewards_data_dir.resolve()
    try:
        person_folder, person_folder_exists = person_folder_status(settings, person_id)
    except PersonFilesError as exc:
        raise PersonArchiveError(str(exc)) from exc
    entries_by_path: dict[Path, str] = {}

    if person_folder_exists:
        for path in sorted(person_folder.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if not _safe_material_file(path, person_folder):
                continue
            resolved = path.resolve()
            entries_by_path[resolved] = resolved.relative_to(person_folder.resolve()).as_posix()

    missing_media = []
    for photo in person_photo_items(person, rewards):
        raw_path = photo.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        resolution = resolve_media(settings, raw_path)
        if resolution.fallback:
            missing_media.append(raw_path)
            continue
        resolved = Path(resolution.serving_path).resolve()
        if resolved in entries_by_path or not _safe_linked_material(resolved, data_root):
            continue
        relative = resolved.relative_to(data_root).as_posix()
        entries_by_path[resolved] = f"Связанные материалы/{relative}"

    source_entries = sorted(
        ((source_name, path) for path, source_name in entries_by_path.items()),
        key=lambda item: (item[0].casefold(), item[0]),
    )
    entries = _flatten_material_entries(source_entries)
    return entries, missing_media


def _flatten_material_entries(source_entries: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    used_names: dict[str, set[str]] = {
        PHOTO_ARCHIVE_DIR: set(),
        DOCUMENT_ARCHIVE_DIR: set(),
    }
    entries = []
    for _, path in source_entries:
        archive_dir = PHOTO_ARCHIVE_DIR if path.suffix.lower() in IMAGE_SUFFIXES else DOCUMENT_ARCHIVE_DIR
        filename = _unique_archive_filename(path.name, used_names[archive_dir])
        entries.append((f"{archive_dir}/{filename}", path))
    return entries


def _unique_archive_filename(filename: str, used_names: set[str]) -> str:
    path = Path(filename)
    stem = path.stem or "Материал"
    suffix = path.suffix
    candidate = filename
    duplicate_index = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem} ({duplicate_index}){suffix}"
        duplicate_index += 1
    used_names.add(candidate.casefold())
    return candidate


def _safe_material_file(path: Path, folder: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        relative = path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    forbidden_parts = {part.casefold() for part in FORBIDDEN_ARCHIVE_PARTS}
    if any(part.startswith(".") or part.casefold() in forbidden_parts for part in relative.parts):
        return False
    return path.suffix.lower() not in FORBIDDEN_ARCHIVE_SUFFIXES


def _safe_linked_material(path: Path, data_root: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        relative = path.resolve().relative_to(data_root)
    except ValueError:
        return False
    if not relative.parts or relative.parts[0] not in {"Source", "SourceMark", "default"}:
        return False
    forbidden_parts = {part.casefold() for part in FORBIDDEN_ARCHIVE_PARTS}
    if any(part.startswith(".") or part.casefold() in forbidden_parts for part in relative.parts[1:]):
        return False
    return path.suffix.lower() not in FORBIDDEN_ARCHIVE_SUFFIXES
