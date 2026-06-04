from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import hashlib
import unittest

from backend.app.config import Settings
from backend.app.main import app
from backend.app.services import updater


class UpdaterTests(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            rewards_data_dir=root / "Rewards",
            rewards_db_path=root / "Rewards" / "database" / "MyDatabase.sqlite",
            read_only=True,
            write_mode=False,
            update_check_enabled=True,
            update_manifest_url="https://example.test/latest.json",
            update_timeout_seconds=10,
            app_install_dir=root / "app",
            update_backup_dir=root / "app" / "updates" / "backups",
            update_download_dir=root / "app" / "updates" / "downloads",
            update_extract_dir=root / "app" / "updates" / "extracted",
        )

    def _write_current_app(self, app_dir: Path) -> None:
        (app_dir / "backend" / "app").mkdir(parents=True)
        (app_dir / "backend" / "app" / "main.py").write_text("old", encoding="utf-8")
        (app_dir / "README.md").write_text("old readme", encoding="utf-8")
        (app_dir / ".env").write_text("SECRET=keep\n", encoding="utf-8")
        (app_dir / "database").mkdir()
        (app_dir / "database" / "MyDatabase.sqlite").write_text("do not touch", encoding="utf-8")
        (app_dir / "Source").mkdir()
        (app_dir / "Source" / "photo.jpg").write_text("do not touch", encoding="utf-8")
        (app_dir / "SourceMark").mkdir()
        (app_dir / "SourceMark" / "photo.jpg").write_text("do not touch", encoding="utf-8")

    def _make_update_zip(self, path: Path, members: dict[str, str] | None = None) -> str:
        default_members = {
            "FedorinovRewards_WebPreview/backend/app/main.py": "new",
            "FedorinovRewards_WebPreview/README.md": "new readme",
            "FedorinovRewards_WebPreview/.env.windows.example": "example",
        }
        with ZipFile(path, "w") as archive:
            for name, content in (members or default_members).items():
                archive.writestr(name, content)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _manifest(self, zip_path: Path, checksum: str, version: str = "0.1.1") -> dict[str, object]:
        return {
            "enabled": True,
            "update_available": True,
            "current_version": "0.1.0",
            "latest_version": version,
            "released_at": "2026-06-04",
            "notes": ["test"],
            "download_url": "https://example.test/app.zip",
            "sha256": checksum,
            "error": None,
        }

    def test_sha256_verification_success_and_fail(self) -> None:
        with TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "update.zip"
            checksum = self._make_update_zip(zip_path)
            self.assertEqual(updater.verify_zip_sha256(zip_path, checksum), checksum)
            with self.assertRaises(updater.UpdateError):
                updater.verify_zip_sha256(zip_path, "0" * 64)

    def test_forbidden_paths_in_zip_abort(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            zip_path = tmp / "bad.zip"
            self._make_update_zip(zip_path, {"FedorinovRewards_WebPreview/.env": "bad"})
            with self.assertRaises(updater.UpdateError):
                updater.extract_update_zip(zip_path, tmp / "extract")

    def test_invalid_zip_structure_aborts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            zip_path = tmp / "bad.zip"
            self._make_update_zip(zip_path, {"WrongRoot/README.md": "bad"})
            with self.assertRaises(updater.UpdateError):
                updater.extract_update_zip(zip_path, tmp / "extract")

    def test_dry_run_does_not_change_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = self._settings(root)
            self._write_current_app(settings.app_install_dir)
            manifest = self._manifest(root / "unused.zip", "a" * 64)
            with patch.object(updater, "check_for_updates", return_value=manifest):
                result = updater.apply_update(settings, dry_run=True)
            self.assertTrue(result["ok"])
            self.assertEqual((settings.app_install_dir / "backend" / "app" / "main.py").read_text(), "old")
            self.assertFalse(settings.update_backup_dir.exists())

    def test_no_update_available_does_not_apply(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = self._settings(root)
            self._write_current_app(settings.app_install_dir)
            manifest = {"enabled": True, "update_available": False, "current_version": "0.1.0", "latest_version": "0.1.0", "error": None}
            with patch.object(updater, "check_for_updates", return_value=manifest):
                result = updater.apply_update(settings, dry_run=False)
            self.assertTrue(result["ok"])
            self.assertEqual(result["message"], "Обновлений нет. Установлена актуальная версия.")
            self.assertEqual((settings.app_install_dir / "README.md").read_text(), "old readme")

    def test_apply_update_preserves_env_and_data_and_creates_backup(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = self._settings(root)
            self._write_current_app(settings.app_install_dir)
            local_zip = root / "update.zip"
            checksum = self._make_update_zip(local_zip)
            manifest = self._manifest(local_zip, checksum)

            def fake_downloader(url: str, destination: Path, timeout: int) -> Path:
                destination.write_bytes(local_zip.read_bytes())
                return destination

            with patch.object(updater, "check_for_updates", return_value=manifest):
                result = updater.apply_update(settings, dry_run=False, zip_downloader=fake_downloader)

            self.assertTrue(result["ok"])
            self.assertEqual((settings.app_install_dir / "backend" / "app" / "main.py").read_text(), "new")
            self.assertEqual((settings.app_install_dir / "README.md").read_text(), "new readme")
            self.assertEqual((settings.app_install_dir / ".env").read_text(), "SECRET=keep\n")
            self.assertEqual((settings.app_install_dir / "database" / "MyDatabase.sqlite").read_text(), "do not touch")
            self.assertEqual((settings.app_install_dir / "Source" / "photo.jpg").read_text(), "do not touch")
            self.assertEqual((settings.app_install_dir / "SourceMark" / "photo.jpg").read_text(), "do not touch")
            self.assertTrue(Path(str(result["backup_path"])).exists())
            with ZipFile(str(result["backup_path"])) as archive:
                names = set(archive.namelist())
            self.assertIn("README.md", names)
            self.assertNotIn(".env", names)
            self.assertNotIn("database/MyDatabase.sqlite", names)

    def test_updates_apply_route_requires_post(self) -> None:
        routes = [route for route in app.routes if getattr(route, "path", None) == "/updates/apply"]
        methods = set().union(*(getattr(route, "methods", set()) for route in routes))
        self.assertIn("POST", methods)
        self.assertNotIn("GET", methods)

    def test_legacy_about_template_has_update_form_in_available_branch(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "legacy.html").read_text()
        self.assertIn('action="/updates/apply"', template)
        self.assertIn('name="confirm_update"', template)
        self.assertIn("Доступно обновление", template)


if __name__ == "__main__":
    unittest.main()
