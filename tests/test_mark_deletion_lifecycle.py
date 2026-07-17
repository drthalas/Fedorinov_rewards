from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.repositories.marks_write import (
    MarkDeleteBlockedError,
    delete_mark_with_result,
    mark_delete_confirmation_message,
    mark_delete_preview,
)


MEDIA_FIELDS = ("front_foto", "back_foto", "book1_foto", "book2_foto")
JPEG_BYTES = b"\xff\xd8\xff\xe0mark-delete"


class MarkDeletionLifecycleTests(unittest.TestCase):
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
                "create table person (id integer primary key, person_foto text, main_foto text, rewards_foto text, "
                "book1_foto text, book2_foto text, card1_foto text, card2_foto text)"
            )
            connection.execute(
                "create table rewards (id integer primary key, person_id integer, front_foto text, back_foto text, "
                "book1_foto text, book2_foto text, reward_list text)"
            )
            connection.execute(
                "create table mark (id integer primary key, front_foto text, back_foto text, book1_foto text, book2_foto text)"
            )
            connection.execute("create table guide (id integer primary key, image_path text)")
            for level in range(5):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, image_path text)")
            connection.execute("create table person_media (id integer primary key, person_id integer, file_path text)")
            connection.execute("insert into mark (id) values (20)")
            connection.execute("insert into mark (id) values (21)")
            connection.execute("insert into guide (id) values (30)")
            connection.commit()

    def _write(self, relative_path: str, content: bytes = JPEG_BYTES) -> Path:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def _update_mark(self, mark_id: int, **values: object) -> None:
        assignments = ", ".join(f"{field} = ?" for field in values)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(f"update mark set {assignments} where id = ?", (*values.values(), mark_id))
            connection.commit()

    def _mark(self, mark_id: int):
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("select * from mark where id = ?", (mark_id,)).fetchone()

    def _count(self, table: str) -> int:
        with closing(sqlite3.connect(self.db_path)) as connection:
            return int(connection.execute(f"select count(*) from {table}").fetchone()[0])

    def test_deletes_all_four_fields_exact_folder_and_owned_documents(self) -> None:
        paths = {field: f"SourceMark/20/{field}.jpg" for field in MEDIA_FIELDS}
        for path in paths.values():
            self._write(path)
        document = self._write("SourceMark/20/provenance.pdf", b"test-document")
        self._update_mark(20, **paths)

        result = delete_mark_with_result(self.settings(), 20, confirm=True, operation_id="mark-all-media")

        self.assertEqual(result.operation.status, "completed")
        self.assertIsNone(self._mark(20))
        self.assertFalse((self.root / "SourceMark" / "20").exists())
        self.assertFalse(document.exists())
        self.assertIsNotNone(self._mark(21))
        self.assertEqual(self._count("guide"), 1)

    def test_shared_path_outside_owned_folder_is_preserved(self) -> None:
        shared = self._write("SourceMark/shared.jpg")
        owned = self._write("SourceMark/20/owned.jpg")
        self._update_mark(20, front_foto="SourceMark/shared.jpg", back_foto="SourceMark/20/owned.jpg")
        self._update_mark(21, front_foto="SourceMark/shared.jpg")

        preview = mark_delete_preview(self.settings(), 20)
        self.assertEqual(preview.media.linked_media_count, 2)
        self.assertEqual(preview.media.folder_item_count, 1)
        self.assertEqual(preview.media.preserved_shared_reference_count, 1)
        self.assertIsNone(preview.media.block_reason)
        self.assertIn("общих файлов будет сохранено: 1", mark_delete_confirmation_message(preview))

        result = delete_mark_with_result(self.settings(), 20, confirm=True, operation_id="mark-shared-ref")

        self.assertEqual(result.operation.preserved_shared_references, 1)
        self.assertTrue(shared.exists())
        self.assertFalse(owned.exists())
        self.assertEqual(self._mark(21)["front_foto"], "SourceMark/shared.jpg")

    def test_external_reference_into_owned_folder_blocks_without_mutation(self) -> None:
        shared_inside = self._write("SourceMark/20/shared.jpg")
        self._update_mark(20, front_foto="SourceMark/20/shared.jpg")
        self._update_mark(21, front_foto="SourceMark/20/shared.jpg")

        preview = mark_delete_preview(self.settings(), 20)
        self.assertIn("Внешняя запись", preview.media.block_reason or "")

        with self.assertRaises(MarkDeleteBlockedError):
            delete_mark_with_result(self.settings(), 20, confirm=True, operation_id="mark-external-ref")

        self.assertIsNotNone(self._mark(20))
        self.assertIsNotNone(self._mark(21))
        self.assertTrue(shared_inside.exists())

    def test_missing_media_is_safe_but_unsafe_path_blocks(self) -> None:
        self._update_mark(20, front_foto="SourceMark/20/missing.jpg")
        result = delete_mark_with_result(self.settings(), 20, confirm=True, operation_id="mark-missing-media")
        self.assertEqual(result.operation.status, "completed")
        self.assertIsNone(self._mark(20))

        self._update_mark(21, front_foto="../outside.jpg")
        with self.assertRaisesRegex(MarkDeleteBlockedError, "путь к материалам"):
            delete_mark_with_result(self.settings(), 21, confirm=True, operation_id="mark-unsafe-path")
        self.assertIsNotNone(self._mark(21))

    def test_symlink_in_mark_folder_blocks_delete(self) -> None:
        outside = self._write("outside.jpg")
        mark_dir = self.root / "SourceMark" / "20"
        mark_dir.mkdir(parents=True)
        link = mark_dir / "linked.jpg"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")

        with self.assertRaises(MarkDeleteBlockedError):
            delete_mark_with_result(self.settings(), 20, confirm=True, operation_id="mark-symlink")

        self.assertTrue(link.is_symlink())
        self.assertIsNotNone(self._mark(20))

    def test_failure_after_staging_rolls_back_row_and_restores_folder(self) -> None:
        photo = self._write("SourceMark/20/front.jpg")
        self._update_mark(20, front_foto="SourceMark/20/front.jpg")

        def fail(checkpoint: str) -> None:
            if checkpoint == "database_phase_complete":
                raise RuntimeError("injected pre-commit failure")

        with self.assertRaisesRegex(RuntimeError, "injected pre-commit failure"):
            delete_mark_with_result(
                self.settings(), 20, confirm=True, operation_id="mark-db-failure", fault_hook=fail
            )

        self.assertIsNotNone(self._mark(20))
        self.assertTrue(photo.exists())
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / "mark-db-failure").exists())

    def test_purge_failure_warns_and_same_submit_recovers_idempotently(self) -> None:
        self._write("SourceMark/20/front.jpg")
        self._update_mark(20, front_foto="SourceMark/20/front.jpg")
        operation_id = "mark-purge-retry"
        with patch("backend.app.services.deletion_lifecycle._purge_operation", side_effect=OSError("busy")):
            first = delete_mark_with_result(self.settings(), 20, confirm=True, operation_id=operation_id)
        self.assertTrue(first.operation.warning_required)
        self.assertIsNone(self._mark(20))
        self.assertTrue((self.root / ".deletion-quarantine" / "operations" / operation_id).exists())

        retry = delete_mark_with_result(self.settings(), 20, confirm=True, operation_id=operation_id)
        repeated = delete_mark_with_result(self.settings(), 20, confirm=True, operation_id=operation_id)

        self.assertEqual(retry.operation.status, "completed")
        self.assertEqual(repeated.operation.status, "already_completed")
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / operation_id).exists())
        self.assertIsNotNone(self._mark(21))

    def test_audit_records_operation_counts_without_paths(self) -> None:
        self._write("SourceMark/20/front.jpg")
        self._update_mark(20, front_foto="SourceMark/20/front.jpg")
        delete_mark_with_result(self.settings(), 20, confirm=True, operation_id="mark-audit-event")
        audit = (self.root / "logs" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"operation_id": "mark-audit-event"', audit)
        self.assertIn('"staged_paths": 1', audit)
        self.assertNotIn("SourceMark/20/front.jpg", audit)


if __name__ == "__main__":
    unittest.main()
