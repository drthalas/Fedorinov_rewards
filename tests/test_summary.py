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
    summary_csv_text,
    summary_matrix,
    summary_matrix_csv_text,
    summary_rows,
)
from backend.app.routers.legacy import summary_csv, summary_csv_save, summary_matrix_csv, summary_matrix_csv_save
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
            connection.execute("insert into guide_lev_1 values (1, 1, 'Ордена')")
            connection.execute("insert into guide_lev_2 values (1, 1, 'Боевые')")
            connection.execute("insert into guide_lev_3 values (1, 1, 'Орден Тестовый')")
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

    def test_csv_export_text_uses_utf8_bom(self) -> None:
        rows = summary_rows(self.db_path, normalized_summary_filters(include_marks=True))
        text = summary_csv_text(rows)
        self.assertTrue(text.startswith("\ufeff"))
        self.assertIn("Страна", text)
        self.assertIn("Орден Тестовый", text)

    def test_matrix_generates_person_rows_and_reward_columns(self) -> None:
        matrix = summary_matrix(self.db_path, normalized_summary_filters())
        self.assertEqual(matrix["person_total"], 2)
        self.assertEqual(matrix["reward_columns"][0]["name"], "Орден Тестовый")
        self.assertEqual(matrix["rows"][0]["photo_flags"]["person_foto"], 1)
        self.assertEqual(matrix["rows"][1]["photo_flags"]["person_foto"], 0)
        self.assertEqual(matrix["reward_total"], 2)

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
        self.assertTrue(legacy_routes)
        self.assertTrue(csv_routes)
        self.assertTrue(csv_head_routes)
        self.assertTrue(matrix_csv_routes)

    def test_summary_repository_uses_parameter_placeholders(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "backend" / "app" / "repositories" / "summary.py").read_text()
        self.assertIn(" = ?", source)
        self.assertIn(" like ?", source)


if __name__ == "__main__":
    unittest.main()
