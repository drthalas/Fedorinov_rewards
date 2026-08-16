from __future__ import annotations

import json
import random
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.app.config import Settings, _active_optimized_workspace
from backend.app.services import media_optimization_workflow as workflow
from backend.app.services.media_optimization import build_optimized_copy
from scripts.analyze_managed_media import inventory_files, metadata_fingerprint, sha256_file
from tests.image_fixtures import JPEG_BYTES


class MediaOptimizationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        for name in ("Source/1", "SourceMark", "default", "GuideImages", "database"):
            (self.source / name).mkdir(parents=True, exist_ok=True)
        self.database = self.source / "database/MyDatabase.sqlite"
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
                    person_id integer references person(id),
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
                );
                create table mark (
                    id integer primary key,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text
                );
                """
            )
            connection.execute(
                "insert into person(id, person_foto) values (1, ?)",
                ("Source/1/photo.png",),
            )
            connection.commit()
        Image.frombytes("RGB", (320, 320), random.Random(393).randbytes(320 * 320 * 3)).save(
            self.source / "Source/1/photo.png",
            format="PNG",
        )
        (self.source / "default/nofoto.jpg").write_bytes(JPEG_BYTES)
        self.state = self.root / "state"
        self.target = self.root / "optimized"
        self.settings = Settings(
            rewards_data_dir=self.source,
            rewards_db_path=self.database,
            configured_rewards_data_dir=self.source,
            media_optimization_state_dir=self.state,
            media_optimization_target_dir=self.target,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_baseline_copy_report_activation_and_zero_delta_share_service_results(self) -> None:
        source_db_sha = sha256_file(self.database)
        source_media = metadata_fingerprint(inventory_files(self.source))

        baseline = workflow.run_check(self.settings)
        self.assertEqual(baseline["mode"], "baseline")
        self.assertEqual(baseline["decoded"], 0)
        result = workflow.run_optimize(self.settings)
        snapshot = workflow.workflow_snapshot(self.settings)

        self.assertTrue(snapshot["target_complete"])
        self.assertTrue(snapshot["health_passed"])
        self.assertEqual(snapshot["source_bytes"], result["source_bytes"])
        self.assertEqual(snapshot["target_bytes"], result["destination_bytes"])
        self.assertEqual(snapshot["actual_saved_bytes"], result["saved_bytes"])
        self.assertEqual(snapshot["converted_files"], result["converted"])
        self.assertEqual(snapshot["error_files"], result["errors"])
        self.assertEqual(sha256_file(self.database), source_db_sha)
        self.assertEqual(metadata_fingerprint(inventory_files(self.source)), source_media)

        with self.assertRaisesRegex(workflow.MediaOptimizationWorkflowError, "Сначала откройте"):
            workflow.activate_optimized_workspace(self.settings)
        workflow.preview_optimized_workspace(self.settings)
        self.assertEqual(
            _active_optimized_workspace(self.state, self.source, self.target),
            self.target.resolve(),
        )
        pointer = json.loads((self.state / workflow.ACTIVE_WORKSPACE).read_text(encoding="utf-8"))
        self.assertEqual(pointer["mode"], "preview")
        workflow.activate_optimized_workspace(self.settings)
        pointer = json.loads((self.state / workflow.ACTIVE_WORKSPACE).read_text(encoding="utf-8"))
        self.assertEqual(pointer["mode"], "optimized")
        optimized_settings = self.settings.model_copy(
            update={
                "rewards_data_dir": self.target,
                "rewards_db_path": self.target / "database/MyDatabase.sqlite",
            }
        )
        delta = workflow.run_check(optimized_settings)
        self.assertEqual(delta["mode"], "delta")
        self.assertEqual(delta["decoded"], 0)
        self.assertEqual(delta["unchanged"], len(inventory_files(self.target)))

        removed = self.target / "default/nofoto.jpg"
        removed.unlink()
        delta = workflow.run_check(optimized_settings)
        self.assertEqual(delta["missing"], 1)
        current_bytes = sum(item.size for item in inventory_files(self.target))
        self.assertEqual(workflow.workflow_snapshot(optimized_settings)["current_bytes"], current_bytes)

        with self.assertRaisesRegex(workflow.MediaOptimizationWorkflowError, "Подтвердите возврат"):
            workflow.activate_source_workspace(optimized_settings)
        workflow.activate_source_workspace(optimized_settings, confirm_snapshot_rollback=True)
        self.assertEqual(_active_optimized_workspace(self.state, self.source, self.target), self.source)

    def test_incomplete_copy_cannot_activate_and_can_restart_safely(self) -> None:
        workflow.run_check(self.settings)
        with self.assertRaises(InterruptedError):
            build_optimized_copy(
                self.source,
                self.database,
                self.state / "baseline/media_manifest.jsonl",
                self.target,
                interrupt_after=1,
            )
        snapshot = workflow.workflow_snapshot(self.settings)
        self.assertTrue(snapshot["target_incomplete"])
        self.assertFalse(snapshot["resume_available"])
        self.assertTrue(snapshot["restart_available"])
        self.assertFalse(snapshot["can_activate"])
        with self.assertRaisesRegex(workflow.MediaOptimizationWorkflowError, "не прошла"):
            workflow.activate_optimized_workspace(self.settings)

        result = workflow.run_optimize(self.settings, restart_incomplete=True)
        self.assertTrue(result["health_passed"])
        self.assertTrue(workflow.workflow_snapshot(self.settings)["can_preview"])
        self.assertFalse(workflow.workflow_snapshot(self.settings)["can_activate"])

    def test_incremental_mode_converts_only_detected_delta_and_is_idempotent(self) -> None:
        workflow.run_check(self.settings)
        workflow.run_optimize(self.settings)
        workflow.preview_optimized_workspace(self.settings)
        workflow.activate_optimized_workspace(self.settings)
        optimized = self.settings.model_copy(
            update={
                "rewards_data_dir": self.target,
                "rewards_db_path": self.target / "database/MyDatabase.sqlite",
            }
        )
        delta = self.target / "Source/1/delta.png"
        Image.frombytes("RGB", (320, 320), random.Random(397).randbytes(320 * 320 * 3)).save(delta, format="PNG")
        with closing(sqlite3.connect(optimized.rewards_db_path)) as connection:
            connection.execute("update person set main_foto = ? where id = 1", ("Source/1/delta.png",))
            connection.commit()

        checked = workflow.run_check(optimized)
        self.assertEqual(checked["new"], 1)
        self.assertEqual(workflow.workflow_snapshot(optimized)["incremental_candidate_files"], 1)
        result = workflow.run_incremental_optimize(optimized)
        self.assertEqual(result["converted"], 1)
        self.assertFalse(delta.exists())
        self.assertTrue((self.target / "Source/1/delta.jpg").is_file())
        with closing(sqlite3.connect(optimized.rewards_db_path)) as connection:
            reference = connection.execute("select main_foto from person where id = 1").fetchone()[0]
        self.assertEqual(reference, "Source/1/delta.jpg")
        self.assertEqual(workflow.run_check(optimized)["decoded"], 0)
        self.assertEqual(workflow.workflow_snapshot(optimized)["incremental_candidate_files"], 0)
        self.assertTrue((self.source / "Source/1/photo.png").is_file())

    def test_interrupted_operation_state_is_recoverable(self) -> None:
        self.state.mkdir(parents=True)
        (self.state / workflow.OPERATION_STATUS).write_text(
            json.dumps({"state": "running", "operation": "check", "percent": 45}),
            encoding="utf-8",
        )
        snapshot = workflow.workflow_snapshot(self.settings)
        self.assertEqual(snapshot["operation"]["state"], "interrupted")
        self.assertFalse(snapshot["resume_available"])
        self.assertFalse(snapshot["restart_available"])
        self.assertIn("заново", snapshot["operation"]["message"])

    def test_physical_legacy_marker_permission_error_becomes_actionable_retry(self) -> None:
        self.state.mkdir(parents=True)
        (self.state / workflow.OPERATION_STATUS).write_text(
            json.dumps(
                {
                    "state": "error",
                    "operation": "optimize",
                    "error_type": "PermissionError",
                    "message": "[Errno 13] Permission denied: 'C:/fixture/master-optimized/.optimization-incomplete'",
                }
            ),
            encoding="utf-8",
        )

        snapshot = workflow.workflow_snapshot(self.settings)

        self.assertEqual(snapshot["operation"]["error_code"], "target_not_writable")
        self.assertIn("доступное расположение", snapshot["operation"]["message"])
        self.assertTrue(snapshot["retry_available"])
        self.assertFalse(snapshot["restart_available"])
        self.assertFalse(snapshot["resume_available"])

    def test_optimize_uses_configured_working_database_when_media_root_database_differs(self) -> None:
        working_database = self.root / "working-state/database/MyDatabase.sqlite"
        working_database.parent.mkdir(parents=True)
        working_database.write_bytes(self.database.read_bytes())
        with closing(sqlite3.connect(working_database)) as connection:
            connection.execute("insert into person(id, person_foto) values (2, null)")
            connection.commit()
        split_settings = self.settings.model_copy(update={"rewards_db_path": working_database})

        workflow.run_check(split_settings)
        workflow.run_optimize(split_settings)

        with closing(sqlite3.connect(self.target / "database/MyDatabase.sqlite")) as connection:
            optimized_count = int(connection.execute("select count(*) from person").fetchone()[0])
        with closing(sqlite3.connect(self.database)) as connection:
            root_count = int(connection.execute("select count(*) from person").fetchone()[0])
        self.assertEqual(optimized_count, 2)
        self.assertEqual(root_count, 1)

    def test_state_write_retries_transient_windows_replace_denial(self) -> None:
        destination = self.state / workflow.OPERATION_STATUS
        real_replace = workflow.os.replace
        attempts = 0

        def replace_with_transient_denial(source: Path, target: Path) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError(5, "Access is denied", str(target))
            real_replace(source, target)

        with patch.object(workflow.os, "replace", side_effect=replace_with_transient_denial):
            workflow._write_json(destination, {"state": "complete"})

        self.assertEqual(attempts, 3)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"state": "complete"})
        self.assertEqual(list(self.state.glob("*.tmp")), [])

    def test_same_volume_space_estimate_counts_new_jpeg_bytes_not_hardlinks(self) -> None:
        analysis = {
            "records": {"classifications": {"jpeg_candidate": {"bytes": 1_000_000_000}}},
            "quality_forecasts": {"90": {"predicted_saved_bytes": 800_000_000}},
        }
        with patch.object(workflow, "_same_filesystem", return_value=True):
            required, strategy = workflow._estimated_required_bytes(
                analysis,
                self.source,
                self.target,
                2_000_000_000,
            )
        self.assertEqual(required, 200_000_000 + 128 * 1024 * 1024)
        self.assertEqual(strategy, "same-volume-hardlinks")

    def test_cross_volume_space_estimate_requires_full_logical_copy(self) -> None:
        analysis = {
            "records": {"classifications": {"jpeg_candidate": {"bytes": 1_000_000_000}}},
            "quality_forecasts": {"90": {"predicted_saved_bytes": 800_000_000}},
        }
        with patch.object(workflow, "_same_filesystem", return_value=False):
            required, strategy = workflow._estimated_required_bytes(
                analysis,
                self.source,
                self.target,
                2_000_000_000,
            )
        self.assertEqual(required, 2_000_000_000)
        self.assertEqual(strategy, "full-copy")

    def test_space_budget_adds_ten_percent_and_exact_threshold_passes(self) -> None:
        analysis_dir = self.state / workflow.ANALYSIS_DIR
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "summary.json").write_text(
            json.dumps(
                {
                    "records": {"classifications": {"jpeg_candidate": {"bytes": 1_000_000_000}}},
                    "quality_forecasts": {
                        "90": {
                            "predicted_total_bytes": 2_000_000_000,
                            "predicted_saved_bytes": 800_000_000,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        additional = 200_000_000 + 128 * 1024 * 1024
        required = additional + (additional * 10 + 99) // 100
        with (
            patch.object(workflow, "_same_filesystem", return_value=True),
            patch.object(workflow, "_available_bytes", return_value=required),
        ):
            budget = workflow._optimization_space_budget(self.settings)
        self.assertEqual(budget["estimated_additional_bytes"], additional)
        self.assertEqual(budget["safety_reserve_bytes"], (additional * 10 + 99) // 100)
        self.assertEqual(budget["required_free_space_bytes"], required)
        self.assertTrue(budget["space_ok"])
        workflow._require_optimization_space(budget)

    def test_insufficient_space_is_rejected_before_target_creation(self) -> None:
        workflow.run_check(self.settings)
        with patch.object(workflow, "_available_bytes", return_value=1):
            with self.assertRaises(workflow.MediaOptimizationInsufficientSpaceError):
                workflow.start_optimize(self.settings)
        self.assertFalse(self.target.exists())
        self.assertFalse(workflow.workflow_snapshot(self.settings)["running"])

    def test_running_space_guard_stops_when_reserve_is_crossed(self) -> None:
        with patch.object(workflow, "_available_bytes", side_effect=[1_000, 99]):
            guard = workflow._migration_space_guard(self.settings, 100)
            guard(0, 1_000)
            with self.assertRaises(workflow.MediaOptimizationInsufficientSpaceError):
                guard(workflow.SPACE_GUARD_INTERVAL, 1_000)

    def test_background_error_and_cancel_finish_the_lifecycle(self) -> None:
        with patch.object(
            workflow,
            "run_check",
            side_effect=workflow.OptimizationTargetNotWritableError("denied"),
        ):
            workflow.start_check(self.settings)
            self._wait_for_state("error")
        status = json.loads((self.state / workflow.OPERATION_STATUS).read_text(encoding="utf-8"))
        self.assertEqual(status["error_type"], "OptimizationTargetNotWritableError")
        self.assertEqual(status["error_code"], "target_not_writable")
        self.assertIn("защищена от записи", status["message"])

        def wait_until_cancelled(settings: Settings) -> dict[str, object]:
            while not workflow._is_cancelled(settings):
                time.sleep(0.005)
            raise InterruptedError("cancelled")

        with patch.object(workflow, "run_check", side_effect=wait_until_cancelled):
            workflow.start_check(self.settings)
            self.assertTrue(workflow.cancel_operation(self.settings))
            self._wait_for_state("cancelled")
        self.assertFalse(workflow.workflow_snapshot(self.settings)["running"])

    def test_active_pointer_accepts_only_configured_verified_target(self) -> None:
        self.state.mkdir(parents=True)
        other = self.root / "other"
        (other / "database").mkdir(parents=True)
        (other / "database/MyDatabase.sqlite").write_bytes(b"not used")
        (other / ".optimization-complete").write_text("complete\n", encoding="ascii")
        (self.state / workflow.ACTIVE_WORKSPACE).write_text(
            json.dumps({"workspace": str(other)}),
            encoding="utf-8",
        )
        self.assertEqual(
            _active_optimized_workspace(self.state, self.source, self.target),
            self.source,
        )

        (self.target / "database").mkdir(parents=True)
        (self.target / "database/MyDatabase.sqlite").write_bytes(b"not used")
        (self.target / ".optimization-complete").write_text("complete\n", encoding="ascii")
        (self.state / workflow.ACTIVE_WORKSPACE).write_text(
            json.dumps({"workspace": str(self.target)}),
            encoding="utf-8",
        )
        self.assertEqual(_active_optimized_workspace(self.state, self.source, self.target), self.source)
        (self.target / "health-report.json").write_text(
            json.dumps({"passed": True}),
            encoding="utf-8",
        )
        self.assertEqual(
            _active_optimized_workspace(self.state, self.source, self.target),
            self.target.resolve(),
        )

    def _wait_for_state(self, state: str) -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                payload = json.loads((self.state / workflow.OPERATION_STATUS).read_text(encoding="utf-8"))
            except OSError:
                time.sleep(0.005)
                continue
            if payload.get("state") == state:
                return
            time.sleep(0.005)
        self.fail(f"operation did not reach {state}")


if __name__ == "__main__":
    unittest.main()
