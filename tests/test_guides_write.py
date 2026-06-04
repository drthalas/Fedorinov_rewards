from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest

from backend.app.config import Settings
from backend.app.repositories.guides_write import (
    GuideDeleteBlockedError,
    GuideLevelData,
    RankGuideData,
    create_guide_level_item,
    create_rank,
    delete_guide_level_item,
    delete_rank,
    update_guide_level_item,
    update_rank,
)
from backend.app.services.navigation import safe_return_to
from backend.app.services.write_guard import WriteBlockedError


class GuideWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.log")
        self._create_db()

    def tearDown(self) -> None:
        os.environ.pop("REWARDS_AUDIT_LOG", None)
        self.tmp.cleanup()

    def settings(self, write_mode: bool = True) -> Settings:
        return Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=not write_mode,
            write_mode=write_mode,
            require_backup_before_write=False,
        )

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key autoincrement, name varchar)")
            connection.execute("create table person (id integer primary key autoincrement, id_rank integer)")
            for level in range(5):
                connection.execute(
                    f"create table guide_lev_{level} (id integer primary key autoincrement, idl integer, name varchar)"
                )
            connection.execute(
                """
                create table rewards (
                    id integer primary key autoincrement,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link text
                )
                """
            )
            connection.execute(
                """
                create table mark (
                    id integer primary key autoincrement,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link text
                )
                """
            )

    def fetch_one(self, table: str, item_id: int) -> sqlite3.Row | None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(f"select * from {table} where id = ?", (item_id,)).fetchone()

    def test_write_mode_disabled_blocks_guide_writes(self) -> None:
        settings = self.settings(write_mode=False)
        with self.assertRaises(WriteBlockedError):
            create_rank(settings, RankGuideData(name="Blocked"))
        with self.assertRaises(WriteBlockedError):
            update_rank(settings, 1, RankGuideData(name="Blocked"))
        with self.assertRaises(WriteBlockedError):
            delete_rank(settings, 1)
        with self.assertRaises(WriteBlockedError):
            create_guide_level_item(settings, GuideLevelData(level=0, name="Blocked", parent_id=-1))

    def test_create_update_delete_rank_works(self) -> None:
        rank_id = create_rank(self.settings(), RankGuideData(name="QA TEST RANK"))
        update_rank(self.settings(), rank_id, RankGuideData(name="QA TEST RANK UPDATED"))
        row = self.fetch_one("guide", rank_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "QA TEST RANK UPDATED")
        delete_rank(self.settings(), rank_id)
        self.assertIsNone(self.fetch_one("guide", rank_id))

    def test_delete_used_rank_blocked(self) -> None:
        rank_id = create_rank(self.settings(), RankGuideData(name="USED RANK"))
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into person (id_rank) values (?)", (rank_id,))
        with self.assertRaises(GuideDeleteBlockedError) as blocked:
            delete_rank(self.settings(), rank_id)
        self.assertIn("карточках награждённых", str(blocked.exception))
        self.assertIsNotNone(self.fetch_one("guide", rank_id))

    def test_create_update_delete_guide_level_works(self) -> None:
        item_id = create_guide_level_item(self.settings(), GuideLevelData(level=0, name="QA TEST COUNTRY", parent_id=-1))
        update_guide_level_item(
            self.settings(),
            0,
            item_id,
            GuideLevelData(level=0, name="QA TEST COUNTRY UPDATED", parent_id=-1),
        )
        row = self.fetch_one("guide_lev_0", item_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "QA TEST COUNTRY UPDATED")
        delete_guide_level_item(self.settings(), 0, item_id)
        self.assertIsNone(self.fetch_one("guide_lev_0", item_id))

    def test_delete_guide_level_with_children_blocked(self) -> None:
        parent_id = create_guide_level_item(self.settings(), GuideLevelData(level=0, name="Parent", parent_id=-1))
        create_guide_level_item(self.settings(), GuideLevelData(level=1, name="Child", parent_id=parent_id))
        with self.assertRaises(GuideDeleteBlockedError) as blocked:
            delete_guide_level_item(self.settings(), 0, parent_id)
        self.assertIn("дочерние записи", str(blocked.exception))
        self.assertIsNotNone(self.fetch_one("guide_lev_0", parent_id))

    def test_delete_guide_level_used_by_rewards_or_marks_blocked(self) -> None:
        root_id = create_guide_level_item(self.settings(), GuideLevelData(level=0, name="Root", parent_id=-1))
        level1_id = create_guide_level_item(self.settings(), GuideLevelData(level=1, name="Level 1", parent_id=root_id))
        level2_id = create_guide_level_item(self.settings(), GuideLevelData(level=2, name="Level 2", parent_id=level1_id))
        level3_id = create_guide_level_item(self.settings(), GuideLevelData(level=3, name="Used name", parent_id=level2_id))
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into rewards (id_name) values (?)", (level3_id,))
        with self.assertRaises(GuideDeleteBlockedError) as blocked_reward:
            delete_guide_level_item(self.settings(), 3, level3_id)
        self.assertIn("наградах или знаках", str(blocked_reward.exception))

        level2_mark_id = create_guide_level_item(self.settings(), GuideLevelData(level=2, name="Used category", parent_id=level1_id))
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into mark (id_sub_catigory) values (?)", (level2_mark_id,))
        with self.assertRaises(GuideDeleteBlockedError) as blocked_mark:
            delete_guide_level_item(self.settings(), 2, level2_mark_id)
        self.assertIn("наградах или знаках", str(blocked_mark.exception))

    def test_safe_return_to_rejects_external_urls(self) -> None:
        self.assertEqual(safe_return_to("/guides?return_to=%2Flegacy%3Ftab%3Drewards"), "/guides?return_to=%2Flegacy%3Ftab%3Drewards")
        self.assertEqual(safe_return_to("https://example.com", "/guides"), "/guides")


if __name__ == "__main__":
    unittest.main()
