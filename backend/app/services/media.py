from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from ..config import Settings


ALLOWED_ROOTS = ("Source", "SourceMark", "default", "GuideImages")


@dataclass
class MediaResolution:
    input_path: str
    normalized_path: str
    resolved_absolute_path: str
    data_root: str
    exists: bool
    is_file: bool
    suffix: str
    readable: bool
    fallback: bool
    fallback_reason: str
    serving_path: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def fallback_image(settings: Settings) -> Path | None:
    if settings.nofoto_path.exists() and settings.nofoto_path.is_file():
        return settings.nofoto_path
    return None


def is_readable_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            handle.read(1)
        return True
    except OSError:
        return False


def _normalize_db_path(raw_path: str) -> str:
    value = unquote(raw_path).strip().strip('"').strip("'")
    if not value:
        return ""
    value = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    if windows.drive and not Path(value).is_absolute():
        return ""
    return value


def _has_traversal(path: Path) -> bool:
    return any(part in {"..", "."} for part in path.parts)


def _fallback_resolution(
    settings: Settings,
    input_path: str,
    normalized_path: str,
    data_root: Path,
    reason: str,
    requested_path: Path | None = None,
) -> MediaResolution:
    exists = requested_path.exists() if requested_path is not None else False
    is_file = requested_path.is_file() if requested_path is not None else False
    readable = is_readable_file(requested_path) if requested_path is not None and exists and is_file else False
    fallback = fallback_image(settings)
    serving_path = fallback if fallback is not None and is_readable_file(fallback) else None
    return MediaResolution(
        input_path=input_path,
        normalized_path=normalized_path,
        resolved_absolute_path=str(requested_path) if requested_path is not None else "",
        data_root=str(data_root),
        exists=exists,
        is_file=is_file,
        suffix=requested_path.suffix if requested_path is not None else "",
        readable=readable,
        fallback=True,
        fallback_reason=reason,
        serving_path=str(serving_path) if serving_path is not None else "",
    )


def resolve_media(settings: Settings, raw_path: object) -> MediaResolution:
    input_path = raw_path if isinstance(raw_path, str) else ""
    data_root = settings.rewards_data_dir.resolve()
    if not isinstance(raw_path, str):
        return _fallback_resolution(settings, input_path, "", data_root, "path is not a string")

    normalized = _normalize_db_path(raw_path)
    if not normalized:
        return _fallback_resolution(settings, input_path, normalized, data_root, "path missing or unsupported")

    candidate = Path(normalized)
    if _has_traversal(candidate):
        return _fallback_resolution(settings, input_path, normalized, data_root, "path traversal rejected")

    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(data_root)
        except ValueError:
            return _fallback_resolution(settings, input_path, normalized, data_root, "path outside data root", candidate)
        if not relative.parts or relative.parts[0] not in ALLOWED_ROOTS:
            return _fallback_resolution(settings, input_path, normalized, data_root, "path root is not allowed", resolved)
        return _resolved_or_fallback(settings, input_path, normalized, data_root, resolved)

    parts = candidate.parts
    if not parts:
        return _fallback_resolution(settings, input_path, normalized, data_root, "path missing")

    if parts[0] not in ALLOWED_ROOTS:
        for index, part in enumerate(parts):
            if part in ALLOWED_ROOTS:
                candidate = Path(*parts[index:])
                parts = candidate.parts
                break
        else:
            return _fallback_resolution(settings, input_path, normalized, data_root, "path root is not allowed")

    resolved = (data_root / candidate).resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError:
        return _fallback_resolution(settings, input_path, normalized, data_root, "path outside data root", resolved)

    return _resolved_or_fallback(settings, input_path, normalized, data_root, resolved)


def _resolved_or_fallback(
    settings: Settings,
    input_path: str,
    normalized_path: str,
    data_root: Path,
    resolved: Path,
) -> MediaResolution:
    exists = resolved.exists()
    is_file = resolved.is_file()
    readable = is_readable_file(resolved) if exists and is_file else False
    if not exists:
        return _fallback_resolution(settings, input_path, normalized_path, data_root, "file does not exist", resolved)
    if not is_file:
        return _fallback_resolution(settings, input_path, normalized_path, data_root, "path is not a file", resolved)
    if not readable:
        return _fallback_resolution(settings, input_path, normalized_path, data_root, "file is not readable", resolved)
    return MediaResolution(
        input_path=input_path,
        normalized_path=normalized_path,
        resolved_absolute_path=str(resolved),
        data_root=str(data_root),
        exists=True,
        is_file=True,
        suffix=resolved.suffix,
        readable=True,
        fallback=False,
        fallback_reason="",
        serving_path=str(resolved),
    )


def resolve_media_path(settings: Settings, raw_path: object) -> Path | None:
    resolution = resolve_media(settings, raw_path)
    return Path(resolution.serving_path) if resolution.serving_path else None
