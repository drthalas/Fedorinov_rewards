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


if __name__ == "__main__":
    unittest.main()
