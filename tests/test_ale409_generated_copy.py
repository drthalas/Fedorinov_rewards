from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.app.services.generated_copy import GeneratedCopyError, open_generated_pdf, stage_generated_pdf


class GeneratedPDFCopyTests(unittest.TestCase):
    def test_staged_pdf_opens_only_by_opaque_token(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            token = stage_generated_pdf(b"%PDF-test", root=root)
            opened = []

            path = open_generated_pdf(token, root=root, opener=opened.append)

            self.assertRegex(token, r"^[0-9a-f]{32}$")
            self.assertEqual(path.read_bytes(), b"%PDF-test")
            self.assertEqual(opened, [path])

    def test_invalid_or_missing_token_never_selects_an_arbitrary_path(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.pdf"
            outside.write_bytes(b"private")
            self.addCleanup(outside.unlink, missing_ok=True)

            for token in ("", "../outside", "f" * 31, "g" * 32):
                with self.subTest(token=token), self.assertRaises(GeneratedCopyError):
                    open_generated_pdf(token, root=root, opener=lambda _path: None)

            self.assertEqual(outside.read_bytes(), b"private")


if __name__ == "__main__":
    unittest.main()
