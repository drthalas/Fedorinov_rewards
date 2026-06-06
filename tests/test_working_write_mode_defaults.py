from pathlib import Path
import unittest

from backend.app.config import Settings
from backend.app.services.write_guard import WriteBlockedError, ensure_dangerous_action_allowed, ensure_write_allowed
from backend.app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class WorkingWriteModeDefaultsTests(unittest.TestCase):
    def test_windows_env_defaults_enable_working_write_mode(self) -> None:
        text = (ROOT / ".env.windows.example").read_text(encoding="utf-8")
        self.assertIn("READ_ONLY=false", text)
        self.assertIn("WRITE_MODE=true", text)
        self.assertIn("REQUIRE_BACKUP_BEFORE_WRITE=false", text)
        self.assertIn("REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS=true", text)
        self.assertIn("UPDATE_CHECK_ENABLED=true", text)

    def test_write_guard_blocks_when_write_mode_false(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=False,
            write_mode=False,
            require_backup_before_write=False,
        )
        with self.assertRaises(WriteBlockedError):
            ensure_write_allowed(settings)

    def test_write_guard_blocks_when_read_only_true(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=True,
            write_mode=True,
            require_backup_before_write=False,
        )
        with self.assertRaises(WriteBlockedError):
            ensure_write_allowed(settings)

    def test_ordinary_write_allowed_without_mandatory_backup(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=False,
            write_mode=True,
            require_backup_before_write=False,
        )
        ensure_write_allowed(settings)

    def test_dangerous_action_allowed_without_mandatory_backup_when_dangerous_backup_disabled(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=False,
            write_mode=True,
            require_backup_before_write=False,
            require_backup_before_dangerous_actions=False,
        )
        ensure_dangerous_action_allowed(settings)

    def test_dangerous_action_allowed_when_mandatory_write_backup_disabled(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=False,
            write_mode=True,
            require_backup_before_write=False,
            require_backup_before_dangerous_actions=True,
        )
        ensure_dangerous_action_allowed(settings)

    def test_dangerous_action_still_respects_read_only_and_write_mode(self) -> None:
        read_only = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=True,
            write_mode=True,
            require_backup_before_write=False,
            require_backup_before_dangerous_actions=False,
        )
        write_off = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=False,
            write_mode=False,
            require_backup_before_write=False,
            require_backup_before_dangerous_actions=False,
        )
        with self.assertRaises(WriteBlockedError):
            ensure_dangerous_action_allowed(read_only)
        with self.assertRaises(WriteBlockedError):
            ensure_dangerous_action_allowed(write_off)

    def test_no_old_english_backup_message_in_user_templates(self) -> None:
        for relative in ["backend/app/templates/base.html", "backend/app/templates/legacy.html", "HELP_RU.md"]:
            self.assertNotIn(
                "Create a fresh backup before making changes",
                (ROOT / relative).read_text(encoding="utf-8"),
            )

    def test_app_version_is_013(self) -> None:
        self.assertEqual(APP_VERSION, "0.1.3")


if __name__ == "__main__":
    unittest.main()
