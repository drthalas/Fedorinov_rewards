from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest

from backend.app.config import Settings
from backend.app.repositories.rewards_write import (
    RewardValidationError,
    RewardWriteData,
    create_reward,
    delete_reward,
    update_reward,
)
from backend.app.services.write_guard import WriteBlockedError


class RewardWriteTests(unittest.TestCase):
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
            require_backup_before_dangerous_actions=False,
        )

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table person (id integer primary key autoincrement, fio varchar)")
            connection.execute(
                """
                create table rewards (
                    id integer primary key autoincrement,
                    person_id integer,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    number integer,
                    instock boolean,
                    date_purchase date,
                    price_purchase integer,
                    price_now integer,
                    front_foto varchar,
                    back_foto varchar,
                    id_link text,
                    book1_foto varchar,
                    book2_foto varchar,
                    reward_list varchar
                )
                """
            )
            connection.execute("insert into person (id, fio) values (1, 'Person')")

    def fetch_reward(self, reward_id: int) -> sqlite3.Row | None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("select * from rewards where id = ?", (reward_id,)).fetchone()

    def test_write_mode_disabled_blocks_create_update_delete(self) -> None:
        settings = self.settings(write_mode=False)
        data = RewardWriteData(number=1)
        with self.assertRaises(WriteBlockedError):
            create_reward(settings, 1, data)
        with self.assertRaises(WriteBlockedError):
            update_reward(settings, 1, data)
        with self.assertRaises(WriteBlockedError):
            delete_reward(settings, 1, confirm=True)

    def test_create_reward_works(self) -> None:
        reward_id = create_reward(
            self.settings(),
            1,
            RewardWriteData(id_gos=1, id_catigory=2, id_sub_catigory=3, id_name=4, number=77, instock=True),
        )
        row = self.fetch_reward(reward_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["person_id"], 1)
        self.assertEqual(row["number"], 77)
        self.assertEqual(row["instock"], 1)

    def test_update_reward_works(self) -> None:
        reward_id = create_reward(self.settings(), 1, RewardWriteData(number=1, price_now=100))
        update_reward(
            self.settings(),
            reward_id,
            RewardWriteData(number=2, price_purchase=500, price_now=700, instock=False),
        )
        row = self.fetch_reward(reward_id)
        self.assertEqual(row["number"], 2)
        self.assertEqual(row["price_purchase"], 500)
        self.assertEqual(row["price_now"], 700)
        self.assertEqual(row["instock"], 0)

    def test_delete_reward_removes_row_but_not_media_folder(self) -> None:
        media_dir = self.root / "Source" / "1" / "1"
        media_dir.mkdir(parents=True)
        (media_dir / "FotoFront.jpg").write_bytes(b"fake")
        reward_id = create_reward(self.settings(), 1, RewardWriteData(front_foto="Source/1/1/FotoFront.jpg"))
        delete_reward(self.settings(), reward_id, confirm=True)
        self.assertIsNone(self.fetch_reward(reward_id))
        self.assertTrue(media_dir.exists())
        self.assertTrue((media_dir / "FotoFront.jpg").exists())

    def test_sql_handles_quotes_and_text(self) -> None:
        text = "Link 'single' and \"double\""
        reward_id = create_reward(self.settings(), 1, RewardWriteData(id_link=text, reward_list="Source/quoted path.jpg"))
        row = self.fetch_reward(reward_id)
        self.assertEqual(row["id_link"], text)
        self.assertEqual(row["reward_list"], "Source/quoted path.jpg")

    def test_create_reward_fails_for_nonexistent_person(self) -> None:
        with self.assertRaises(RewardValidationError):
            create_reward(self.settings(), 999, RewardWriteData(number=1))


if __name__ == "__main__":
    unittest.main()
