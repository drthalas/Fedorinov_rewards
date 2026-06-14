from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
import asyncio
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.main import app
from backend.app.repositories.summary import (
    normalized_summary_filters,
    parse_optional_int,
    summary_filter_cascade,
    summary_filter_options,
    summary_csv_text,
    summary_matrix,
    summary_matrix_csv_text,
    summary_rows,
)
from backend.app.routers.legacy import (
    summary_csv,
    summary_csv_save,
    summary_matrix_csv,
    summary_matrix_csv_save,
    summary_matrix_pdf,
    summary_pdf,
)
from backend.app.services.save_dialog import SaveDialogCancelled


class FakeRequest:
    def __init__(self, values: dict[str, object] | None = None):
        self._body = urlencode(values or {}).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


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

    def test_summary_filter_cascade_contains_all_branches_for_js(self) -> None:
        cascade = summary_filter_cascade(self.db_path)
        self.assertEqual({row["id"] for row in cascade["countries"]}, {1, 2})
        self.assertEqual({row["id"] for row in cascade["categories"]}, {1, 2})
        self.assertEqual({row["id"] for row in cascade["subcategories"]}, {1, 2})
        self.assertEqual({row["id"] for row in cascade["names"]}, {1, 2})

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

    def test_summary_csv_route_returns_csv_response(self) -> None:
        response = summary_csv(country_id="", category_id="", subcategory_id="", name_id="", extra="", include_marks="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.media_type)
        self.assertIn("Орден Тестовый", response.body.decode("utf-8"))

    def test_summary_matrix_csv_route_returns_csv_response(self) -> None:
        response = summary_matrix_csv(country_id="", category_id="", subcategory_id="", name_id="1", extra="", include_marks="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.media_type)
        text = response.body.decode("utf-8")
        self.assertTrue(text.startswith("\ufeff"))
        self.assertIn("ФИО", text)
        self.assertIn("Орден Тестовый", text)

    def test_matrix_total_row_stays_last_in_csv_after_sort(self) -> None:
        matrix = summary_matrix(self.db_path, normalized_summary_filters(), sort_by="fio", sort_dir="desc")
        text = summary_matrix_csv_text(matrix)
        data_lines = [line for line in text.splitlines() if line.strip()]
        self.assertTrue(data_lines[-1].startswith("Итого;"))

    def test_summary_pdf_route_returns_pdf_response(self) -> None:
        response = summary_pdf(country_id="", category_id="", subcategory_id="", name_id="", extra="", include_marks="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF"))
        self.assertIn('filename="summary.pdf"', response.headers["content-disposition"])

    def test_summary_matrix_pdf_route_returns_pdf_response(self) -> None:
        response = summary_matrix_pdf(country_id="", category_id="", subcategory_id="", name_id="1", extra="", include_marks="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF"))
        self.assertIn('filename="summary_matrix.pdf"', response.headers["content-disposition"])
        self.assertFalse((self.root / "generated").exists())

    def test_summary_pdf_filters_are_accepted_without_422(self) -> None:
        response = summary_matrix_pdf(country_id="1", category_id="1", subcategory_id="1", name_id="1", extra="1", include_marks="true")
        self.assertIn(response.status_code, {200, 400})
        if response.status_code == 200:
            self.assertTrue(response.body.startswith(b"%PDF"))

    def test_too_wide_summary_matrix_pdf_is_handled_gracefully(self) -> None:
        with patch("backend.app.services.summary_pdf.SUMMARY_MATRIX_MAX_COLUMNS", 5):
            response = summary_matrix_pdf(country_id="", category_id="", subcategory_id="", name_id="", extra="", include_marks="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Таблица слишком широкая для PDF", response.body.decode("utf-8"))

    def test_summary_matrix_csv_save_writes_selected_path(self) -> None:
        selected_path = self.root / "exports" / "matrix.csv"
        request = FakeRequest({"name_id": "1", "return_to": "/legacy?tab=summary"})
        with patch("backend.app.routers.legacy.choose_save_path", return_value=selected_path):
            response = asyncio.run(summary_matrix_csv_save(request))
        self.assertEqual(response.status_code, 303)
        self.assertTrue(selected_path.exists())
        self.assertIn("ФИО", selected_path.read_text(encoding="utf-8"))

    def test_summary_csv_save_cancel_does_not_write(self) -> None:
        selected_path = self.root / "exports" / "summary.csv"
        request = FakeRequest({"return_to": "/legacy?tab=summary"})
        with patch("backend.app.routers.legacy.choose_save_path", side_effect=SaveDialogCancelled("cancel")):
            response = asyncio.run(summary_csv_save(request))
        self.assertEqual(response.status_code, 303)
        self.assertFalse(selected_path.exists())

    def test_summary_routes_are_registered(self) -> None:
        legacy_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/legacy" and "GET" in getattr(route, "methods", set())
        ]
        csv_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary.csv" and "GET" in getattr(route, "methods", set())
        ]
        csv_head_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary.csv" and "HEAD" in getattr(route, "methods", set())
        ]
        matrix_csv_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary_matrix.csv" and "GET" in getattr(route, "methods", set())
        ]
        summary_pdf_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary.pdf" and "GET" in getattr(route, "methods", set())
        ]
        matrix_pdf_routes = [
            route for route in app.routes if getattr(route, "path", None) == "/summary_matrix.pdf" and "GET" in getattr(route, "methods", set())
        ]
        self.assertTrue(legacy_routes)
        self.assertTrue(csv_routes)
        self.assertTrue(csv_head_routes)
        self.assertTrue(matrix_csv_routes)
        self.assertTrue(summary_pdf_routes)
        self.assertTrue(matrix_pdf_routes)

    def test_summary_csv_buttons_use_browser_save_as_forms(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        save_as = (Path(__file__).resolve().parents[1] / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        self.assertIn('id="summary-matrix-save-form" method="get" action="/summary_matrix.csv" data-save-as-form', template)
        self.assertIn('data-save-as-filename="summary_matrix.csv"', template)
        self.assertIn('id="summary-save-form" method="get" action="/summary.csv" data-save-as-form', template)
        self.assertIn('data-save-as-filename="summary.csv"', template)
        self.assertIn('id="summary-pdf-save-form" method="get" action="{{ \'/summary_matrix.pdf\' if summary_mode == \'matrix\' else \'/summary.pdf\' }}" data-save-as-form', template)
        self.assertIn('data-save-as-filename="{{ \'summary_matrix.pdf\' if summary_mode == \'matrix\' else \'summary.pdf\' }}"', template)
        self.assertIn('data-save-as-mime="application/pdf"', template)
        self.assertIn('form="summary-pdf-save-form">PDF</button>', template)
        self.assertIn("Браузер не передаёт приложению путь выбранной папки", save_as)
        self.assertIn("Открыть копию файла", save_as)
        self.assertNotIn('action="/summary_matrix.csv/save"', template)
        self.assertNotIn('action="/summary.csv/save"', template)
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
