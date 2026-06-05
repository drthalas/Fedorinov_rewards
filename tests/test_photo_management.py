from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest
from zipfile import ZipFile

from backend.app.config import Settings
from backend.app.services.person_files import PersonFilesError, archive_person_folder, open_person_folder, safe_person_folder
from backend.app.services.photos import PhotoValidationError, clear_photo, save_photo
from backend.app.services.write_guard import WriteBlockedError


class PhotoManagementTests(unittest.TestCase):
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
                    fio text,
                    person_foto text,
                    main_foto text,
                    rewards_foto text,
                    book1_foto text,
                    book2_foto text,
                    card1_foto text,
                    card2_foto text
                )
                """
            )
            connection.execute(
                """
                create table rewards (
                    id integer primary key autoincrement,
                    person_id integer,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
                )
                """
            )
            connection.execute(
                """
                create table mark (
                    id integer primary key autoincrement,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text
                )
                """
            )
            connection.execute("insert into person (id, fio) values (1, 'Test Person')")
            connection.execute("insert into rewards (id, person_id) values (10, 1)")
            connection.execute("insert into mark (id) values (20)")

    def fetch_value(self, table: str, row_id: int, field: str) -> str | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(f"select {field} from {table} where id = ?", (row_id,)).fetchone()
            return row[0] if row else None

    def test_person_photo_upload_and_clear(self) -> None:
        path = save_photo(self.settings(), "person", 1, "person_foto", "portrait.jpg", b"jpeg-bytes")
        self.assertTrue(path.startswith("Source/1/FotoPerson_"))
        self.assertEqual(self.fetch_value("person", 1, "person_foto"), path)
        target = self.root / path
        self.assertTrue(target.exists())

        clear_photo(self.settings(), "person", 1, "person_foto")
        self.assertIsNone(self.fetch_value("person", 1, "person_foto"))
        self.assertTrue(target.exists())

    def test_reward_photo_upload_uses_person_reward_folder(self) -> None:
        path = save_photo(self.settings(), "reward", 10, "front_foto", "front.png", b"png-bytes")
        self.assertTrue(path.startswith("Source/1/10/FotoFront_"))
        self.assertEqual(self.fetch_value("rewards", 10, "front_foto"), path)
        self.assertTrue((self.root / path).exists())

    def test_mark_photo_upload_uses_source_mark_folder(self) -> None:
        path = save_photo(self.settings(), "mark", 20, "back_foto", "back.webp", b"webp-bytes")
        self.assertTrue(path.startswith("SourceMark/20/FotoBack_"))
        self.assertEqual(self.fetch_value("mark", 20, "back_foto"), path)
        self.assertTrue((self.root / path).exists())

    def test_invalid_extension_is_blocked(self) -> None:
        with self.assertRaises(PhotoValidationError):
            save_photo(self.settings(), "person", 1, "person_foto", "portrait.txt", b"text")

    def test_write_mode_disabled_blocks_upload_and_clear(self) -> None:
        with self.assertRaises(WriteBlockedError):
            save_photo(self.settings(write_mode=False), "person", 1, "person_foto", "portrait.jpg", b"jpeg")
        with self.assertRaises(WriteBlockedError):
            clear_photo(self.settings(write_mode=False), "person", 1, "person_foto")

    def test_person_folder_resolves_inside_data_root(self) -> None:
        folder = safe_person_folder(self.settings(), 1)
        self.assertEqual(folder, (self.root / "Source" / "1").resolve())
        self.assertTrue(str(folder).startswith(str(self.root.resolve())))

    def test_person_folder_rejects_invalid_id(self) -> None:
        with self.assertRaises(PersonFilesError):
            safe_person_folder(self.settings(), -1)

    def test_person_folder_missing_is_handled(self) -> None:
        with self.assertRaises(PersonFilesError):
            open_person_folder(self.settings(), 1, opener=lambda path: None)

    def test_person_folder_open_uses_injected_opener(self) -> None:
        folder = self.root / "Source" / "1"
        folder.mkdir(parents=True)
        opened: list[Path] = []
        open_person_folder(self.settings(), 1, opener=opened.append)
        self.assertEqual(opened, [folder.resolve()])

    def test_archive_person_folder_creates_zip_without_deleting_files(self) -> None:
        folder = self.root / "Source" / "1"
        folder.mkdir(parents=True)
        source_file = folder / "photo.jpg"
        source_file.write_bytes(b"image")
        result = archive_person_folder(self.settings(), 1, "Test Person")
        self.assertTrue(result.path.exists())
        self.assertTrue(source_file.exists())
        with ZipFile(result.path) as archive:
            self.assertIn("photo.jpg", archive.namelist())

    def test_archive_person_folder_skips_forbidden_members(self) -> None:
        folder = self.root / "Source" / "1"
        folder.mkdir(parents=True)
        (folder / "photo.jpg").write_bytes(b"image")
        (folder / ".env").write_text("SECRET=1", encoding="utf-8")
        (folder / "nested.zip").write_bytes(b"zip")
        result = archive_person_folder(self.settings(), 1, "Test Person")
        with ZipFile(result.path) as archive:
            names = set(archive.namelist())
        self.assertIn("photo.jpg", names)
        self.assertNotIn(".env", names)
        self.assertNotIn("nested.zip", names)


if __name__ == "__main__":
    unittest.main()
