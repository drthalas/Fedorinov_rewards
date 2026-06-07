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
        self.assertIn("есть изменения без пользовательского описания", text)
        self.assertNotIn("Refactor backend routes", text)
        self.assertNotIn("backend", text)
        self.assertNotIn("workflow", text)

    def test_recent_release_commits_have_factual_russian_summary(self) -> None:
        generator = load_generator()
        with patch.object(
            generator,
            "git_subjects_for_date",
            return_value=[
                "Fix legacy photo frame layout",
                "Add summary PDF export",
                "Prepare v0.1.3 release",
            ],
        ):
            text = generator.build_report(dt.date(2026, 6, 6))

        self.assertIn("реальные фотографии и блоки “Нет фото” теперь находятся в одинаковых рамках", text)
        self.assertIn("PDF-экспорт для сводной таблицы и шахматки", text)
        self.assertIn("подготовили и выпустили релиз v0.1.3", text)
        self.assertIn("проверить, что фото и “Нет фото” отображаются в одинаковых рамках", text)
        self.assertIn("проверить PDF на вкладке “Свод.таблица”", text)
        self.assertIn("проверить обновление через кнопку", text)
        self.assertIn("проверка владельцем после v0.1.3", text)
        self.assertIn("собрать замечания владельца", text)

    def test_known_recent_commits_do_not_use_generic_fallback(self) -> None:
        generator = load_generator()
        with patch.object(
            generator,
            "git_subjects_for_date",
            return_value=[
                "Fix legacy photo frame layout",
                "Add summary PDF export",
                "Unknown backend cleanup",
            ],
        ):
            text = generator.build_report(dt.date(2026, 6, 6))

        self.assertNotIn("доработали рабочий интерфейс и проверки", text)
        self.assertNotIn("внесли технические улучшения в проект", text)
        self.assertNotIn("есть изменения без пользовательского описания", text)
        self.assertNotIn("Unknown backend cleanup", text)
        self.assertNotIn("backend", text)

    def test_check_section_matches_recent_commits(self) -> None:
        generator = load_generator()
        with patch.object(
            generator,
            "git_subjects_for_date",
            return_value=[
                "Fix legacy photo frame layout",
                "Add summary PDF export",
            ],
        ):
            text = generator.build_report(dt.date(2026, 6, 6))

        check_section = text.split("Что теперь можно проверить:", 1)[1].split("Что дальше:", 1)[0]
        self.assertIn("фото и “Нет фото”", check_section)
        self.assertIn("PDF на вкладке “Свод.таблица”", check_section)
        self.assertNotIn("открыть основной экран", check_section)
        self.assertNotIn("кликнуть по фотографии", check_section)

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
