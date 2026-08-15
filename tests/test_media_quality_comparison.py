from __future__ import annotations

import io
import unittest

from PIL import Image

from scripts.compare_media_quality import jpeg_bytes, psnr


class MediaQualityComparisonTests(unittest.TestCase):
    def test_quality_profiles_preserve_resolution_and_report_signal(self) -> None:
        original = Image.effect_noise((320, 240), 80).convert("RGB")
        encoded = jpeg_bytes(original, 90)
        with Image.open(io.BytesIO(encoded)) as decoded:
            decoded.load()
            self.assertEqual(decoded.size, original.size)
            self.assertEqual(decoded.format, "JPEG")
            self.assertGreater(psnr(original, decoded), 20)


if __name__ == "__main__":
    unittest.main()
