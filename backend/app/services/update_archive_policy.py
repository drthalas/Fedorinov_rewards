from __future__ import annotations

import fnmatch
from pathlib import Path
import re
import stat
from zipfile import ZipFile, ZipInfo


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
FORBIDDEN_PATTERNS = (
    "*.sqlite",
    "*.db",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.webp",
    "*.svg",
    "*.gif",
    "*.pdf",
    "*.exe",
    "*.dll",
    "*.zip",
)

# These are application-owned assets only. Arbitrary images remain forbidden.
SYSTEM_UI_ASSET_PATHS = {
    ("backend", "app", "static", "assets", "cavaliers", "cavaliers-empty-state-awards.png"),
    ("backend", "app", "static", "assets", "cavaliers", "left-rail.png"),
    ("backend", "app", "static", "assets", "cavaliers", "top-right-emblem.png"),
    ("backend", "app", "static", "assets", "guides", "archive-header-bg.png"),
    ("backend", "app", "static", "assets", "guides", "left-rail.png"),
    ("backend", "app", "static", "assets", "guides", "top-right-emblem.png"),
}

MAX_ARCHIVE_MEMBERS = 20_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000

_DRIVE_PATH_RE = re.compile(r"^[a-zA-Z]:($|/)")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"


class ArchivePolicyError(ValueError):
    pass


def normalize_archive_path(path: Path | str | tuple[str, ...]) -> tuple[str, ...]:
    raw = "/".join(path) if isinstance(path, tuple) else str(path)
    if "\x00" in raw:
        raise ArchivePolicyError("NUL byte in archive path")
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//") or _DRIVE_PATH_RE.match(normalized):
        raise ArchivePolicyError("absolute archive path")

    parts: list[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ArchivePolicyError("path traversal")
        if ":" in part:
            raise ArchivePolicyError("Windows drive or alternate stream path")
        if part.endswith((" ", ".")):
            raise ArchivePolicyError("Windows-ambiguous archive path")
        parts.append(part)
    return tuple(parts)


def strip_package_root(parts: tuple[str, ...]) -> tuple[str, ...]:
    if parts and parts[0] == PACKAGE_ROOT_NAME:
        return parts[1:]
    return parts


def _casefold_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(part.casefold() for part in parts)


def forbidden_relative_reason(
    path: Path | str | tuple[str, ...],
    *,
    allow_system_ui_assets: bool = True,
) -> str | None:
    try:
        parts = strip_package_root(normalize_archive_path(path))
    except ArchivePolicyError as exc:
        return str(exc)
    if not parts:
        return None

    folded = _casefold_parts(parts)
    folded_ui_assets = {_casefold_parts(item) for item in SYSTEM_UI_ASSET_PATHS}
    folded_forbidden_exact = {item.casefold() for item in FORBIDDEN_EXACT}
    folded_forbidden_dirs = {item.casefold() for item in FORBIDDEN_DIRS}
    folded_allowed_top_level = {item.casefold() for item in ALLOWED_TOP_LEVEL}

    if folded[-1] in folded_forbidden_exact:
        return f"forbidden file: {parts[-1]}"
    if any(part in folded_forbidden_dirs for part in folded):
        return "forbidden directory"
    for prefix in FORBIDDEN_PREFIXES:
        folded_prefix = _casefold_parts(prefix)
        if len(folded) >= len(folded_prefix) and folded[: len(folded_prefix)] == folded_prefix:
            return f"forbidden path: {'/'.join(prefix)}"
    if allow_system_ui_assets and folded in folded_ui_assets:
        return None
    if any(fnmatch.fnmatch(folded[-1], pattern.casefold()) for pattern in FORBIDDEN_PATTERNS):
        return "forbidden file type"
    if folded[0] not in folded_allowed_top_level:
        return f"not an application path: {parts[0]}"
    return None


def _is_link_or_special(member: ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0xFFFF
    if not mode:
        return False
    file_type = stat.S_IFMT(mode)
    if file_type == 0:
        return False
    return stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))


def _validate_system_asset_content(archive: ZipFile, member: ZipInfo, relative: tuple[str, ...]) -> None:
    if _casefold_parts(relative) not in {_casefold_parts(item) for item in SYSTEM_UI_ASSET_PATHS}:
        return
    prefix = archive.read(member, pwd=None)[:8]
    suffix = relative[-1].casefold()
    if suffix == ".png" or suffix.endswith(".png"):
        valid = prefix.startswith(_PNG_SIGNATURE)
    elif suffix == ".jpg" or suffix.endswith(".jpg") or suffix.endswith(".jpeg"):
        valid = prefix.startswith(_JPEG_SIGNATURE)
    else:
        valid = False
    if not valid:
        raise ArchivePolicyError(f"invalid system UI asset content: {'/'.join(relative)}")


def validate_zip_members(
    archive: ZipFile,
    *,
    allow_system_ui_assets: bool = True,
    require_package_root: bool = True,
) -> list[tuple[ZipInfo, tuple[str, ...]]]:
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ArchivePolicyError("too many archive members")

    seen: set[tuple[str, ...]] = set()
    total_size = 0
    validated: list[tuple[ZipInfo, tuple[str, ...]]] = []
    for member in members:
        parts = normalize_archive_path(member.filename)
        if not parts:
            continue
        if require_package_root and parts[0] != PACKAGE_ROOT_NAME:
            raise ArchivePolicyError("unexpected package root")
        relative = strip_package_root(parts)
        if not relative:
            continue

        folded = _casefold_parts(relative)
        if folded in seen:
            raise ArchivePolicyError(f"duplicate normalized path: {'/'.join(relative)}")
        seen.add(folded)
        if member.flag_bits & 0x1:
            raise ArchivePolicyError("encrypted archive member")
        if _is_link_or_special(member):
            raise ArchivePolicyError(f"link or special archive member: {'/'.join(relative)}")
        if member.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise ArchivePolicyError(f"archive member too large: {'/'.join(relative)}")
        total_size += member.file_size
        if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ArchivePolicyError("archive uncompressed size limit exceeded")
        if member.file_size and member.compress_size == 0:
            raise ArchivePolicyError(f"suspicious compression size: {'/'.join(relative)}")
        if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
            raise ArchivePolicyError(f"suspicious compression ratio: {'/'.join(relative)}")

        reason = forbidden_relative_reason(relative, allow_system_ui_assets=allow_system_ui_assets)
        if reason:
            raise ArchivePolicyError(f"{'/'.join(relative)} ({reason})")
        if not member.is_dir() and allow_system_ui_assets:
            _validate_system_asset_content(archive, member, relative)
        validated.append((member, relative))
    return validated
