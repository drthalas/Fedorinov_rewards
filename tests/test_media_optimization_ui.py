from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import app
from backend.app.routers import media_optimization as router
from backend.app.services.display import format_bytes, format_timestamp


class MediaOptimizationUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        (self.data / "database").mkdir(parents=True)
        (self.data / "database/MyDatabase.sqlite").write_bytes(b"db")
        self.settings = Settings(
            rewards_data_dir=self.data,
            rewards_db_path=self.data / "database/MyDatabase.sqlite",
            configured_rewards_data_dir=self.data,
            media_optimization_state_dir=self.root / "state",
            media_optimization_target_dir=self.root / "optimized",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_page_exposes_owner_actions_status_and_separate_copy_confirmation(self) -> None:
        with patch.object(router, "get_settings", return_value=self.settings):
            response = self.client.get("/maintenance/media-optimization")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Обслуживание данных", response.text)
        self.assertIn("Оптимизация изображений", response.text)
        self.assertIn("Проверить", response.text)
        self.assertIn("Оптимизировать", response.text)
        self.assertIn("отдельную optimized copy", response.text)
        self.assertIn("Исходная база и изображения останутся без изменений", response.text)
        self.assertIn("Текущий размер", response.text)
        self.assertNotIn("<dd data-metric=\"current_bytes\">0 Б</dd>", response.text)
        self.assertNotIn("Активировать проверенную копию", response.text)

    def test_check_endpoint_delegates_to_shared_workflow(self) -> None:
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "start_check") as start,
        ):
            response = self.client.post("/maintenance/media-optimization/check", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        start.assert_called_once_with(self.settings)

    def test_first_optimization_requires_explicit_confirmation(self) -> None:
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "start_optimize") as start,
        ):
            rejected = self.client.post("/maintenance/media-optimization/optimize", follow_redirects=False)
            accepted = self.client.post(
                "/maintenance/media-optimization/optimize",
                data={"confirm_separate_copy": "true"},
                follow_redirects=False,
            )
        self.assertEqual(rejected.status_code, 303)
        self.assertIn("error=", rejected.headers["location"])
        self.assertEqual(accepted.status_code, 303)
        start.assert_called_once_with(self.settings, restart_incomplete=False)

    def test_read_only_mode_blocks_optimization_without_server_error(self) -> None:
        blocked = self.settings.model_copy(update={"read_only": True})
        with patch.object(router, "get_settings", return_value=blocked):
            response = self.client.post(
                "/maintenance/media-optimization/optimize",
                data={"confirm_separate_copy": "true"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])

    def test_incomplete_copy_is_explicit_restart_not_resume(self) -> None:
        self.settings.media_optimization_state_dir.mkdir(parents=True)
        (self.settings.media_optimization_state_dir / "baseline").mkdir()
        (self.settings.media_optimization_state_dir / "baseline/summary.json").write_text(
            json.dumps({"inventory": {"bytes": 1}}),
            encoding="utf-8",
        )
        self.settings.media_optimization_target_dir.mkdir(parents=True)
        (self.settings.media_optimization_target_dir / ".optimization-incomplete").write_text(
            "incomplete\n",
            encoding="ascii",
        )
        (self.settings.media_optimization_target_dir / "optimization-status.json").write_text(
            json.dumps({"state": "incomplete"}),
            encoding="utf-8",
        )
        with patch.object(router, "get_settings", return_value=self.settings):
            page = self.client.get("/maintenance/media-optimization")
        self.assertIn("Удалить незавершённую копию и начать заново", page.text)
        self.assertIn('name="restart" value="true"', page.text)
        self.assertNotIn('name="resume"', page.text)
        self.assertIn("не поддерживает пофайловое продолжение", page.text)

        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "start_optimize") as start,
        ):
            response = self.client.post(
                "/maintenance/media-optimization/optimize",
                data={"confirm_separate_copy": "true", "restart": "true"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        start.assert_called_once_with(self.settings, restart_incomplete=True)

    def test_operation_error_page_shows_actionable_reason(self) -> None:
        self.settings.media_optimization_state_dir.mkdir(parents=True)
        (self.settings.media_optimization_state_dir / "operation-status.json").write_text(
            json.dumps(
                {
                    "state": "error",
                    "operation": "optimize",
                    "error_code": "target_not_writable",
                    "message": "Не удалось создать optimized copy: папка назначения защищена от записи.",
                }
            ),
            encoding="utf-8",
        )
        with patch.object(router, "get_settings", return_value=self.settings):
            response = self.client.get("/maintenance/media-optimization")
        self.assertIn("папка назначения защищена от записи", response.text)
        self.assertIn("Повторить", response.text)
        self.assertNotIn("Продолжить безопасно", response.text)

    def test_static_client_uses_shared_endpoints_and_recovers_controls_on_failure(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "backend/app/static/media_optimization.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("fetch(form.action", script)
        self.assertIn("setFormsDisabled(observedRunning)", script)
        self.assertIn("button.dataset.defaultDisabled", script)
        self.assertIn("if (observedRunning) schedulePoll()", script)
        self.assertIn("window.location.reload()", script)
        self.assertNotIn("Её можно продолжить", script)
        self.assertNotIn("jpeg", script.lower())
        self.assertNotIn("quality", script.lower())

    def test_decimal_byte_format_is_user_readable(self) -> None:
        self.assertEqual(format_bytes(58_957_324_235), "58.96 ГБ")
        self.assertEqual(format_bytes(None), "—")
        self.assertRegex(format_timestamp("2026-08-15T15:38:25+00:00"), r"^15\.08\.2026 \d{2}:38$")


if __name__ == "__main__":
    unittest.main()
