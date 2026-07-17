from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import asyncio
import os
import sqlite3
import unittest
from unittest.mock import patch

from jinja2 import Environment
from starlette.datastructures import FormData, UploadFile

from backend.app.config import Settings
from backend.app.repositories.guides import get_rank_guide_item, list_rank_guide
from backend.app.repositories.guides_write import GuideValidationError, RankGuideData, create_rank, update_rank
from backend.app.repositories.persons import get_person
from backend.app.routers import guides as guides_router
from backend.app.services.display import dash_if_empty, format_birth_year


ROOT = Path(__file__).resolve().parents[1]
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"rank-png"
WEBP_BYTES = b"RIFF" + (9).to_bytes(4, "little") + b"WEBP" + b"rank-webp"


class FakeMultipartRequest:
    def __init__(self, values: list[tuple[str, object]]):
        self._form = FormData(values)

    async def form(self) -> FormData:
        return self._form


class Ale263ReferenceRankInsigniaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.log")
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
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key autoincrement, name text)")
            connection.execute(
                """
                create table person (
                    id integer primary key,
                    fio text,
                    birthday text,
                    id_rank integer,
                    person_foto text,
                    main_foto text,
                    rewards_foto text,
                    book1_foto text,
                    book2_foto text,
                    card1_foto text,
                    card2_foto text,
                    link1 text,
                    link2 text,
                    comment text,
                    biography text
                )
                """
            )
            connection.execute("insert into guide (id, name) values (1, 'Красноармеец')")
            connection.execute(
                "insert into person (id, fio, birthday, id_rank) values (77, 'Тестов Тест Тестович', '1922', 1)"
            )

    def _columns(self) -> set[str]:
        with sqlite3.connect(self.db_path) as connection:
            return {row[1] for row in connection.execute("pragma table_info(guide)")}

    def test_old_rank_schema_reads_image_as_none_without_mutation(self) -> None:
        self.assertNotIn("image_path", self._columns())
        self.assertIsNone(list_rank_guide(self.db_path)[0]["image_path"])
        self.assertIsNone(get_rank_guide_item(self.db_path, 1)["image_path"])
        self.assertIsNone(get_person(self.db_path, 77)["rank_image_path"])
        self.assertNotIn("image_path", self._columns())

    def test_rank_router_create_replace_and_clear_removes_unreferenced_media(self) -> None:
        create_upload = UploadFile(file=BytesIO(PNG_BYTES), filename="insignia.png")
        create_request = FakeMultipartRequest(
            [("name", "Гвардии капитан"), ("return_to", "/guides"), ("image_file", create_upload)]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.rank_create(create_request))
        self.assertEqual(response.status_code, 303)

        rank = next(item for item in list_rank_guide(self.db_path) if item["name"] == "Гвардии капитан")
        rank_id = int(rank["id"])
        first_path = str(rank["image_path"])
        self.assertTrue((self.root / first_path).is_file())

        replace_upload = UploadFile(file=BytesIO(WEBP_BYTES), filename="insignia.webp")
        replace_request = FakeMultipartRequest(
            [("name", "Гвардии капитан"), ("return_to", "/guides"), ("image_file", replace_upload)]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.rank_update(replace_request, rank_id))
        self.assertEqual(response.status_code, 303)
        second_path = str(get_rank_guide_item(self.db_path, rank_id)["image_path"])
        self.assertNotEqual(first_path, second_path)
        self.assertFalse((self.root / first_path).exists())
        self.assertTrue((self.root / second_path).is_file())

        clear_request = FakeMultipartRequest(
            [("name", "Гвардии капитан"), ("return_to", "/guides"), ("clear_image", "true")]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.rank_update(clear_request, rank_id))
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(get_rank_guide_item(self.db_path, rank_id)["image_path"])
        self.assertFalse((self.root / second_path).exists())

    def test_rank_image_path_validation_and_person_join(self) -> None:
        with self.assertRaises(GuideValidationError):
            create_rank(self.settings(), RankGuideData(name="Traversal", image_path="../outside.png"))

        rank_id = create_rank(self.settings(), RankGuideData(name="Лейтенант", image_path="GuideImages/rank.png"))
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("update person set id_rank = ? where id = 77", (rank_id,))
        person = get_person(self.db_path, 77)
        self.assertEqual(person["rank_name"], "Лейтенант")
        self.assertEqual(person["rank_image_path"], "GuideImages/rank.png")

        with self.assertRaises(GuideValidationError):
            update_rank(self.settings(), rank_id, RankGuideData(name="Лейтенант", image_path="Source/rank.png"))

    def test_validation_error_preserves_entered_name_and_current_image(self) -> None:
        rank_id = create_rank(self.settings(), RankGuideData(name="Майор", image_path="GuideImages/current.png"))
        request = FakeMultipartRequest([("name", ""), ("return_to", "/guides")])
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.rank_update(request, rank_id))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context["rank"]["name"], "")
        self.assertEqual(response.context["rank"]["image_path"], "GuideImages/current.png")
        self.assertEqual(get_rank_guide_item(self.db_path, rank_id)["name"], "Майор")

    def test_scoped_templates_scripts_and_styles_expose_required_ui(self) -> None:
        guides = (ROOT / "backend/app/templates/guides.html").read_text(encoding="utf-8")
        rank_form = (ROOT / "backend/app/templates/rank_form.html").read_text(encoding="utf-8")
        legacy = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        tree_script = (ROOT / "backend/app/static/guide_tree_state.js").read_text(encoding="utf-8")
        preview_script = (ROOT / "backend/app/static/guide_image_preview.js").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("data-guide-tree-filter", guides)
        self.assertIn('aria-label="Поиск по дереву наград и знаков"', guides)
        self.assertIn('aria-label="Поиск по званиям и специальностям"', guides)
        self.assertIn("data-guide-tree-filter-clear", guides)
        self.assertIn("data-guide-tree-empty", guides)
        self.assertIn("data-guide-search-name", guides)
        self.assertEqual(guides.count("window.confirm("), 2)
        self.assertNotIn("return confirm(", guides)
        self.assertIn("guide-rank-insignia", guides)
        self.assertIn("media_exists(rank.image_path)", guides)
        self.assertIn("normalizeSearchText", tree_script)
        self.assertIn("savedOpenState", tree_script)
        self.assertIn("filterTreeNode", tree_script)

        self.assertIn('enctype="multipart/form-data"', rank_form)
        self.assertIn("data-rank-image-trigger", rank_form)
        self.assertIn("data-rank-image-clear", rank_form)
        self.assertIn('type="file"', rank_form)
        self.assertNotIn("Вставить изображение из буфера", rank_form)
        self.assertIn("FedorinovClipboardImages", preview_script)
        self.assertIn("DataTransfer", preview_script)
        self.assertIn("normalizeRankImage", preview_script)
        self.assertIn("rankContentBounds", preview_script)
        self.assertNotIn("pickerNext", preview_script)
        rank_flow = preview_script.split("async function beginRankImageFlow()", 1)[1].split(
            'trigger.addEventListener("click"', 1
        )[0]
        self.assertLess(
            rank_flow.index("helper.readWithTimeout"),
            rank_flow.index("openFilePicker()"),
        )
        self.assertIn("confirmation.run(trigger, beginRankImageFlow)", preview_script)
        self.assertIn("input.click();", preview_script)
        self.assertNotIn("showPicker", preview_script)
        self.assertIn('input.addEventListener("cancel"', preview_script)
        preview_frame_end = rank_form.index("</div>", rank_form.index("rank-insignia-preview-frame"))
        self.assertGreater(rank_form.index('class="rank-insignia-controls"'), preview_frame_end)

        self.assertIn("legacy-rank-insignia", legacy)
        self.assertIn("media_exists(selected_person.rank_image_path)", legacy)
        self.assertIn("object-fit: contain", styles)
        self.assertIn("position: absolute", styles)
        self.assertIn("inset: 0", styles)
        self.assertIn("guide-list li.has-rank-insignia", styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 48px minmax(140px, auto)", styles)
        self.assertIn("[data-guide-rank-row][hidden]", styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", styles)
        self.assertIn("object-position: center center", styles)
        self.assertIn(".app-toast-region", styles)
        self.assertIn("position: fixed", styles)
        self.assertNotIn("data-guide-toast", guides)
        self.assertNotIn("initGuideToasts", tree_script)
        self.assertIn("_transient_notifications.html", (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8"))

    def test_guide_statuses_have_scoped_success_and_error_lifetimes(self) -> None:
        with (
            patch.object(guides_router, "list_rank_guide", return_value=[]),
            patch.object(guides_router, "guide_tree", return_value=[]),
            patch.object(guides_router, "apply_guide_tree_state", return_value=([], "")),
        ):
            success = guides_router._context(self.settings(), object(), status="rank_updated")
            blocked = guides_router._context(self.settings(), object(), status="rank_delete_used")

        self.assertEqual(success["status_message"], "Звание/специальность сохранены.")
        self.assertEqual(success["status_kind"], "success")
        self.assertEqual(success["status_timeout_ms"], 4000)
        self.assertEqual(blocked["status_kind"], "error")
        self.assertEqual(blocked["status_timeout_ms"], 8000)

    def test_selected_person_heading_renders_available_insignia_before_unchanged_metadata(self) -> None:
        legacy_template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        heading = legacy_template.split('<div class="legacy-person-heading">', 1)[1].split(
            '<div class="legacy-actions">', 1
        )[0]
        environment = Environment(autoescape=True)
        environment.filters["dash"] = dash_if_empty
        environment.filters["format_birth_year"] = format_birth_year
        environment.globals["media_url"] = lambda path: f"/media?path={path}"

        person = {
            "id": 77,
            "fio": "Тестов Тест Тестович",
            "rank_name": "гражданский",
            "rank_image_path": "GuideImages/rank.png",
            "birthday": "1945-05-09",
        }
        environment.globals["media_exists"] = lambda path: path == "GuideImages/rank.png"
        rendered = environment.from_string(heading).render(selected_person=person)
        self.assertIn('class="legacy-rank-insignia"', rendered)
        self.assertLess(rendered.index('class="legacy-rank-insignia-frame"'), rendered.index("Гражданский"))
        self.assertIn("Гражданский · 1945 г.р.", rendered)

        environment.globals["media_exists"] = lambda _path: False
        missing_rendered = environment.from_string(heading).render(selected_person=person)
        self.assertNotIn('class="legacy-rank-insignia"', missing_rendered)
        self.assertIn("Гражданский · 1945 г.р.", missing_rendered)


if __name__ == "__main__":
    unittest.main()
