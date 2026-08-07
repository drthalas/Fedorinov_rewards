import asyncio
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from zipfile import ZipFile

from fastapi import HTTPException

from backend.app.config import Settings
from backend.app.routers import persons as persons_router
from backend.app.services.booklets import person_archive_profile_data
from backend.app.services.person_archive import (
    DOCUMENT_ARCHIVE_DIR,
    PHOTO_ARCHIVE_DIR,
    PROFILE_ARCHIVE_NAME,
    PersonArchiveError,
    build_person_archive,
)
from backend.app.services.person_files import person_archive_filename


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, values: dict[str, object] | None = None):
        self._body = urlencode(values or {}).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class Ale256ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self.settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
        )
        self._create_db()
        self._create_materials()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key, name text)")
            for level in range(4):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, idl integer, name text)")
                connection.execute(f"insert into guide_lev_{level} values (1, 0, 'Уровень {level}')")
            connection.execute(
                """
                create table person (
                    id integer primary key, fio text, birthday text, id_rank integer,
                    person_foto text, main_foto text, rewards_foto text,
                    book1_foto text, book2_foto text, card1_foto text, card2_foto text,
                    link1 text, link2 text, comment text, biography text
                )
                """
            )
            connection.execute(
                """
                create table rewards (
                    id integer primary key, person_id integer,
                    id_gos integer, id_catigory integer, id_sub_catigory integer, id_name integer,
                    number text, instock text, date_purchase text, price_purchase integer, price_now integer,
                    front_foto text, back_foto text, book1_foto text, book2_foto text, reward_list text
                )
                """
            )
            connection.execute("insert into guide values (1, 'Гвардии капитан')")
            connection.execute(
                """
                insert into person values (
                    1, 'Иванов Иван Иванович', '1945-05-09', 1,
                    'Source/1/person.jpg', 'Source/1/missing.jpg', '', '', '', '', '',
                    'https://example.com/memory', '', 'Комментарий владельца',
                    'Длинная биография с кириллицей. ' || printf('%.*c', 1200, 'Я')
                )
                """
            )
            connection.execute(
                """
                insert into rewards values (
                    10, 1, 1, 1, 1, 1, 'А-123', '1', '2020-03-04', 100, 200,
                    'Source/1/10/front.png', '', '', '', ''
                )
                """
            )
            connection.execute(
                """
                insert into person values (
                    2, 'Другой Кавалер', '', 1,
                    'Source/2/other.jpg', '', '', '', '', '', '', '', '', '', ''
                )
                """
            )
            connection.commit()

    def _create_materials(self) -> None:
        person_dir = self.root / "Source" / "1"
        (person_dir / "10").mkdir(parents=True)
        (person_dir / "docs").mkdir()
        (person_dir / "duplicate").mkdir()
        (self.root / "Source" / "2").mkdir(parents=True)
        (person_dir / "person.jpg").write_bytes(b"person-image")
        (person_dir / "10" / "front.png").write_bytes(b"reward-image")
        (person_dir / "duplicate" / "front.png").write_bytes(b"person-image-with-duplicate-name")
        (person_dir / "docs" / "record.pdf").write_bytes(b"document")
        (person_dir / "docs" / "notes.txt").write_text("notes", encoding="utf-8")
        (person_dir / "extra.webp").write_bytes(b"extra-image")
        (person_dir / "unsafe.zip").write_bytes(b"nested archive")
        (self.root / "Source" / "2" / "other.jpg").write_bytes(b"other-person")

    def test_archive_contains_only_selected_person_materials_and_generated_profile(self) -> None:
        before_db = sha256(self.db_path.read_bytes()).hexdigest()
        result = build_person_archive(self.settings, 1)
        after_db = sha256(self.db_path.read_bytes()).hexdigest()

        self.assertEqual(result.filename, "Иванов Иван Иванович.zip")
        self.assertEqual(before_db, after_db)
        with ZipFile(BytesIO(result.content)) as archive:
            names = archive.namelist()
            profile_pdf = archive.read(PROFILE_ARCHIVE_NAME)
        self.assertEqual(
            set(names),
            {
                f"{PHOTO_ARCHIVE_DIR}/",
                f"{DOCUMENT_ARCHIVE_DIR}/",
                f"{PHOTO_ARCHIVE_DIR}/extra.webp",
                f"{PHOTO_ARCHIVE_DIR}/front.png",
                f"{PHOTO_ARCHIVE_DIR}/front (2).png",
                f"{PHOTO_ARCHIVE_DIR}/person.jpg",
                f"{DOCUMENT_ARCHIVE_DIR}/notes.txt",
                f"{DOCUMENT_ARCHIVE_DIR}/record.pdf",
                PROFILE_ARCHIVE_NAME,
            },
        )
        self.assertEqual(result.files_count, len(names) - 2)
        self.assertTrue(profile_pdf.startswith(b"%PDF"))
        self.assertIn("Source/1/missing.jpg", result.missing_media)
        self.assertFalse(any(name.endswith("unsafe.zip") for name in names))
        self.assertFalse(any(name.endswith("other.jpg") for name in names))
        self.assertTrue(all(name == PROFILE_ARCHIVE_NAME or name.count("/") == 1 for name in names))

    def test_duplicate_material_names_get_stable_readable_suffixes(self) -> None:
        first = build_person_archive(self.settings, 1)
        second = build_person_archive(self.settings, 1)
        self.assertEqual(first.entries, second.entries)
        self.assertIn(f"{PHOTO_ARCHIVE_DIR}/front.png", first.entries)
        self.assertIn(f"{PHOTO_ARCHIVE_DIR}/front (2).png", first.entries)

    def test_profile_data_contains_available_fields_and_no_empty_placeholders(self) -> None:
        profile = person_archive_profile_data(self.settings, 1)
        person_rows = dict(profile["person_rows"])
        self.assertEqual(person_rows["ФИО"], "Иванов Иван Иванович")
        self.assertEqual(person_rows["Год рождения"], "1945")
        self.assertEqual(person_rows["Звание / специальность"], "Гвардии капитан")
        self.assertIn("кириллицей", profile["biography"])
        self.assertEqual(profile["comment"], "Комментарий владельца")
        self.assertEqual(profile["links"], [("Память народа", "https://example.com/memory")])
        self.assertEqual(profile["rewards"][0]["title"], "Уровень 3")
        flattened_values = [value for _, value in profile["person_rows"]]
        for reward in profile["rewards"]:
            flattened_values.extend(value for _, value in reward["rows"])
        self.assertNotIn("—", flattened_values)
        self.assertNotIn("None", flattened_values)

    def test_archive_filename_preserves_spaces_and_sanitizes_windows_characters(self) -> None:
        filename = person_archive_filename('Иванов: Иван/Петров*? "Тест"', 1)
        self.assertTrue(filename.endswith(".zip"))
        self.assertIn("Иванов", filename)
        self.assertIn(" ", filename)
        for character in '<>:"/\\|?*':
            self.assertNotIn(character, filename)

    def test_native_save_as_cancel_does_not_prepare_or_write_archive(self) -> None:
        with patch.object(persons_router, "get_settings", return_value=self.settings), patch.object(
            persons_router, "choose_save_path", side_effect=persons_router.SaveDialogCancelled("cancel")
        ), patch.object(persons_router, "save_person_archive") as save_archive:
            response = asyncio.run(
                persons_router.person_archive_folder(FakeRequest({"return_to": "/legacy?tab=rewards&person_id=1"}), 1)
            )
        self.assertEqual(response.status_code, 303)
        self.assertIn("archive_cancelled", response.headers["location"])
        save_archive.assert_not_called()

    def test_archive_generation_error_is_not_reported_as_cancel(self) -> None:
        with patch.object(persons_router, "get_settings", return_value=self.settings), patch.object(
            persons_router, "build_person_archive", side_effect=PersonArchiveError("Ошибка PDF")
        ):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(persons_router.person_archive_folder_zip(1))
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail, "Ошибка PDF")


