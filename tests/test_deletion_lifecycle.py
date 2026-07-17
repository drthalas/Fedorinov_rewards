from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import closing
import os
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.services import deletion_lifecycle
from backend.app.services.deletion_lifecycle import (
    DeletionBlockedError,
    DeletionCrash,
    DeletionValidationError,
    MediaReferenceExclusion,
    OwnedPath,
    RowCountExpectation,
    build_delete_plan,
    execute_delete_plan,
    guide_owned_image,
    person_owned_directory,
    recover_delete_operation,
    reward_owned_directory,
)


JPEG_BYTES = b"\xff\xd8\xff\xe0deletion-foundation"


class DeletionLifecycleTests(unittest.TestCase):
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
                "create table person (id integer primary key, person_foto text, main_foto text)"
            )
            connection.execute(
                "create table rewards (id integer primary key, person_id integer, front_foto text)"
            )
            connection.execute("create table guide (id integer primary key, image_path text)")
            connection.execute("create table guide_lev_0 (id integer primary key, image_path text)")
            connection.execute("insert into person (id) values (1)")
            connection.execute("insert into person (id) values (2)")
            connection.execute("insert into rewards (id, person_id) values (10, 1)")
            connection.execute("insert into guide (id) values (20)")
            connection.execute("insert into guide_lev_0 (id) values (30)")
            connection.commit()

    def _write(self, relative_path: str, content: bytes = JPEG_BYTES) -> Path:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def _person_plan(self, *, operation_id: str, references: tuple[object, ...] = ()):
        return build_delete_plan(
            self.settings(),
            operation_id=operation_id,
            entity_type="person",
            entity_ids=(1,),
            expected_row_counts=(RowCountExpectation("person", "id", 1, 1),),
            reference_paths=references,
            excluded_rows=(MediaReferenceExclusion("person", 1),),
            owned_paths=(person_owned_directory(1),),
        )

    def _delete_person(self, connection) -> None:
        connection.execute("delete from person where id = 1")

    def _person_exists(self) -> bool:
        with closing(sqlite3.connect(self.db_path)) as connection:
            return connection.execute("select 1 from person where id = 1").fetchone() is not None

    def test_owned_path_constructors_are_exact_and_plan_is_immutable(self) -> None:
        self.assertEqual(person_owned_directory(7).relative_path, "Source/7")
        self.assertEqual(reward_owned_directory(7, 9).relative_path, "Source/7/9")
        self.assertEqual(guide_owned_image(self.settings(), "GuideImages/rank.jpg").relative_path, "GuideImages/rank.jpg")
        with self.assertRaises(DeletionValidationError):
            person_owned_directory(0)
        with self.assertRaises(DeletionValidationError):
            guide_owned_image(self.settings(), "GuideImages/nested/rank.jpg")
        with self.assertRaises(DeletionValidationError):
            build_delete_plan(
                self.settings(),
                operation_id="bad-traversal",
                entity_type="person",
                entity_ids=(1,),
                expected_row_counts=(RowCountExpectation("person", "id", 1, 1),),
                owned_paths=(OwnedPath("person_directory", "Source/../1", "directory"),),
            )
        with self.assertRaises(DeletionValidationError):
            self._person_plan(operation_id="absolute-ref", references=("/tmp/outside.jpg",))
        plan = self._person_plan(operation_id="immutable-plan")
        with self.assertRaises(AttributeError):
            plan.entity_type = "reward"  # type: ignore[misc]

    def test_success_stages_then_commits_and_purges_owned_tree(self) -> None:
        photo = self._write("Source/1/photo.jpg")
        unrelated = self._write("Source/2/unrelated.jpg", b"unrelated")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("update person set person_foto = ? where id = 1", ("Source/1/photo.jpg",))
            connection.commit()
        plan = self._person_plan(operation_id="success-delete", references=("Source/1/photo.jpg",))

        result = execute_delete_plan(self.settings(), plan, self._delete_person)

        self.assertEqual(result.status, "completed")
        self.assertFalse(self._person_exists())
        self.assertFalse(photo.exists())
        self.assertFalse((self.root / "Source" / "1").exists())
        self.assertEqual(unrelated.read_bytes(), b"unrelated")
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / plan.operation_id).exists())

    def test_database_failure_restores_staged_tree_and_row(self) -> None:
        photo = self._write("Source/1/photo.jpg")
        plan = self._person_plan(operation_id="rollback-delete")

        def fail_database_phase(connection) -> None:
            connection.execute("delete from person where id = 1")
            raise RuntimeError("injected database failure")

        with self.assertRaisesRegex(RuntimeError, "injected database failure"):
            execute_delete_plan(self.settings(), plan, fail_database_phase)

        self.assertTrue(self._person_exists())
        self.assertEqual(photo.read_bytes(), JPEG_BYTES)
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / plan.operation_id).exists())

    def test_crash_after_staging_is_restored_from_manifest(self) -> None:
        photo = self._write("Source/1/photo.jpg")
        plan = self._person_plan(operation_id="crash-staged")

        def crash(checkpoint: str) -> None:
            if checkpoint == "paths_staged":
                raise DeletionCrash("simulated stop")

        with self.assertRaises(DeletionCrash):
            execute_delete_plan(self.settings(), plan, self._delete_person, fault_hook=crash)
        self.assertTrue(self._person_exists())
        self.assertFalse(photo.exists())

        result = recover_delete_operation(self.settings(), plan.operation_id)

        self.assertEqual(result.status, "restored")
        self.assertTrue(photo.exists())
        self.assertTrue(self._person_exists())

    def test_crash_after_commit_is_completed_by_recovery(self) -> None:
        photo = self._write("Source/1/photo.jpg")
        plan = self._person_plan(operation_id="crash-commit")

        def crash(checkpoint: str) -> None:
            if checkpoint == "database_committed":
                raise DeletionCrash("simulated stop")

        with self.assertRaises(DeletionCrash):
            execute_delete_plan(self.settings(), plan, self._delete_person, fault_hook=crash)
        self.assertFalse(self._person_exists())
        self.assertFalse(photo.exists())

        result = recover_delete_operation(self.settings(), plan.operation_id)

        self.assertEqual(result.status, "completed")
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / plan.operation_id).exists())

    def test_post_commit_purge_failure_is_retryable_and_warns(self) -> None:
        self._write("Source/1/photo.jpg")
        plan = self._person_plan(operation_id="purge-retry")
        with patch("backend.app.services.deletion_lifecycle._purge_operation", side_effect=OSError("busy")):
            result = execute_delete_plan(self.settings(), plan, self._delete_person)

        self.assertEqual(result.status, "cleanup_pending")
        self.assertTrue(result.warning_required)
        self.assertFalse(self._person_exists())
        self.assertTrue((self.root / ".deletion-quarantine" / "operations" / plan.operation_id).exists())

        recovered = recover_delete_operation(self.settings(), plan.operation_id)

        self.assertEqual(recovered.status, "completed")
        self.assertFalse((self.root / ".deletion-quarantine" / "operations" / plan.operation_id).exists())

    def test_repeating_completed_operation_is_idempotent(self) -> None:
        self._write("Source/1/photo.jpg")
        plan = self._person_plan(operation_id="idempotent-delete")
        execute_delete_plan(self.settings(), plan, self._delete_person)
        called = False

        def should_not_run(_connection) -> None:
            nonlocal called
            called = True

        result = execute_delete_plan(self.settings(), plan, should_not_run)

        self.assertEqual(result.status, "already_completed")
        self.assertFalse(called)

    def test_external_reference_inside_owned_directory_blocks_delete(self) -> None:
        photo = self._write("Source/1/shared.jpg")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("update person set person_foto = ? where id = 1", ("Source/1/shared.jpg",))
            connection.execute("update person set person_foto = ? where id = 2", ("Source/1/shared.jpg",))
            connection.commit()
        plan = self._person_plan(operation_id="shared-directory", references=("Source/1/shared.jpg",))

        with self.assertRaises(DeletionBlockedError):
            execute_delete_plan(self.settings(), plan, self._delete_person)

        self.assertTrue(photo.exists())
        self.assertTrue(self._person_exists())

    def test_shared_flat_guide_image_is_preserved_after_row_delete(self) -> None:
        image = self._write("GuideImages/shared.jpg")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("update guide set image_path = ? where id = 20", ("GuideImages/shared.jpg",))
            connection.execute("update guide_lev_0 set image_path = ? where id = 30", ("GuideImages/shared.jpg",))
            connection.commit()
        plan = build_delete_plan(
            self.settings(),
            operation_id="shared-guide",
            entity_type="guide",
            entity_ids=(20,),
            expected_row_counts=(RowCountExpectation("guide", "id", 20, 1),),
            reference_paths=("GuideImages/shared.jpg",),
            excluded_rows=(MediaReferenceExclusion("guide", 20),),
            owned_paths=(guide_owned_image(self.settings(), "GuideImages/shared.jpg"),),
        )

        result = execute_delete_plan(
            self.settings(),
            plan,
            lambda connection: connection.execute("delete from guide where id = 20"),
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.preserved_shared_references, 1)
        self.assertTrue(image.exists())

    def test_symlink_and_hardlink_are_blocked_without_mutation(self) -> None:
        outside = self._write("outside.jpg")
        person_dir = self.root / "Source" / "1"
        person_dir.mkdir(parents=True)
        symlink = person_dir / "linked.jpg"
        try:
            symlink.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        plan = self._person_plan(operation_id="symlink-block")
        with self.assertRaises(DeletionBlockedError):
            execute_delete_plan(self.settings(), plan, self._delete_person)
        self.assertTrue(self._person_exists())
        symlink.unlink()

        source = self._write("Source/1/original.jpg")
        hardlink = person_dir / "hardlink.jpg"
        try:
            os.link(source, hardlink)
        except OSError as exc:
            self.skipTest(f"hardlink unavailable: {exc}")
        hardlink_plan = self._person_plan(operation_id="hardlink-block")
        with self.assertRaises(DeletionBlockedError):
            execute_delete_plan(self.settings(), hardlink_plan, self._delete_person)
        self.assertTrue(source.exists())
        self.assertTrue(hardlink.exists())
        self.assertTrue(self._person_exists())

    def test_same_volume_policy_accepts_local_and_rejects_cross_volume(self) -> None:
        photo = self._write("Source/1/photo.jpg")
        deletion_lifecycle._validate_same_volume(self.settings(), photo)
        other_device = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=photo.stat().st_dev + 1))
        with patch(
            "backend.app.services.deletion_lifecycle._quarantine_root",
            return_value=other_device,
        ):
            with self.assertRaisesRegex(DeletionBlockedError, "same filesystem"):
                deletion_lifecycle._validate_same_volume(self.settings(), photo)
        self.assertTrue(photo.exists())
        self.assertTrue(self._person_exists())

    def test_unowned_last_reference_is_blocked_instead_of_deleted(self) -> None:
        photo = self._write("Source/2/photo.jpg")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("update person set person_foto = ? where id = 1", ("Source/2/photo.jpg",))
            connection.commit()
        plan = self._person_plan(operation_id="unowned-reference", references=("Source/2/photo.jpg",))

        with self.assertRaises(DeletionBlockedError):
            execute_delete_plan(self.settings(), plan, self._delete_person)

        self.assertTrue(photo.exists())
        self.assertTrue(self._person_exists())


if __name__ == "__main__":
    unittest.main()
