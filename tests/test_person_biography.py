from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest

from backend.app.repositories.persons import get_person
from scripts.migrate_add_person_biography import apply_migration, biography_column_exists, dry_run


ROOT = Path(__file__).resolve().parents[1]


class PersonBiographyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self._previous_env = {key: os.environ.get(key) for key in self._env_keys()}
        os.environ["REWARDS_DATA_DIR"] = str(self.root)
        os.environ["REWARDS_DB_PATH"] = str(self.db_path)
        os.environ["READ_ONLY"] = "false"
        os.environ["WRITE_MODE"] = "true"
        os.environ["REQUIRE_BACKUP_BEFORE_WRITE"] = "false"
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.log")

    def tearDown(self) -> None:
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    @staticmethod
    def _env_keys() -> list[str]:
        return [
            "REWARDS_DATA_DIR",
            "REWARDS_DB_PATH",
            "READ_ONLY",
            "WRITE_MODE",
            "REQUIRE_BACKUP_BEFORE_WRITE",
            "REWARDS_AUDIT_LOG",
        ]

    def _create_person_db(self, with_biography: bool = False) -> None:
        biography_column = ", biography text" if with_biography else ""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key, name text)")
            connection.execute(
                f"""
                create table person (
                    id integer primary key,
                    fio text,
                    birthday text,
                    id_rank integer,
                    person_foto text,
                    main_foto text,
                    rewards_foto text,
                    book1_foto text,
                    book2_foto text,
                    card1_foto text,
                    card2_foto text,
                    link1 text,
                    link2 text,
                    comment text
                    {biography_column}
                )
                """
            )
            connection.execute("create table rewards (id integer primary key, person_id integer)")
            if with_biography:
                connection.execute(
                    "insert into person (id, fio, biography) values (1, 'Test Person', 'Test biography text')"
                )
            else:
                connection.execute("insert into person (id, fio) values (1, 'Test Person')")

    def test_migration_dry_run_does_not_change_schema(self) -> None:
        self._create_person_db(with_biography=False)
        self.assertEqual(dry_run(), "would_add")
        self.assertFalse(biography_column_exists(self.db_path))

    def test_migration_apply_is_idempotent(self) -> None:
        self._create_person_db(with_biography=False)
        self.assertEqual(apply_migration(), "added")
        self.assertTrue(biography_column_exists(self.db_path))
        self.assertEqual(apply_migration(), "already_exists")

    def test_person_detail_loads_and_renders_biography(self) -> None:
        self._create_person_db(with_biography=True)
        person = get_person(self.db_path, 1)
        person_detail = (ROOT / "backend" / "app" / "templates" / "person_detail.html").read_text(encoding="utf-8")
        self.assertEqual(person["biography"], "Test biography text")
        self.assertIn("Краткая биография", person_detail)
        self.assertIn("person.biography", person_detail)

    def test_forms_use_owner_facing_labels_and_photo_controls(self) -> None:
        person_form = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text(encoding="utf-8")
        reward_form = (ROOT / "backend" / "app" / "templates" / "reward_form.html").read_text(encoding="utf-8")
        mark_form = (ROOT / "backend" / "app" / "templates" / "mark_form.html").read_text(encoding="utf-8")
        photo_management = (ROOT / "backend" / "app" / "templates" / "photo_management.html").read_text(encoding="utf-8")

        self.assertNotIn(">Link 1<", person_form)
        self.assertNotIn(">Link 2<", person_form)
        self.assertIn("Ссылка на сайт “Память народа”", person_form)
        self.assertIn("Ссылка на сайт “Форум коллекционеров”", person_form)
        self.assertIn("Краткая биография", person_form)
        self.assertIn("Ссылка на Монетный двор / справочник", reward_form)
        self.assertIn("Ссылка / дополнительное поле", mark_form)
        self.assertIn("/photos/upload", photo_management)
        self.assertIn("/photos/clear", photo_management)
        self.assertIn("Вставить из буфера", photo_management)


if __name__ == "__main__":
    unittest.main()
