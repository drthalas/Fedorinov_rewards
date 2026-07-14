from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
import asyncio
from io import BytesIO
import os
import sqlite3
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from backend.app.routers import persons as persons_router
from backend.app.routers.templates import templates
from backend.app.services.booklets import BookletPDFResult, generate_person_booklet_pdf, person_booklet_context


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, values: dict[str, object] | None = None, path: str = "/persons/1/booklet"):
        self._body = urlencode(values or {}).encode("utf-8")
        self.url = type("URL", (), {"path": path})()

    async def body(self) -> bytes:
        return self._body

    def url_for(self, name: str, **path_params) -> str:
        if name == "static":
            return f"/static/{path_params.get('path', '')}"
        return f"/{name}"


class PersonBookletTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self._previous_env = {
            key: os.environ.get(key)
            for key in ["REWARDS_DATA_DIR", "REWARDS_DB_PATH", "WRITE_MODE", "READ_ONLY"]
        }
        os.environ["REWARDS_DATA_DIR"] = str(self.root)
        os.environ["REWARDS_DB_PATH"] = str(self.db_path)
        os.environ["WRITE_MODE"] = "true"
        os.environ["READ_ONLY"] = "false"
        self._create_db()

    def tearDown(self) -> None:
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _create_db(self) -> None:
        (self.root / "Source" / "1").mkdir(parents=True)
        (self.root / "Source" / "1" / "FotoPerson.jpg").write_bytes(b"fake jpg")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key, name text)")
            for level in range(4):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, idl integer, name text)")
                connection.execute(f"insert into guide_lev_{level} values (1, 0, 'Guide {level}')")
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
            connection.execute(
                """
                create table rewards (
                    id integer primary key,
                    person_id integer,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    number text,
                    instock text,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
                )
                """
            )
            connection.execute("insert into guide values (1, 'капитан')")
            connection.execute(
                """
                insert into person (
                    id, fio, birthday, id_rank, person_foto, main_foto, rewards_foto,
                    book1_foto, book2_foto, card1_foto, card2_foto, link1, link2, comment, biography
                )
                values (
                    1, 'Иванов Иван', '1910-01-02', 1, 'Source/1/FotoPerson.jpg', '../secret.jpg', '',
                    '', '', '', '', 'https://example.com/memory', 'javascript:alert(1)', 'Комментарий', 'Биография'
                )
                """
            )
            connection.execute(
                """
                insert into rewards (
                    id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number,
                    instock, date_purchase, price_purchase, price_now, front_foto, back_foto,
                    book1_foto, book2_foto, reward_list
                )
                values (10, 1, 1, 1, 1, 1, '123', '1', '2020-03-04', 100, 200, '', '', '', '', '')
                """
            )
            connection.commit()

    def _counts(self) -> tuple[int, int]:
        with sqlite3.connect(self.db_path) as connection:
            person_count = connection.execute("select count(*) from person").fetchone()[0]
            reward_count = connection.execute("select count(*) from rewards").fetchone()[0]
        return person_count, reward_count

    def test_booklet_preview_context_respects_return_to(self) -> None:
        return_to = "/legacy?tab=rewards&person_id=1"
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_booklet(FakeRequest(), 1, return_to=return_to)
        self.assertEqual(context["return_to"], return_to)
        self.assertEqual(context["person"]["fio"], "Иванов Иван")
        self.assertEqual(len(context["rewards"]), 1)

    def test_person_detail_manifest_includes_folder_photos_not_only_visible_thumbnail_links(self) -> None:
        (self.root / "Source" / "1" / "extra.jpg").write_bytes(b"extra")
        (self.root / "Source" / "1" / "nested").mkdir()
        (self.root / "Source" / "1" / "nested" / "extra2.png").write_bytes(b"extra")
        (self.root / "Source" / "1" / "unsafe.exe").write_bytes(b"unsafe")

        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_detail(FakeRequest(path="/persons/1"), 1)
        rendered = templates.env.get_template("person_detail.html").render(
            request=FakeRequest(path="/persons/1"),
            **context,
        )

        self.assertIn("data-person-full-lightbox-items", rendered)
        self.assertIn("data-lightbox-items=\"person-1-all\"", rendered)
        self.assertIn("Source%2F1%2Fextra.jpg", rendered)
        self.assertIn("Source%2F1%2Fnested%2Fextra2.png", rendered)
        self.assertNotIn("unsafe.exe", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_person_detail_links_use_compact_labels_and_keep_full_url_in_title(self) -> None:
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_detail(FakeRequest(path="/persons/1"), 1)
        rendered = templates.env.get_template("person_detail.html").render(
            request=FakeRequest(path="/persons/1"),
            **context,
        )

        self.assertIn("<dt>Память народа</dt>", rendered)
        self.assertIn('class="compact-link-value"', rendered)
        self.assertIn('class="compact-external-link"', rendered)
        self.assertIn('href="https://example.com/memory"', rendered)
        self.assertIn('title="https://example.com/memory"', rendered)
        self.assertIn(">Память народа</a>", rendered)
        self.assertNotIn(">https://example.com/memory</a>", rendered)

    def test_booklet_preview_renders_person_biography_and_rewards(self) -> None:
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_booklet(FakeRequest(), 1, return_to="/persons/1")
        rendered = templates.env.get_template("person_booklet.html").render(
            request=FakeRequest(),
            **context,
        )
        self.assertIn("Иванов Иван", rendered)
        self.assertIn("Биография", rendered)
        self.assertIn("Guide 3", rendered)
        self.assertIn("Сохранить PDF", rendered)
        self.assertIn("data-save-as-form", rendered)
        self.assertIn("data-save-as-filename=", rendered)
        self.assertIn("data-save-as-mime=\"application/pdf\"", rendered)
        self.assertIn("Иванов_Иван_1_booklet_", rendered)
        self.assertNotIn('name="save_dialog"', rendered)

    def test_missing_and_unsafe_photos_do_not_crash_or_get_included(self) -> None:
        context = person_booklet_context(persons_router.get_settings(), 1)
        photos = {photo["field"]: photo for photo in context["person_photos"]}
        self.assertTrue(photos["person_foto"]["available"])
        self.assertFalse(photos["main_foto"]["available"])
        self.assertTrue(photos["main_foto"]["missing"])
        self.assertIn("traversal", photos["main_foto"]["reason"])
        self.assertNotIn("secret", photos["main_foto"]["resolved_path"])

    def test_booklet_preview_does_not_write_database(self) -> None:
        before = self._counts()
        person_booklet_context(persons_router.get_settings(), 1)
        after = self._counts()
        self.assertEqual(after, before)

    def test_pdf_route_saves_to_selected_path_when_generator_succeeds(self) -> None:
        selected_path = self.root / "selected" / "test.pdf"
        with patch.object(
            persons_router,
            "choose_save_path",
            return_value=selected_path,
        ), patch.object(
            persons_router,
            "generate_person_booklet_pdf",
            return_value=BookletPDFResult(path=selected_path, filename="test.pdf"),
        ):
            response = asyncio.run(
                persons_router.person_booklet_pdf(FakeRequest({"return_to": "/persons/1", "save_dialog": "1"}), 1)
            )
        self.assertEqual(response.status_code, 303)
        self.assertIn("message=", response.headers["location"])

    def test_pdf_route_cancel_does_not_generate_file(self) -> None:
        with patch.object(
            persons_router,
            "choose_save_path",
            side_effect=persons_router.SaveDialogCancelled("cancel"),
        ), patch.object(persons_router, "generate_person_booklet_pdf") as generator:
            response = asyncio.run(
                persons_router.person_booklet_pdf(FakeRequest({"return_to": "/persons/1", "save_dialog": "1"}), 1)
            )
        self.assertEqual(response.status_code, 303)
        generator.assert_not_called()

    def test_pdf_route_returns_application_pdf(self) -> None:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab is not installed")
        before = self._counts()
        response = asyncio.run(persons_router.person_booklet_pdf(FakeRequest({"return_to": "/persons/1"}), 1))
        after = self._counts()
        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(Path(response.path).read_bytes().startswith(b"%PDF"))
        self.assertEqual(after, before)

    def test_archive_blob_route_returns_zip(self) -> None:
        (self.root / "Source" / "1" / "document.txt").write_text("content", encoding="utf-8")
        response = asyncio.run(persons_router.person_archive_folder_zip(1))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/zip")
        self.assertIn("Content-Disposition", response.headers)
        with ZipFile(BytesIO(response.body)) as archive:
            names = set(archive.namelist())
        self.assertIn("Фотографии/", names)
        self.assertIn("Документы/", names)
        self.assertIn("Фотографии/FotoPerson.jpg", names)
        self.assertIn("Документы/document.txt", names)

    def test_archive_blob_route_skips_forbidden_members(self) -> None:
        (self.root / "Source" / "1" / "photo.jpg").write_bytes(b"image")
        (self.root / "Source" / "1" / ".env").write_text("SECRET=1", encoding="utf-8")
        (self.root / "Source" / "1" / "nested.zip").write_bytes(b"zip")
        response = asyncio.run(persons_router.person_archive_folder_zip(1))
        with ZipFile(BytesIO(response.body)) as archive:
            names = set(archive.namelist())
        self.assertIn("Фотографии/photo.jpg", names)
        self.assertFalse(any(name.endswith(".env") for name in names))
        self.assertFalse(any(name.endswith("nested.zip") for name in names))

    def test_generate_person_booklet_pdf_creates_pdf_when_reportlab_available(self) -> None:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab is not installed")
        result = generate_person_booklet_pdf(persons_router.get_settings(), 1)
        self.assertTrue(result.path.exists())
        self.assertEqual(result.path.suffix, ".pdf")
        self.assertIn("generated", result.path.parts)
        self.assertTrue(result.path.read_bytes().startswith(b"%PDF"))

    def test_generate_person_booklet_pdf_can_write_selected_path(self) -> None:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab is not installed")
        selected_path = self.root / "chosen" / "custom.pdf"
        result = generate_person_booklet_pdf(persons_router.get_settings(), 1, output_path=selected_path)
        self.assertEqual(result.path, selected_path.resolve())
        self.assertTrue(result.path.exists())

    def test_generated_pdf_paths_are_ignored(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.pdf", gitignore)
        self.assertIn("generated/", gitignore)


if __name__ == "__main__":
    unittest.main()
