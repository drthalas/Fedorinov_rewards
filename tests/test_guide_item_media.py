from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import asyncio
import os
import sqlite3
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import FormData, UploadFile

from backend.app.config import Settings
from backend.app.repositories.guides import get_guide_level_item, guide_tree, list_guide_level
from backend.app.repositories.guides_write import (
    GuideLevelData,
    GuideValidationError,
    RankGuideData,
    clear_guide_level_image,
    create_guide_level_item,
    create_rank,
    guide_level_data_from_mapping,
    update_guide_level_item,
)
from backend.app.routers import guides as guides_router
from backend.app.services.guide_images import (
    MAX_GUIDE_IMAGE_BYTES,
    GuideImageValidationError,
    normalize_guide_image_path,
    save_guide_image,
)
from backend.app.services.media_lifecycle import cleanup_unreferenced_image
from backend.app.services.guide_tree_state import (
    apply_guide_tree_state,
    guide_tree_return_url,
    parse_guide_node_keys,
)


ROOT = Path(__file__).resolve().parents[1]
from tests.image_fixtures import PNG_BYTES, WEBP_BYTES


class FakeMultipartRequest:
    def __init__(self, values: list[tuple[str, object]]):
        self._form = FormData(values)

    async def form(self) -> FormData:
        return self._form


