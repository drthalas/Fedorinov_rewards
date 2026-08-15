from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


JPEG_CANDIDATE_MIN_BYTES = 64 * 1024
JPEG_CANDIDATE_MIN_DIMENSION = 256
JPEG_MAX_DIMENSION = 65_500
PHOTO_LIKE_MIN_COLORS = 1024
JPEG_QUALITY = 90
JPEG_POLICY_VERSION = "jpeg-q90-opaque-photo-v1"
JPEG_OPTIONS = {
    "quality": JPEG_QUALITY,
    "optimize": False,
    "progressive": False,
    "subsampling": 0,
}
SUPPORTED_UPLOAD_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}


class ImagePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedImage:
    content: bytes
    extension: str
    actual_format: str
    width: int
    height: int
    has_alpha_channel: bool
    has_transparency: bool
    decision: str
    policy_version: str


def alpha_state(image: Image.Image) -> tuple[bool, bool]:
    has_alpha_channel = "A" in image.getbands() or "transparency" in image.info
    if not has_alpha_channel:
        return False, False
    try:
        alpha = image.convert("RGBA").getchannel("A")
        extrema = alpha.getextrema()
        return True, bool(extrema and extrema[0] < 255)
    except (OSError, ValueError):
        return True, True


def photo_like(image: Image.Image) -> bool:
    sample = image.convert("RGB")
    sample.thumbnail((256, 256))
    return sample.getcolors(maxcolors=PHOTO_LIKE_MIN_COLORS) is None


def classify_png(
    image: Image.Image,
    source_bytes: int,
    has_alpha_channel: bool,
    has_transparency: bool,
) -> tuple[str, str]:
    if has_transparency:
        return "keep_lossless_alpha", "actual_transparency"
    if image.mode not in {"RGB", "RGBA"}:
        return "keep_lossless_other", f"non_rgb_mode:{image.mode}"
    if source_bytes < JPEG_CANDIDATE_MIN_BYTES:
        return "keep_lossless_other", "small_source"
    if min(image.size) < JPEG_CANDIDATE_MIN_DIMENSION:
        return "keep_lossless_other", "small_dimension"
    if max(image.size) > JPEG_MAX_DIMENSION:
        return "keep_lossless_other", "jpeg_dimension_limit"
    if not photo_like(image):
        return "keep_lossless_other", "limited_color_graphic_or_document"
    reason = "opaque_photo_like_rgba_png" if has_alpha_channel else "opaque_photo_like_rgb_png"
    return "jpeg_candidate", reason


def _decoded_image(content: bytes) -> tuple[Image.Image, str]:
    try:
        source = Image.open(io.BytesIO(content))
        source.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImagePolicyError("Файл не является корректным поддерживаемым изображением") from exc
    actual_format = (source.format or "UNKNOWN").upper()
    if actual_format not in SUPPORTED_UPLOAD_FORMATS:
        source.close()
        raise ImagePolicyError("Разрешены только JPEG, PNG и WebP")
    return source, actual_format


def normalize_uploaded_image(filename: str, content: bytes) -> NormalizedImage:
    if not content:
        raise ImagePolicyError("Файл пустой")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ImagePolicyError("Разрешены только .jpg, .jpeg, .png, .webp")

    image, actual_format = _decoded_image(content)
    try:
        has_alpha_channel, has_transparency = alpha_state(image)
        width, height = image.size
        if actual_format == "PNG":
            decision, _reason = classify_png(
                image,
                len(content),
                has_alpha_channel,
                has_transparency,
            )
            if decision == "jpeg_candidate":
                output = io.BytesIO()
                image.convert("RGB").save(output, format="JPEG", **JPEG_OPTIONS)
                normalized_content = output.getvalue()
                extension = ".jpg"
                normalized_format = "JPEG"
                decision = "converted"
            else:
                normalized_content = content
                extension = ".png"
                normalized_format = "PNG"
        elif actual_format in {"JPEG", "MPO"}:
            normalized_content = content
            extension = ".jpg"
            normalized_format = "JPEG"
            decision = "already_optimized"
        else:
            normalized_content = content
            extension = ".webp"
            normalized_format = "WEBP"
            decision = "already_optimized"
    finally:
        image.close()

    return NormalizedImage(
        content=normalized_content,
        extension=extension,
        actual_format=normalized_format,
        width=width,
        height=height,
        has_alpha_channel=has_alpha_channel,
        has_transparency=has_transparency,
        decision=decision,
        policy_version=JPEG_POLICY_VERSION,
    )
