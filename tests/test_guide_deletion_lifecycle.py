from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import sqlite3
import unittest

from backend.app.config import Settings
from backend.app.repositories.guides_write import (
    GuideDeleteBlockedError,
    delete_guide_level_item,
    delete_rank,
    guide_delete_confirmation_message,
    guide_delete_preview,
    rank_delete_confirmation_message,
    rank_delete_preview,
)
from backend.app.services.deletion_lifecycle import DeletionCrash, recover_delete_operation


class GuideDeletionLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "audit.jsonl")
        self._create_db()

    def tearDown(self) -> None:
        os.environ.pop("REWARDS_AUDIT_LOG", None)
        self.tmp.cleanup()

    def settings(self) -> Settings:
        return Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
            require_backup_before_write=False,
            require_backup_before_dangerous_actions=False,
        )

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "create table guide (id integer primary key, name text, image_path text)"
            )
            connection.execute(
                "create table person (id integer primary key, id_rank integer)"
            )
            for level in range(5):
                connection.execute(
                    f"create table guide_lev_{level} ("
                    "id integer primary key, idl integer, name text, rating_rank integer, image_path text)"
                )
            connection.execute(
                "create table rewards (id integer primary key, person_id integer, id_gos integer, "
                "id_catigory integer, id_sub_catigory integer, id_name integer, id_link text)"
            )
            connection.execute(
                "create table mark (id integer primary key, id_gos integer, id_catigory integer, "
                "id_sub_catigory integer, id_name integer, id_link text)"
            )

    def _write_image(self, name: str) -> str:
        path = f"GuideImages/{name}"
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        return path

    def _count(self, table: str, row_id: int) -> int:
        with sqlite3.connect(self.db_path) as connection:
            return int(connection.execute(f"select count(*) from {table} where id = ?", (row_id,)).fetchone()[0])

    def test_unused_rank_deletes_final_unshared_image(self) -> None:
        image_path = self._write_image("rank.png")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide values (1, 'Unused', ?)", (image_path,))

        result = delete_rank(self.settings(), 1, confirm=True, operation_id="rank-delete-001")

        self.assertEqual(result.status, "completed")
        self.assertEqual(self._count("guide", 1), 0)
        self.assertFalse((self.root / image_path).exists())

    def test_used_rank_is_blocked_before_media_mutation(self) -> None:
        image_path = self._write_image("used-rank.png")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide values (2, 'Used', ?)", (image_path,))
            connection.execute("insert into person values (10, 2)")

        preview = rank_delete_preview(self.settings(), 2)
        self.assertTrue(preview.blocked)
        self.assertEqual(preview.used_count, 1)
        self.assertIn("Удаление недоступно", rank_delete_confirmation_message(preview))

        with self.assertRaises(GuideDeleteBlockedError):
            delete_rank(self.settings(), 2, confirm=True, operation_id="rank-delete-002")

        self.assertEqual(self._count("guide", 2), 1)
        self.assertTrue((self.root / image_path).is_file())

    def test_shared_rank_and_level_three_image_is_preserved(self) -> None:
        image_path = self._write_image("shared.png")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide values (3, 'Shared rank', ?)", (image_path,))
            connection.execute(
                "insert into guide_lev_3 values (30, 0, 'Shared item', null, ?)",
                (image_path,),
            )

        result = delete_rank(self.settings(), 3, confirm=True, operation_id="rank-delete-003")

        self.assertEqual(result.preserved_shared_references, 1)
        self.assertEqual(self._count("guide", 3), 0)
        self.assertEqual(self._count("guide_lev_3", 30), 1)
        self.assertTrue((self.root / image_path).is_file())

    def test_level_three_delete_cleans_unshared_flat_image(self) -> None:
        image_path = self._write_image("level3.png")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "insert into guide_lev_3 values (31, 0, 'Unused item', null, ?)",
                (image_path,),
            )

        result = delete_guide_level_item(
            self.settings(), 3, 31, confirm=True, operation_id="guide-delete-031"
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(self._count("guide_lev_3", 31), 0)
        self.assertFalse((self.root / image_path).exists())

    def test_children_and_current_usage_policy_still_block_each_level(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            for level in range(4):
                connection.execute(
                    f"insert into guide_lev_{level} values (?, -1, ?, null, null)",
                    (100 + level, f"Parent {level}"),
                )
                connection.execute(
                    f"insert into guide_lev_{level + 1} values (?, ?, ?, null, null)",
                    (200 + level, 100 + level, f"Child {level}"),
                )
            connection.execute("insert into guide_lev_4 values (104, -1, 'Common', null, null)")
            connection.execute("insert into rewards (id, id_link) values (1, 'prefix common suffix')")

        child_preview = guide_delete_preview(self.settings(), 0, 100)
        self.assertTrue(child_preview.blocked)
        self.assertEqual(child_preview.child_count, 1)
        self.assertIn("дочерние записи", guide_delete_confirmation_message(child_preview))

        for level in range(4):
            with self.subTest(level=level), self.assertRaises(GuideDeleteBlockedError):
                delete_guide_level_item(
                    self.settings(), level, 100 + level, confirm=True, operation_id=f"child-block-{level:03d}"
                )
        with self.assertRaises(GuideDeleteBlockedError):
            delete_guide_level_item(self.settings(), 4, 104, confirm=True, operation_id="level4-block-104")

    def test_reward_and_mark_usage_still_block_levels_zero_through_three(self) -> None:
        usage_fields = ("id_gos", "id_catigory", "id_sub_catigory", "id_name")
        with sqlite3.connect(self.db_path) as connection:
            for level, field in enumerate(usage_fields):
                item_id = 300 + level
                connection.execute(
                    f"insert into guide_lev_{level} values (?, -1, ?, null, null)",
                    (item_id, f"Used {level}"),
                )
                table = "rewards" if level % 2 == 0 else "mark"
                connection.execute(f"insert into {table} (id, {field}) values (?, ?)", (400 + level, item_id))

        for level in range(4):
            with self.subTest(level=level), self.assertRaises(GuideDeleteBlockedError):
                delete_guide_level_item(
                    self.settings(), level, 300 + level, confirm=True, operation_id=f"usage-block-{level:03d}"
                )

    def test_unsafe_missing_symlink_and_hardlink_paths_are_conservative(self) -> None:
        missing = "GuideImages/missing.png"
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide values (4, 'Missing', ?)", (missing,))
            connection.execute("insert into guide values (5, 'Unsafe', '../outside.png')")
        result = delete_rank(self.settings(), 4, confirm=True, operation_id="rank-missing-004")
        self.assertEqual(result.status, "completed")
        with self.assertRaises(GuideDeleteBlockedError):
            delete_rank(self.settings(), 5, confirm=True, operation_id="rank-unsafe-005")
        self.assertEqual(self._count("guide", 5), 1)

        target = self.root / self._write_image("target.png")
        symlink = self.root / "GuideImages" / "symlink.png"
        symlink.symlink_to(target)
        hardlink = self.root / "GuideImages" / "hardlink.png"
        os.link(target, hardlink)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide values (6, 'Symlink', 'GuideImages/symlink.png')")
            connection.execute("insert into guide values (7, 'Hardlink', 'GuideImages/hardlink.png')")
        for row_id in (6, 7):
            with self.subTest(row_id=row_id), self.assertRaises(GuideDeleteBlockedError):
                delete_rank(
                    self.settings(), row_id, confirm=True, operation_id=f"rank-link-{row_id:03d}"
                )
            self.assertEqual(self._count("guide", row_id), 1)

    def test_cleanup_failure_is_retryable_and_double_submit_is_idempotent(self) -> None:
        image_path = self._write_image("retry.png")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide values (8, 'Retry', ?)", (image_path,))

        with patch(
            "backend.app.services.deletion_lifecycle._purge_operation",
            side_effect=OSError("injected purge failure"),
        ):
            first = delete_rank(self.settings(), 8, confirm=True, operation_id="rank-retry-008")
        self.assertTrue(first.warning_required)
        self.assertEqual(self._count("guide", 8), 0)

        second = delete_rank(self.settings(), 8, confirm=True, operation_id="rank-retry-008")
        third = delete_rank(self.settings(), 8, confirm=True, operation_id="rank-retry-008")
        self.assertEqual(second.status, "completed")
        self.assertEqual(third.status, "already_completed")
        self.assertFalse((self.root / image_path).exists())

    def test_precommit_crash_restores_file_and_recovery_is_scoped(self) -> None:
        image_path = self._write_image("crash.png")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide_lev_3 values (32, 0, 'Crash', null, ?)", (image_path,))

        def crash(stage: str) -> None:
            if stage == "paths_staged":
                raise DeletionCrash("injected crash")

        with self.assertRaises(DeletionCrash):
            delete_guide_level_item(
                self.settings(), 3, 32, confirm=True, operation_id="guide-crash-032", fault_hook=crash
            )
        self.assertEqual(self._count("guide_lev_3", 32), 1)
        self.assertFalse((self.root / image_path).exists())

        recovered = recover_delete_operation(self.settings(), "guide-crash-032")
        self.assertEqual(recovered.status, "restored")
        self.assertTrue((self.root / image_path).is_file())

    def test_unrelated_orphan_hierarchy_is_not_repaired(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide_lev_0 values (40, -1, 'Delete me', null, null)")
            connection.execute("insert into guide_lev_2 values (99, 9999, 'Existing orphan', null, null)")

        delete_guide_level_item(self.settings(), 0, 40, confirm=True, operation_id="guide-delete-040")

        self.assertEqual(self._count("guide_lev_0", 40), 0)
        self.assertEqual(self._count("guide_lev_2", 99), 1)


if __name__ == "__main__":
    unittest.main()
