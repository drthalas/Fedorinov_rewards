from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest

from backend.app.config import Settings
from backend.app.repositories.persons_write import (
    PersonValidationError,
    PersonWriteData,
    create_person,
    delete_person,
    person_data_from_mapping,
    update_person,
)
from backend.app.services.write_guard import WriteBlockedError


class PersonWriteTests(unittest.TestCase):
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

    def person_data(self, fio: str = "Test Person", **overrides) -> PersonWriteData:
        values = {"fio": fio, "birthday": "1913", "id_rank": 1}
        values.update(overrides)
        return PersonWriteData(**values)

    def _create_db(self, with_biography: bool = True) -> None:
        biography_column = ", biography text" if with_biography else ""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                f"""
                create table person (
                    id integer primary key autoincrement,
                    fio varchar,
                    birthday date,
                    id_rank integer,
                    person_foto varchar,
                    main_foto varchar,
                    rewards_foto varchar,
                    book1_foto varchar,
                    book2_foto varchar,
                    card1_foto varchar,
                    card2_foto varchar,
                    link1 varchar,
                    link2 varchar,
                    comment text
                    {biography_column}
                )
                """
            )
            connection.execute(
                """
                create table rewards (
                    id integer primary key autoincrement,
                    person_id integer
                )
                """
            )

    def fetch_person(self, person_id: int) -> sqlite3.Row | None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("select * from person where id = ?", (person_id,)).fetchone()

    def test_write_mode_disabled_blocks_create_update_delete(self) -> None:
        settings = self.settings(write_mode=False)
        data = self.person_data("Blocked")
        with self.assertRaises(WriteBlockedError):
            create_person(settings, data)
        with self.assertRaises(WriteBlockedError):
            update_person(settings, 1, data)
        with self.assertRaises(WriteBlockedError):
            delete_person(settings, 1, confirm=True)

    def test_missing_backup_blocks_create_when_required(self) -> None:
        settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
            require_backup_before_write=True,
            require_backup_before_dangerous_actions=False,
        )
        with self.assertRaises(WriteBlockedError):
            create_person(settings, self.person_data("Needs backup"))

    def test_read_only_blocks_create_even_when_write_mode_true(self) -> None:
        settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=True,
            write_mode=True,
            require_backup_before_write=False,
        )
        with self.assertRaises(WriteBlockedError):
            create_person(settings, self.person_data("Read only"))

    def test_dangerous_delete_requires_backup_when_enabled(self) -> None:
        settings = self.settings()
        person_id = create_person(settings, self.person_data("Dangerous delete"))
        dangerous_settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
            require_backup_before_write=True,
            require_backup_before_dangerous_actions=True,
        )
        with self.assertRaises(WriteBlockedError):
            delete_person(dangerous_settings, person_id, confirm=True)
        self.assertIsNotNone(self.fetch_person(person_id))

    def test_delete_person_with_confirm_works_without_mandatory_backup(self) -> None:
        person_id = create_person(self.settings(), self.person_data("Delete without backup"))
        delete_person(self.settings(), person_id, confirm=True)
        self.assertIsNone(self.fetch_person(person_id))

    def test_delete_person_without_confirm_is_blocked(self) -> None:
        person_id = create_person(self.settings(), self.person_data("Needs confirm"))
        with self.assertRaises(PersonValidationError) as blocked:
            delete_person(self.settings(), person_id)
        self.assertEqual(str(blocked.exception), "Действие требует подтверждения.")
        self.assertIsNotNone(self.fetch_person(person_id))

    def test_create_person_works(self) -> None:
        person_id = create_person(
            self.settings(),
            PersonWriteData(fio="TEST DEV PERSON", birthday="1913", id_rank=2, link1="a", link2="b"),
        )
        row = self.fetch_person(person_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["fio"], "TEST DEV PERSON")
        self.assertEqual(str(row["birthday"]), "1913")
        self.assertEqual(row["id_rank"], 2)

    def test_update_person_works(self) -> None:
        person_id = create_person(self.settings(), self.person_data("Before"))
        update_person(
            self.settings(),
            person_id,
            PersonWriteData(fio="After", birthday="1920", id_rank=3, comment="Updated"),
        )
        row = self.fetch_person(person_id)
        self.assertEqual(row["fio"], "After")
        self.assertEqual(row["comment"], "Updated")

    def test_delete_person_without_rewards_works(self) -> None:
        person_id = create_person(self.settings(), self.person_data("Delete me"))
        delete_person(self.settings(), person_id, confirm=True)
        self.assertIsNone(self.fetch_person(person_id))

    def test_delete_person_with_rewards_cascades(self) -> None:
        person_id = create_person(self.settings(), self.person_data("Has rewards"))
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into rewards (person_id) values (?)", (person_id,))
        delete_person(self.settings(), person_id, confirm=True)
        self.assertIsNone(self.fetch_person(person_id))
        with sqlite3.connect(self.db_path) as connection:
            reward_count = connection.execute(
                "select count(*) from rewards where person_id = ?", (person_id,)
            ).fetchone()[0]
        self.assertEqual(reward_count, 0)

    def test_sql_handles_quotes_in_fio_and_comment(self) -> None:
        fio = "O'Connor \"TEST\""
        comment = "Quote: 'single' and \"double\""
        person_id = create_person(self.settings(), self.person_data(fio, comment=comment))
        row = self.fetch_person(person_id)
        self.assertEqual(row["fio"], fio)
        self.assertEqual(row["comment"], comment)

    def test_create_update_person_saves_biography_when_column_exists(self) -> None:
        person_id = create_person(self.settings(), self.person_data("Biography person", biography="Short bio"))
        row = self.fetch_person(person_id)
        self.assertEqual(row["biography"], "Short bio")

        update_person(self.settings(), person_id, self.person_data("Biography person", biography="Updated bio"))
        row = self.fetch_person(person_id)
        self.assertEqual(row["biography"], "Updated bio")

    def test_update_person_adds_biography_column_when_missing(self) -> None:
        self.db_path.unlink()
        self._create_db(with_biography=False)
        person_id = create_person(self.settings(), self.person_data("Biography migration", biography="Added bio"))
        row = self.fetch_person(person_id)
        self.assertIn("biography", row.keys())
        self.assertEqual(row["biography"], "Added bio")

        update_person(self.settings(), person_id, self.person_data("Biography migration", biography=""))
        row = self.fetch_person(person_id)
        self.assertIsNone(row["biography"])

    def test_empty_person_is_not_created(self) -> None:
        with self.assertRaises(PersonValidationError) as exc:
            person_data_from_mapping({"fio": "", "birthday": "1913", "id_rank": "1"})
        self.assertEqual(str(exc.exception), "Заполните ФИО.")

    def test_person_without_birthday_is_allowed(self) -> None:
        data = person_data_from_mapping({"fio": "No birthday", "birthday": "", "id_rank": "1"})
        self.assertIsNone(data.birthday)

    def test_person_without_rank_is_not_created(self) -> None:
        with self.assertRaises(PersonValidationError) as exc:
            person_data_from_mapping({"fio": "No rank", "birthday": "1913", "id_rank": ""})
        self.assertEqual(str(exc.exception), "Выберите звание / специальность.")

    def test_birthday_accepts_year_only(self) -> None:
        data = person_data_from_mapping({"fio": "Date user", "birthday": "1913", "id_rank": "2"})
        self.assertEqual(data.birthday, "1913")

    def test_birthday_rejects_full_date(self) -> None:
        with self.assertRaises(PersonValidationError) as exc:
            person_data_from_mapping({"fio": "Date user", "birthday": "09.05.1913", "id_rank": "2"})
        self.assertEqual(str(exc.exception), "Укажите год рождения в формате ГГГГ.")

    def test_birthday_rejects_out_of_range_year(self) -> None:
        with self.assertRaises(PersonValidationError) as exc:
            person_data_from_mapping({"fio": "Date user", "birthday": "1799", "id_rank": "2"})
        self.assertEqual(str(exc.exception), "Год рождения должен быть от 1800 до текущего года.")


if __name__ == "__main__":
    unittest.main()
