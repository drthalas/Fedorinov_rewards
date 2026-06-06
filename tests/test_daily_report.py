import datetime as dt
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    path = ROOT / "scripts" / "generate_daily_report.py"
    spec = importlib.util.spec_from_file_location("generate_daily_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DailyReportTests(unittest.TestCase):
    def test_report_uses_human_language_for_known_changes(self) -> None:
        generator = load_generator()
        with patch.object(
            generator,
            "git_subjects_for_date",
            return_value=[
                "Add daily Telegram progress reports",
                "Stage 3G search rewrite",
                "Make legacy UI single shell and add photo lightbox",
            ],
        ):
            text = generator.build_report(dt.date(2026, 6, 3))

        self.assertIn("Доброе утро!", text)
        self.assertIn("Награды и награждённые", text)
        self.assertIn("ежедневный утренний отчёт", text)
        self.assertIn("исправили поиск по фамилиям", text)
        self.assertIn("фото открываются крупно прямо на странице", text)
        for forbidden in generator.BANNED_TERMS:
            self.assertNotIn(forbidden, text)

    def test_empty_day_report_is_safe(self) -> None:
        generator = load_generator()
        with patch.object(generator, "git_subjects_for_date", return_value=[]):
            text = generator.build_report(dt.date(2026, 6, 3))

        self.assertIn("новых доработок не было", text)
        self.assertNotIn(".env", text)
        self.assertNotIn("SQLite", text)

    def test_known_english_commit_messages_are_translated(self) -> None:
        generator = load_generator()
        with patch.object(
            generator,
            "git_subjects_for_date",
            return_value=[
                "Add person booklet PDF",
                "Fix cascading guide dropdowns",
                "Improve search results and suggestions",
                "Implement browser Save As for exports",
                "Polish forms validation and errors",
                "Fix delete backup guard in working write mode",
            ],
        ):
            text = generator.build_report(dt.date(2026, 6, 5))

        self.assertIn("добавили PDF-буклет по кавалеру", text)
        self.assertIn("исправили выпадающие справочники", text)
        self.assertIn("улучшили поиск", text)
        self.assertIn("сохранение файлов через системное окно браузера", text)
        self.assertIn("улучшили проверки форм", text)
        self.assertIn("исправили удаление записей", text)

        for forbidden in ["Add", "Fix", "Improve", "Update", "Release", "backend", "endpoint", "route", "commit"]:
            self.assertNotIn(forbidden, text)

    def test_unknown_english_commit_message_uses_russian_fallback(self) -> None:
        generator = load_generator()
        with patch.object(
            generator,
            "git_subjects_for_date",
            return_value=["Refactor backend routes for internal workflow"],
        ):
            text = generator.build_report(dt.date(2026, 6, 5))

        self.assertIn("Награды и награждённые", text)
        self.assertIn("доработали рабочий интерфейс и проверки", text)
        self.assertNotIn("Refactor backend routes", text)
        self.assertNotIn("backend", text)
        self.assertNotIn("workflow", text)

    def test_report_rejects_commit_style_words(self) -> None:
        generator = load_generator()
        subjects = [
            "Add person booklet PDF",
            "Fix cascading guide dropdowns",
            "Improve search results and suggestions",
            "Update internal backend endpoint",
            "Release workflow cleanup",
        ]
        with patch.object(generator, "git_subjects_for_date", return_value=subjects):
            text = generator.build_report(dt.date(2026, 6, 5))

        for forbidden in ["Add", "Fix", "Improve", "Update", "Release", "backend", "endpoint", "route", "commit"]:
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
