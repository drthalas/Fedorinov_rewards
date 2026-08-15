from __future__ import annotations

import json
import random
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.app.services import media_optimization
from backend.app.services.media_optimization import (
    COMPLETE_MARKER,
    INCOMPLETE_MARKER,
    ConversionPolicy,
    OptimizationError,
    build_optimized_copy,
)
from scripts.analyze_managed_media import run_analysis, sha256_file


class MediaOptimizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        for directory in ("Source/1", "default", "SourceMark", "GuideImages", "database"):
            (self.source / directory).mkdir(parents=True, exist_ok=True)
        self.database = self.source / "database" / "MyDatabase.sqlite"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(
                """
                pragma foreign_keys = on;
                create table person (
                    id integer primary key,
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
                    person_id integer references person(id),
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
                );
                create table mark (id integer primary key, front_foto text, back_foto text, book1_foto text, book2_foto text);
                """
            )
            connection.execute(
                "insert into person (id, person_foto, main_foto, rewards_foto) values (1, ?, ?, ?)",
                ("Source/1/photo.png", "Source/1/alpha.png", "Source/1/missing.png"),
            )
            connection.execute(
                "insert into rewards (id, person_id, front_foto) values (10, 1, ?)",
                ("Source/1/photo.png",),
            )
            connection.commit()
        photo = Image.frombytes("RGB", (512, 512), random.Random(391).randbytes(512 * 512 * 3))
        photo.save(self.source / "Source" / "1" / "photo.png", format="PNG")
        Image.new("RGBA", (512, 512), (100, 20, 30, 100)).save(
            self.source / "Source" / "1" / "alpha.png",
            format="PNG",
        )
        Image.new("RGB", (64, 64), "gray").save(self.source / "default" / "nofoto.jpg", format="JPEG")
        self.analysis = self.root / "analysis"
        run_analysis(self.source, self.database, self.analysis, estimate_sample_size=10)
        self.manifest = self.analysis / "media_manifest.jsonl"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_builds_separate_copy_updates_shared_references_and_passes_health(self) -> None:
        source_db_sha = sha256_file(self.database)
        source_photo_sha = sha256_file(self.source / "Source" / "1" / "photo.png")
        destination = self.root / "optimized"

        result = build_optimized_copy(self.source, self.database, self.manifest, destination)

        self.assertTrue(result.health_passed)
        self.assertEqual(result.converted, 1)
        self.assertEqual(result.repaired_missing_references, 1)
        self.assertTrue((destination / COMPLETE_MARKER).is_file())
        self.assertFalse((destination / INCOMPLETE_MARKER).exists())
        target_photo = destination / "Source" / "1" / "photo.jpg"
        with Image.open(target_photo) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (512, 512))
        manifest_records = [
            json.loads(line)
            for line in (destination / "conversion-manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        converted_record = next(item for item in manifest_records if item["status"] == "converted")
        self.assertEqual(converted_record["source_format"], "PNG")
        self.assertEqual(converted_record["target_format"], "JPEG")
        self.assertEqual(converted_record["source_width"], converted_record["target_width"])
        self.assertEqual(converted_record["source_height"], converted_record["target_height"])
        with closing(sqlite3.connect(destination / "database" / "MyDatabase.sqlite")) as connection:
            person = connection.execute("select person_foto, main_foto, rewards_foto from person").fetchone()
            reward = connection.execute("select front_foto from rewards").fetchone()
        self.assertEqual(person[0], "Source/1/photo.jpg")
        self.assertEqual(reward[0], "Source/1/photo.jpg")
        self.assertEqual(person[1], "Source/1/alpha.png")
        self.assertEqual(person[2], "default/nofoto.jpg")
        self.assertEqual(sha256_file(self.database), source_db_sha)
        self.assertEqual(sha256_file(self.source / "Source" / "1" / "photo.png"), source_photo_sha)

        repeated = build_optimized_copy(self.source, self.database, self.manifest, destination)
        self.assertEqual(repeated.as_dict(), result.as_dict())

    def test_interruption_marks_incomplete_and_restart_is_safe(self) -> None:
        destination = self.root / "interrupted"
        with self.assertRaises(InterruptedError):
            build_optimized_copy(
                self.source,
                self.database,
                self.manifest,
                destination,
                interrupt_after=1,
            )
        self.assertTrue((destination / INCOMPLETE_MARKER).is_file())
        status = json.loads((destination / "optimization-status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "incomplete")
        with self.assertRaisesRegex(OptimizationError, "incomplete"):
            build_optimized_copy(self.source, self.database, self.manifest, destination)

        result = build_optimized_copy(
            self.source,
            self.database,
            self.manifest,
            destination,
            restart_incomplete=True,
        )
        self.assertTrue(result.health_passed)

    def test_destination_inside_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(OptimizationError, "outside"):
            build_optimized_copy(
                self.source,
                self.database,
                self.manifest,
                self.source / "optimized",
                ConversionPolicy(),
            )

    def test_status_write_retries_transient_windows_replace_denial(self) -> None:
        destination = self.root / "optimization-status.json"
        real_replace = media_optimization.os.replace
        attempts = 0

        def replace_with_transient_denial(source: Path, target: Path) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError(5, "Access is denied", str(target))
            real_replace(source, target)

        with patch.object(media_optimization.os, "replace", side_effect=replace_with_transient_denial):
            media_optimization._write_json(destination, {"state": "running"})

        self.assertEqual(attempts, 3)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"state": "running"})
        self.assertEqual(list(self.root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