class FakeUrlencodedRequest:
    def __init__(self, values: dict[str, object]):
        self._body = urlencode(values).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class GuideItemMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.log")
        self._create_db()
        self._preflight_patch = patch("backend.app.routers.guides.authorize_delete_execution")
        self._preflight_patch.start()
        self.addCleanup(self._preflight_patch.stop)

    def tearDown(self) -> None:
        os.environ.pop("REWARDS_AUDIT_LOG", None)
        self.tmp.cleanup()

    def settings(self, write_mode: bool = True) -> Settings:
        return Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=not write_mode,
            write_mode=write_mode,
        )

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key autoincrement, name text)")
            connection.execute("create table person (id integer primary key autoincrement, id_rank integer)")
            for level in range(5):
                connection.execute(
                    f"create table guide_lev_{level} (id integer primary key autoincrement, idl integer, name text)"
                )
            connection.execute(
                "create table rewards (id integer primary key, id_gos integer, id_catigory integer, "
                "id_sub_catigory integer, id_name integer, id_link text)"
            )
            connection.execute(
                "create table mark (id integer primary key, id_gos integer, id_catigory integer, "
                "id_sub_catigory integer, id_name integer, id_link text)"
            )
            connection.execute("insert into guide_lev_0 (id, idl, name) values (1, -1, 'СССР')")
            connection.execute("insert into guide_lev_1 (id, idl, name) values (1, 1, 'Боевые')")
            connection.execute("insert into guide_lev_2 (id, idl, name) values (1, 1, 'Ордена')")
            connection.execute("insert into guide_lev_3 (id, idl, name) values (1, 1, 'Орден тестовый')")

    def _columns(self, level: int) -> set[str]:
        with sqlite3.connect(self.db_path) as connection:
            return {row[1] for row in connection.execute(f"pragma table_info(guide_lev_{level})")}

    def test_old_schema_reads_without_mutating_database(self) -> None:
        self.assertNotIn("rating_rank", self._columns(0))
        rows = list_guide_level(self.db_path, 0)
        tree = guide_tree(self.db_path)

        self.assertIsNone(rows[0]["rating_rank"])
        self.assertIsNone(rows[0]["image_path"])
        self.assertIsNone(tree[0]["rating_rank"])
        self.assertIsNone(tree[0]["image_path"])
        self.assertNotIn("rating_rank", self._columns(0))
        self.assertNotIn("image_path", self._columns(0))

    def test_rating_rank_accepts_empty_or_positive_integer(self) -> None:
        empty = guide_level_data_from_mapping(0, {"name": "Без рейтинга", "rating_rank": ""})
        rated = guide_level_data_from_mapping(0, {"name": "С рейтингом", "rating_rank": "12"})

        self.assertIsNone(empty.rating_rank)
        self.assertEqual(rated.rating_rank, 12)

        for value in ["0", "-1", "1.5", "abc"]:
            with self.subTest(value=value), self.assertRaises(GuideValidationError):
                guide_level_data_from_mapping(0, {"name": "Ошибка", "rating_rank": value})

    def test_lazy_schema_create_and_update_rating(self) -> None:
        item_id = create_guide_level_item(
            self.settings(),
            GuideLevelData(level=0, name="Рейтинговая награда", parent_id=-1, rating_rank=3),
        )
        self.assertIn("rating_rank", self._columns(0))
        self.assertIn("image_path", self._columns(0))
        self.assertEqual(get_guide_level_item(self.db_path, 0, item_id)["rating_rank"], 3)

        update_guide_level_item(
            self.settings(),
            0,
            item_id,
            GuideLevelData(level=0, name="Рейтинговая награда", parent_id=-1, rating_rank=4),
        )
        self.assertEqual(get_guide_level_item(self.db_path, 0, item_id)["rating_rank"], 4)

        with self.assertRaises(GuideValidationError):
            create_guide_level_item(
                self.settings(),
                GuideLevelData(level=0, name="Некорректный рейтинг", parent_id=-1, rating_rank=-2),
            )

    def test_guide_image_path_and_file_validation(self) -> None:
        self.assertEqual(normalize_guide_image_path("GuideImages/award.png"), "GuideImages/award.png")
        for path in ["../award.png", "GuideImages/../award.png", "/tmp/award.png", "Source/award.png"]:
            with self.subTest(path=path), self.assertRaises(GuideImageValidationError):
                normalize_guide_image_path(path)

        with self.assertRaises(GuideImageValidationError):
            save_guide_image(self.settings(), "award.gif", b"GIF89a")
        with self.assertRaises(GuideImageValidationError):
            save_guide_image(self.settings(), "award.png", b"not-a-png")
        with self.assertRaises(GuideImageValidationError):
            save_guide_image(
                self.settings(),
                "award.png",
                b"\x89PNG\r\n\x1a\n" + b"x" * MAX_GUIDE_IMAGE_BYTES,
            )
        with self.assertRaises(GuideValidationError):
            create_guide_level_item(
                self.settings(),
                GuideLevelData(level=0, name="Traversal", parent_id=-1, image_path="../award.png"),
            )

    def test_image_save_tree_display_clear_and_physical_delete(self) -> None:
        image_path = save_guide_image(self.settings(), "award.png", PNG_BYTES)
        self.assertEqual(image_path, "GuideImages/award.png")
        image_file = self.root / image_path
        self.assertTrue(image_file.is_file())

        item_id = create_guide_level_item(
            self.settings(),
            GuideLevelData(
                level=0,
                name="Орден с изображением",
                parent_id=-1,
                rating_rank=8,
                image_path=image_path,
            ),
        )
        node = next(item for item in guide_tree(self.db_path) if item["id"] == item_id)
        self.assertEqual(node["rating_rank"], 8)
        self.assertEqual(node["image_path"], image_path)

        cleared_path = clear_guide_level_image(self.settings(), 0, item_id)
        self.assertEqual(cleared_path, image_path)
        cleanup = cleanup_unreferenced_image(
            self.settings(),
            cleared_path,
            allowed_roots=frozenset({"GuideImages"}),
        )
        self.assertEqual(cleanup.status, "deleted")
        self.assertFalse(image_file.exists())
        self.assertIsNone(get_guide_level_item(self.db_path, 0, item_id)["image_path"])

    def test_guide_image_collision_uses_short_numeric_suffix(self) -> None:
        first = save_guide_image(self.settings(), "Кириллическое имя.png", PNG_BYTES)
        second = save_guide_image(self.settings(), "Кириллическое имя.png", PNG_BYTES)

        self.assertEqual(first, "GuideImages/Кириллическое_имя.png")
        self.assertEqual(second, "GuideImages/Кириллическое_имя_2.png")
        self.assertTrue((self.root / first).is_file())
        self.assertTrue((self.root / second).is_file())

    def test_router_add_replace_and_delete_image_on_temp_database(self) -> None:
        create_upload = UploadFile(file=BytesIO(PNG_BYTES), filename="award.png")
        create_request = FakeMultipartRequest(
            [
                ("parent_id", "1"),
                ("name", "Новая награда"),
                ("rating_rank", "9"),
                ("return_to", "/guides"),
                ("image_file", create_upload),
            ]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.guide_level_create(create_request, 3))
        self.assertEqual(response.status_code, 303)

        created = next(item for item in list_guide_level(self.db_path, 3) if item["name"] == "Новая награда")
        first_path = str(created["image_path"])
        self.assertEqual(created["rating_rank"], 9)
        self.assertTrue((self.root / first_path).is_file())

        replace_upload = UploadFile(file=BytesIO(WEBP_BYTES), filename="award.webp")
        update_request = FakeMultipartRequest(
            [
                ("parent_id", "1"),
                ("name", "Новая награда"),
                ("rating_rank", "10"),
                ("return_to", "/guides"),
                ("image_file", replace_upload),
            ]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.guide_level_update(update_request, 3, int(created["id"])))
        self.assertEqual(response.status_code, 303)
        updated = get_guide_level_item(self.db_path, 3, int(created["id"]))
        second_path = str(updated["image_path"])
        self.assertEqual(updated["rating_rank"], 10)
        self.assertNotEqual(second_path, first_path)
        self.assertFalse((self.root / first_path).exists())
        self.assertTrue((self.root / second_path).is_file())

        delete_request = FakeUrlencodedRequest({"confirm": "true", "return_to": "/guides"})
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.guide_level_image_delete(delete_request, 3, int(created["id"])))
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(get_guide_level_item(self.db_path, 3, int(created["id"]))["image_path"])
        self.assertFalse((self.root / second_path).exists())

    def test_router_add_without_rating_or_image_remains_supported(self) -> None:
        request = FakeMultipartRequest([("name", "Обычный элемент"), ("rating_rank", ""), ("return_to", "/guides")])
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.guide_level_create(request, 0))
        self.assertEqual(response.status_code, 303)
        created = next(item for item in list_guide_level(self.db_path, 0) if item["name"] == "Обычный элемент")
        self.assertIsNone(created["rating_rank"])
        self.assertIsNone(created["image_path"])

    def test_router_image_delete_requires_confirmation(self) -> None:
        image_path = save_guide_image(self.settings(), "award.png", PNG_BYTES)
        item_id = create_guide_level_item(
            self.settings(),
            GuideLevelData(level=3, name="Защищённое изображение", parent_id=1, image_path=image_path),
        )
        request = FakeUrlencodedRequest({"confirm": "", "return_to": "/guides"})
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(guides_router.guide_level_image_delete(request, 3, item_id))
        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(get_guide_level_item(self.db_path, 3, item_id)["image_path"], image_path)
        self.assertTrue((self.root / image_path).is_file())

    def test_router_item_delete_removes_owned_image_file(self) -> None:
        image_path = save_guide_image(self.settings(), "award.png", PNG_BYTES)
        item_id = create_guide_level_item(
            self.settings(),
            GuideLevelData(level=3, name="Удаляемый элемент", parent_id=1, image_path=image_path),
        )
        request = FakeUrlencodedRequest({"confirm": "true", "return_to": "/guides"})
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.guide_level_delete(request, 3, item_id))
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(get_guide_level_item(self.db_path, 3, item_id))
        self.assertFalse((self.root / image_path).exists())

    def test_router_item_delete_exposes_recoverable_cleanup_warning(self) -> None:
        image_path = save_guide_image(self.settings(), "warning.png", PNG_BYTES)
        item_id = create_guide_level_item(
            self.settings(),
            GuideLevelData(level=3, name="Cleanup warning", parent_id=1, image_path=image_path),
        )
        request = FakeUrlencodedRequest(
            {
                "confirm": "true",
                "delete_operation_id": "guide-warning-001",
                "return_to": "/guides?open=0-1&focus=3-1",
            }
        )
        with (
            patch.object(guides_router, "get_settings", return_value=self.settings()),
            patch(
                "backend.app.services.deletion_lifecycle._purge_operation",
                side_effect=OSError("injected purge failure"),
            ),
        ):
            response = asyncio.run(guides_router.guide_level_delete(request, 3, item_id))

        location = response.headers["location"]
        self.assertIn("status=guide_deleted", location)
        self.assertIn("media_cleanup=failed", location)
        self.assertIn("open=0-1", location)
        self.assertIn("focus=3-1", location)
        self.assertIsNone(get_guide_level_item(self.db_path, 3, item_id))

    def test_router_rank_delete_exposes_recoverable_cleanup_warning(self) -> None:
        image_path = save_guide_image(self.settings(), "rank-warning.png", PNG_BYTES)
        rank_id = create_rank(self.settings(), RankGuideData(name="Cleanup warning", image_path=image_path))
        request = FakeUrlencodedRequest(
            {
                "confirm": "true",
                "delete_operation_id": "rank-warning-001",
                "return_to": "/guides?section=ranks&focus=rank-1",
            }
        )
        with (
            patch.object(guides_router, "get_settings", return_value=self.settings()),
            patch(
                "backend.app.services.deletion_lifecycle._purge_operation",
                side_effect=OSError("injected purge failure"),
            ),
        ):
            response = asyncio.run(guides_router.rank_delete(request, rank_id))

        location = response.headers["location"]
        self.assertIn("status=rank_deleted", location)
        self.assertIn("media_cleanup=failed", location)
        self.assertIn("section=ranks", location)

    def test_non_award_routes_ignore_rating_and_image_upload(self) -> None:
        upload = UploadFile(file=BytesIO(PNG_BYTES), filename="country.png")
        request = FakeMultipartRequest(
            [
                ("name", "Новое государство"),
                ("rating_rank", "4"),
                ("return_to", "/guides"),
                ("image_file", upload),
            ]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            response = asyncio.run(guides_router.guide_level_create(request, 0))
        self.assertEqual(response.status_code, 303)
        created = next(item for item in list_guide_level(self.db_path, 0) if item["name"] == "Новое государство")
        self.assertIsNone(created["rating_rank"])
        self.assertIsNone(created["image_path"])
        self.assertEqual(list((self.root / "GuideImages").glob("*")) if (self.root / "GuideImages").exists() else [], [])

    def test_guides_templates_expose_compact_rating_and_image_controls(self) -> None:
        guides = (ROOT / "backend" / "app" / "templates" / "guides.html").read_text(encoding="utf-8")
        form = (ROOT / "backend" / "app" / "templates" / "guide_level_form.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("Рейтинг: {{ node.rating_rank }}", guides)
        self.assertIn("Рейтинг не задан", guides)
        self.assertIn("Изображение не загружено", guides)
        self.assertIn("guide-tree-image", guides)
        self.assertIn("node.level == 3 and (node.rating_rank or node.image_path)", guides)
        self.assertIn("<details ", guides)
        self.assertIn("<summary>", guides)
        self.assertIn("Добавить дочерний", guides)
        self.assertIn(">Изменить</a>", guides)
        self.assertIn(">Удалить</button>", guides)
        self.assertIn('name="delete_operation_id"', guides)
        self.assertIn('data-confirm-preview-url="/delete-preflight/guide_level_{{ node.level }}/{{ node.id }}"', guides)
        self.assertIn('data-confirm-preview-url="/delete-preflight/rank/{{ rank.id }}"', guides)
        self.assertNotIn("guide_delete_operation_ids", guides)
        self.assertNotIn("rank_delete_operation_ids", guides)
        self.assertIn("guide-theme", guides)
        self.assertIn("guide-directory-grid", guides)
        self.assertIn("guide-tree-scroll", guides)
        self.assertNotIn("Уровень {{ node.level }}", guides)
        self.assertNotIn("#{{ node.id }}", guides)
        self.assertNotIn("#{{ rank.id }}", guides)
        self.assertIn('name="rating_rank"', form)
        self.assertIn('name="image_file"', form)
        self.assertIn("{% if supports_award_media %}", form)
        self.assertIn('enctype="multipart/form-data"', form)
        self.assertIn("Удалить изображение", form)
        self.assertIn("Изображение не загружено", form)
        self.assertNotIn("Изменить элемент справочника #", form)
        self.assertNotIn("Изменить: {{ level_label }} #", form)
        self.assertNotIn(">#{{ parent.id }} · {{ parent.name }}</option>", form)
        self.assertIn("object-fit: contain", styles)
        self.assertIn("width: 72px", styles)
        self.assertIn("width: 120px", styles)
        self.assertIn(".guide-theme", styles)
        self.assertIn("--guide-gold", styles)
        self.assertIn(".guide-theme .tree summary::before", styles)
        self.assertIn(".guide-theme details[data-guide-active] > .tree-actions", styles)
        self.assertNotIn(".guide-theme details > .tree-actions:hover", styles)
        self.assertNotIn(".guide-theme details:hover > .tree-actions", styles)
        self.assertIn("min-width: 194px", styles)

    def test_guide_visual_package_assets_are_used(self) -> None:
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")
        assets = ROOT / "backend" / "app" / "static" / "assets" / "guides"

        expected = {
            "left-rail.png": '/static/assets/guides/left-rail.png',
            "top-right-emblem.png": '/static/assets/guides/top-right-emblem.png',
            "archive-header-bg.png": '/static/assets/guides/archive-header-bg.png',
        }
        for filename, static_path in expected.items():
            with self.subTest(filename=filename):
                self.assertTrue((assets / filename).is_file())
                self.assertIn(static_path, styles)

    def test_tree_actions_follow_active_node_and_leaf_type(self) -> None:
        guides = (ROOT / "backend" / "app" / "templates" / "guides.html").read_text(encoding="utf-8")
        tree_script = (ROOT / "backend" / "app" / "static" / "guide_tree_state.js").read_text(encoding="utf-8")
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("guide-leaf-details", guides)
        self.assertIn("{% if node.level < 3 %}", guides)
        self.assertNotIn("{% if node.level < 4 %}", guides)
        self.assertIn('setAttribute("data-guide-active", "")', tree_script)
        self.assertIn('removeAttribute("data-guide-active")', tree_script)
        self.assertIn("if (details.open) setActiveDetails(details)", tree_script)
        self.assertIn("details[data-guide-active] > .tree-actions", styles)
        self.assertNotIn("summary:hover ~ .tree-actions", styles)

    def test_edit_title_uses_award_type_from_guide_branch(self) -> None:
        order = get_guide_level_item(self.db_path, 3, 1)
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            order_title = guides_router._guide_item_display_title(self.settings(), 3, order)
        self.assertEqual(order_title, "Орден: тестовый")
        self.assertNotIn("#1", order_title)

        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide_lev_1 (id, idl, name) values (2, 1, 'Медали')")
            connection.execute("insert into guide_lev_2 (id, idl, name) values (2, 2, 'Юбилейные')")
            connection.execute("insert into guide_lev_3 (id, idl, name) values (2, 2, 'За отвагу')")
        medal = get_guide_level_item(self.db_path, 3, 2)
        self.assertEqual(guides_router._guide_item_display_title(self.settings(), 3, medal), "Медаль: За отвагу")

    def test_edit_title_falls_back_to_name_when_branch_type_is_unknown(self) -> None:
        root = get_guide_level_item(self.db_path, 0, 1)
        self.assertEqual(guides_router._guide_item_display_title(self.settings(), 0, root), "СССР")

    def test_link_title_and_form_context_do_not_expose_award_media(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide_lev_4 (id, idl, name) values (1, 1, 'https://example.test')")
        link = get_guide_level_item(self.db_path, 4, 1)
        self.assertEqual(guides_router._guide_item_display_title(self.settings(), 4, link), "https://example.test")

        render = lambda request, name, context, **kwargs: {"template": name, **context}
        with (
            patch.object(guides_router, "get_settings", return_value=self.settings()),
            patch.object(guides_router.templates, "TemplateResponse", side_effect=render),
        ):
            country_context = guides_router.guide_level_new(None, 0)
            link_context = guides_router.guide_level_edit(None, 4, 1)
            award_context = guides_router.guide_level_edit(None, 3, 1)

        self.assertEqual(country_context["form_title"], "Добавить государство")
        self.assertFalse(country_context["supports_award_media"])
        self.assertFalse(link_context["supports_award_media"])
        self.assertTrue(award_context["supports_award_media"])

    def test_guide_tree_state_sanitizes_and_marks_open_focus_nodes(self) -> None:
        tree = guide_tree(self.db_path)
        safe_open, safe_focus = apply_guide_tree_state(tree, "0-1,1-1,2-1,9-9,bad", "3-1")
        self.assertEqual(safe_open, ("0-1", "1-1", "2-1"))
        self.assertEqual(safe_focus, "3-1")
        self.assertTrue(tree[0]["is_open"])
        leaf = tree[0]["children"][0]["children"][0]["children"][0]
        self.assertTrue(leaf["is_focus"])

        focus_only_tree = guide_tree(self.db_path)
        focus_open, focus_key = apply_guide_tree_state(focus_only_tree, "", "3-1")
        self.assertEqual(focus_open, ("0-1", "1-1", "2-1"))
        self.assertEqual(focus_key, "3-1")
        self.assertTrue(focus_only_tree[0]["is_open"])

        self.assertEqual(parse_guide_node_keys("bad,5-1,0-0,0-1,0-1"), ("0-1",))

    def test_guide_tree_return_url_preserves_only_safe_internal_state(self) -> None:
        url = guide_tree_return_url(
            "/guides?return_to=%2Flegacy%3Ftab%3Drewards&open=0-1,1-1&status=old",
            focus_key="3-1",
            add_open_keys=("2-1", "bad"),
        )
        self.assertIn("return_to=%2Flegacy%3Ftab%3Drewards", url)
        self.assertIn("open=0-1%2C1-1%2C2-1", url)
        self.assertIn("focus=3-1", url)
        self.assertNotIn("status=", url)
        self.assertEqual(guide_tree_return_url("https://evil.example", focus_key="3-1"), "/guides?focus=3-1")
        self.assertEqual(guide_tree_return_url("/legacy?tab=rewards", focus_key="3-1"), "/legacy?tab=rewards")

    def test_create_and_update_redirects_restore_tree_state(self) -> None:
        create_request = FakeMultipartRequest(
            [
                ("parent_id", "1"),
                ("name", "Новый орден"),
                ("rating_rank", ""),
                ("return_to", "/guides?open=0-1,1-1,2-1&focus=2-1"),
            ]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            created_response = asyncio.run(guides_router.guide_level_create(create_request, 3))
        created = next(item for item in list_guide_level(self.db_path, 3) if item["name"] == "Новый орден")
        created_location = created_response.headers["location"]
        self.assertIn(f"focus=3-{created['id']}", created_location)
        self.assertIn("open=0-1%2C1-1%2C2-1", created_location)

        update_request = FakeMultipartRequest(
            [
                ("parent_id", "1"),
                ("name", "Новый орден"),
                ("rating_rank", "9"),
                ("return_to", "/guides?open=0-1,1-1,2-1"),
            ]
        )
        with patch.object(guides_router, "get_settings", return_value=self.settings()):
            updated_response = asyncio.run(
                guides_router.guide_level_update(update_request, 3, int(created["id"]))
            )
        self.assertIn(f"focus=3-{created['id']}", updated_response.headers["location"])

    def test_tree_template_and_javascript_preserve_manual_state(self) -> None:
        guides = (ROOT / "backend" / "app" / "templates" / "guides.html").read_text(encoding="utf-8")
        form = (ROOT / "backend" / "app" / "templates" / "guide_level_form.html").read_text(encoding="utf-8")
        tree_script = (ROOT / "backend" / "app" / "static" / "guide_tree_state.js").read_text(encoding="utf-8")
        preview_script = (ROOT / "backend" / "app" / "static" / "guide_image_preview.js").read_text(encoding="utf-8")
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text(encoding="utf-8")

        self.assertIn('data-guide-key="{{ node.guide_key }}"', guides)
        self.assertIn("{% if node.is_open %} open{% endif %}", guides)
        self.assertIn("data-guide-focus-target", guides)
        self.assertNotIn("guide-node-focus", guides)
        self.assertNotIn("guide-node-focus", styles)
        self.assertNotIn("#fff8dc", styles)
        self.assertIn("data-guide-action", guides)
        self.assertIn("<summary><span class=\"guide-node-content\">{{ render_node_title(node) }}</span></summary>", guides)
        self.assertIn("{{ render_node_extra(node) }}", guides)
        self.assertIn("display_title", form)
        self.assertIn("history.replaceState", tree_script)
        self.assertIn('stateUrl("")', tree_script)
        self.assertIn('searchParams.set("return_to"', tree_script)
        self.assertIn("[data-guide-focus-target]", tree_script)
        self.assertIn("data-guide-image-input", form)
        self.assertIn("data-guide-image-preview-image", form)
        self.assertIn("data-guide-image-preview-placeholder", form)
        self.assertIn("data-guide-upload-name", form)
        self.assertIn("Выберите файл или перетащите его сюда", form)
        self.assertIn("URL.createObjectURL", preview_script)
        self.assertIn("URL.revokeObjectURL", preview_script)
        self.assertIn("allowedExtensions", preview_script)
        self.assertIn("allowedTypes", preview_script)
        self.assertIn("setCustomValidity", preview_script)
        self.assertIn("file.name", preview_script)
        self.assertIn("guide_tree_state.js", base)
        self.assertIn("guide_image_preview.js", base)


if __name__ == "__main__":
    unittest.main()
