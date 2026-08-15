from __future__ import annotations

import io

from PIL import Image


def image_bytes(format_name: str, *, mode: str = "RGB", size: tuple[int, int] = (24, 24)) -> bytes:
    color: tuple[int, ...] = (70, 120, 180, 160) if mode == "RGBA" else (70, 120, 180)
    image = Image.new(mode, size, color)
    output = io.BytesIO()
    image.save(output, format=format_name)
    return output.getvalue()


JPEG_BYTES = image_bytes("JPEG")
PNG_BYTES = image_bytes("PNG")
WEBP_BYTES = image_bytes("WEBP")
