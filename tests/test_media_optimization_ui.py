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
from backend.app.services import media_optimization_workflow as workflow
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

    def write_baseline(self) -> None:
        baseline = self.settings.media_optimization_state_dir / "baseline"
        baseline.mkdir(parents=True, exist_ok=True)
        (baseline / "summary.json").write_text(
            json.dumps(
                {
                    "inventory": {"bytes": 1_000_000_000},
                    "records": {
                        "classifications": {
                            "jpeg_candidate": {"files": 10, "bytes": 600_000_000},
                        }
                    },
                    "references": {"missing_reference_occurrences": 0},
                    "quality_forecasts": {
                        "90": {
                            "predicted_total_bytes": 650_000_000,
                            "predicted_saved_bytes": 350_000_000,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_first_run_exposes_only_read_only_check_action(self) -> None:
        with patch.object(router, "get_settings", return_value=self.settings):
            response = self.client.get("/maintenance/media-optimization")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Обслуживание данных", response.text)
        self.assertIn("Оптимизация изображений", response.text)
        self.assertIn("Проверить возможность оптимизации", response.text)
        self.assertNotIn("Создать и оптимизировать копию", response.text)
        self.assertNotIn("confirm_separate_copy", response.text)
        self.assertIn("Данные и изображения не изменяются", response.text)
        self.assertNotIn("Текущая рабочая база", response.text)
        self.assertNotIn("Не оптимизирована", response.text)
        self.assertNotIn("Не проверено", response.text)
        self.assertNotIn("1. Проверить базу", response.text)
        self.assertNotIn("Рабочие копии", response.text)
        self.assertEqual(response.text.count("Проверить возможность оптимизации"), 1)
        self.assertNotIn("<dd data-metric=\"current_bytes\">0 Б</dd>", response.text)
        self.assertNotIn("Сделать эту копию рабочей", response.text)

    def test_check_endpoint_delegates_to_shared_workflow(self) -> None:
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "start_check") as start,
        ):
            response = self.client.post("/maintenance/media-optimization/check", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        start.assert_called_once_with(self.settings)

    def test_first_optimization_is_mandatory_safe_copy_without_checkbox(self) -> None:
        snapshot = {
            "target_complete": False,
            "target_incomplete": False,
        }
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "workflow_snapshot", return_value=snapshot),
            patch.object(router, "start_optimize") as start,
        ):
            accepted = self.client.post("/maintenance/media-optimization/optimize", follow_redirects=False)
        self.assertEqual(accepted.status_code, 303)
        start.assert_called_once_with(self.settings, restart_incomplete=False)

    def test_read_only_mode_blocks_optimization_without_server_error(self) -> None:
        blocked = self.settings.model_copy(update={"read_only": True})
        with patch.object(router, "get_settings", return_value=blocked):
            response = self.client.post(
                "/maintenance/media-optimization/optimize",
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])

    def test_analyzed_first_run_shows_safe_copy_and_space_reserve(self) -> None:
        self.write_baseline()
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(workflow, "_available_bytes", return_value=2_000_000_000),
        ):
            response = self.client.get("/maintenance/media-optimization")
        self.assertIn("Результат проверки", response.text)
        self.assertIn("Можно освободить", response.text)
        self.assertIn("Безопасный режим", response.text)
        self.assertIn("Создать и оптимизировать копию", response.text)
        self.assertIn("Сделать её рабочей отдельным подтверждением", response.text)
        self.assertIn("Всего требуется", response.text)
        self.assertIn("Запас 10%", response.text)
        self.assertIn("полной отдельной копии", response.text)
        self.assertIn("data-primary-safe-copy-action", response.text)
        self.assertNotIn("2. Создать", response.text)
        self.assertNotIn("Рабочие копии", response.text)
        self.assertNotIn("confirm_separate_copy", response.text)

    def test_insufficient_space_disables_safe_copy_action(self) -> None:
        self.write_baseline()
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(workflow, "_available_bytes", return_value=100),
        ):
            response = self.client.get("/maintenance/media-optimization")
        self.assertIn("Недостаточно свободного места", response.text)
        self.assertRegex(
            response.text,
            r'<button class="button" type="submit" data-primary-safe-copy-action disabled>Создать и оптимизировать копию</button>',
        )

    def test_missing_references_explain_non_blocking_repair_and_affected_groups(self) -> None:
        self.write_baseline()
        summary = self.settings.media_optimization_state_dir / "baseline/summary.json"
        payload = json.loads(summary.read_text(encoding="utf-8"))
        payload["references"] = {
            "missing_reference_occurrences": 193,
            "missing_reference_unique_paths": 193,
            "missing_reference_groups": [
                {"label": "Фото кавалеров", "occurrences": 5},
                {"label": "Фото и документы наград", "occurrences": 188},
            ],
            "missing_reference_repair_ready": True,
        }
        summary.write_text(json.dumps(payload), encoding="utf-8")
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(workflow, "_available_bytes", return_value=2_000_000_000),
        ):
            response = self.client.get("/maintenance/media-optimization")
        self.assertIn("старые ссылки на отсутствующие файлы: 193", response.text)
        self.assertIn("Фото кавалеров — 5", response.text)
        self.assertIn("Фото и документы наград — 188", response.text)
        self.assertIn("будут заменены штатным изображением «Нет фото»", response.text)
        self.assertIn("Это предупреждение не мешает созданию копии", response.text)
        self.assertNotRegex(
            response.text,
            r'<button class="button" type="submit" data-primary-safe-copy-action disabled>Создать и оптимизировать копию</button>',
        )

    def test_missing_references_without_placeholder_block_copy_action(self) -> None:
        self.write_baseline()
        summary = self.settings.media_optimization_state_dir / "baseline/summary.json"
        payload = json.loads(summary.read_text(encoding="utf-8"))
        payload["references"] = {
            "missing_reference_occurrences": 193,
            "missing_reference_unique_paths": 193,
            "missing_reference_groups": [{"label": "Фото и документы наград", "occurrences": 193}],
            "missing_reference_repair_ready": False,
        }
        summary.write_text(json.dumps(payload), encoding="utf-8")
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(workflow, "_available_bytes", return_value=2_000_000_000),
        ):
            response = self.client.get("/maintenance/media-optimization")
        self.assertIn("Создание копии заблокировано", response.text)
        self.assertRegex(
            response.text,
            r'<button class="button" type="submit" data-primary-safe-copy-action disabled>Создать и оптимизировать копию</button>',
        )

    def test_preview_activation_and_rollback_routes_use_explicit_states(self) -> None:
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "preview_optimized_workspace") as preview,
        ):
            response = self.client.post("/maintenance/media-optimization/preview", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/legacy?tab=rewards")
        preview.assert_called_once_with(self.settings)

        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "activate_source_workspace") as activate_source,
        ):
            self.client.post("/maintenance/media-optimization/activate-source", follow_redirects=False)
            self.client.post(
                "/maintenance/media-optimization/activate-source",
                data={"confirm_snapshot_rollback": "true"},
                follow_redirects=False,
            )
        self.assertEqual(activate_source.call_count, 2)
        self.assertFalse(activate_source.call_args_list[0].kwargs["confirm_snapshot_rollback"])
        self.assertTrue(activate_source.call_args_list[1].kwargs["confirm_snapshot_rollback"])

    def test_incremental_action_delegates_to_shared_workflow(self) -> None:
        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "start_incremental_optimize") as start,
        ):
            response = self.client.post(
                "/maintenance/media-optimization/optimize-incremental",
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        start.assert_called_once_with(self.settings)

    def test_incomplete_copy_is_explicit_restart_not_resume(self) -> None:
        self.write_baseline()
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
        self.assertIn("нельзя продолжить пофайлово", page.text)

        with (
            patch.object(router, "get_settings", return_value=self.settings),
            patch.object(router, "start_optimize") as start,
        ):
            response = self.client.post(
                "/maintenance/media-optimization/optimize",
                data={"restart": "true"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        start.assert_called_once_with(self.settings, restart_incomplete=True)

    def test_operation_error_page_shows_actionable_reason(self) -> None:
        self.write_baseline()
        self.settings.media_optimization_state_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.media_optimization_state_dir / "operation-status.json").write_text(
            json.dumps(
                {
                    "state": "error",
                    "operation": "optimize",
                    "error_code": "target_not_writable",
                    "message": "Не удалось создать оптимизированную копию: папка назначения защищена от записи.",
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
        self.assertIn('window.sessionStorage.setItem(revealNextActionKey, "true")', script)
        self.assertIn('[data-primary-safe-copy-action]:not(:disabled)', script)
        self.assertIn('action.scrollIntoView({ block: "center", inline: "nearest" })', script)
        self.assertIn("rememberCompletedAnalysis();\n      window.location.reload()", script)
        self.assertIn("window.location.assign(finalUrl.href)", script)
        self.assertIn("operation.phase_label", script)
        self.assertIn("updateStages", script)
        self.assertIn("firstRunAction.hidden = running", script)
        self.assertNotIn("Её можно продолжить", script)
        self.assertNotIn("jpeg", script.lower())
        self.assertNotIn("quality", script.lower())

    def test_decimal_byte_format_is_user_readable(self) -> None:
        self.assertEqual(format_bytes(58_957_324_235), "58.96 ГБ")
        self.assertEqual(format_bytes(None), "—")
        self.assertRegex(format_timestamp("2026-08-15T15:38:25+00:00"), r"^15\.08\.2026 \d{2}:38$")


if __name__ == "__main__":
    unittest.main()
