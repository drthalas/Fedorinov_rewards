import importlib.util
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "full_dataset_fixture.py"
SPEC = importlib.util.spec_from_file_location("full_dataset_fixture", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FullDatasetFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.master = self.root / "fixture" / "master"
        self.state = self.root / "fixture" / "state"
        (self.master / "database").mkdir(parents=True)
        (self.master / "Source" / "100").mkdir(parents=True)
        (self.master / "Source" / "100" / "sample.jpg").write_bytes(b"fixture")
        db_path = self.master / "database" / "MyDatabase.sqlite"
        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("create table person (id integer primary key)")
            connection.execute(
                "create table rewards (id integer primary key, person_id integer references person(id))"
            )
            connection.execute("insert into person(id) values (100)")
            connection.execute("insert into rewards(id, person_id) values (200, 100)")
            connection.commit()
        db_path.chmod(0o444)

    def tearDown(self):
        self.temp.cleanup()

    def test_inventory_is_sanitized_and_healthy(self):
        summary, private = MODULE.inventory(
            self.master,
            include_tree_fingerprint=True,
            sample_size=0,
        )

        self.assertEqual(summary["database"]["integrity_check"], "ok")
        self.assertEqual(summary["database"]["foreign_key_violations"], 0)
        self.assertEqual(summary["database"]["row_counts"]["person"], 1)
        self.assertEqual(summary["media"]["files"], 1)
        self.assertNotIn(str(self.master), str(summary))
        self.assertEqual(private["root"], str(self.master.resolve()))

    def test_prepare_run_copies_only_database(self):
        dry_run = MODULE.prepare_run(
            self.master,
            self.state,
            "test-run",
            apply=False,
        )
        self.assertFalse(dry_run["baseline_exists"])
        self.assertFalse(self.state.exists())

        applied = MODULE.prepare_run(
            self.master,
            self.state,
            "test-run",
            apply=True,
        )
        self.assertEqual(applied["copy_scope"], "database-only")
        self.assertEqual(applied["integrity_check"], "ok")
        self.assertEqual(applied["foreign_key_violations"], 0)
        self.assertTrue(
            (self.state / "runs/test-run/database/MyDatabase.sqlite").is_file()
        )
        self.assertFalse((self.state / "runs/test-run/Source").exists())
        run_db = self.state / "runs/test-run/database/MyDatabase.sqlite"
        with closing(sqlite3.connect(run_db)) as connection:
            connection.execute("insert into person(id) values (101)")
            connection.commit()
        with closing(sqlite3.connect(run_db)) as connection:
            self.assertEqual(
                connection.execute("select count(*) from person").fetchone()[0],
                2,
            )
        MODULE.prepare_run(
            self.master,
            self.state,
            "test-run",
            apply=True,
        )
        with closing(sqlite3.connect(run_db)) as connection:
            self.assertEqual(
                connection.execute("select count(*) from person").fetchone()[0],
                1,
            )

    def test_state_root_inside_master_is_rejected(self):
        with self.assertRaises(MODULE.FixtureError):
            MODULE.prepare_run(
                self.master,
                self.master / "state",
                "test-run",
                apply=False,
            )

    def test_verify_detects_master_change(self):
        summary, private = MODULE.inventory(
            self.master,
            include_tree_fingerprint=True,
            sample_size=0,
        )
        self.assertIsNotNone(summary["tree"]["content_fingerprint"])
        manifest = self.root / "private.json"
        MODULE.write_private_manifest(manifest, private)
        self.assertTrue(MODULE.verify_manifest(manifest, full=True)["pass"])

        (self.master / "Source/100/sample.jpg").write_bytes(b"changed")
        result = MODULE.verify_manifest(manifest, full=True)
        self.assertFalse(result["pass"])
        self.assertFalse(result["checks"]["tree_content_fingerprint"])

    def test_os_metadata_is_excluded_from_cross_platform_fingerprint(self):
        before, _private = MODULE.inventory(
            self.master,
            include_tree_fingerprint=True,
            sample_size=0,
        )
        (self.master / ".DS_Store").write_bytes(b"local metadata")
        after, _private = MODULE.inventory(
            self.master,
            include_tree_fingerprint=True,
            sample_size=0,
        )
        self.assertEqual(
            before["tree"]["content_fingerprint"],
            after["tree"]["content_fingerprint"],
        )
        self.assertEqual(before["tree"]["files"], after["tree"]["files"])

    def test_extract_requires_checksum_and_rejects_unsafe_paths(self):
        archive = self.root / "fixture.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("fixture/database/file.txt", "safe")
        checksum = MODULE.sha256_file(archive)
        destination = self.root / "extracted"

        dry_run = MODULE.safe_extract_archive(
            archive,
            destination,
            expected_sha256=checksum,
            apply=False,
            strip_single_root=True,
        )
        self.assertTrue(dry_run["space_ok"])
        self.assertFalse(destination.exists())

        applied = MODULE.safe_extract_archive(
            archive,
            destination,
            expected_sha256=checksum,
            apply=True,
            strip_single_root=True,
        )
        self.assertTrue(applied["extracted"])
        self.assertEqual(
            (destination / "database/file.txt").read_text(encoding="utf-8"),
            "safe",
        )

        unsafe_archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(unsafe_archive, "w") as bundle:
            bundle.writestr("../outside.txt", "unsafe")
        with self.assertRaises(MODULE.FixtureError):
            MODULE.safe_extract_archive(
                unsafe_archive,
                self.root / "unsafe-output",
                expected_sha256=MODULE.sha256_file(unsafe_archive),
                apply=False,
                strip_single_root=True,
            )


if __name__ == "__main__":
    unittest.main()
