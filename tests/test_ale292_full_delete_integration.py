from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import sqlite3
import unittest

from backend.app.config import Settings
from backend.app.repositories.guides_write import (
    GuideDeleteBlockedError,
    delete_guide_level_item,
    delete_rank,
)
from backend.app.repositories.marks_write import delete_mark_with_result
from backend.app.repositories.persons_write import (
    PersonDeleteBlockedError,
    delete_person_with_result,
)
from backend.app.repositories.rewards_write import delete_reward_with_result
from backend.app.services.deletion_lifecycle import DeletionCrash


PERSON_MEDIA_FIELDS = (
    "person_foto",
    "main_foto",
    "rewards_foto",
    "book1_foto",
    "book2_foto",
    "card1_foto",
    "card2_foto",
)
REWARD_MEDIA_FIELDS = ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list")
MARK_MEDIA_FIELDS = ("front_foto", "back_foto", "book1_foto", "book2_foto")
JPEG_BYTES = b"\xff\xd8\xff\xe0ale292-integration"
PNG_BYTES = b"\x89PNG\r\n\x1a\nale292-integration"


class FullDeletionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.jsonl")
        self._create_schema()
        self._seed_representative_dataset()

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

    def _create_schema(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executescript(
                """
                create table person (
                    id integer primary key,
                    fio text,
                    id_rank integer,
                    person_foto text,
                    main_foto text,
                    rewards_foto text,
                    book1_foto text,
                    book2_foto text,
                    card1_foto text,
                    card2_foto text
                );
                create table rewards (
                    id integer primary key,
                    person_id integer,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link text,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
                );
                create table person_media (
                    id integer primary key,
                    person_id integer,
                    photo_field text,
                    title text,
                    file_path text
                );
                create table mark (
                    id integer primary key,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link text,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text
                );
                create table guide (id integer primary key, name text, image_path text);
                """
            )
            for level in range(5):
                connection.execute(
                    f"create table guide_lev_{level} ("
                    "id integer primary key, idl integer, name text, rating_rank integer, image_path text)"
                )

    def _seed_representative_dataset(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executemany(
                "insert into guide (id, name) values (?, ?)",
                (
                    (401, "Aggregate rank"),
                    (402, "Used rank"),
                    (403, "Unused rank"),
                    (404, "Shared-image rank"),
                ),
            )
            connection.executemany(
                "insert into person (id, fio, id_rank) values (?, ?, ?)",
                (
                    (101, "ALE292 Aggregate", 401),
                    (102, "ALE292 Neighbor", 402),
                    (201, "ALE292 Reward owner", 401),
                ),
            )
            connection.executemany(
                "insert into rewards (id, person_id) values (?, ?)",
                ((111, 101), (112, 101), (211, 201), (212, 201)),
            )
            connection.execute(
                "insert into person_media (id, person_id, photo_field, title) values (121, 101, 'additional', 'Owned document')"
            )
            connection.executemany("insert into mark (id) values (?)", ((301,), (302,)))
            connection.executemany(
                "insert into guide_lev_0 values (?, ?, ?, ?, ?)",
                ((500, -1, "Parent", None, None),),
            )
            connection.executemany(
                "insert into guide_lev_1 values (?, ?, ?, ?, ?)",
                ((510, 500, "Child", None, None),),
            )
            connection.executemany(
                "insert into guide_lev_2 values (?, ?, ?, ?, ?)",
                ((599, 9999, "Pre-existing hierarchy gap", None, None),),
            )
            connection.executemany(
                "insert into guide_lev_3 values (?, ?, ?, ?, ?)",
                (
                    (503, 0, "Unused image", None, None),
                    (505, 0, "Shared image", None, None),
                ),
            )
            connection.execute(
                "insert into guide_lev_4 values (504, 0, 'Common Badge', null, null)"
            )
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

    def _insert_person(self, person_id: int, *, fio: str, photo_path: str | None = None) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "insert into person (id, fio, id_rank, person_foto) values (?, ?, 401, ?)",
                (person_id, fio, photo_path),
            )
            connection.commit()

    def _insert_reward(self, reward_id: int, person_id: int, photo_path: str | None = None) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "insert into rewards (id, person_id, front_foto) values (?, ?, ?)",
                (reward_id, person_id, photo_path),
            )
            connection.commit()

    def _count(self, table: str, where: str = "", values: tuple[object, ...] = ()) -> int:
        suffix = f" where {where}" if where else ""
        with closing(sqlite3.connect(self.db_path)) as connection:
            return int(connection.execute(f"select count(*) from {table}{suffix}", values).fetchone()[0])

    def _value(self, table: str, row_id: int, field: str):
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(f"select {field} from {table} where id = ?", (row_id,)).fetchone()
            return row[0] if row else None

    def test_representative_success_matrix_preserves_shared_and_neighbor_data(self) -> None:
        aggregate_paths = {field: f"Source/101/person/{field}.jpg" for field in PERSON_MEDIA_FIELDS}
        reward_111_paths = {field: f"Source/101/111/{field}.jpg" for field in REWARD_MEDIA_FIELDS}
        reward_112_paths = {field: f"Source/101/112/{field}.jpg" for field in REWARD_MEDIA_FIELDS}
        for path in (*aggregate_paths.values(), *reward_111_paths.values(), *reward_112_paths.values()):
            self._write(path)
        additional_path = "Source/101/materials/additional.jpg"
        self._write(additional_path)
        self._write("Source/101/materials/nested/provenance.pdf", b"owned document")
        self._update("person", 101, **aggregate_paths)
        self._update("rewards", 111, **reward_111_paths)
        self._update("rewards", 112, **reward_112_paths)
        self._update("person_media", 121, file_path=additional_path)

        reward_shared = self._write("Source/201/shared.jpg")
        reward_owned = {field: f"Source/201/211/{field}.jpg" for field in REWARD_MEDIA_FIELDS[1:]}
        for path in reward_owned.values():
            self._write(path)
        self._write("Source/201/211/documents/note.txt", b"owned note")
        self._update("rewards", 211, front_foto="Source/201/shared.jpg", **reward_owned)
        self._update("rewards", 212, front_foto="Source/201/shared.jpg", id_link="prefix common badge suffix")

        mark_shared = self._write("SourceMark/shared.jpg")
        mark_owned = {field: f"SourceMark/301/{field}.jpg" for field in MARK_MEDIA_FIELDS[1:]}
        for path in mark_owned.values():
            self._write(path)
        self._write("SourceMark/301/documents/note.txt", b"owned mark note")
        self._update("mark", 301, front_foto="SourceMark/shared.jpg", **mark_owned)
        self._update("mark", 302, front_foto="SourceMark/shared.jpg")

        unused_rank_image = self._write("GuideImages/ale292-unused-rank.png", PNG_BYTES)
        unused_item_image = self._write("GuideImages/ale292-unused-item.png", PNG_BYTES)
        shared_guide_image = self._write("GuideImages/ale292-shared.png", PNG_BYTES)
        self._update("guide", 403, image_path="GuideImages/ale292-unused-rank.png")
        self._update("guide", 404, image_path="GuideImages/ale292-shared.png")
        self._update("guide_lev_3", 503, image_path="GuideImages/ale292-unused-item.png")
        self._update("guide_lev_3", 505, image_path="GuideImages/ale292-shared.png")

        reward_result = delete_reward_with_result(
            self.settings(), 211, confirm=True, operation_id="ale292-reward-success"
        )
        mark_result = delete_mark_with_result(
            self.settings(), 301, confirm=True, operation_id="ale292-mark-success"
        )
        person_result = delete_person_with_result(
            self.settings(), 101, confirm=True, operation_id="ale292-person-success"
        )
        rank_result = delete_rank(self.settings(), 403, confirm=True, operation_id="ale292-rank-success")
        shared_rank_result = delete_rank(
            self.settings(), 404, confirm=True, operation_id="ale292-rank-shared"
        )
        item_result = delete_guide_level_item(
            self.settings(), 3, 503, confirm=True, operation_id="ale292-guide-success"
        )
        shared_item_result = delete_guide_level_item(
            self.settings(), 3, 505, confirm=True, operation_id="ale292-guide-shared"
        )

        self.assertEqual(reward_result.operation.preserved_shared_references, 1)
        self.assertEqual(mark_result.operation.preserved_shared_references, 1)
        self.assertEqual(person_result.preview.reward_count, 2)
        self.assertEqual(person_result.preview.person_media_count, 1)
        self.assertEqual(rank_result.status, "completed")
        self.assertEqual(shared_rank_result.preserved_shared_references, 1)
        self.assertEqual(item_result.status, "completed")
        self.assertEqual(shared_item_result.status, "completed")

        self.assertEqual(self._count("rewards", "id = ?", (211,)), 0)
        self.assertEqual(self._count("rewards", "id = ?", (212,)), 1)
        self.assertFalse((self.root / "Source" / "201" / "211").exists())
        self.assertTrue(reward_shared.is_file())
        self.assertEqual(self._value("rewards", 212, "front_foto"), "Source/201/shared.jpg")

        self.assertEqual(self._count("mark", "id = ?", (301,)), 0)
        self.assertEqual(self._count("mark", "id = ?", (302,)), 1)
        self.assertFalse((self.root / "SourceMark" / "301").exists())
        self.assertTrue(mark_shared.is_file())

        self.assertEqual(self._count("person", "id = ?", (101,)), 0)
        self.assertEqual(self._count("rewards", "person_id = ?", (101,)), 0)
        self.assertEqual(self._count("person_media", "person_id = ?", (101,)), 0)
        self.assertFalse((self.root / "Source" / "101").exists())
        self.assertEqual(self._count("person", "id = ?", (102,)), 1)
        self.assertEqual(self._count("guide", "id = ?", (401,)), 1)

        self.assertFalse(unused_rank_image.exists())
        self.assertFalse(unused_item_image.exists())
        self.assertFalse(shared_guide_image.exists())
        self.assertEqual(self._count("guide_lev_2", "id = ?", (599,)), 1)

        with self.assertRaises(GuideDeleteBlockedError):
            delete_rank(self.settings(), 402, confirm=True, operation_id="ale292-rank-used")
        with self.assertRaises(GuideDeleteBlockedError):
            delete_guide_level_item(
                self.settings(), 0, 500, confirm=True, operation_id="ale292-guide-child-block"
            )
        with self.assertRaises(GuideDeleteBlockedError):
            delete_guide_level_item(
                self.settings(), 4, 504, confirm=True, operation_id="ale292-guide-level4-block"
            )
        self.assertEqual(self._count("guide", "id = ?", (402,)), 1)
        self.assertEqual(self._count("guide_lev_0", "id = ?", (500,)), 1)
        self.assertEqual(self._count("guide_lev_4", "id = ?", (504,)), 1)

        operation_dirs = self.root / ".deletion-quarantine" / "operations"
        self.assertFalse(operation_dirs.exists() and any(operation_dirs.iterdir()))

    def test_failure_restart_purge_retry_and_idempotency_converge(self) -> None:
        rollback_path = self._write("Source/701/front.jpg")
        self._insert_person(701, fio="ALE292 Rollback", photo_path="Source/701/front.jpg")

        def fail_before_commit(checkpoint: str) -> None:
            if checkpoint == "database_phase_complete":
                raise RuntimeError("injected pre-commit failure")

        with self.assertRaisesRegex(RuntimeError, "injected pre-commit failure"):
            delete_person_with_result(
                self.settings(),
                701,
                confirm=True,
                operation_id="ale292-precommit-failure",
                fault_hook=fail_before_commit,
            )
        self.assertEqual(self._count("person", "id = ?", (701,)), 1)
        self.assertTrue(rollback_path.is_file())

        staged_path = self._write("Source/702/front.jpg")
        self._insert_person(702, fio="ALE292 Precommit restart", photo_path="Source/702/front.jpg")

        def crash_after_staging(checkpoint: str) -> None:
            if checkpoint == "paths_staged":
                raise DeletionCrash("injected staged crash")

        with self.assertRaises(DeletionCrash):
            delete_person_with_result(
                self.settings(),
                702,
                confirm=True,
                operation_id="ale292-staged-restart",
                fault_hook=crash_after_staging,
            )
        self.assertEqual(self._count("person", "id = ?", (702,)), 1)
        self.assertFalse(staged_path.exists())
        staged_retry = delete_person_with_result(
            self.settings(), 702, confirm=True, operation_id="ale292-staged-restart"
        )
        self.assertEqual(staged_retry.operation.status, "completed")
        self.assertEqual(self._count("person", "id = ?", (702,)), 0)

        committed_path = self._write("Source/703/front.jpg")
        self._insert_person(703, fio="ALE292 Postcommit restart", photo_path="Source/703/front.jpg")

        def crash_after_commit(checkpoint: str) -> None:
            if checkpoint == "database_committed":
                raise DeletionCrash("injected committed crash")

        with self.assertRaises(DeletionCrash):
            delete_person_with_result(
                self.settings(),
                703,
                confirm=True,
                operation_id="ale292-committed-restart",
                fault_hook=crash_after_commit,
            )
        self.assertEqual(self._count("person", "id = ?", (703,)), 0)
        self.assertFalse(committed_path.exists())
        committed_retry = delete_person_with_result(
            self.settings(), 703, confirm=True, operation_id="ale292-committed-restart"
        )
        self.assertEqual(committed_retry.operation.status, "completed")

        purge_path = self._write("Source/201/710/front.jpg")
        self._insert_reward(710, 201, "Source/201/710/front.jpg")
        unrelated_orphan = self._write("Source/999999/pre-existing-orphan.jpg")
        with patch("backend.app.services.deletion_lifecycle._purge_operation", side_effect=OSError("busy")):
            first = delete_reward_with_result(
                self.settings(), 710, confirm=True, operation_id="ale292-purge-retry"
            )
        self.assertTrue(first.operation.warning_required)
        self.assertEqual(first.operation.status, "cleanup_pending")
        self.assertEqual(self._count("rewards", "id = ?", (710,)), 0)
        self.assertFalse(purge_path.exists())
        operation_dir = self.root / ".deletion-quarantine" / "operations" / "ale292-purge-retry"
        self.assertTrue(operation_dir.is_dir())

        retry = delete_reward_with_result(
            self.settings(), 710, confirm=True, operation_id="ale292-purge-retry"
        )
        repeated = delete_reward_with_result(
            self.settings(), 710, confirm=True, operation_id="ale292-purge-retry"
        )
        self.assertEqual(retry.operation.status, "completed")
        self.assertEqual(repeated.operation.status, "already_completed")
        self.assertFalse(operation_dir.exists())
        self.assertFalse((self.root / "Source" / "201" / "710").exists())
        self.assertTrue(unrelated_orphan.is_file())
        self.assertEqual(self._count("rewards", "id = ?", (212,)), 1)

    def test_external_references_symlinks_and_hardlinks_block_without_mutation(self) -> None:
        shared_inside = self._write("Source/101/external-reference.jpg")
        self._update("person", 101, person_foto="Source/101/external-reference.jpg")
        self._update("person", 102, person_foto="Source/101/external-reference.jpg")
        with self.assertRaises(PersonDeleteBlockedError):
            delete_person_with_result(
                self.settings(), 101, confirm=True, operation_id="ale292-external-reference"
            )
        self.assertEqual(self._count("person", "id = ?", (101,)), 1)
        self.assertTrue(shared_inside.is_file())

        outside = self._write("outside-symlink-target.jpg")
        self._insert_person(801, fio="ALE292 Symlink")
        symlink_dir = self.root / "Source" / "801"
        symlink_dir.mkdir(parents=True)
        symlink = symlink_dir / "linked.jpg"
        try:
            symlink.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaises(PersonDeleteBlockedError):
            delete_person_with_result(self.settings(), 801, confirm=True, operation_id="ale292-symlink")
        self.assertEqual(self._count("person", "id = ?", (801,)), 1)
        self.assertTrue(symlink.is_symlink())
        self.assertTrue(outside.is_file())

        hardlinked = self._write("Source/802/hardlinked.jpg")
        self._insert_person(802, fio="ALE292 Hardlink", photo_path="Source/802/hardlinked.jpg")
        hardlink_copy = self.root / "hardlink-copy.jpg"
        try:
            os.link(hardlinked, hardlink_copy)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        with self.assertRaises(PersonDeleteBlockedError):
            delete_person_with_result(self.settings(), 802, confirm=True, operation_id="ale292-hardlink")
        self.assertEqual(self._count("person", "id = ?", (802,)), 1)
        self.assertTrue(hardlinked.is_file())
        self.assertTrue(hardlink_copy.is_file())


if __name__ == "__main__":
    unittest.main()
