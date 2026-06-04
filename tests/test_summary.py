from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest

from backend.app.main import app
from backend.app.repositories.summary import parse_optional_int, normalized_summary_filters, summary_csv_text, summary_rows
from backend.app.routers.legacy import summary_csv


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
            connection.execute(
                """
                create table rewards (
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
            connection.execute(
                """
                insert into rewards
                values (10, 1, 1, 1, 1, 'extra-link', 1, '2024-01-01', 100, 200)
                """
            )
            connection.execute(
                """
                insert into rewards
                values (11, 1, 1, 1, 1, 'other-link', 0, '2024-02-01', 300, 400)
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

    def test_summary_csv_route_returns_csv_response(self) -> None:
        response = summary_csv(country_id="", category_id="", subcategory_id="", name_id="", extra="", include_marks="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.media_type)
        self.assertIn("Орден Тестовый", response.body.decode("utf-8"))

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
        self.assertTrue(legacy_routes)
        self.assertTrue(csv_routes)
        self.assertTrue(csv_head_routes)

    def test_summary_repository_uses_parameter_placeholders(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "backend" / "app" / "repositories" / "summary.py").read_text()
        self.assertIn(" = ?", source)
        self.assertIn(" like ?", source)


if __name__ == "__main__":
    unittest.main()
