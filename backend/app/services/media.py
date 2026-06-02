from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from ..config import Settings


ALLOWED_ROOTS = ("Source", "SourceMark", "default")


def fallback_image(settings: Settings) -> Path | None:
    if settings.nofoto_path.exists() and settings.nofoto_path.is_file():
        return settings.nofoto_path
    return None


def _normalize_db_path(raw_path: str) -> str:
    value = unquote(raw_path).strip().strip('"').strip("'")
    if not value:
        return ""
    value = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    if windows.drive:
        return ""
    return value


def resolve_media_path(settings: Settings, raw_path: object) -> Path | None:
    if not isinstance(raw_path, str):
        return fallback_image(settings)

    normalized = _normalize_db_path(raw_path)
    if not normalized:
        return fallback_image(settings)

    data_root = settings.rewards_data_dir.resolve()
    candidate = Path(normalized)

    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
            resolved.relative_to(data_root)
        except ValueError:
            return fallback_image(settings)
        return resolved if resolved.exists() and resolved.is_file() else fallback_image(settings)

    parts = candidate.parts
    if not parts or parts[0] not in ALLOWED_ROOTS:
        return fallback_image(settings)

    resolved = (data_root / candidate).resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError:
        return fallback_image(settings)

    if resolved.exists() and resolved.is_file():
        return resolved
    return fallback_image(settings)
