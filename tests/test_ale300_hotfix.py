from __future__ import annotations

import base64
from contextlib import closing
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from backend.app.config import Settings
from backend.app.routers import delete_preflight as delete_preflight_router
from backend.app.services.delete_preflight import reset_delete_preflight_registry
from backend.app.services.media_lifecycle import (
    MediaReferenceExclusion,
    managed_image_reference_counts_in_connection,
)
from scripts import build_windows_preview_package


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "backend/app/static/assets/cavaliers/cavaliers-empty-state-awards-optimized.jpg"


class Ale300BackgroundTests(unittest.TestCase):
    def test_optimized_artwork_is_browser_safe_and_has_a_visual_fallback(self) -> None:
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")
        encoded_length = len(base64.b64encode(ASSET.read_bytes()))

        with Image.open(ASSET) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (1844, 853))
            image.verify()

        self.assertLess(encoded_length, build_windows_preview_package.MAX_EMBEDDED_ASSET_TOKEN_CHARS)
        empty_state = styles.split(".legacy-rewards-theme .legacy-cavalier-empty-state {", 1)[1].split("}", 1)[0]
        self.assertEqual(empty_state.count("background-image:"), 2)
        self.assertIn("radial-gradient", empty_state)
        self.assertIn("linear-gradient", empty_state)
        self.assertIn("cavaliers-empty-state-awards-optimized.jpg", empty_state)
        self.assertNotIn("cavaliers-empty-state-awards.png", empty_state)

    def test_packaged_background_declaration_stays_below_token_budget(self) -> None:
        with TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "FedorinovRewards_WebPreview"
            styles_path = package_root / "backend/app/static/styles.css"
            styles_path.parent.mkdir(parents=True)
            styles_path.write_text(
                (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            with patch.object(build_windows_preview_package, "PACKAGE_ROOT", package_root):
                build_windows_preview_package._embed_ui_assets()

            packaged = styles_path.read_text(encoding="utf-8")
            variable = build_windows_preview_package._asset_variable(ASSET.relative_to(ROOT))
            match = re.search(
                rf'{re.escape(variable)}: url\("data:image/jpeg;base64,([^\"]+)"\)',
                packaged,
            )
            self.assertIsNotNone(match)
            token = match.group(1)
            self.assertLess(len(token), build_windows_preview_package.MAX_EMBEDDED_ASSET_TOKEN_CHARS)
            self.assertEqual(base64.b64decode(token), ASSET.read_bytes())
            self.assertIn(f"var({variable}, none)", packaged)

    def test_packager_rejects_an_oversized_embedded_token(self) -> None:
        with TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir) / "FedorinovRewards_WebPreview"
            styles_path = package_root / "backend/app/static/styles.css"
            styles_path.parent.mkdir(parents=True)
            styles_path.write_text(
                (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            with patch.object(build_windows_preview_package, "PACKAGE_ROOT", package_root), patch.object(
                build_windows_preview_package, "MAX_EMBEDDED_ASSET_TOKEN_CHARS", 10
            ), self.assertRaisesRegex(RuntimeError, "browser-safe CSS token budget"):
                build_windows_preview_package._embed_ui_assets()


class Ale300DeletePreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database/MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self.settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
            require_backup_before_write=False,
            require_backup_before_dangerous_actions=False,
        )
        self._create_db()
        reset_delete_preflight_registry()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executescript(
                """
                create table person (
                    id integer primary key, fio text, id_rank integer,
                    person_foto text, main_foto text, rewards_foto text,
                    book1_foto text, book2_foto text, card1_foto text, card2_foto text
                );
                create table rewards (
                    id integer primary key, person_id integer,
                    front_foto text, back_foto text, book1_foto text, book2_foto text, reward_list text
                );
                create table mark (
                    id integer primary key, front_foto text, back_foto text, book1_foto text, book2_foto text
                );
                create table person_media (id integer primary key, person_id integer, file_path text);
                create table guide (id integer primary key, image_path text);
                create table guide_lev_0 (id integer primary key, image_path text);
                create table guide_lev_1 (id integer primary key, image_path text);
                create table guide_lev_2 (id integer primary key, image_path text);
                create table guide_lev_3 (id integer primary key, image_path text);
                create table guide_lev_4 (id integer primary key, image_path text);
                insert into person (id, fio, person_foto) values (1, 'Delete Target', 'Source/shared/person.jpg');
                insert into person (id, fio, person_foto, main_foto) values
                    (2, 'Neighbor', 'Source/shared/person.jpg', 'Source/2/neighbor.jpg');
                insert into rewards (id, person_id, front_foto) values (10, 1, 'Source/1/10/front.jpg');
                insert into mark (id, front_foto) values (20, 'SourceMark/20/front.jpg');
                """
            )
        for relative in (
            "Source/shared/person.jpg",
            "Source/1/10/front.jpg",
            "Source/2/neighbor.jpg",
            "SourceMark/20/front.jpg",
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\xff\xd8\xff\xe0ale300")

    def test_preflight_endpoints_return_fresh_operation_and_exact_counts(self) -> None:
        with patch.object(delete_preflight_router, "get_settings", return_value=self.settings):
            person = delete_preflight_router.delete_preflight("person", 1)
            reward = delete_preflight_router.delete_preflight("reward", 10)
            mark = delete_preflight_router.delete_preflight("mark", 20)

        self.assertIn("Наград: 1", person["message"])
        self.assertIn("общих файлов будет сохранено: 1", person["message"])
        self.assertFalse(person["blocked"])
        self.assertIn("Связанных материалов: 1", reward["message"])
        self.assertFalse(reward["blocked"])
        self.assertIn("Связанных материалов: 1", mark["message"])
        self.assertFalse(mark["blocked"])
        operation_ids = {person["operation_id"], reward["operation_id"], mark["operation_id"]}
        self.assertEqual(len(operation_ids), 3)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{32}", item) for item in operation_ids))

    def test_batch_reference_analysis_reads_schema_once_per_table(self) -> None:
        traces: list[str] = []
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            connection.set_trace_callback(traces.append)
            counts = managed_image_reference_counts_in_connection(
                connection,
                self.settings,
                {"Source/shared/person.jpg", "Source/2/neighbor.jpg"},
                excluded_rows=(MediaReferenceExclusion("person", 1),),
            )

        self.assertEqual(counts["Source/shared/person.jpg"], 1)
        self.assertEqual(counts["Source/2/neighbor.jpg"], 1)
        pragma_statements = [item for item in traces if item.lstrip().upper().startswith("PRAGMA TABLE_INFO")]
        self.assertEqual(len(pragma_statements), len(set(pragma_statements)))
        self.assertLessEqual(len(pragma_statements), 10)

    def test_normal_views_do_not_compute_destructive_previews(self) -> None:
        legacy_source = (ROOT / "backend/app/routers/legacy.py").read_text(encoding="utf-8")
        persons_source = (ROOT / "backend/app/routers/persons.py").read_text(encoding="utf-8")
        rewards_source = (ROOT / "backend/app/routers/rewards.py").read_text(encoding="utf-8")
        marks_source = (ROOT / "backend/app/routers/marks.py").read_text(encoding="utf-8")

        selected_person_block = legacy_source.split("if selected_person_id is not None:", 1)[1].split(
            "selected_mark_id =", 1
        )[0]
        self.assertNotIn("delete_preview", selected_person_block)
        self.assertNotIn("person_delete_preview", persons_source.split("def person_detail", 1)[1].split("def person_delete_preflight", 1)[0])
        self.assertNotIn("reward_delete_preview", rewards_source.split("def reward_detail", 1)[1].split("def reward_delete_preflight", 1)[0])
        self.assertNotIn("mark_delete_preview", marks_source.split("def mark_detail", 1)[1].split("def mark_delete_preflight", 1)[0])

    def test_templates_and_javascript_use_lazy_preflight(self) -> None:
        templates = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "backend/app/templates/legacy.html",
                "backend/app/templates/person_detail.html",
                "backend/app/templates/reward_detail.html",
                "backend/app/templates/mark_detail.html",
            )
        )
        confirm_script = (ROOT / "backend/app/static/confirm_submit.js").read_text(encoding="utf-8")
        navigation_script = (ROOT / "backend/app/static/legacy_rewards.js").read_text(encoding="utf-8")

        self.assertGreaterEqual(templates.count("data-confirm-preview-url="), 6)
        self.assertIn("loadDeletePreflight(form, submitter, dialog)", confirm_script)
        self.assertIn("DELETE_PREFLIGHT_TIMEOUT_MS = 15000", confirm_script)
        self.assertIn("validateDeletePreview(form", confirm_script)
        self.assertIn("abortActiveDeleteRequest()", confirm_script)
        self.assertIn("confirmButton.hidden = blocked", confirm_script)
        self.assertIn("REQUEST_TIMEOUT_MS = 15000", navigation_script)
        self.assertIn("const response = await window.fetch", navigation_script)
        self.assertIn("timedOut ? TIMEOUT_TEXT : ERROR_TEXT", navigation_script)
        self.assertIn("activeFetchController !== controller", navigation_script)
        self.assertIn("restoreSelectionFromLocation()", navigation_script)
        self.assertIn('new URL(window.location.href).searchParams.get("person_id")', navigation_script)
        self.assertIn("window.clearTimeout(timeoutId)", navigation_script)
        self.assertIn('target.getAttribute("aria-busy") === "true"', navigation_script)


if __name__ == "__main__":
    unittest.main()
