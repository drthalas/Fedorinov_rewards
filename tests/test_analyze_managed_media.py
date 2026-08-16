from __future__ import annotations

import json
import random
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from PIL import Image

from scripts.analyze_managed_media import extension_matches, run_analysis


class ManagedMediaAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "fixture"
        self.output = self.root / "output"
        for name in ("Source", "SourceMark", "default", "GuideImages"):
            (self.data / name).mkdir(parents=True)
        self.database = self.root / "MyDatabase.sqlite"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(
                """
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
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
                );
                create table guide (id integer primary key, image_path text);
                """
            )
            connection.execute(
                "insert into person (id, person_foto, main_foto, rewards_foto) values (1, ?, ?, ?)",
                ("Source/opaque.jpg", "Source/alpha.png", "Source/missing.png"),
            )
            connection.execute(
                "insert into rewards (id, front_foto) values (1, ?)",
                (r"C:\fixture\Source\photo.jpeg",),
            )
            connection.commit()

        opaque = Image.frombytes("RGB", (512, 512), random.Random(390).randbytes(512 * 512 * 3))
        opaque.save(self.data / "Source" / "opaque.jpg", format="PNG")
        alpha = Image.new("RGBA", (512, 512), (120, 30, 20, 120))
        alpha.save(self.data / "Source" / "alpha.png", format="PNG")
        opaque_alpha = opaque.convert("RGBA")
        opaque_alpha.putalpha(255)
        opaque_alpha.save(self.data / "Source" / "opaque-alpha.png", format="PNG")
        opaque.save(self.data / "Source" / "photo.jpeg", format="JPEG", quality=90)
        (self.data / "Source" / "broken.png").write_bytes(b"not an image")
        (self.data / "Source" / "notes.docx").write_bytes(b"document")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def source_snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.data).as_posix(): path.read_bytes()
            for path in self.data.rglob("*")
            if path.is_file()
        }

    def test_read_only_inventory_classification_and_forecast(self) -> None:
        before = self.source_snapshot()
        database_before = self.database.read_bytes()

        summary = run_analysis(
            self.data,
            self.database,
            self.output,
            qualities=(88, 90, 92),
            estimate_sample_size=10,
        )

        self.assertEqual(self.source_snapshot(), before)
        self.assertEqual(self.database.read_bytes(), database_before)
        self.assertTrue(summary["safety"]["database_unchanged"])
        self.assertTrue(summary["safety"]["media_metadata_unchanged"])
        self.assertEqual(summary["safety"]["source_write_operations"], 0)
        self.assertEqual(summary["records"]["actual_formats"]["PNG"]["files"], 3)
        self.assertEqual(summary["records"]["actual_formats"]["JPEG"]["files"], 1)
        self.assertEqual(summary["records"]["mismatched_extension_content_files"], 1)
        self.assertEqual(summary["records"]["corrupt_or_unsupported_files"], 1)
        self.assertEqual(summary["records"]["classifications"]["jpeg_candidate"]["files"], 2)
        self.assertEqual(summary["records"]["classifications"]["keep_lossless_alpha"]["files"], 1)
        self.assertEqual(summary["records"]["png_alpha"]["actual_transparency_files"], 1)
        self.assertEqual(summary["records"]["png_alpha"]["opaque_alpha_channel_files"], 1)
        self.assertEqual(summary["references"]["missing_reference_occurrences"], 1)
        self.assertEqual(summary["quality_forecasts"]["90"]["eligible_candidate_count"], 2)
        self.assertTrue((self.output / "media_manifest.jsonl").is_file())
        self.assertTrue((self.output / "summary.json").is_file())
        self.assertTrue((self.output / "summary.md").is_file())

    def test_corrupt_file_does_not_abort_and_repeat_is_deterministic(self) -> None:
        first = run_analysis(self.data, self.database, self.output / "first", estimate_sample_size=2)
        second = run_analysis(self.data, self.database, self.output / "second", estimate_sample_size=2)

        self.assertEqual(first["classification_digest"], second["classification_digest"])
        first_manifest = (self.output / "first" / "media_manifest.jsonl").read_text(encoding="utf-8")
        second_manifest = (self.output / "second" / "media_manifest.jsonl").read_text(encoding="utf-8")
        self.assertEqual(first_manifest, second_manifest)
        records = [json.loads(line) for line in first_manifest.splitlines()]
        broken = next(record for record in records if record["relative_path"].endswith("broken.png"))
        self.assertEqual(broken["decode_status"], "corrupt_or_unsupported")

    def test_output_inside_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be inside"):
            run_analysis(self.data, self.database, self.data / "report")

    def test_mpo_is_a_jpeg_extension_family_match(self) -> None:
        self.assertTrue(extension_matches("MPO", ".jpg"))


if __name__ == "__main__":
    unittest.main()
