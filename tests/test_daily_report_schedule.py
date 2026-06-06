from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "send_daily_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("send_daily_report_test_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DummyGenerator:
    @staticmethod
    def default_report_date() -> dt.date:
        return dt.date(2026, 6, 3)

    @staticmethod
    def build_report(report_date: dt.date) -> str:
        return f"Доброе утро!\n\nЗа вчера по проекту “Награды и награждённые” сделали:\n\n1. Test {report_date.isoformat()}"


class DailyReportScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.config = {
            "REPORT_TIMEZONE": "Europe/Moscow",
            "REPORT_SEND_HOUR": "9",
            "REPORT_SEND_MINUTE": "0",
            "REPORT_SEND_WINDOW_MINUTES": "15",
        }
        self.report_date = dt.date(2026, 6, 3)

    def test_scheduled_mode_outside_moscow_window_does_not_send(self) -> None:
        now = dt.datetime(2026, 6, 4, 8, 45, tzinfo=ZoneInfo("Europe/Moscow"))
        status = self.module.scheduled_status(self.config, self.report_date, 1, [2], now=now)
        self.assertFalse(status["inside_window"])
        self.assertFalse(status["would_send"])
        self.assertEqual(status["reason"], "outside_window")

    def test_scheduled_mode_inside_moscow_window_would_send(self) -> None:
        now = dt.datetime(2026, 6, 4, 9, 5, tzinfo=ZoneInfo("Europe/Moscow"))
        status = self.module.scheduled_status(self.config, self.report_date, 1, [2], now=now)
        self.assertTrue(status["inside_window"])
        self.assertTrue(status["would_send"])
        self.assertEqual(status["reason"], "inside_window")

    def test_already_sent_today_prevents_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "daily_reports.jsonl"
            for role, recipient_id in (("primary", 1), ("copy", 2)):
                log_path.write_text(
                    log_path.read_text() if log_path.exists() else "",
                    encoding="utf-8",
                )
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({
                        "report_date": self.report_date.isoformat(),
                        "recipient_role": role,
                        "recipient_id": recipient_id,
                        "status": "sent",
                    }) + "\n")
            now = dt.datetime(2026, 6, 4, 9, 5, tzinfo=ZoneInfo("Europe/Moscow"))
            status = self.module.scheduled_status(self.config, self.report_date, 1, [2], now=now, log_path=log_path)
        self.assertTrue(status["inside_window"])
        self.assertTrue(status["already_sent"])
        self.assertFalse(status["would_send"])
        self.assertEqual(status["reason"], "already_sent")

    def test_timezone_europe_moscow_is_used_not_local_machine_timezone(self) -> None:
        utc_now = dt.datetime(2026, 6, 4, 6, 5, tzinfo=ZoneInfo("UTC"))
        status = self.module.scheduled_status(self.config, self.report_date, 1, [2], now=utc_now)
        self.assertEqual(status["timezone"], "Europe/Moscow")
        self.assertIn("09:05", status["now"])
        self.assertTrue(status["inside_window"])

    def test_invalid_timezone_gives_clear_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Invalid REPORT_TIMEZONE"):
            self.module.report_timezone({"REPORT_TIMEZONE": "Invalid/Timezone"})

    def test_dry_run_scheduled_never_sends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".env.daily-report"
            config_path.write_text(
                "\n".join([
                    "REPORT_PRIMARY_CHAT_ID=1",
                    "REPORT_COPY_CHAT_IDS=2",
                    "REPORT_PRIMARY_SEND_CONFIRMED=true",
                    "REPORT_TIMEZONE=Europe/Moscow",
                    "REPORT_SEND_HOUR=9",
                    "REPORT_SEND_MINUTE=0",
                    "REPORT_SEND_WINDOW_MINUTES=15",
                ]),
                encoding="utf-8",
            )
            with patch.object(self.module, "LOCAL_CONFIG", config_path), \
                patch.object(self.module, "LOG_PATH", Path(tmp) / "daily_reports.jsonl"), \
                patch.object(self.module, "_load_generate_module", return_value=DummyGenerator), \
                patch.object(self.module, "send_message") as send_message, \
                patch("sys.argv", ["send_daily_report.py", "--scheduled", "--dry-run"]):
                result = self.module.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()

    def test_dry_run_never_sends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".env.daily-report"
            config_path.write_text(
                "\n".join([
                    "REPORT_PRIMARY_CHAT_ID=1",
                    "REPORT_COPY_CHAT_IDS=2",
                    "REPORT_PRIMARY_SEND_CONFIRMED=true",
                ]),
                encoding="utf-8",
            )
            with patch.object(self.module, "LOCAL_CONFIG", config_path), \
                patch.object(self.module, "LOG_PATH", Path(tmp) / "daily_reports.jsonl"), \
                patch.object(self.module, "_load_generate_module", return_value=DummyGenerator), \
                patch.object(self.module, "send_message") as send_message, \
                patch("sys.argv", ["send_daily_report.py", "--dry-run"]):
                result = self.module.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()

    def test_launchd_example_uses_scheduled_mode(self) -> None:
        text = (ROOT / "deploy" / "launchd" / "com.fedorinov.daily-report.plist.example").read_text()
        self.assertIn("<string>--scheduled</string>", text)
        self.assertIn("<key>StartInterval</key>", text)
        self.assertIn("<integer>900</integer>", text)
        self.assertNotIn("StartCalendarInterval", text)


if __name__ == "__main__":
    unittest.main()
