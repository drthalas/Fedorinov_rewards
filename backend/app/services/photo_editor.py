"""Local reward photo transforms; no writes until the guarded save pipeline."""
from contextlib import closing
from io import BytesIO
import math
from pathlib import Path
import warnings

from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

from ..config import Settings
from ..db import open_readonly_connection, open_write_connection
from .media import resolve_media
from .photos import MAX_PHOTO_BYTES, PhotoConflictError, PhotoValidationError, PhotoMutationResult, _field_config, _table_name, save_photo_with_result
from .guide_images import MAX_GUIDE_IMAGE_BYTES, save_guide_image
from .media_lifecycle import cleanup_unreferenced_image, discard_uncommitted_image
from uuid import uuid4
from .write_guard import ensure_write_allowed

MAX_EDITOR_PIXELS = 40_000_000


def edited_image(content: bytes, crop: list[int], brightness: float) -> bytes:
    if (len(crop) != 4 or any(type(v) is not int for v in crop)
            or not math.isfinite(brightness) or not 0.25 <= brightness <= 2):
        raise PhotoValidationError("Некорректные параметры редактора.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.width * source.height > MAX_EDITOR_PIXELS:
                    raise PhotoValidationError("Изображение больше 40 миллионов пикселей.")
                image = ImageOps.exif_transpose(source).convert("RGBA")
        x, y, width, height = crop
        if min(x, y) < 0 or min(width, height) < 1 or x + width > image.width or y + height > image.height:
            raise PhotoValidationError("Область обрезки выходит за границы изображения.")
        image = image.crop((x, y, x + width, y + height))
        alpha = image.getchannel("A")
        image = ImageEnhance.Brightness(image.convert("RGB")).enhance(brightness).convert("RGBA")
        image.putalpha(alpha)
        output = BytesIO()
        image.save(output, format="PNG")
        result = output.getvalue()
        if len(result) > MAX_PHOTO_BYTES:
            raise PhotoValidationError("Результат больше 25 MB. Выберите меньшую область.")
        return result
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PhotoValidationError("Не удалось открыть изображение для редактирования.") from exc


def edit_photo(settings: Settings, entity_type: str, entity_id: int, field: str,
               expected_path: str, crop: list[int], brightness: float):
    ensure_write_allowed(settings)
    if entity_type in {"rank", "guide"}:
        if field != "image_path":
            raise PhotoValidationError("Некорректное поле фото")
        table = "guide" if entity_type == "rank" else "guide_lev_3"
    else:
        _field_config(entity_type, field)
        table = _table_name(entity_type)
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        row = connection.execute(f"select {field} from {table} where id = ?", (entity_id,)).fetchone()
    if row is None or not expected_path or row[0] != expected_path:
        raise PhotoConflictError("Фото уже изменено. Закройте редактор и обновите форму.")
    resolution = resolve_media(settings, expected_path)
    if resolution.fallback or not resolution.serving_path:
        raise PhotoValidationError("Исходное фото недоступно.")
    path = Path(resolution.serving_path)
    if path.stat().st_size > MAX_PHOTO_BYTES:
        raise PhotoValidationError("Исходное фото недоступно или больше 25 MB.")
    result = edited_image(path.read_bytes(), crop, brightness)
    if entity_type not in {"rank", "guide"}:
        return save_photo_with_result(settings, entity_type, entity_id, field, "edited.png", result,
                                      expected_path=expected_path)
    if len(result) > MAX_GUIDE_IMAGE_BYTES:
        raise PhotoValidationError("Изображение справочника больше 5 MB. Выберите меньшую область.")
    candidate = None
    roots = frozenset({"GuideImages"})
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(f"select image_path from {table} where id = ?", (entity_id,)).fetchone()
        if current is None or current[0] != expected_path:
            raise PhotoConflictError("Фото уже изменено. Закройте редактор и обновите форму.")
        try:
            candidate = save_guide_image(settings, f"edited_{uuid4().hex}.png", result)
            connection.execute(f"update {table} set image_path = ? where id = ?", (candidate, entity_id))
            connection.commit()
        except Exception:
            connection.rollback()
            discard_uncommitted_image(settings, candidate, allowed_roots=roots)
            raise
    cleanup = cleanup_unreferenced_image(settings, expected_path, allowed_roots=roots)
    return PhotoMutationResult(candidate, cleanup)


def edit_reward_photo(settings: Settings, reward_id: int, field: str, expected_path: str,
                      crop: list[int], brightness: float):
    return edit_photo(settings, "reward", reward_id, field, expected_path, crop, brightness)