class Ale256UiContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_selected_person_meta_keeps_rank_and_puts_birth_year_label_last(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        heading = template.split('<div class="legacy-person-heading">', 1)[1].split(
            '<div class="legacy-actions">', 1
        )[0]
        self.assertIn("selected_person_rank", heading)
        self.assertIn("{{ selected_person_birth_year }} г.р.", heading)
        self.assertNotIn("{{ selected_person_birth_year }} ГР", heading)
        self.assertIn("selected_person_birth_year != '—'", heading)

    def test_archive_cancel_status_is_transient_and_outside_layout(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        script = self.read("backend/app/static/save_as.js")
        styles = self.read("backend/app/static/styles.css")
        self.assertIn('data-save-as-cancel-timeout="4000"', template)
        self.assertIn('data-save-as-success-message="Архив сохранён."', template)
        self.assertIn('id="person-archive-status"', template)
        self.assertNotIn("Откроется предпросмотр буклета", template)
        self.assertIn('setMessage(form, "Сохранение отменено.", "cancel")', script)
        self.assertIn("target.hidden = true", script)
        self.assertIn(".archive-save-status", styles)
        self.assertIn("position: fixed", styles.split(".archive-save-status", 1)[1].split("}", 1)[0])

    def test_person_main_photo_layout_uses_intrinsic_panel_space_without_overlap(self) -> None:
        styles = self.read("backend/app/static/styles.css")
        scoped = styles.split(".cavalier-page-theme .person-main-photo-panel .photo-frame", 1)[1]
        self.assertIn("flex: 1 1 auto", scoped.split("}", 1)[0])
        self.assertIn("height: auto", scoped.split("}", 1)[0])
        self.assertIn("grid-auto-rows: minmax(250px, auto)", styles)
        self.assertIn("object-fit: contain", styles)

    def test_person_photo_plus_is_button_with_clipboard_first_and_file_picker_fallback(self) -> None:
        template = self.read("backend/app/templates/photo_management.html")
        script = self.read("backend/app/static/clipboard_paste.js")
        self.assertIn("data-person-photo-trigger", template)
        self.assertIn('data-file-input-id="{{ file_input_id }}"', template)
        self.assertIn('type="file"', template)
        self.assertIn("navigator.clipboard.read", script)
        person_handler = script.split("function bindInlinePhotoTrigger(button)", 1)[1].split(
            'document.addEventListener("DOMContentLoaded"', 1
        )[0]
        self.assertLess(
            person_handler.index("await freshImageBlobFromClipboardWithTimeout(CLIPBOARD_ATTEMPT_TIMEOUT_MS)"),
            person_handler.index("await uploadClipboardImage"),
        )
        self.assertIn("openPersonFilePicker(button)", person_handler)
        self.assertIn("input.click()", script)
        self.assertNotIn("input.showPicker()", script)
        self.assertIn("freshImageBlobFromClipboardWithTimeout(CLIPBOARD_ATTEMPT_TIMEOUT_MS)", person_handler)
        self.assertIn("window.location.reload()", script)
        self.assertIn('form.append("entity_id", button.getAttribute("data-entity-id")', script)
        self.assertIn('form.append("photo_field", button.getAttribute("data-photo-field")', script)
        self.assertNotIn("Вставить изображение из буфера", template.split("{% if photo_entity_type == 'person' %}", 1)[1].split("{% else %}", 1)[0])

    def test_corrective_runtime_javascript_uses_a_new_static_cache_key(self) -> None:
        templates = self.read("backend/app/routers/templates.py")
        self.assertIn('STATIC_ASSET_VERSION = "20260807-ale354-alphabet-lifecycle-corrective-2"', templates)
        self.assertNotIn('STATIC_ASSET_VERSION = "20260712-cavaliers-design-4"', templates)


if __name__ == "__main__":
    unittest.main()
