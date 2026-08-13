from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import asyncio
import unittest

from backend.app.config import Settings
from backend.app.routers import legacy
from backend.app.services.app_settings import app_settings_path, program_title, save_program_title
from backend.app.version import APP_NAME, APP_VERSION, APP_VERSION_DATE


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class AboutSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def settings(self, write_mode: bool = True) -> Settings:
        return Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=not write_mode,
            write_mode=write_mode,
        )

    def test_program_title_defaults_to_app_name_and_saves(self) -> None:
        settings = self.settings()

        self.assertEqual(program_title(settings), APP_NAME)
        save_program_title(settings, "Коллекция Сергея")

        self.assertEqual(program_title(settings), "Коллекция Сергея")
        self.assertEqual(app_settings_path(settings), self.root / "app_settings.json")

    def test_empty_program_title_is_preserved(self) -> None:
        settings = self.settings()

        save_program_title(settings, "")

        self.assertEqual(program_title(settings), "")

    def test_about_title_update_saves_setting(self) -> None:
        settings = self.settings()
        request = FakeRequest("program_title=%D0%9C%D0%BE%D1%8F+%D0%B1%D0%B0%D0%B7%D0%B0&return_to=/legacy?tab=about")

        with patch.object(legacy, "get_settings", return_value=settings):
            response = asyncio.run(legacy.legacy_about_title_update(request))

        self.assertEqual(response.status_code, 303)
        self.assertIn("message=", response.headers["location"])
        self.assertEqual(program_title(settings), "Моя база")

    def test_about_title_update_blocks_read_only(self) -> None:
        settings = self.settings(write_mode=False)
        request = FakeRequest("program_title=%D0%9D%D0%B5%D0%BB%D1%8C%D0%B7%D1%8F&return_to=/legacy?tab=about")

        with patch.object(legacy, "get_settings", return_value=settings):
            response = asyncio.run(legacy.legacy_about_title_update(request))

        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])
        self.assertEqual(program_title(settings), APP_NAME)

    def test_about_template_shows_version_date_and_editable_title(self) -> None:
        template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        router = (ROOT / "backend" / "app" / "routers" / "legacy.py").read_text(encoding="utf-8")

        self.assertIn('action="/legacy/about/title"', template)
        self.assertIn('name="program_title"', template)
        self.assertIn("app_display_name", template)
        self.assertIn("app_version_date|format_date", template)
        self.assertIn("APP_VERSION_DATE", router)
        self.assertRegex(APP_VERSION_DATE, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(APP_VERSION, "2.0.13")


if __name__ == "__main__":
    unittest.main()
