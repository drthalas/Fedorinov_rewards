from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from io import BytesIO
import os
import sqlite3
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import base64

from backend.app.main import app
from backend.app.repositories.summary import (
    normalized_summary_filters,
    parse_optional_int,
    summary_filter_cascade,
    summary_filter_options,
    summary_csv_text,
    summary_matrix,
    summary_matrix_csv_text,
    summary_matrix_table,
    summary_rows,
    summary_table,
)
from backend.app.routers.legacy import (
    legacy_index,
    summary_matrix_xlsx,
    summary_matrix_pdf,
    summary_pdf,
    summary_xlsx,
)
from backend.app.services.summary_xlsx import MAX_COLUMN_WIDTH, XLSX_MEDIA_TYPE, summary_matrix_xlsx_bytes, summary_xlsx_bytes


class FakeRequest:
    def __init__(self, values: dict[str, object] | None = None):
        self._body = urlencode(values or {}).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class FakeTemplateRequest(FakeRequest):
    pass


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self._previous_env = {key: os.environ.get(key) for key in ["REWARDS_DATA_DIR", "REWARDS_DB_PATH"]}
        os.environ["REWARDS_DATA_DIR"] = str(self.root)
        os.environ["REWARDS_DB_PATH"] = str(self.db_path)
        self._create_db()

    def tearDown(self) -> None:
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _create_db(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            for level in range(5):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, idl integer, name text)")
            connection.execute("create table guide (id integer primary key, name text)")
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
                    card2_foto text
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
                    id_link text,
                    instock boolean,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer
                )
                """
            )
            connection.execute(
                """
                create table mark (
                    id integer primary key,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link text,
                    instock boolean,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer
                )
                """
            )
            connection.execute("insert into guide_lev_0 values (1, -1, 'СССР')")
            connection.execute("insert into guide_lev_0 values (2, -1, 'Россия')")
            connection.execute("insert into guide_lev_1 values (1, 1, 'Ордена')")
            connection.execute("insert into guide_lev_1 values (2, 2, 'Юбилейные')")
            connection.execute("insert into guide_lev_2 values (1, 1, 'Боевые')")
            connection.execute("insert into guide_lev_2 values (2, 2, 'Гражданские')")
            connection.execute("insert into guide_lev_3 values (1, 1, 'Орден Тестовый')")
            connection.execute("insert into guide_lev_3 values (2, 2, 'Медаль Другая')")
            connection.execute("insert into guide_lev_4 values (1, 1, 'extra-link')")
            connection.execute("insert into guide values (1, 'Капитан')")
            connection.execute(
                """
                insert into person
                values (1, 'Иванов Иван', '1901-02-03', 1, 'Source/1/person.jpg', '', 'Source/1/rewards.jpg', '', '', 'Source/1/card1.jpg', '')
                """
            )
            connection.execute(
                """
                insert into person
                values (2, 'Петров Петр', '1902', 1, '', '', '', '', '', '', '')
                """
            )
            connection.execute(
                """
                insert into rewards
                values (10, 1, 1, 1, 1, 1, 'A-1', 'extra-link', 1, '2024-01-01', 100, 200)
                """
            )
            connection.execute(
                """
                insert into rewards
                values (11, 2, 1, 1, 1, 1, 'B-1', 'other-link', 0, '2024-02-01', 300, 400)
                """
            )
            connection.execute(
                """
                insert into mark
                values (20, 1, 1, 1, 1, 'extra-link', 1, '2024-03-01', 500, 600)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def test_empty_filters_do_not_crash(self) -> None:
        rows = summary_rows(self.db_path, normalized_summary_filters())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total"], 2)

    def test_parse_optional_int_handles_empty_none_and_value(self) -> None:
        self.assertIsNone(parse_optional_int(""))
        self.assertIsNone(parse_optional_int(None))
        self.assertEqual(parse_optional_int("1"), 1)

    def test_empty_string_filters_normalize_to_all(self) -> None:
        filters = normalized_summary_filters(country_id="", category_id="", subcategory_id="", name_id="", extra="")
        self.assertIsNone(filters.country_id)
        self.assertIsNone(filters.category_id)
        self.assertIsNone(filters.subcategory_id)
        self.assertIsNone(filters.name_id)
        rows = summary_rows(self.db_path, filters)
        self.assertEqual(rows[0]["total"], 2)

    def test_include_marks_changes_result(self) -> None:
        rewards_only = summary_rows(self.db_path, normalized_summary_filters())
        with_marks = summary_rows(self.db_path, normalized_summary_filters(include_marks="true"))
        self.assertEqual(rewards_only[0]["total"], 2)
        self.assertEqual(with_marks[0]["total"], 3)

    def test_filters_work(self) -> None:
        rows = summary_rows(self.db_path, normalized_summary_filters(country_id=999))
        self.assertEqual(rows, [])
        rows = summary_rows(self.db_path, normalized_summary_filters(country_id=1, extra="1", include_marks=True))
        self.assertEqual(rows[0]["total"], 2)
        self.assertEqual(rows[0]["last_purchase_date"], "2024-03-01")

    def test_summary_filter_options_are_cascaded(self) -> None:
        root_options = summary_filter_options(self.db_path, normalized_summary_filters())
        self.assertEqual([row["id"] for row in root_options["countries"]], [1, 2])
        self.assertEqual(root_options["categories"], [])
        self.assertEqual(root_options["subcategories"], [])
        self.assertEqual(root_options["names"], [])

        country_options = summary_filter_options(self.db_path, normalized_summary_filters(country_id=1))
        self.assertEqual([row["id"] for row in country_options["categories"]], [1])

        category_options = summary_filter_options(self.db_path, normalized_summary_filters(country_id=1, category_id=1))
        self.assertEqual([row["id"] for row in category_options["subcategories"]], [1])

        subcategory_options = summary_filter_options(
            self.db_path,
            normalized_summary_filters(country_id=1, category_id=1, subcategory_id=1),
        )
        self.assertEqual([row["id"] for row in subcategory_options["names"]], [1])
        self.assertNotIn(2, [row["id"] for row in subcategory_options["names"]])

    def test_summary_reward_names_are_alphabetical_and_stable(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                "insert into guide_lev_3 values (?, ?, ?)",
                [
                    (3, 1, "Янтарная награда"),
                    (4, 1, "армейская награда"),
                    (5, 1, "Ёлочная награда"),
                ],
            )

        options = summary_filter_options(
            self.db_path,
            normalized_summary_filters(country_id=1, category_id=1, subcategory_id=1),
        )

        self.assertEqual(
            [row["name"] for row in options["names"]],
            ["армейская награда", "Ёлочная награда", "Орден Тестовый", "Янтарная награда"],
        )
        self.assertEqual({int(row["id"]) for row in options["names"]}, {1, 3, 4, 5})

    def test_summary_template_omits_only_the_extra_filter(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        summary_section = template.split('{% elif tab == "summary" %}', 1)[1].split(
            '{% elif tab == "about" %}', 1
        )[0]

        self.assertNotIn("<span>Дополнительно</span>", summary_section)
        for label in ("Страна", "Категория", "Подкатегория", "Наименование", "Знаки"):
            self.assertIn(f"<span>{label}</span>", summary_section)
        self.assertIn('class="summary-filter-actions"', summary_section)

    def test_summary_filter_cascade_contains_all_branches_for_js(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                "insert into guide_lev_3 values (?, ?, ?)",
                [
                    (3, 1, "Янтарная награда"),
                    (4, 1, "армейская награда"),
                    (5, 1, "Ёлочная награда"),
                ],
            )

        cascade = summary_filter_cascade(self.db_path)
        self.assertEqual({row["id"] for row in cascade["countries"]}, {1, 2})
        self.assertEqual({row["id"] for row in cascade["categories"]}, {1, 2})
        self.assertEqual({row["id"] for row in cascade["subcategories"]}, {1, 2})
        self.assertEqual({row["id"] for row in cascade["names"]}, {1, 2, 3, 4, 5})
        self.assertEqual(
            [row["name"] for row in cascade["names"] if int(row["idl"]) == 1],
            ["армейская награда", "Ёлочная награда", "Орден Тестовый", "Янтарная награда"],
        )

    def test_csv_export_text_uses_utf8_bom(self) -> None:
        rows = summary_rows(self.db_path, normalized_summary_filters(include_marks=True))
        text = summary_csv_text(rows)
        self.assertTrue(text.startswith("\ufeff"))
        self.assertIn("Страна", text)
        self.assertIn("Орден Тестовый", text)

    def test_summary_csv_uses_excel_semicolon_delimiter(self) -> None:
        rows = summary_rows(self.db_path, normalized_summary_filters(include_marks=True))
        text = summary_csv_text(rows)
        first_line = text.splitlines()[0]
        self.assertTrue(first_line.startswith("\ufeffСтрана;Категория;Подкатегория;Наименование"))
        self.assertNotIn("Страна,Категория", first_line)

    def test_matrix_generates_person_rows_and_reward_columns(self) -> None:
        matrix = summary_matrix(self.db_path, normalized_summary_filters())
        self.assertEqual(matrix["person_total"], 2)
        self.assertEqual(matrix["reward_columns"][0]["name"], "Орден Тестовый")
        self.assertEqual(matrix["rows"][0]["photo_flags"]["person_foto"], 1)
        self.assertEqual(matrix["rows"][1]["photo_flags"]["person_foto"], 0)
        self.assertEqual(matrix["rows"][0]["photo_paths"]["person_foto"], "Source/1/person.jpg")
        self.assertEqual(matrix["rows"][0]["photo_paths"]["rewards_foto"], "Source/1/rewards.jpg")
        self.assertEqual(matrix["reward_total"], 2)

    def test_matrix_sorting_by_visible_columns(self) -> None:
        by_fio_desc = summary_matrix(self.db_path, normalized_summary_filters(), sort_by="fio", sort_dir="desc")
        self.assertEqual([row["fio"] for row in by_fio_desc["rows"]], ["Петров Петр", "Иванов Иван"])

        by_birthday_desc = summary_matrix(self.db_path, normalized_summary_filters(), sort_by="birthday", sort_dir="desc")
        self.assertEqual(by_birthday_desc["rows"][0]["fio"], "Петров Петр")

        by_reward_desc = summary_matrix(self.db_path, normalized_summary_filters(), sort_by="reward:1", sort_dir="desc")
        self.assertEqual(by_reward_desc["rows"][0]["reward_counts"][1], 1)

        by_total_asc = summary_matrix(self.db_path, normalized_summary_filters(), sort_by="row_total", sort_dir="asc")
        self.assertEqual([row["row_total"] for row in by_total_asc["rows"]], [1, 1])

    def test_matrix_filters_affect_reward_columns(self) -> None:
        empty = summary_matrix(self.db_path, normalized_summary_filters(country_id=999))
        self.assertEqual(empty["reward_columns"], [])
        self.assertEqual(empty["rows"], [])
        filtered = summary_matrix(self.db_path, normalized_summary_filters(country_id=1, name_id=1))
        self.assertEqual(len(filtered["reward_columns"]), 1)
        self.assertTrue(filtered["show_numbers"])

    def test_matrix_duplicate_rewards_produce_count_above_one(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """
                insert into rewards
                values (12, 1, 1, 1, 1, 1, 'A-2', 'extra-link', 1, '2024-03-01', 100, 200)
                """
            )
            connection.commit()
        finally:
            connection.close()
        matrix = summary_matrix(self.db_path, normalized_summary_filters(name_id=1))
        row = next(item for item in matrix["rows"] if item["id"] == 1)
        self.assertEqual(row["row_total"], 2)
        self.assertIn("A-1", row["numbers"])
        self.assertIn("A-2", row["numbers"])

    def test_matrix_exposes_filtered_reward_photos_and_selected_guide_image(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("alter table rewards add column front_foto text")
            connection.execute("alter table rewards add column back_foto text")
            connection.execute("alter table guide_lev_3 add column image_path text")
            connection.execute(
                "update rewards set front_foto = ?, back_foto = ? where id = 10",
                ("Source/1/10/front.jpg", "Source/1/10/back.jpg"),
            )
            connection.execute(
                "update guide_lev_3 set image_path = ? where id = 1",
                ("GuideImages/reward.jpg",),
            )
            connection.commit()
        finally:
            connection.close()

        matrix = summary_matrix(self.db_path, normalized_summary_filters(name_id=1))
        ivanov = next(row for row in matrix["rows"] if row["id"] == 1)
        petrov = next(row for row in matrix["rows"] if row["id"] == 2)

        self.assertEqual(
            matrix["reward_photo_columns"],
            [
                {"field": "front_foto", "label": "Фото аверс"},
                {"field": "back_foto", "label": "Фото реверс"},
            ],
        )
        self.assertEqual(ivanov["reward_photo_flags"], {"front_foto": 1, "back_foto": 1})
        self.assertEqual(ivanov["reward_photo_paths"]["front_foto"], ["Source/1/10/front.jpg"])
        self.assertEqual(petrov["reward_photo_flags"], {"front_foto": 0, "back_foto": 0})
        self.assertEqual(matrix["reward_photo_totals"], {"front_foto": 1, "back_foto": 1})
        self.assertEqual(matrix["selected_reward_image_path"], "GuideImages/reward.jpg")
        self.assertEqual(ivanov["pdf_reward_numbers"], ["A-1"])

    def test_matrix_csv_uses_bom_and_contains_columns(self) -> None:
        matrix = summary_matrix(self.db_path, normalized_summary_filters(name_id=1))
        text = summary_matrix_csv_text(matrix)
        self.assertTrue(text.startswith("\ufeff"))
        self.assertIn("ФИО", text)
        self.assertIn("Орден Тестовый", text)
        self.assertIn("Фото кавалера", text)
        self.assertNotIn("Source/1/person.jpg", text)

    def test_matrix_csv_uses_excel_semicolon_delimiter(self) -> None:
        matrix = summary_matrix(self.db_path, normalized_summary_filters(name_id=1))
        text = summary_matrix_csv_text(matrix)
        first_line = text.splitlines()[0]
        self.assertTrue(first_line.startswith("\ufeffФИО;Звание / специальность;Дата рождения"))
        self.assertNotIn("ФИО,Звание / специальность", first_line)

    def test_summary_xlsx_route_returns_workbook_response(self) -> None:
        response = summary_xlsx(country_id="", category_id="", subcategory_id="", name_id="", extra="", include_marks="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, XLSX_MEDIA_TYPE)
        self.assertTrue(response.body.startswith(b"PK"))
        self.assertIn('filename="summary.xlsx"', response.headers["content-disposition"])

    def test_summary_matrix_xlsx_route_returns_workbook_response(self) -> None:
        response = summary_matrix_xlsx(country_id="", category_id="", subcategory_id="", name_id="1", extra="", include_marks="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, XLSX_MEDIA_TYPE)
        self.assertTrue(response.body.startswith(b"PK"))
        self.assertIn('filename="summary_matrix.xlsx"', response.headers["content-disposition"])

    def test_xlsx_content_matches_current_summary_and_matrix_values(self) -> None:
        rows = summary_rows(self.db_path, normalized_summary_filters(include_marks=True))
        matrix = summary_matrix(self.db_path, normalized_summary_filters(name_id=1))

        summary_workbook_rows = self._xlsx_rows(summary_xlsx_bytes(rows))
        matrix_workbook_rows = self._xlsx_rows(summary_matrix_xlsx_bytes(matrix))
        summary_headers, summary_values = summary_table(rows)
        matrix_headers, matrix_values = summary_matrix_table(matrix)

        self.assertEqual(summary_workbook_rows, [[str(value) for value in summary_headers], *[[str(value) for value in row] for row in summary_values]])
        self.assertEqual(matrix_workbook_rows, [[str(value) for value in matrix_headers], *[[str(value) for value in row] for row in matrix_values]])

    def test_xlsx_columns_use_bounded_auto_width_and_wrapped_cells(self) -> None:
        rows = summary_rows(self.db_path, normalized_summary_filters(include_marks=True))
        rows[0]["name"] = "Очень длинное наименование " * 20
        blob = summary_xlsx_bytes(rows)
        with ZipFile(BytesIO(blob)) as archive:
            worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            styles = ET.fromstring(archive.read("xl/styles.xml"))
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        widths = [float(column.attrib["width"]) for column in worksheet.findall("x:cols/x:col", namespace)]
        self.assertTrue(widths)
        self.assertLessEqual(max(widths), MAX_COLUMN_WIDTH)
        self.assertEqual(widths[3], MAX_COLUMN_WIDTH)
        self.assertTrue(styles.findall(".//x:alignment[@wrapText='1']", namespace))

    @staticmethod
    def _xlsx_rows(blob: bytes) -> list[list[str]]:
        with ZipFile(BytesIO(blob)) as archive:
            worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows = []
        for row in worksheet.findall("x:sheetData/x:row", namespace):
            values = []
            for cell in row.findall("x:c", namespace):
                inline_text = cell.find("x:is/x:t", namespace)
                numeric = cell.find("x:v", namespace)
                values.append((inline_text.text if inline_text is not None else numeric.text if numeric is not None else "") or "")
            rows.append(values)
        return rows

    def test_matrix_total_row_stays_last_in_csv_after_sort(self) -> None:
        matrix = summary_matrix(self.db_path, normalized_summary_filters(), sort_by="fio", sort_dir="desc")
        text = summary_matrix_csv_text(matrix)
        data_lines = [line for line in text.splitlines() if line.strip()]
        self.assertTrue(data_lines[-1].startswith("Итого;"))

    def test_summary_pdf_route_returns_pdf_response(self) -> None:
        with patch("backend.app.routers.legacy.stage_generated_pdf", return_value="a" * 32):
            response = summary_pdf(country_id="", category_id="", subcategory_id="", name_id="", extra="", include_marks="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF"))
        self.assertIn('filename="summary.pdf"', response.headers["content-disposition"])
        self.assertEqual(response.headers["x-fedorinov-open-copy-token"], "a" * 32)

    def test_summary_matrix_pdf_route_returns_pdf_response(self) -> None:
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("alter table rewards add column front_foto text")
            connection.execute("alter table rewards add column back_foto text")
            connection.execute("alter table guide_lev_3 add column image_path text")
            connection.execute(
                "update rewards set front_foto = ?, back_foto = ? where id = 10",
                ("Source/1/10/front.png", "Source/1/10/back.png"),
            )
            connection.execute(
                "update guide_lev_3 set image_path = ? where id = 1",
                ("GuideImages/reward.png",),
            )
            connection.commit()
        finally:
            connection.close()
        for relative in ("Source/1/10/front.png", "Source/1/10/back.png", "GuideImages/reward.png"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png)

        with patch("backend.app.routers.legacy.stage_generated_pdf", return_value="b" * 32):
            response = summary_matrix_pdf(
                country_id="",
                category_id="",
                subcategory_id="",
                name_id="1",
                extra="",
                include_marks="",
                media_columns="front_foto,back_foto",
                include_reward_number="true",
                pdf_sort="reward_number",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF"))
        self.assertIn('filename="summary_matrix.pdf"', response.headers["content-disposition"])
        self.assertEqual(response.headers["x-fedorinov-open-copy-token"], "b" * 32)
        self.assertGreaterEqual(response.body.count(b"/Subtype /Image"), 2)
        self.assertFalse((self.root / "generated").exists())

    def test_summary_pdf_filters_are_accepted_without_422(self) -> None:
        response = summary_matrix_pdf(country_id="1", category_id="1", subcategory_id="1", name_id="1", extra="1", include_marks="true")
        self.assertIn(response.status_code, {200, 400})
        if response.status_code == 200:
            self.assertTrue(response.body.startswith(b"%PDF"))

    def test_too_wide_summary_matrix_pdf_is_handled_gracefully(self) -> None:
        with patch("backend.app.services.summary_pdf.SUMMARY_MATRIX_MAX_COLUMNS", 5):
            response = summary_matrix_pdf(
                country_id="",
                category_id="",
                subcategory_id="",
                name_id="",
                extra="",
                include_marks="",
                media_columns="main_foto,rewards_foto,book1_foto,book2_foto,card1_foto",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Таблица слишком широкая для PDF. Используйте фильтры или XLSX.", response.body.decode("utf-8"))

    def test_legacy_summary_tab_does_not_auto_build_result(self) -> None:
        with (
            patch("backend.app.routers.legacy.summary_rows") as rows_mock,
            patch("backend.app.routers.legacy.summary_matrix") as matrix_mock,
            patch("backend.app.routers.legacy._legacy_summary") as summary_mock,
            patch("backend.app.routers.legacy.count_marks", return_value=0),
            patch("backend.app.routers.legacy.list_marks", return_value=[]),
            patch("backend.app.routers.legacy.templates.TemplateResponse", side_effect=lambda request, name, context: context),
        ):
            context = legacy_index(FakeTemplateRequest(), tab="summary")

        rows_mock.assert_not_called()
        matrix_mock.assert_not_called()
        summary_mock.assert_not_called()
        self.assertFalse(context["summary_has_result"])
        self.assertFalse(context["summary_applied"])
        self.assertIsNone(context["summary_matrix"])
        self.assertEqual(context["summary_rows"], [])
        self.assertEqual(context["summary_reset_url"], "/legacy?tab=summary&summary_mode=matrix")

    def test_legacy_summary_tab_builds_after_show(self) -> None:
        with (
            patch("backend.app.routers.legacy.summary_rows") as rows_mock,
            patch("backend.app.routers.legacy.count_marks", return_value=0),
            patch("backend.app.routers.legacy.list_marks", return_value=[]),
            patch("backend.app.routers.legacy.templates.TemplateResponse", side_effect=lambda request, name, context: context),
        ):
            context = legacy_index(FakeTemplateRequest(), tab="summary", summary_applied="1", name_id="1")

        rows_mock.assert_not_called()
        self.assertTrue(context["summary_has_result"])
        self.assertTrue(context["summary_applied"])
        self.assertIsNotNone(context["summary_matrix"])
        self.assertGreaterEqual(len(context["summary_matrix"]["rows"]), 1)
        self.assertEqual(context["summary_rows"], [])
        self.assertIsNotNone(context["summary_pagination"])
        self.assertIn("summary_applied=1", context["summary_matrix_mode_url"])
        self.assertIn("summary_applied=1", context["summary_aggregate_mode_url"])
        self.assertIn("summary_applied=1", context["summary_matrix_sort"]["urls"]["fio"])

    def test_legacy_summary_reset_returns_to_unapplied_state(self) -> None:
        with (
            patch("backend.app.routers.legacy.summary_matrix") as matrix_mock,
            patch("backend.app.routers.legacy.count_marks", return_value=0),
            patch("backend.app.routers.legacy.list_marks", return_value=[]),
            patch("backend.app.routers.legacy.templates.TemplateResponse", side_effect=lambda request, name, context: context),
        ):
            context = legacy_index(FakeTemplateRequest(), tab="summary", summary_mode="aggregate", summary_applied="1", name_id="1")

        matrix_mock.assert_not_called()
        self.assertEqual(context["summary_reset_url"], "/legacy?tab=summary&summary_mode=aggregate")
        self.assertNotIn("summary_applied", context["summary_reset_url"])

    def test_summary_routes_are_registered(self) -> None:
        legacy_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/legacy" and "GET" in getattr(route, "methods", set())
        ]
        xlsx_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary.xlsx" and "GET" in getattr(route, "methods", set())
        ]
        xlsx_head_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary.xlsx" and "HEAD" in getattr(route, "methods", set())
        ]
        matrix_xlsx_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary_matrix.xlsx" and "GET" in getattr(route, "methods", set())
        ]
        summary_pdf_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary.pdf" and "GET" in getattr(route, "methods", set())
        ]
        matrix_pdf_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary_matrix.pdf" and "GET" in getattr(route, "methods", set())
        ]
        self.assertTrue(legacy_routes)
        self.assertTrue(xlsx_routes)
        self.assertTrue(xlsx_head_routes)
        self.assertTrue(matrix_xlsx_routes)
        self.assertFalse([route for route in app.routes if getattr(route, "path", None) in {"/summary.csv", "/summary_matrix.csv"}])
        self.assertTrue(summary_pdf_routes)
        self.assertTrue(matrix_pdf_routes)

    def test_summary_xlsx_buttons_use_browser_save_as_forms(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        save_as = (Path(__file__).resolve().parents[1] / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        self.assertIn('name="summary_applied" value="1"', template)
        self.assertIn("Выберите фильтры и нажмите «Показать».", template)
        self.assertIn("{% if summary_has_result %}", template)
        self.assertIn("{% if not summary_has_result %}", template)
        self.assertIn('href="{{ summary_reset_url }}"', template)
        self.assertIn('id="summary-matrix-save-form" method="get" action="/summary_matrix.xlsx" data-save-as-form', template)
        self.assertIn('data-save-as-filename="summary_matrix.xlsx"', template)
        self.assertIn('id="summary-save-form" method="get" action="/summary.xlsx" data-save-as-form', template)
        self.assertIn('data-save-as-filename="summary.xlsx"', template)
        self.assertIn('data-save-as-success-message="XLSX сохранён." data-save-as-open-copy="true"', template)
        self.assertIn('id="summary-export-status" class="save-as-status summary-export-status"', template)
        self.assertIn('id="summary-pdf-save-form" method="get" action="{{ \'/summary_matrix.pdf\' if summary_mode == \'matrix\' else \'/summary.pdf\' }}" data-save-as-form', template)
        self.assertIn('data-save-as-filename="{{ \'summary_matrix.pdf\' if summary_mode == \'matrix\' else \'summary.pdf\' }}"', template)
        self.assertIn('data-save-as-mime="application/pdf"', template)
        self.assertIn('data-summary-pdf-options-open>Сформировать PDF</button>', template)
        self.assertIn("Открыть копию файла", save_as)
        self.assertIn('form.getAttribute("data-save-as-open-copy") === "true"', save_as)
        self.assertNotIn("CSV шахматка", template)
        self.assertNotIn("CSV свод", template)
        self.assertNotIn("PDF-экспорт будет добавлен следующим этапом", template)
        self.assertNotIn("disabled-button\">PDF", template)

    def test_summary_template_uses_cascading_filters_and_sort_links(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn('class="summary-filter-form guide-cascade"', template)
        self.assertIn("data-guide-cascade-options", template)
        self.assertIn('name="country_id" data-guide-role="country"', template)
        self.assertIn('name="category_id" data-guide-role="category"', template)
        self.assertIn('name="subcategory_id" data-guide-role="subcategory"', template)
        self.assertIn('name="name_id" data-guide-role="name"', template)
        self.assertIn('name="matrix_sort"', template)
        self.assertIn('name="matrix_dir"', template)
        self.assertIn("matrix-sort-link", template)
        self.assertIn('class="legacy-table summary-matrix person-reward-matrix resizable-search-table" data-resizable-table', template)
        self.assertIn('class="legacy-table summary-matrix resizable-search-table" data-resizable-table', template)
        self.assertIn("summary_matrix_sort.urls.fio", template)
        self.assertIn("summary_matrix_sort.urls.birthday", template)
        self.assertIn("summary_matrix_sort.reward_urls", template)

    def test_summary_repository_uses_parameter_placeholders(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "backend" / "app" / "repositories" / "summary.py").read_text()
        self.assertIn(" = ?", source)
        self.assertIn(" like ?", source)


if __name__ == "__main__":
    unittest.main()
