from __future__ import annotations

import io
import random
import unittest

from PIL import Image

from backend.app.services.media_image_policy import (
    ImagePolicyError,
    normalize_uploaded_image,
)
from tests.image_fixtures import JPEG_BYTES, PNG_BYTES, WEBP_BYTES, image_bytes


class MediaImagePolicyTests(unittest.TestCase):
    def test_opaque_photo_like_png_is_normalized_to_q90_jpeg(self) -> None:
        source = Image.frombytes("RGB", (512, 512), random.Random(392).randbytes(512 * 512 * 3))
        output = io.BytesIO()
        source.save(output, format="PNG")

        normalized = normalize_uploaded_image("clipboard.png", output.getvalue())

        self.assertEqual(normalized.extension, ".jpg")
        self.assertEqual(normalized.actual_format, "JPEG")
        self.assertEqual(normalized.decision, "converted")
        with Image.open(io.BytesIO(normalized.content)) as decoded:
            self.assertEqual(decoded.format, "JPEG")
            self.assertEqual(decoded.size, source.size)

    def test_alpha_and_graphic_png_remain_lossless(self) -> None:
        alpha = normalize_uploaded_image("alpha.png", image_bytes("PNG", mode="RGBA", size=(512, 512)))
        graphic = normalize_uploaded_image("graphic.png", PNG_BYTES)
        self.assertEqual(alpha.extension, ".png")
        self.assertTrue(alpha.has_transparency)
        self.assertEqual(graphic.extension, ".png")
        self.assertEqual(alpha.content, image_bytes("PNG", mode="RGBA", size=(512, 512)))
        self.assertEqual(graphic.content, PNG_BYTES)

    def test_actual_content_controls_extension(self) -> None:
        png = normalize_uploaded_image("mismatched.jpg", PNG_BYTES)
        jpeg = normalize_uploaded_image("mismatched.png", JPEG_BYTES)
        webp = normalize_uploaded_image("mismatched.jpg", WEBP_BYTES)
        self.assertEqual(png.extension, ".png")
        self.assertEqual(jpeg.extension, ".jpg")
        self.assertEqual(webp.extension, ".webp")

    def test_invalid_content_is_rejected_by_decode(self) -> None:
        with self.assertRaises(ImagePolicyError):
            normalize_uploaded_image("fake.jpg", b"\xff\xd8\xffnot-a-real-image")


if __name__ == "__main__":
    unittest.main()
