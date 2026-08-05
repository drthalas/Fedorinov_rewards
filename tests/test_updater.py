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

    def test_corrupt_zip_aborts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            zip_path = tmp / "corrupt.zip"
            zip_path.write_bytes(b"not a zip")
            with self.assertRaisesRegex(updater.UpdateError, "ZIP не читается"):
                updater.extract_update_zip(zip_path, tmp / "extract")

    def test_retry_after_validation_error_uses_fresh_manifest_and_versioned_zip(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = self._settings(root)
            self._write_current_app(settings.app_install_dir)
            failed_zip = root / "v2.0.0.zip"
            failed_sha = self._make_update_zip(
                failed_zip,
                {"FedorinovRewards_WebPreview/backend/app/static/arbitrary.jpg": "forbidden"},
            )
            fixed_zip = root / "v2.0.1.zip"
            fixed_sha = self._make_update_zip(fixed_zip)
            manifests = [
                {**self._manifest(failed_zip, failed_sha, version="2.0.0"), "download_url": "https://example.test/v2.0.0.zip"},
                {**self._manifest(fixed_zip, fixed_sha, version="2.0.1"), "download_url": "https://example.test/v2.0.1.zip"},
            ]
            downloaded: list[str] = []

            def downloader(url: str, destination: Path, timeout: int) -> Path:
                downloaded.append(destination.name)
                source = failed_zip if "2.0.0" in url else fixed_zip
                destination.write_bytes(source.read_bytes())
                return destination

            with patch.object(updater, "check_for_updates", side_effect=manifests):
                with self.assertRaisesRegex(updater.UpdateError, "forbidden file type"):
                    updater.apply_update(settings, current_version="0.1.14", zip_downloader=downloader)
                result = updater.apply_update(settings, current_version="0.1.14", zip_downloader=downloader)

            self.assertTrue(result["ok"])
            self.assertEqual(
                downloaded,
                ["FedorinovRewards_WebPreview_v2.0.0.zip", "FedorinovRewards_WebPreview_v2.0.1.zip"],
            )
            self.assertEqual((settings.app_install_dir / "backend/app/main.py").read_text(), "new")

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

    def test_update_status_idle_by_default_and_success_after_apply(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = self._settings(root)
            self._write_current_app(settings.app_install_dir)
            local_zip = root / "update.zip"
            checksum = self._make_update_zip(local_zip)
            manifest = self._manifest(local_zip, checksum)

            self.assertEqual(updater.read_update_status(settings)["status"], "idle")

            def fake_downloader(url: str, destination: Path, timeout: int) -> Path:
                destination.write_bytes(local_zip.read_bytes())
                return destination

            with patch.object(updater, "check_for_updates", return_value=manifest):
                result = updater.apply_update(settings, dry_run=False, zip_downloader=fake_downloader)

            status = updater.read_update_status(settings)
            self.assertTrue(result["ok"])
            self.assertEqual(status["status"], "success")
            self.assertEqual(status["step"], "success")

    def test_second_update_blocked_when_status_running(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = self._settings(Path(tmpdir))
            self._write_current_app(settings.app_install_dir)
            updater.write_update_status(settings, "running", "downloading")
            with self.assertRaisesRegex(updater.UpdateError, "Обновление уже выполняется"):
                updater.apply_update(settings, dry_run=False)

    def test_error_status_after_apply_failure(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = self._settings(root)
            self._write_current_app(settings.app_install_dir)
            manifest = self._manifest(root / "unused.zip", "a" * 64)

            def failing_downloader(url: str, destination: Path, timeout: int) -> Path:
                raise updater.UpdateError("download failed")

            with patch.object(updater, "check_for_updates", return_value=manifest):
                with self.assertRaises(updater.UpdateError):
                    updater.apply_update(settings, dry_run=False, zip_downloader=failing_downloader)

            status = updater.read_update_status(settings)
            self.assertEqual(status["status"], "error")
            self.assertEqual(status["step"], "error")
            self.assertIn("download failed", str(status["error"]))

    def test_rollback_removes_only_candidate_files_missing_before_install(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            install_dir = root / "app"
            package_root = root / "package"
            (install_dir / "backend").mkdir(parents=True)
            (install_dir / "backend" / "existing.py").write_text("old", encoding="utf-8")
            (install_dir / "local-note.txt").write_text("keep", encoding="utf-8")
            (package_root / "backend" / "new_module.py").parent.mkdir(parents=True)
            (package_root / "backend" / "new_module.py").write_text("new", encoding="utf-8")
            (package_root / "backend" / "existing.py").write_text("new", encoding="utf-8")

            introduced = updater.package_files_missing_from_install(package_root, install_dir)
            updater.copy_package_files(package_root, install_dir)
            removed = updater.remove_new_package_files(install_dir, introduced)

            self.assertEqual(removed, 1)
            self.assertFalse((install_dir / "backend" / "new_module.py").exists())
            self.assertTrue((install_dir / "backend" / "existing.py").exists())
            self.assertEqual((install_dir / "local-note.txt").read_text(encoding="utf-8"), "keep")

    def test_updates_apply_route_requires_post(self) -> None:
        routes = [route for route in app.routes if getattr(route, "path", None) == "/updates/apply"]
        methods = set().union(*(getattr(route, "methods", set()) for route in routes))
        self.assertIn("POST", methods)
        self.assertNotIn("GET", methods)

    def test_updates_status_route_registered(self) -> None:
        routes = [route for route in app.routes if getattr(route, "path", None) == "/updates/status"]
        methods = set().union(*(getattr(route, "methods", set()) for route in routes))
        self.assertIn("GET", methods)

    def test_legacy_about_template_has_update_form_in_available_branch(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "legacy.html").read_text()
        self.assertIn('action="/updates/apply"', template)
        self.assertIn('name="confirm_update"', template)
        self.assertIn("Доступно обновление", template)
        self.assertIn("data-update-progress", template)
        self.assertIn("Проверяем новую версию", template)
        self.assertIn("Скачиваем обновление", template)


if __name__ == "__main__":
    unittest.main()
