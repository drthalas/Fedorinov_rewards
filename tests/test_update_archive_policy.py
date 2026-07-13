from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import stat
import unittest

from backend.app.services import updater
from backend.app.services.update_archive_policy import (
    ArchivePolicyError,
    PACKAGE_ROOT_NAME,
    SYSTEM_UI_ASSET_PATHS,
    forbidden_relative_reason,
    normalize_archive_path,
    validate_zip_members,
)
from scripts import check_package_safety


class UpdateArchivePolicyTests(unittest.TestCase):
    def _zip(self, path: Path, members: list[tuple[str | ZipInfo, bytes]]) -> Path:
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            for name, payload in members:
                archive.writestr(name, payload)
        return path

    def test_windows_and_mixed_separators_are_normalized(self) -> None:
        self.assertEqual(
            normalize_archive_path(r"backend\app/static\styles.css"),
            ("backend", "app", "static", "styles.css"),
        )
        for unsafe in (
            "../file",
            r"..\file",
            "/etc/passwd",
            r"C:\temp\file",
            r"\\server\share\file",
            "backend/C:/temp/file",
            "backend/app/file.py.",
        ):
            with self.subTest(path=unsafe), self.assertRaises(ArchivePolicyError):
                normalize_archive_path(unsafe)

    def test_producer_and_consumer_use_the_same_policy(self) -> None:
        samples = [
            "backend/app/main.py",
            "backend/app/static/random.jpg",
            "Source/77/photo.jpg",
            "database/MyDatabase.sqlite",
            "BACKEND/APP/STATIC/RANDOM.PNG",
        ]
        samples.extend("/".join(parts) for parts in SYSTEM_UI_ASSET_PATHS)
        for sample in samples:
            with self.subTest(path=sample):
                producer = check_package_safety._is_forbidden(f"{PACKAGE_ROOT_NAME}/{sample}")
                consumer = updater._is_forbidden_relative(Path(sample))
                self.assertEqual(producer, consumer)

    def test_exact_system_assets_are_allowed_but_arbitrary_images_are_rejected(self) -> None:
        for parts in SYSTEM_UI_ASSET_PATHS:
            self.assertIsNone(forbidden_relative_reason(Path(*parts)))
        for path in (
            "backend/app/static/random.jpg",
            "backend/app/static/assets/random.png",
            "backend/app/static/assets/random.webp",
            "backend/app/static/assets/random.svg",
            "Source/77/photo.jpg",
            "SourceMark/photo.png",
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(forbidden_relative_reason(path))

    def test_zip_rejects_duplicate_casefold_path(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = self._zip(
                Path(tmpdir) / "duplicate.zip",
                [
                    (f"{PACKAGE_ROOT_NAME}/backend/app/main.py", b"one"),
                    (f"{PACKAGE_ROOT_NAME}/BACKEND/app/main.py", b"two"),
                ],
            )
            with ZipFile(path) as archive, self.assertRaisesRegex(ArchivePolicyError, "duplicate normalized path"):
                validate_zip_members(archive)

    def test_zip_rejects_symlink_entry(self) -> None:
        with TemporaryDirectory() as tmpdir:
            info = ZipInfo(f"{PACKAGE_ROOT_NAME}/backend/app/link.py")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            path = self._zip(Path(tmpdir) / "link.zip", [(info, b"target")])
            with ZipFile(path) as archive, self.assertRaisesRegex(ArchivePolicyError, "link or special"):
                validate_zip_members(archive)

    def test_zip_rejects_wrong_system_asset_content(self) -> None:
        relative = "/".join(next(iter(SYSTEM_UI_ASSET_PATHS)))
        with TemporaryDirectory() as tmpdir:
            path = self._zip(Path(tmpdir) / "fake-image.zip", [(f"{PACKAGE_ROOT_NAME}/{relative}", b"not an image")])
            with ZipFile(path) as archive, self.assertRaisesRegex(ArchivePolicyError, "invalid system UI asset"):
                validate_zip_members(archive)

    def test_zip_accepts_exact_system_asset_with_valid_content(self) -> None:
        relative = next(parts for parts in SYSTEM_UI_ASSET_PATHS if parts[-1].endswith(".png"))
        with TemporaryDirectory() as tmpdir:
            path = self._zip(
                Path(tmpdir) / "valid-image.zip",
                [(f"{PACKAGE_ROOT_NAME}/{'/'.join(relative)}", b"\x89PNG\r\n\x1a\ncontent")],
            )
            with ZipFile(path) as archive:
                validated = validate_zip_members(archive)
            self.assertEqual(len(validated), 1)

    def test_zip_rejects_oversized_member(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = self._zip(Path(tmpdir) / "large.zip", [(f"{PACKAGE_ROOT_NAME}/README.md", b"1234")])
            with patch("backend.app.services.update_archive_policy.MAX_MEMBER_UNCOMPRESSED_BYTES", 3):
                with ZipFile(path) as archive, self.assertRaisesRegex(ArchivePolicyError, "too large"):
                    validate_zip_members(archive)

    def test_old_consumer_policy_rejects_every_v2_binary_asset(self) -> None:
        legacy_patterns = ("*.jpg", "*.jpeg", "*.png", "*.pdf", "*.exe", "*.dll", "*.zip")
        import fnmatch

        for parts in SYSTEM_UI_ASSET_PATHS:
            filename = parts[-1]
            self.assertTrue(any(fnmatch.fnmatch(filename, pattern) for pattern in legacy_patterns))


if __name__ == "__main__":
    unittest.main()
