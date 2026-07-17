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
    reward_data_from_mapping,
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

    def reward_data(self, **overrides) -> RewardWriteData:
        values = {"id_gos": 1, "id_catigory": 2, "id_sub_catigory": 3, "id_name": 4}
        values.update(overrides)
        return RewardWriteData(**values)

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
            connection.execute("insert into person (id, fio) values (2, 'Other Person')")

    def fetch_reward(self, reward_id: int) -> sqlite3.Row | None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("select * from rewards where id = ?", (reward_id,)).fetchone()

    def test_write_mode_disabled_blocks_create_update_delete(self) -> None:
        settings = self.settings(write_mode=False)
        data = self.reward_data(number=1)
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

    def test_create_reward_with_empty_number_skips_duplicate_validation(self) -> None:
        first_id = create_reward(self.settings(), 1, self.reward_data(number=None))
        second_id = create_reward(self.settings(), 2, self.reward_data(number=None))

        self.assertIsNotNone(self.fetch_reward(first_id))
        self.assertIsNotNone(self.fetch_reward(second_id))

    def test_create_reward_blocks_duplicate_name_and_number_across_database(self) -> None:
        create_reward(self.settings(), 1, self.reward_data(number=555))

        with self.assertRaises(RewardValidationError) as blocked:
            create_reward(self.settings(), 2, self.reward_data(number=555))

        self.assertIn("Награда с таким наименованием и номером уже есть в базе.", str(blocked.exception))
        self.assertIn("Person, кавалер #1", str(blocked.exception))

    def test_update_reward_works(self) -> None:
        reward_id = create_reward(self.settings(), 1, self.reward_data(number=1, price_now=100))
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

    def test_update_reward_keeps_same_name_and_number_without_duplicate_error(self) -> None:
        reward_id = create_reward(self.settings(), 1, self.reward_data(number=777))

        update_reward(self.settings(), reward_id, self.reward_data(number=777, price_now=900))

        row = self.fetch_reward(reward_id)
        self.assertEqual(row["number"], 777)
        self.assertEqual(row["price_now"], 900)

    def test_update_reward_blocks_duplicate_name_and_number_from_other_row(self) -> None:
        create_reward(self.settings(), 1, self.reward_data(number=888))
        reward_id = create_reward(self.settings(), 2, self.reward_data(id_name=5, number=999))

        with self.assertRaises(RewardValidationError) as blocked:
            update_reward(self.settings(), reward_id, self.reward_data(id_name=4, number=888))

        self.assertIn("Награда с таким наименованием и номером уже есть в базе.", str(blocked.exception))
        row = self.fetch_reward(reward_id)
        self.assertEqual(row["id_name"], 5)
        self.assertEqual(row["number"], 999)

    def test_delete_reward_removes_row_and_owned_media_folder(self) -> None:
        media_dir = self.root / "Source" / "1" / "1"
        media_dir.mkdir(parents=True)
        (media_dir / "FotoFront.jpg").write_bytes(b"fake")
        reward_id = create_reward(self.settings(), 1, self.reward_data(front_foto="Source/1/1/FotoFront.jpg"))
        delete_reward(self.settings(), reward_id, confirm=True)
        self.assertIsNone(self.fetch_reward(reward_id))
        self.assertFalse(media_dir.exists())

    def test_delete_reward_with_confirm_works_without_mandatory_backup(self) -> None:
        reward_id = create_reward(self.settings(), 1, self.reward_data(number=101))
        delete_reward(self.settings(), reward_id, confirm=True)
        self.assertIsNone(self.fetch_reward(reward_id))

    def test_delete_reward_without_confirm_is_blocked(self) -> None:
        reward_id = create_reward(self.settings(), 1, self.reward_data(number=102))
        with self.assertRaises(RewardValidationError) as blocked:
            delete_reward(self.settings(), reward_id)
        self.assertEqual(str(blocked.exception), "Действие требует подтверждения.")
        self.assertIsNotNone(self.fetch_reward(reward_id))

    def test_dangerous_delete_requires_backup_when_enabled(self) -> None:
        reward_id = create_reward(self.settings(), 1, self.reward_data(number=103))
        settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
            require_backup_before_write=True,
            require_backup_before_dangerous_actions=True,
        )
        with self.assertRaises(WriteBlockedError):
            delete_reward(settings, reward_id, confirm=True)
        self.assertIsNotNone(self.fetch_reward(reward_id))

    def test_sql_handles_quotes_and_text(self) -> None:
        text = "Link 'single' and \"double\""
        reward_id = create_reward(self.settings(), 1, self.reward_data(id_link=text, reward_list="Source/quoted path.jpg"))
        row = self.fetch_reward(reward_id)
        self.assertEqual(row["id_link"], text)
        self.assertEqual(row["reward_list"], "Source/quoted path.jpg")

    def test_create_reward_fails_for_nonexistent_person(self) -> None:
        with self.assertRaises(RewardValidationError):
            create_reward(self.settings(), 999, self.reward_data(number=1))

    def test_empty_reward_is_not_created(self) -> None:
        with self.assertRaises(RewardValidationError) as exc:
            create_reward(self.settings(), 1, RewardWriteData(number=1))
        self.assertEqual(str(exc.exception), "Выберите наименование награды.")

    def test_reward_date_purchase_normalizes_user_format(self) -> None:
        data = reward_data_from_mapping({"id_name": "4", "date_purchase": "05.06.2026"})
        self.assertEqual(data.date_purchase, "2026-06-05")

    def test_update_reward_preserves_existing_guide_ids_when_form_omits_them(self) -> None:
        reward_id = create_reward(self.settings(), 1, self.reward_data(number=77))
        update_reward(self.settings(), reward_id, RewardWriteData(number=88, price_now=700))
        row = self.fetch_reward(reward_id)
        self.assertEqual(row["number"], 88)
        self.assertEqual(row["id_gos"], 1)
        self.assertEqual(row["id_catigory"], 2)
        self.assertEqual(row["id_sub_catigory"], 3)
        self.assertEqual(row["id_name"], 4)


if __name__ == "__main__":
    unittest.main()
