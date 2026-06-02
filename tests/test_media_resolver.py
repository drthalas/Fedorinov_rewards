from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.app.config import Settings
from backend.app.services.media import resolve_media_path


class MediaResolverTests(unittest.TestCase):
    def make_settings(self, root: Path) -> Settings:
        return Settings(
            rewards_data_dir=root,
            rewards_db_path=root / "database" / "MyDatabase.sqlite",
            read_only=True,
        )

    def test_resolves_posix_and_windows_relative_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "Source" / "1" / "1" / "FotoFront.jpg"
            fallback = root / "default" / "nofoto.jpg"
            media.parent.mkdir(parents=True)
            fallback.parent.mkdir(parents=True)
            media.write_bytes(b"real")
            fallback.write_bytes(b"fallback")
            settings = self.make_settings(root)

            self.assertEqual(resolve_media_path(settings, "Source/1/1/FotoFront.jpg"), media.resolve())
            self.assertEqual(resolve_media_path(settings, "Source\\1\\1\\FotoFront.jpg"), media.resolve())

    def test_rejects_traversal_and_outside_absolute_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fallback = root / "default" / "nofoto.jpg"
            fallback.parent.mkdir(parents=True)
            fallback.write_bytes(b"fallback")
            settings = self.make_settings(root)

            self.assertEqual(resolve_media_path(settings, "../database/MyDatabase.sqlite"), fallback)
            self.assertEqual(resolve_media_path(settings, "/etc/passwd"), fallback)

    def test_allows_absolute_path_inside_data_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "SourceMark" / "6" / "FotoFront.jpg"
            fallback = root / "default" / "nofoto.jpg"
            media.parent.mkdir(parents=True)
            fallback.parent.mkdir(parents=True)
            media.write_bytes(b"real")
            fallback.write_bytes(b"fallback")
            settings = self.make_settings(root)

            self.assertEqual(resolve_media_path(settings, str(media)), media.resolve())

    def test_missing_file_returns_fallback(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fallback = root / "default" / "nofoto.jpg"
            fallback.parent.mkdir(parents=True)
            fallback.write_bytes(b"fallback")
            settings = self.make_settings(root)

            self.assertEqual(resolve_media_path(settings, "Source/1/missing.jpg"), fallback)


if __name__ == "__main__":
    unittest.main()
