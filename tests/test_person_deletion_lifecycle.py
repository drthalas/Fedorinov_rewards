from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.repositories.persons_write import (
    PersonDeleteBlockedError,
    delete_person_with_result,
    person_delete_confirmation_message,
    person_delete_preview,
)
from backend.app.services.deletion_lifecycle import DeletionCrash


PERSON_FIELDS = (
    "person_foto",
    "main_foto",
    "rewards_foto",
    "book1_foto",
    "book2_foto",
    "card1_foto",
    "card2_foto",
)
REWARD_FIELDS = ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list")
JPEG_BYTES = b"\xff\xd8\xff\xe0person-delete"


class PersonDeletionLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.jsonl")
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
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "create table person (id integer primary key, fio text, id_rank integer, person_foto text, "
                "main_foto text, rewards_foto text, book1_foto text, book2_foto text, card1_foto text, card2_foto text)"
            )
            connection.execute(
                "create table rewards (id integer primary key, person_id integer, front_foto text, back_foto text, "
                "book1_foto text, book2_foto text, reward_list text)"
            )
            connection.execute(
                "create table person_media (id integer primary key, person_id integer, photo_field text, title text, file_path text)"
            )
            connection.execute(
                "create table mark (id integer primary key, front_foto text, back_foto text, book1_foto text, book2_foto text)"
            )
            connection.execute("create table guide (id integer primary key, image_path text)")
            for level in range(5):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, image_path text)")
            connection.execute("create table rank (id integer primary key, name text)")
            connection.execute("insert into rank (id, name) values (7, 'Neighbor rank')")
            connection.execute("insert into person (id, fio, id_rank) values (1, 'Aggregate Person', 7)")
            connection.execute("insert into person (id, fio, id_rank) values (2, 'Neighbor Person', 7)")
            connection.execute("insert into rewards (id, person_id) values (10, 1)")
            connection.execute("insert into rewards (id, person_id) values (11, 1)")
            connection.execute("insert into rewards (id, person_id) values (20, 2)")
            connection.execute("insert into person_media (id, person_id, photo_field, title) values (30, 1, 'additional', 'Document')")
            connection.execute("insert into guide (id) values (40)")
            connection.commit()

    def _write(self, relative_path: str, content: bytes = JPEG_BYTES) -> Path:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def _update(self, table: str, row_id: int, **values: object) -> None:
        assignments = ", ".join(f"{field} = ?" for field in values)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(f"update {table} set {assignments} where id = ?", (*values.values(), row_id))
            connection.commit()

    def _count(self, table: str, column: str = "id", value: int | None = None) -> int:
        with closing(sqlite3.connect(self.db_path)) as connection:
            if value is None:
                return int(connection.execute(f"select count(*) from {table}").fetchone()[0])
            return int(connection.execute(f"select count(*) from {table} where {column} = ?", (value,)).fetchone()[0])

    def _value(self, table: str, row_id: int, field: str):
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(f"select {field} from {table} where id = ?", (row_id,)).fetchone()
            return row[0] if row else None

    def test_deletes_full_aggregate_exact_folder_and_preserves_neighbors(self) -> None:
        person_paths = {field: f"Source/1/{field}.jpg" for field in PERSON_FIELDS}
        reward_10_paths = {field: f"Source/1/10/{field}.jpg" for field in REWARD_FIELDS}
        reward_11_paths = {field: f"Source/1/11/{field}.jpg" for field in REWARD_FIELDS}
        for path in (*person_paths.values(), *reward_10_paths.values(), *reward_11_paths.values()):
            self._write(path)
        media_path = "Source/1/additional.jpg"
        self._write(media_path)
        nested_document = self._write("Source/1/materials/nested/provenance.pdf", b"owned document")
        self._update("person", 1, **person_paths)
        self._update("rewards", 10, **reward_10_paths)
        self._update("rewards", 11, **reward_11_paths)
        self._update("person_media", 30, file_path=media_path)

        result = delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-full-aggregate")

        self.assertEqual(result.operation.status, "completed")
        self.assertEqual(result.preview.reward_count, 2)
        self.assertEqual(result.preview.person_media_count, 1)
        self.assertEqual(self._count("person", "id", 1), 0)
        self.assertEqual(self._count("rewards", "person_id", 1), 0)
        self.assertEqual(self._count("person_media", "person_id", 1), 0)
        self.assertFalse((self.root / "Source" / "1").exists())
        self.assertFalse(nested_document.exists())
        self.assertEqual(self._count("person", "id", 2), 1)
        self.assertEqual(self._count("rewards", "person_id", 2), 1)
        self.assertEqual(self._value("person", 2, "id_rank"), 7)
        self.assertEqual(self._count("rank", "id", 7), 1)
        self.assertEqual(self._count("guide", "id", 40), 1)

    def test_person_without_rewards_or_folder_deletes(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("delete from rewards where person_id = 1")
            connection.execute("delete from person_media where person_id = 1")
            connection.commit()

        result = delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-empty-owned")

        self.assertEqual(result.operation.status, "completed")
        self.assertEqual(result.preview.reward_count, 0)
        self.assertEqual(result.preview.person_media_count, 0)
        self.assertEqual(self._count("person", "id", 1), 0)

    def test_preview_counts_and_confirmation_warning_are_exact(self) -> None:
        self._write("Source/1/front.jpg")
        self._write("Source/1/docs/a.pdf", b"pdf")
        self._update("person", 1, person_foto="Source/1/front.jpg")
        self._update("rewards", 10, front_foto="Source/1/front.jpg")
        self._update("person_media", 30, file_path="Source/1/front.jpg")

        preview = person_delete_preview(self.settings(), 1)
        message = person_delete_confirmation_message(preview)

        self.assertEqual(preview.reward_count, 2)
        self.assertEqual(preview.person_media_count, 1)
        self.assertEqual(preview.database_media_reference_count, 3)
        self.assertEqual(preview.folder_item_count, 3)
        self.assertIn("Наград: 2", message)
        self.assertIn("дополнительных материалов: 1", message)
        self.assertIn("связанных материалов: 3", message)
        self.assertIn("файлов и папок: 3", message)

    def test_shared_path_outside_person_folder_is_preserved(self) -> None:
        shared = self._write("Source/2/shared.jpg")
        self._update("person", 1, person_foto="Source/2/shared.jpg")
        self._update("person", 2, person_foto="Source/2/shared.jpg")

        preview = person_delete_preview(self.settings(), 1)
        self.assertEqual(preview.preserved_shared_reference_count, 1)
        self.assertIsNone(preview.block_reason)

        result = delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-shared-outside")

        self.assertEqual(result.operation.preserved_shared_references, 1)
        self.assertTrue(shared.exists())
        self.assertEqual(self._value("person", 2, "person_foto"), "Source/2/shared.jpg")

    def test_external_reference_into_person_folder_blocks_without_mutation(self) -> None:
        shared_inside = self._write("Source/1/shared.jpg")
        self._update("person", 1, person_foto="Source/1/shared.jpg")
        self._update("person", 2, person_foto="Source/1/shared.jpg")

        preview = person_delete_preview(self.settings(), 1)
        self.assertIn("Внешняя запись", preview.block_reason or "")

        with self.assertRaises(PersonDeleteBlockedError):
            delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-external-ref")

        self.assertEqual(self._count("person", "id", 1), 1)
        self.assertEqual(self._count("rewards", "person_id", 1), 2)
        self.assertEqual(self._count("person_media", "person_id", 1), 1)
        self.assertTrue(shared_inside.exists())

    def test_missing_media_is_safe_but_unsafe_reference_blocks(self) -> None:
        self._update("person", 1, person_foto="Source/1/missing.jpg")
        result = delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-missing-media")
        self.assertEqual(result.operation.status, "completed")

        self._update("person", 2, person_foto="../outside.jpg")
        with self.assertRaisesRegex(PersonDeleteBlockedError, "путь к материалам"):
            delete_person_with_result(self.settings(), 2, confirm=True, operation_id="person-unsafe-path")
        self.assertEqual(self._count("person", "id", 2), 1)

    def test_symlink_and_hardlink_ambiguity_block_delete(self) -> None:
        outside = self._write("outside.jpg")
        person_dir = self.root / "Source" / "1"
        person_dir.mkdir(parents=True)
        link = person_dir / "linked.jpg"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaises(PersonDeleteBlockedError):
            delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-symlink")
        self.assertEqual(self._count("person", "id", 1), 1)
        link.unlink()

        owned = self._write("Source/1/hardlinked.jpg")
        hardlink = self.root / "hardlink-copy.jpg"
        try:
            os.link(owned, hardlink)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        with self.assertRaises(PersonDeleteBlockedError):
            delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-hardlink")
        self.assertTrue(owned.exists())
        self.assertEqual(self._count("person", "id", 1), 1)

    def test_database_failure_restores_folder_and_all_rows(self) -> None:
        photo = self._write("Source/1/front.jpg")
        self._update("person", 1, person_foto="Source/1/front.jpg")

        def fail(checkpoint: str) -> None:
            if checkpoint == "database_phase_complete":
                raise RuntimeError("injected aggregate DB failure")

        with self.assertRaisesRegex(RuntimeError, "injected aggregate DB failure"):
            delete_person_with_result(
                self.settings(), 1, confirm=True, operation_id="person-db-failure", fault_hook=fail
            )

        self.assertEqual(self._count("person", "id", 1), 1)
        self.assertEqual(self._count("rewards", "person_id", 1), 2)
        self.assertEqual(self._count("person_media", "person_id", 1), 1)
        self.assertTrue(photo.exists())
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / "person-db-failure").exists())

    def test_purge_failure_and_double_submit_recover_idempotently(self) -> None:
        self._write("Source/1/front.jpg")
        self._update("person", 1, person_foto="Source/1/front.jpg")
        operation_id = "person-purge-retry"
        with patch("backend.app.services.deletion_lifecycle._purge_operation", side_effect=OSError("busy")):
            first = delete_person_with_result(self.settings(), 1, confirm=True, operation_id=operation_id)
        self.assertTrue(first.operation.warning_required)
        self.assertEqual(self._count("person", "id", 1), 0)
        self.assertTrue((self.root / ".deletion-quarantine" / "operations" / operation_id).exists())

        retry = delete_person_with_result(self.settings(), 1, confirm=True, operation_id=operation_id)
        repeated = delete_person_with_result(self.settings(), 1, confirm=True, operation_id=operation_id)

        self.assertEqual(retry.operation.status, "completed")
        self.assertEqual(repeated.operation.status, "already_completed")
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / operation_id).exists())
        self.assertEqual(self._count("person", "id", 2), 1)

    def test_crash_after_quarantine_is_restored_then_same_operation_completes(self) -> None:
        photo = self._write("Source/1/front.jpg")
        self._update("person", 1, person_foto="Source/1/front.jpg")

        def crash(checkpoint: str) -> None:
            if checkpoint == "paths_staged":
                raise DeletionCrash("simulated crash")

        with self.assertRaises(DeletionCrash):
            delete_person_with_result(
                self.settings(), 1, confirm=True, operation_id="person-crash-recovery", fault_hook=crash
            )
        self.assertEqual(self._count("person", "id", 1), 1)
        self.assertFalse(photo.exists())

        recovered = delete_person_with_result(
            self.settings(), 1, confirm=True, operation_id="person-crash-recovery"
        )

        self.assertEqual(recovered.operation.status, "completed")
        self.assertEqual(self._count("person", "id", 1), 0)
        self.assertFalse((self.root / "Source" / "1").exists())

    def test_crash_after_database_commit_is_completed_by_same_operation(self) -> None:
        self._write("Source/1/front.jpg")
        self._update("person", 1, person_foto="Source/1/front.jpg")

        def crash(checkpoint: str) -> None:
            if checkpoint == "database_committed":
                raise DeletionCrash("simulated post-commit crash")

        with self.assertRaises(DeletionCrash):
            delete_person_with_result(
                self.settings(), 1, confirm=True, operation_id="person-post-commit-crash", fault_hook=crash
            )
        self.assertEqual(self._count("person", "id", 1), 0)
        self.assertTrue(
            (self.root / ".deletion-quarantine" / "operations" / "person-post-commit-crash").exists()
        )

        recovered = delete_person_with_result(
            self.settings(), 1, confirm=True, operation_id="person-post-commit-crash"
        )

        self.assertEqual(recovered.operation.status, "completed")
        self.assertFalse(
            (self.root / ".deletion-quarantine" / "operations" / "person-post-commit-crash").exists()
        )
        self.assertEqual(self._count("person", "id", 2), 1)

    def test_audit_records_counts_without_media_paths(self) -> None:
        self._write("Source/1/front.jpg")
        self._update("person", 1, person_foto="Source/1/front.jpg")
        delete_person_with_result(self.settings(), 1, confirm=True, operation_id="person-audit-event")

        audit = (self.root / "logs" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"operation_id": "person-audit-event"', audit)
        self.assertIn('"rewards_deleted": 2', audit)
        self.assertIn('"person_media_deleted": 1', audit)
        self.assertNotIn("Source/1/front.jpg", audit)


if __name__ == "__main__":
    unittest.main()
