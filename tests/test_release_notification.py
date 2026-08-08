from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate_release_telegram_message.py"
SENDER_PATH = ROOT / "scripts" / "send_release_notification.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ReleaseNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_module("release_notification_generator_test", GENERATOR_PATH)
        self.sender = load_module("release_notification_sender_test", SENDER_PATH)

    def _manifest(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "version": "0.1.1",
                    "notes": [
                        "Добавили понятный статус процесса обновления",
                        "Теперь видно, что программа скачивает и устанавливает новую версию",
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def _full_manifest(self, path: Path) -> Path:
        notes = [
            "Добавили фильтры на главном экране “Награды”: теперь можно отбирать кавалеров по званию, стране, категории, подкатегории и наименованию награды",
            "Добавили итоги на главном экране: количество награждённых, количество наград, в наличии / не в наличии, общая цена покупки, текущая цена и последняя покупка",
            "Добавили двойной клик по кавалеру: теперь можно быстрее открыть карточку",
            "Сделали ссылки кликабельными: “Память народа”, “Форум коллекционеров” и другие безопасные ссылки открываются как ссылки",
            "Улучшили поиск: отключили старые подсказки браузера, добавили поиск по награждённым, наградам, знакам и номерам",
            "Пустой запрос теперь работает понятнее: если выбрать категорию “Награждённые”, “Награды” или “Знаки” и оставить поле пустым, показываются все записи выбранной категории",
            "Улучшили переходы в справочники из форм: из карточки награждённого, награды и знака открывается нужный раздел справочника, а возврат ведёт обратно в форму",
            "Исправили возврат из карточки кавалера обратно на главный экран",
            "Добавили понятный статус процесса обновления: после нажатия “Обновить” видно, что программа скачивает и устанавливает новую версию",
        ]
        path.write_text(json.dumps({"version": "0.1.1", "notes": notes}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_release_message_is_human_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._manifest(Path(tmpdir) / "latest.json")
            message = self.generator.build_message("0.1.1", manifest)
        self.assertIn("Награды и награждённые", message)
        self.assertIn("v0.1.1", message)
        self.assertIn("Откройте программу", message)
        self.assertIn("Нажмите «Обновить»", message)
        self.assertIn("Если включён автоматический перезапуск, программа откроется самостоятельно", message)
        self.assertIn("Если программа не запустилась автоматически, откройте её вручную через start_windows.bat", message)
        self.assertIn("Данные и фотографии при обновлении сохраняются", message)
        self.assertNotIn("Закройте окно запуска", message)
        self.assertNotIn("запустите start_windows.bat снова", message)
        for term in ["endpoint", "router", "repository", "commit", "hash", "GitHub Release", "ZIP"]:
            self.assertNotIn(term, message)

    def test_release_notes_fallback_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            notes = Path(tmpdir) / "0.1.1.md"
            notes.write_text("# 0.1.1\n\n- Улучшили понятность обновления.\n", encoding="utf-8")
            message = self.generator.build_message("0.1.1", release_notes=notes)
        self.assertIn("Улучшили понятность обновления", message)

    def test_release_notes_011_include_user_visible_items(self) -> None:
        notes = (ROOT / "release_notes" / "0.1.1.md").read_text(encoding="utf-8")
        for expected in ["фильтры", "итоги", "поиск", "справочник", "возврат", "обновления"]:
            self.assertIn(expected, notes)

    def test_correction_message_contains_required_user_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._full_manifest(Path(tmpdir) / "latest.json")
            message = self.generator.build_message("0.1.1", manifest, correction=True)
        self.assertIn("Уточнение", message)
        self.assertIn("Награды и награждённые", message)
        self.assertIn("v0.1.1", message)
        for expected in ["фильтры", "итоги", "поиск", "Пустой запрос", "справочники", "возврат", "статус процесса обновления"]:
            self.assertIn(expected, message)
        self.assertIn("Откройте программу", message)
        self.assertIn("Данные и фотографии при обновлении сохраняются", message)
        for term in ["endpoint", "router", "repository", "commit", "hash", "GitHub Release", "ZIP"]:
            self.assertNotIn(term, message)

    def test_missing_manifest_handled_safely(self) -> None:
        message = self.generator.build_message(
            "0.1.1",
            manifest=Path("/no/such/latest.json"),
            release_notes=Path("/no/such/0.1.1.md"),
        )
        self.assertIn("В этой версии внесены улучшения и исправления", message)

    def test_release_message_012_contains_release_instructions_and_user_items(self) -> None:
        message = self.generator.build_message("0.1.2", release_notes=ROOT / "release_notes" / "0.1.2.md")
        self.assertIn("Награды и награждённые", message)
        self.assertIn("v0.1.2", message)
        for expected in ["шахмат", "CSV", "Открыть каталог", "Архивировать", "фотограф", "PDF-буклет", "рабочий режим"]:
            self.assertIn(expected, message)
        self.assertIn("Откройте программу", message)
        self.assertIn("Нажмите «Обновить»", message)
        self.assertIn("Данные и фотографии при обновлении сохраняются", message)
        for term in ["endpoint", "router", "repository", "commit", "hash", "GitHub Release", "ZIP"]:
            self.assertNotIn(term, message)

    def test_dry_run_does_not_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._manifest(Path(tmpdir) / "latest.json")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "send_message") as send_message, \
                patch("sys.argv", ["send_release_notification.py", "--version", "0.1.1", "--manifest", str(manifest), "--dry-run"]):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()

    def test_correction_dry_run_does_not_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._full_manifest(Path(tmpdir) / "latest.json")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "send_message") as send_message, \
                patch(
                    "sys.argv",
                    [
                        "send_release_notification.py",
                        "--version",
                        "0.1.1",
                        "--manifest",
                        str(manifest),
                        "--dry-run",
                        "--correction",
                    ],
                ):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()

    def test_send_test_to_copy_only_does_not_send_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._manifest(Path(tmpdir) / "latest.json")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "resolve_token", return_value="TOKEN"), \
                patch.object(self.sender.daily, "send_message") as send_message, \
                patch.object(self.sender, "LOG_PATH", Path(tmpdir) / "release_notifications.jsonl"), \
                patch("sys.argv", ["send_release_notification.py", "--version", "0.1.1", "--manifest", str(manifest), "--send-test-to-copy-only"]):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_called_once()
        self.assertEqual(send_message.call_args.args[1], 2)

    def test_recovery_dry_run_reports_exact_artifact_without_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recovery = Path(tmpdir) / "FedorinovRewards_Recovery_v2.0.6.zip"
            recovery.write_bytes(b"exact tested recovery")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "send_message") as send_message, \
                patch.object(self.sender.daily, "send_document") as send_document, \
                patch(
                    "sys.argv",
                    [
                        "send_release_notification.py",
                        "--version",
                        "2.0.6",
                        "--recovery-zip",
                        str(recovery),
                        "--dry-run",
                    ],
                ):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()
        send_document.assert_not_called()

    def test_recovery_send_uses_document_once_per_recipient_and_logs_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            recovery = root / "FedorinovRewards_Recovery_v2.0.6.zip"
            recovery.write_bytes(b"exact tested recovery")
            log = root / "release_notifications.jsonl"
            with patch.object(
                self.sender.daily,
                "merged_config",
                return_value={"REPORT_PRIMARY_SEND_CONFIRMED": "true"},
            ), patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), patch.object(
                self.sender.daily, "resolve_token", return_value="TOKEN"
            ), patch.object(self.sender.daily, "send_message") as send_message, patch.object(
                self.sender.daily, "send_document", side_effect=["101", "102"]
            ) as send_document, patch.object(self.sender, "LOG_PATH", log), patch(
                "sys.argv",
                [
                    "send_release_notification.py",
                    "--version",
                    "2.0.6",
                    "--recovery-zip",
                    str(recovery),
                    "--send",
                ],
            ):
                result = self.sender.main()
            entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            expected_sha = self.sender.hashlib.sha256(recovery.read_bytes()).hexdigest()
        self.assertEqual(result, 0)
        send_message.assert_not_called()
        self.assertEqual(send_document.call_count, 2)
        self.assertEqual(send_document.call_args_list[0].args[2], recovery.resolve())
        self.assertEqual([item["message_id"] for item in entries], ["101", "102"])
        self.assertTrue(all(item["artifact_name"] == recovery.name for item in entries))
        self.assertTrue(all(item["artifact_sha256"] == expected_sha for item in entries))


if __name__ == "__main__":
    unittest.main()
