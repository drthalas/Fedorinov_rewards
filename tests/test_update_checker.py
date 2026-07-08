from pathlib import Path
import json
import unittest
from unittest.mock import patch
import urllib.error

from backend.app.config import Settings
from backend.app.main import app
from backend.app.routers import updates
from backend.app.services.update_checker import check_for_updates, is_newer_version, parse_semver
from backend.app.version import APP_NAME, APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides) -> Settings:
    values = {
        "rewards_data_dir": Path("/tmp/rewards"),
        "rewards_db_path": Path("/tmp/rewards/database/MyDatabase.sqlite"),
        "read_only": True,
        "write_mode": False,
        "require_backup_before_write": True,
        "require_backup_before_dangerous_actions": True,
        "update_check_enabled": True,
        "update_manifest_url": "https://example.test/latest.json",
        "update_timeout_seconds": 10,
    }
    values.update(overrides)
    return Settings(**values)


def _manifest_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode("utf-8")


class UpdateCheckerTests(unittest.TestCase):
    def test_version_route_returns_app_name_and_version(self) -> None:
        self.assertEqual(updates.version_info(), {"app_name": APP_NAME, "version": APP_VERSION})

    def test_update_route_is_registered(self) -> None:
        version_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/version" and "GET" in getattr(route, "methods", set())
        ]
        update_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/updates/check" and "GET" in getattr(route, "methods", set())
        ]
        self.assertTrue(version_routes)
        self.assertTrue(update_routes)

    def test_parse_semver_and_newer_version(self) -> None:
        self.assertEqual(parse_semver("0.1.1"), (0, 1, 1))
        self.assertIsNone(parse_semver("bad"))
        self.assertTrue(is_newer_version("0.1.1", "0.1.0"))
        self.assertFalse(is_newer_version("0.1.0", "0.1.0"))

    def test_update_checker_disabled(self) -> None:
        result = check_for_updates(_settings(update_check_enabled=False))
        self.assertFalse(result["enabled"])
        self.assertFalse(result["update_available"])
        self.assertIsNone(result["error"])

    def test_update_checker_handles_empty_url(self) -> None:
        result = check_for_updates(_settings(update_manifest_url=""))
        self.assertFalse(result["update_available"])
        self.assertIn("Не указан адрес", str(result["error"]))

    def test_update_checker_detects_newer_version(self) -> None:
        def fetcher(url: str, timeout: int) -> bytes:
            self.assertEqual(url, "https://example.test/latest.json")
            self.assertEqual(timeout, 10)
            return _manifest_bytes(
                {
                    "version": "0.1.14",
                    "released_at": "2026-06-04",
                    "download_url": "https://example.test/app.zip",
                    "sha256": "abc",
                    "notes": ["Новая версия"],
                }
            )

        result = check_for_updates(_settings(), fetcher=fetcher)
        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "0.1.14")
        self.assertEqual(result["notes"], ["Новая версия"])

    def test_update_checker_returns_no_update_for_same_version(self) -> None:
        result = check_for_updates(_settings(), fetcher=lambda url, timeout: _manifest_bytes({"version": APP_VERSION}))
        self.assertFalse(result["update_available"])
        self.assertEqual(result["latest_version"], APP_VERSION)

    def test_update_checker_handles_invalid_json(self) -> None:
        result = check_for_updates(_settings(), fetcher=lambda url, timeout: b"{not-json")
        self.assertFalse(result["update_available"])
        self.assertIn("некорректный JSON", str(result["error"]))

    def test_update_checker_handles_network_error(self) -> None:
        def fetcher(url: str, timeout: int) -> bytes:
            raise urllib.error.URLError("offline")

        result = check_for_updates(_settings(), fetcher=fetcher)
        self.assertFalse(result["update_available"])
        self.assertIn("Не удалось проверить обновления", str(result["error"]))

    def test_updates_check_route_returns_json_dict(self) -> None:
        with patch.object(updates, "get_settings", return_value=_settings(update_check_enabled=False)):
            result = updates.updates_check()
        self.assertIsInstance(result, dict)
        self.assertIn("current_version", result)

    def test_legacy_about_template_contains_update_block(self) -> None:
        template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        legacy_router = (ROOT / "backend" / "app" / "routers" / "legacy.py").read_text()
        self.assertIn("Обновления", template)
        self.assertIn("Проверить обновления", template)
        self.assertIn('method="post" action="/updates/apply"', template)
        self.assertIn("Данные и фотографии не будут затронуты", template)
        self.assertIn("check_for_updates(settings)", legacy_router)
        self.assertIn("check_updates", legacy_router)


if __name__ == "__main__":
    unittest.main()
