from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from ..config import Settings
from .media_image_policy import ImagePolicyError, normalize_uploaded_image
from .media_filenames import readable_media_stem, write_collision_safe_media
from .write_guard import ensure_write_allowed


MAX_GUIDE_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_GUIDE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
GUIDE_IMAGE_ROOT = "GuideImages"


class GuideImageValidationError(ValueError):
    pass


def normalize_guide_image_path(raw_path: object) -> str:
    if not isinstance(raw_path, str):
        raise GuideImageValidationError("Некорректный путь изображения.")
    value = unquote(raw_path).strip().replace("\\", "/")
    if not value:
        raise GuideImageValidationError("Некорректный путь изображения.")
    candidate = Path(value)
    if candidate.is_absolute() or PureWindowsPath(value).drive:
        raise GuideImageValidationError("Изображение должно находиться внутри каталога справочника.")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise GuideImageValidationError("Недопустимый путь изображения.")
    if len(candidate.parts) != 2 or candidate.parts[0] != GUIDE_IMAGE_ROOT:
        raise GuideImageValidationError("Изображение должно находиться внутри каталога справочника.")
    if candidate.suffix.lower() not in ALLOWED_GUIDE_IMAGE_EXTENSIONS:
        raise GuideImageValidationError("Разрешены только .jpg, .jpeg, .png, .webp")
    return candidate.as_posix()


def save_guide_image(settings: Settings, filename: str, content: bytes) -> str:
    ensure_write_allowed(settings)
    if len(content) > MAX_GUIDE_IMAGE_BYTES:
        raise GuideImageValidationError("Файл изображения больше 5 MB.")
    try:
        normalized = normalize_uploaded_image(filename, content)
    except ImagePolicyError as exc:
        raise GuideImageValidationError(str(exc)) from exc

    root = settings.guide_images_dir.resolve()
    source_stem = readable_media_stem(Path(filename).stem, fallback="изображение_справочника")
    target = write_collision_safe_media(
        root,
        source_stem,
        normalized.extension,
        normalized.content,
    ).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise GuideImageValidationError("Недопустимый путь изображения.") from exc
    return normalize_guide_image_path(f"{GUIDE_IMAGE_ROOT}/{target.name}")
