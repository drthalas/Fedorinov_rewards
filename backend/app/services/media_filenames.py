from __future__ import annotations

from pathlib import Path
import re


class MediaFilenameError(RuntimeError):
    pass


WINDOWS_RESERVED_STEMS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def readable_media_stem(value: object, *, fallback: str = "изображение") -> str:
    stem = re.sub(r"\s+", "_", str(value or "").strip())
    stem = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_.-]+", "_", stem).strip("._-")
    stem = stem[:64].rstrip("._-") or fallback
    if stem.casefold() in WINDOWS_RESERVED_STEMS:
        stem = f"_{stem}"
    return stem


def write_collision_safe_media(
    directory: Path,
    stem: object,
    extension: str,
    content: bytes,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    readable_stem = readable_media_stem(stem)
    normalized_extension = extension.lower()
    for sequence in range(1, 10_000):
        suffix = "" if sequence == 1 else f"_{sequence}"
        target = directory / f"{readable_stem}{suffix}{normalized_extension}"
        try:
            with target.open("xb") as handle:
                handle.write(content)
            return target
        except FileExistsError:
            continue
        except Exception:
            target.unlink(missing_ok=True)
            raise
    raise MediaFilenameError("Не удалось подобрать свободное имя файла.")
