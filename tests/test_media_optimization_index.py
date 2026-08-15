from __future__ import annotations

import os
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from PIL import Image

from backend.app.services.media_optimization_index import (
    build_index_from_manifest,
    run_incremental_index,
)
from scripts.analyze_managed_media import run_analysis, sha256_file
from tests.image_fixtures import JPEG_BYTES, PNG_BYTES, image_bytes


class MediaOptimizationIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        for name in ("Source/1", "SourceMark", "default", "GuideImages", "database"):
            (self.data / name).mkdir(parents=True, exist_ok=True)
        (self.data / "Source/1/person.jpg").write_bytes(JPEG_BYTES)
        (self.data / "Source/1/document.png").write_bytes(PNG_BYTES)
        (self.data / "default/nofoto.jpg").write_bytes(JPEG_BYTES)
        self.database = self.data / "database/MyDatabase.sqlite"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "create table person (id integer primary key, person_foto text, main_foto text, "
                "rewards_foto text, book1_foto text, book2_foto text, card1_foto text, card2_foto text)"
            )
            connection.execute(
                "insert into person(id, person_foto, book1_foto) values (1, ?, ?)",
                ("Source/1/person.jpg", "Source/1/document.png"),
            )
            connection.commit()
        self.analysis = self.root / "analysis"
        run_analysis(self.data, self.database, self.analysis, estimate_sample_size=10)
        self.index = self.root / "state/optimization-index.sqlite"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_baseline_and_zero_change_do_not_decode_files(self) -> None:
        baseline = build_index_from_manifest(
            self.data,
            self.analysis / "media_manifest.jsonl",
            self.index,
        )
        self.assertEqual(baseline.indexed, 3)
        self.assertEqual(baseline.decoded, 0)

        decoded: list[Path] = []
        repeated = run_incremental_index(
            self.data,
            self.index,
            database=self.database,
            decoded_hook=decoded.append,
        )
        self.assertEqual(repeated.decoded, 0)
        self.assertEqual(repeated.unchanged, 3)
        self.assertEqual(decoded, [])

    def test_baseline_bootstraps_optimized_destination_from_conversion_manifest(self) -> None:
        destination = self.root / "optimized"
        for source in (self.data / "Source/1/person.jpg", self.data / "default/nofoto.jpg"):
            target = destination / source.relative_to(self.data)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        converted_target = destination / "Source/1/document.jpg"
        converted_target.parent.mkdir(parents=True, exist_ok=True)
        converted_target.write_bytes(JPEG_BYTES)
        analysis_records = [
            json.loads(line)
            for line in (self.analysis / "media_manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        conversion_manifest = self.root / "conversion-manifest.jsonl"
        with conversion_manifest.open("w", encoding="utf-8") as handle:
            for record in analysis_records:
                old_path = str(record["relative_path"])
                converted = old_path.endswith("document.png")
                new_path = "Source/1/document.jpg" if converted else old_path
                target = destination / new_path
                handle.write(
                    json.dumps(
                        {
                            "old_path": old_path,
                            "new_path": new_path,
                            "status": "converted" if converted else "kept",
                            "target_format": "JPEG" if converted else record["actual_format"],
                            "target_bytes": target.stat().st_size,
                            "target_sha256": sha256_file(target),
                            "saved_bytes": int(record["source_bytes"]) - target.stat().st_size if converted else 0,
                        }
                    )
                    + "\n"
                )

        result = build_index_from_manifest(
            destination,
            self.analysis / "media_manifest.jsonl",
            self.index,
            conversion_manifest=conversion_manifest,
        )

        self.assertEqual(result.decoded, 0)
        with closing(sqlite3.connect(self.index)) as connection:
            row = connection.execute(
                "select actual_format, converted_target from media_objects where identity = ?",
                ("source/1/document.jpg",),
            ).fetchone()
        self.assertEqual(row, ("JPEG", "Source/1/document.jpg"))

    def test_delta_detects_new_changed_same_name_and_rename(self) -> None:
        build_index_from_manifest(self.data, self.analysis / "media_manifest.jsonl", self.index)
        changed = self.data / "Source/1/person.jpg"
        changed.write_bytes(image_bytes("JPEG", size=(30, 30)))
        stat = changed.stat()
        os.utime(changed, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
        new_path = self.data / "Source/1/new.png"
        Image.effect_noise((300, 300), 90).convert("RGB").save(new_path, format="PNG")
        renamed = self.data / "Source/1/document-renamed.png"
        (self.data / "Source/1/document.png").replace(renamed)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "update person set book1_foto = ? where id = 1",
                ("Source/1/document-renamed.png",),
            )
            connection.commit()
        database_sha = sha256_file(self.database)

        decoded: list[Path] = []
        result = run_incremental_index(
            self.data,
            self.index,
            database=self.database,
            decoded_hook=decoded.append,
        )

        self.assertEqual(result.new, 2)
        self.assertEqual(result.changed, 1)
        self.assertEqual(result.missing, 1)
        self.assertEqual(result.renamed, 1)
        self.assertEqual(result.decoded, 3)
        self.assertEqual({path.name for path in decoded}, {"person.jpg", "new.png", "document-renamed.png"})
        self.assertEqual(sha256_file(self.database), database_sha)
        with closing(sqlite3.connect(self.index)) as connection:
            row = connection.execute(
                "select renamed_from from media_objects where identity = ?",
                ("source/1/document-renamed.png",),
            ).fetchone()
        self.assertEqual(row[0], "source/1/document.png")

    def test_interruption_resumes_without_redecoding_completed_delta(self) -> None:
        build_index_from_manifest(self.data, self.analysis / "media_manifest.jsonl", self.index)
        first = self.data / "Source/1/person.jpg"
        second = self.data / "Source/1/document.png"
        first.write_bytes(image_bytes("JPEG", size=(31, 31)))
        second.write_bytes(image_bytes("PNG", size=(31, 31)))
        for offset, path in enumerate((first, second), start=1):
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + offset * 2_000_000_000))

        first_pass: list[Path] = []
        with self.assertRaises(InterruptedError):
            run_incremental_index(
                self.data,
                self.index,
                interrupt_after=1,
                decoded_hook=first_pass.append,
            )
        second_pass: list[Path] = []
        resumed = run_incremental_index(self.data, self.index, decoded_hook=second_pass.append)
        self.assertEqual(len(first_pass), 1)
        self.assertEqual(resumed.decoded, 1)
        self.assertEqual(len(second_pass), 1)
        repeated = run_incremental_index(self.data, self.index)
        self.assertEqual(repeated.decoded, 0)

    def test_policy_change_invalidates_controlled_current_set(self) -> None:
        build_index_from_manifest(self.data, self.analysis / "media_manifest.jsonl", self.index)
        result = run_incremental_index(self.data, self.index, policy_version="test-policy-v2")
        self.assertEqual(result.policy_invalidated, 3)
        self.assertEqual(result.decoded, 3)
        repeated = run_incremental_index(self.data, self.index, policy_version="test-policy-v2")
        self.assertEqual(repeated.decoded, 0)


if __name__ == "__main__":
    unittest.main()
