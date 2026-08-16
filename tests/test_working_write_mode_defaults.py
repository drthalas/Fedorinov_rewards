from pathlib import Path
import os
import unittest
from unittest.mock import patch

from backend.app.config import Settings, _default_media_optimization_target, get_settings
from backend.app.services.write_guard import WriteBlockedError, ensure_dangerous_action_allowed, ensure_write_allowed
from backend.app.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]


class WorkingWriteModeDefaultsTests(unittest.TestCase):
    def test_windows_env_defaults_enable_working_write_mode(self) -> None:
        text = (ROOT / ".env.windows.example").read_text(encoding="utf-8")
        self.assertIn("READ_ONLY=false", text)
        self.assertIn("WRITE_MODE=true", text)
        self.assertNotIn("REQUIRE_BACKUP_BEFORE_WRITE", text)
        self.assertNotIn("REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS", text)
        self.assertIn("UPDATE_CHECK_ENABLED=true", text)

    def test_write_guard_blocks_when_write_mode_false(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=False,
            write_mode=False,
        )
        with self.assertRaises(WriteBlockedError):
            ensure_write_allowed(settings)

    def test_write_guard_blocks_when_read_only_true(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=True,
            write_mode=True,
        )
        with self.assertRaises(WriteBlockedError):
            ensure_write_allowed(settings)

    def test_default_settings_allow_write_and_delete(self) -> None:
        settings = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
        )
        ensure_write_allowed(settings)
        ensure_dangerous_action_allowed(settings)

    def test_legacy_backup_environment_cannot_restore_a_write_gate(self) -> None:
        with patch.dict(
            os.environ,
            {
                "REWARDS_DATA_DIR": "/tmp/rewards",
                "REWARDS_DB_PATH": "/tmp/rewards/database/MyDatabase.sqlite",
                "READ_ONLY": "false",
                "WRITE_MODE": "true",
                "REQUIRE_BACKUP_BEFORE_WRITE": "true",
                "REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS": "true",
            },
            clear=False,
        ):
            settings = get_settings()
        self.assertFalse(settings.read_only)
        self.assertTrue(settings.write_mode)
        ensure_write_allowed(settings)
        ensure_dangerous_action_allowed(settings)

    def test_windows_media_optimization_target_is_app_owned_and_source_specific(self) -> None:
        local_app_data = self._temporary_local_app_data()
        first_source = Path("/fixtures/sergey-full/master")
        second_source = Path("/fixtures/other/master")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=False):
            first = _default_media_optimization_target(first_source, platform_name="nt")
            repeated = _default_media_optimization_target(first_source, platform_name="nt")
            second = _default_media_optimization_target(second_source, platform_name="nt")

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, second)
        self.assertEqual(first.parent.parent, local_app_data / "FedorinovRewards" / "media-optimization")
        self.assertEqual(first.name, "optimized-data")
        self.assertFalse(first.is_relative_to(first_source))

    @staticmethod
    def _temporary_local_app_data() -> Path:
        return Path("/tmp/fedorinov-local-app-data")

    def test_dangerous_action_still_respects_read_only_and_write_mode(self) -> None:
        read_only = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=True,
            write_mode=True,
        )
        write_off = Settings(
            rewards_data_dir=Path("/tmp/rewards"),
            rewards_db_path=Path("/tmp/rewards/database/MyDatabase.sqlite"),
            read_only=False,
            write_mode=False,
        )
        with self.assertRaises(WriteBlockedError):
            ensure_dangerous_action_allowed(read_only)
        with self.assertRaises(WriteBlockedError):
            ensure_dangerous_action_allowed(write_off)

    def test_no_backup_gate_message_in_user_surfaces(self) -> None:
        for relative in ["backend/app/templates/base.html", "backend/app/templates/legacy.html", "HELP_RU.md", "README.md"]:
            self.assertNotIn(
                "Create a fresh backup before making changes",
                (ROOT / relative).read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "Перед этим действием нужно создать резервную копию.",
                (ROOT / relative).read_text(encoding="utf-8"),
            )

    def test_app_version_is_current_release(self) -> None:
        self.assertEqual(APP_VERSION, "2.0.13")


if __name__ == "__main__":
    unittest.main()
