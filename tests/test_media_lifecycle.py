from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.services.media_lifecycle import (
    MANAGED_IMAGE_ROOTS,
    MediaLifecycleError,
    REFERENCE_FIELDS,
    cleanup_unreferenced_image,
    managed_image_reference_count,
    normalize_managed_image_path,
)
from backend.app.services.photos import clear_photo_with_result, save_photo_with_result


JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"lifecycle-jpeg"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"lifecycle-png"


class MediaLifecycleTests(unittest.TestCase):
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

    def settings(self) -> Settings:
        return Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
        )

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "create table person (id integer primary key, person_foto text, main_foto text, rewards_foto text, "
                "book1_foto text, book2_foto text, card1_foto text, card2_foto text)"
            )
            connection.execute(
                "create table rewards (id integer primary key, person_id integer, front_foto text, back_foto text, "
                "book1_foto text, book2_foto text, reward_list text)"
            )
            connection.execute(
                "create table mark (id integer primary key, front_foto text, back_foto text, "
                "book1_foto text, book2_foto text)"
            )
            connection.execute("create table guide (id integer primary key, name text, image_path text)")
            for level in range(5):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, image_path text)")
            connection.execute(
                "create table person_media (id integer primary key, person_id integer, photo_field text, file_path text)"
            )
            connection.execute("insert into person (id) values (1)")
            connection.execute("insert into rewards (id, person_id) values (10, 1)")
            connection.execute("insert into mark (id) values (20)")
            connection.execute("insert into guide (id, name) values (30, 'Rank')")
            connection.execute("insert into guide_lev_3 (id) values (40)")

    def _write_media(self, path: str, content: bytes = JPEG_BYTES) -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def _value(self, table: str, row_id: int, column: str) -> str | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(f"select {column} from {table} where id = ?", (row_id,)).fetchone()
        return row[0] if row else None

    def test_contract_covers_all_managed_entities_and_slots(self) -> None:
        fields = {(item.table, item.column) for item in REFERENCE_FIELDS}
        expected = {
            ("person", field)
            for field in (
                "person_foto", "main_foto", "rewards_foto", "book1_foto", "book2_foto", "card1_foto", "card2_foto"
            )
        }
        expected.update(
            ("rewards", field)
            for field in ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list")
        )
        expected.update(("mark", field) for field in ("front_foto", "back_foto", "book1_foto", "book2_foto"))
        expected.update({("guide", "image_path"), ("person_media", "file_path")})
        expected.update((f"guide_lev_{level}", "image_path") for level in range(5))
        self.assertEqual(fields, expected)

    def test_path_policy_blocks_traversal_absolute_unc_drive_symlink_and_non_image(self) -> None:
        settings = self.settings()
        self.assertEqual(normalize_managed_image_path(settings, "Source\\1\\photo.jpg"), "Source/1/photo.jpg")
        self.assertEqual(normalize_managed_image_path(settings, "GuideImages/rank.webp"), "GuideImages/rank.webp")
        blocked = (
            "../outside.jpg",
            "Source/../outside.jpg",
            "%252e%252e/outside.jpg",
            "/tmp/outside.jpg",
            "C:\\photos\\outside.jpg",
            "\\\\server\\share\\outside.jpg",
            "default/nofoto.jpg",
            "Source/1/document.pdf",
        )
        for value in blocked:
            with self.subTest(value=value), self.assertRaises(MediaLifecycleError):
                normalize_managed_image_path(settings, value)

        outside = self.root / "outside"
        outside.mkdir()
        source = self.root / "Source"
        source.mkdir()
        (source / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(MediaLifecycleError):
            normalize_managed_image_path(settings, "Source/linked/photo.jpg")

    def test_shared_file_is_deleted_only_after_last_cross_entity_reference(self) -> None:
        shared_path = "Source/1/shared.jpg"
        shared_file = self._write_media(shared_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update person set person_foto = ? where id = 1", (shared_path,))
            connection.execute("update rewards set front_foto = ? where id = 10", ("Source\\1\\shared.jpg",))
            connection.execute("insert into person_media (id, person_id, file_path) values (1, 1, ?)", (shared_path,))

        self.assertEqual(managed_image_reference_count(self.settings(), shared_path), 3)
        person_clear = clear_photo_with_result(self.settings(), "person", 1, "person_foto")
        self.assertEqual(person_clear.cleanup.status, "shared")
        self.assertEqual(person_clear.cleanup.reference_count, 2)
        self.assertTrue(shared_file.exists())

        reward_clear = clear_photo_with_result(self.settings(), "reward", 10, "front_foto")
        self.assertEqual(reward_clear.cleanup.status, "shared")
        self.assertEqual(reward_clear.cleanup.reference_count, 1)
        self.assertTrue(shared_file.exists())

        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update person_media set file_path = null where id = 1")
        final = cleanup_unreferenced_image(self.settings(), shared_path, allowed_roots=frozenset({"Source"}))
        self.assertEqual(final.status, "deleted")
        self.assertFalse(shared_file.exists())

    def test_replace_deletes_unreferenced_old_file_and_preserves_neighbor(self) -> None:
        old_path = "Source/1/old.jpg"
        neighbor_path = "Source/1/neighbor.jpg"
        old_file = self._write_media(old_path)
        neighbor_file = self._write_media(neighbor_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "update person set person_foto = ?, main_foto = ? where id = 1",
                (old_path, neighbor_path),
            )

        result = save_photo_with_result(self.settings(), "person", 1, "person_foto", "new.png", PNG_BYTES)
        self.assertEqual(result.cleanup.status, "deleted")
        self.assertFalse(old_file.exists())
        self.assertTrue((self.root / str(result.path)).is_file())
        self.assertTrue(neighbor_file.is_file())
        self.assertEqual(self._value("person", 1, "main_foto"), neighbor_path)

    def test_missing_file_clear_commits_without_error(self) -> None:
        missing = "SourceMark/20/missing.jpg"
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update mark set front_foto = ? where id = 20", (missing,))
        result = clear_photo_with_result(self.settings(), "mark", 20, "front_foto")
        self.assertEqual(result.cleanup.status, "missing")
        self.assertIsNone(self._value("mark", 20, "front_foto"))

    def test_database_failure_keeps_old_reference_and_discards_new_candidate(self) -> None:
        old_path = "Source/1/old.jpg"
        old_file = self._write_media(old_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update person set person_foto = ? where id = 1", (old_path,))
            connection.execute(
                "create trigger block_person_photo before update of person_foto on person "
                "begin select raise(abort, 'blocked update'); end"
            )

        with self.assertRaises(sqlite3.IntegrityError):
            save_photo_with_result(self.settings(), "person", 1, "person_foto", "new.png", PNG_BYTES)
        self.assertEqual(self._value("person", 1, "person_foto"), old_path)
        self.assertTrue(old_file.is_file())
        created = list((self.root / "Source" / "1").glob("фото_кавалера*.png"))
        self.assertEqual(created, [])

    def test_file_write_failure_keeps_old_reference(self) -> None:
        old_path = "Source/1/old.jpg"
        old_file = self._write_media(old_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update person set person_foto = ? where id = 1", (old_path,))
        with patch("backend.app.services.media_filenames.Path.open", side_effect=PermissionError("read only")):
            with self.assertRaises(PermissionError):
                save_photo_with_result(self.settings(), "person", 1, "person_foto", "new.png", PNG_BYTES)
        self.assertEqual(self._value("person", 1, "person_foto"), old_path)
        self.assertTrue(old_file.is_file())

    def test_cleanup_failure_keeps_committed_new_reference_and_old_file(self) -> None:
        old_path = "Source/1/old.jpg"
        old_file = self._write_media(old_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update person set person_foto = ? where id = 1", (old_path,))
        with patch("pathlib.Path.unlink", side_effect=PermissionError("read only")):
            result = save_photo_with_result(self.settings(), "person", 1, "person_foto", "new.png", PNG_BYTES)

        self.assertEqual(result.cleanup.status, "failed")
        self.assertTrue(result.cleanup.warning_required)
        self.assertEqual(self._value("person", 1, "person_foto"), result.path)
        self.assertTrue((self.root / str(result.path)).is_file())
        self.assertTrue(old_file.is_file())

    def test_malformed_old_reference_is_cleared_without_external_deletion(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.jpg"
        outside.write_bytes(JPEG_BYTES)
        self.addCleanup(outside.unlink, missing_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update person set person_foto = ? where id = 1", (str(outside),))
        result = clear_photo_with_result(self.settings(), "person", 1, "person_foto")
        self.assertEqual(result.cleanup.status, "blocked")
        self.assertTrue(result.cleanup.warning_required)
        self.assertIsNone(self._value("person", 1, "person_foto"))
        self.assertTrue(outside.is_file())

    def test_managed_roots_are_exact_and_do_not_include_user_defaults(self) -> None:
        self.assertEqual(MANAGED_IMAGE_ROOTS, frozenset({"Source", "SourceMark", "GuideImages"}))


if __name__ == "__main__":
    unittest.main()
