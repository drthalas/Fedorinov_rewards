from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest

from backend.app.config import Settings
from backend.app.repositories.persons_write import (
    PersonDeleteBlockedError,
    PersonWriteData,
    create_person,
    delete_person,
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
        )

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
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
                    comment text,
                    biography text
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
        data = PersonWriteData(fio="Blocked")
        with self.assertRaises(WriteBlockedError):
            create_person(settings, data)
        with self.assertRaises(WriteBlockedError):
            update_person(settings, 1, data)
        with self.assertRaises(WriteBlockedError):
            delete_person(settings, 1)

    def test_missing_backup_blocks_create_when_required(self) -> None:
        settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
            require_backup_before_write=True,
        )
        with self.assertRaises(WriteBlockedError):
            create_person(settings, PersonWriteData(fio="Needs backup"))

    def test_create_person_works(self) -> None:
        person_id = create_person(
            self.settings(),
            PersonWriteData(fio="TEST DEV PERSON", birthday="1913-05-09", id_rank=2, link1="a", link2="b"),
        )
        row = self.fetch_person(person_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["fio"], "TEST DEV PERSON")
        self.assertEqual(row["birthday"], "1913-05-09")
        self.assertEqual(row["id_rank"], 2)

    def test_update_person_works(self) -> None:
        person_id = create_person(self.settings(), PersonWriteData(fio="Before"))
        update_person(
            self.settings(),
            person_id,
            PersonWriteData(fio="After", birthday="1920-01-02", id_rank=3, comment="Updated"),
        )
        row = self.fetch_person(person_id)
        self.assertEqual(row["fio"], "After")
        self.assertEqual(row["comment"], "Updated")

    def test_delete_person_without_rewards_works(self) -> None:
        person_id = create_person(self.settings(), PersonWriteData(fio="Delete me"))
        delete_person(self.settings(), person_id)
        self.assertIsNone(self.fetch_person(person_id))

    def test_delete_person_with_rewards_is_blocked(self) -> None:
        person_id = create_person(self.settings(), PersonWriteData(fio="Has rewards"))
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into rewards (person_id) values (?)", (person_id,))
        with self.assertRaises(PersonDeleteBlockedError):
            delete_person(self.settings(), person_id)
        self.assertIsNotNone(self.fetch_person(person_id))

    def test_sql_handles_quotes_in_fio_and_comment(self) -> None:
        fio = "O'Connor \"TEST\""
        comment = "Quote: 'single' and \"double\""
        person_id = create_person(self.settings(), PersonWriteData(fio=fio, comment=comment))
        row = self.fetch_person(person_id)
        self.assertEqual(row["fio"], fio)
        self.assertEqual(row["comment"], comment)

    def test_create_update_person_saves_biography_when_column_exists(self) -> None:
        person_id = create_person(self.settings(), PersonWriteData(fio="Biography person", biography="Short bio"))
        row = self.fetch_person(person_id)
        self.assertEqual(row["biography"], "Short bio")

        update_person(self.settings(), person_id, PersonWriteData(fio="Biography person", biography="Updated bio"))
        row = self.fetch_person(person_id)
        self.assertEqual(row["biography"], "Updated bio")


if __name__ == "__main__":
    unittest.main()
