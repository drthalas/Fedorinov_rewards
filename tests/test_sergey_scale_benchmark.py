from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.generate_sergey_scale_benchmark import (
    DEFAULT_SEED,
    PERSON_COUNT,
    REWARD_COUNT,
    generate_profile,
)
from scripts.run_sergey_scale_benchmark import route_specs


ROOT = Path(__file__).resolve().parents[1]


class SergeyScaleGeneratorTests(unittest.TestCase):
    def test_count_matched_profile_is_exact_healthy_and_deterministic(self) -> None:
        with TemporaryDirectory(prefix="ale302-generator-") as parent:
            first_root = Path(parent) / "first"
            second_root = Path(parent) / "second"
            first = generate_profile("sergey-count-matched", first_root)
            second = generate_profile("sergey-count-matched", second_root)

            self.assertEqual(first["seed"], DEFAULT_SEED)
            self.assertEqual(first["persons"], PERSON_COUNT)
            self.assertEqual(first["rewards"], REWARD_COUNT)
            self.assertEqual(first["integrity_check"], "ok")
            self.assertEqual(first["foreign_key_violations"], 0)
            self.assertFalse(any(first["relationship_health"].values()))
            self.assertEqual(first["db_sha256"], second["db_sha256"])
            self.assertEqual(first["tree_fingerprint"], second["tree_fingerprint"])
            self.assertEqual(first["reward_distribution"], second["reward_distribution"])
            self.assertEqual(first["heavy_persons"], second["heavy_persons"])

            saved = json.loads((first_root / "benchmark_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["persons"], PERSON_COUNT)
            self.assertEqual(saved["rewards"], REWARD_COUNT)

    def test_stress_profile_contains_heavy_shared_missing_windows_and_cyrillic_paths(self) -> None:
        with TemporaryDirectory(prefix="ale302-generator-") as parent:
            root = Path(parent) / "stress"
            manifest = generate_profile("sergey-stress", root)
            db_path = root / "database/MyDatabase.sqlite"
            with closing(sqlite3.connect(db_path)) as connection:
                heavy_id = int(manifest["fixture_ids"]["heavy_person"])
                heavy_rewards = int(
                    connection.execute(
                        "select count(*) from rewards where person_id = ?",
                        (heavy_id,),
                    ).fetchone()[0]
                )
                shared_references = int(
                    connection.execute(
                        """
                        select count(*) from (
                            select person_foto as path from person
                            union all select file_path from person_media
                            union all select front_foto from rewards
                        ) where path = 'Source/benchmark-shared/shared.png'
                        """
                    ).fetchone()[0]
                )
                missing_paths = int(
                    connection.execute(
                        "select count(*) from rewards where front_foto like '%missing%' or front_foto like '%награда-%'"
                    ).fetchone()[0]
                )
                windows_paths = int(
                    connection.execute(
                        "select count(*) from rewards where instr(front_foto, '\\') > 0"
                    ).fetchone()[0]
                )

            self.assertGreaterEqual(heavy_rewards, 1_000)
            self.assertGreater(shared_references, 1)
            self.assertGreater(missing_paths, 1_000)
            self.assertGreater(windows_paths, 0)
            self.assertTrue((root / "Source/benchmark-shared/shared.png").is_file())
            self.assertGreater(manifest["media_files"], 0)

    def test_generator_rejects_non_temp_output(self) -> None:
        unsafe_root = Path(__file__).resolve().parents[1] / "generated-sergey-scale"
        with self.assertRaisesRegex(ValueError, "unique child"):
            generate_profile("sergey-count-matched", unsafe_root)

    def test_route_inventory_covers_required_surfaces(self) -> None:
        manifest = {
            "fixture_ids": {
                "zero_person": 1,
                "ordinary_person": 2,
                "many_person": 3,
                "heavy_person": 4,
                "ordinary_reward": 10,
                "heavy_reward": 11,
                "mark": 20,
            }
        }
        names = {name for name, _ in route_specs(manifest)}
        self.assertTrue(
            {
                "main",
                "person_zero",
                "person_ordinary",
                "person_heavy",
                "person_delete_preflight",
                "reward_delete_preflight",
                "mark_delete_preflight",
                "guides",
                "guides_selected",
                "guide_form",
                "reward_form_cascade",
                "search_initial",
                "search_exact",
                "search_contains",
                "marks",
                "summary",
            }.issubset(names)
        )

    def test_route_probe_reports_sql_filesystem_and_response_metrics(self) -> None:
        with TemporaryDirectory(prefix="ale302-probe-") as parent:
            data_root = Path(parent) / "data"
            generate_profile("sergey-count-matched", data_root)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/sergey_scale_route_probe.py"),
                    "--app-root",
                    str(ROOT),
                    "--data-root",
                    str(data_root),
                    "--route-name",
                    "person_detail",
                    "--path",
                    "/persons/2",
                    "--warm-runs",
                    "1",
                    "--timeout",
                    "10",
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
                timeout=30,
            )
            result = json.loads(completed.stdout)
            self.assertEqual(result["cold"]["status"], 200)
            self.assertGreater(result["cold"]["response_bytes"], 0)
            self.assertGreater(result["cold"]["sql_counts"]["SELECT"], 0)
            self.assertIn("filesystem_counts", result["cold"])
            self.assertEqual(result["aggregate"]["successful_warm_runs"], 1)


if __name__ == "__main__":
    unittest.main()
