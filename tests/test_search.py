from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sqlite3
import unittest

from backend.app.main import app
from backend.app.repositories.search import search_all, search_suggestions
from backend.app.routers.templates import templates


class TemplateRequest:
    def url_for(self, name: str, **path_params) -> str:
        if name == "static":
            return f"/static/{path_params.get('path', '')}"
        return f"/{name}"


class SearchRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self._create_db()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_db(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("create table guide (id integer primary key, name text)")
            connection.execute("create table guide_lev_0 (id integer primary key, idl integer, name text)")
            connection.execute("create table guide_lev_1 (id integer primary key, idl integer, name text)")
            connection.execute("create table guide_lev_2 (id integer primary key, idl integer, name text)")
            connection.execute("create table guide_lev_3 (id integer primary key, idl integer, name text)")
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
                    comment text
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
                    number integer,
                    instock boolean,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer,
                    front_foto text,
                    back_foto text,
                    id_link text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
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
                    number integer,
                    instock boolean,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer,
                    front_foto text,
                    back_foto text,
                    id_link text,
                    book1_foto text,
                    book2_foto text
                )
                """
            )
            connection.execute("insert into guide (id, name) values (1, 'лейтенант')")
            connection.execute("insert into guide_lev_0 (id, idl, name) values (1, 0, 'СССР')")
            connection.execute("insert into guide_lev_1 (id, idl, name) values (1, 1, 'Ордена')")
            connection.execute("insert into guide_lev_2 (id, idl, name) values (1, 1, 'Боевые')")
            connection.execute("insert into guide_lev_3 (id, idl, name) values (1, 1, 'Орден Тестовый')")
            connection.execute(
                """
                insert into person (
                    id, fio, birthday, id_rank, person_foto, main_foto, rewards_foto,
                    book1_foto, book2_foto, card1_foto, card2_foto
                )
                values (1, 'Андросов Леонид Тест', '1913-05-09', 1, 'Source/1/person.jpg', '', '', 'Source/1/book1.jpg', '', '', '')
                """
            )
            connection.execute(
                """
                insert into rewards (id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number, instock, id_link)
                values (10, 1, 1, 1, 1, 1, 777, 1, 'archive-link')
                """
            )
            connection.execute(
                """
                insert into mark (id, id_gos, id_catigory, id_sub_catigory, id_name, number, instock, id_link)
                values (20, 1, 1, 1, 1, 42, 0, 'mark-link')
                """
            )
            connection.commit()
        finally:
            connection.close()

    def test_search_persons_by_partial_cyrillic_last_name(self) -> None:
        result = search_all(self.db_path, "Андрос", scope="persons")
        self.assertEqual(result["counts"]["persons"], 1)
        self.assertEqual(result["persons"][0]["id"], 1)

    def test_search_persons_by_lowercase_cyrillic(self) -> None:
        result = search_all(self.db_path, "андросов", scope="persons")
        self.assertEqual(result["counts"]["persons"], 1)

    def test_search_rewards_by_number(self) -> None:
        result = search_all(self.db_path, "777", scope="rewards")
        self.assertEqual(result["counts"]["rewards"], 1)
        self.assertEqual(result["rewards"][0]["id"], 10)

    def test_search_marks_by_number(self) -> None:
        result = search_all(self.db_path, "42", scope="marks")
        self.assertEqual(result["counts"]["marks"], 1)
        self.assertEqual(result["marks"][0]["id"], 20)

    def test_empty_query_returns_no_huge_result(self) -> None:
        result = search_all(self.db_path, "", scope="all")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["persons"], [])
        self.assertEqual(result["rewards"], [])
        self.assertEqual(result["marks"], [])

    def test_empty_query_with_persons_scope_returns_persons(self) -> None:
        result = search_all(self.db_path, "", scope="persons")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["counts"]["persons"], 1)
        self.assertEqual(result["persons"][0]["id"], 1)
        self.assertEqual(result["rewards"], [])
        self.assertEqual(result["marks"], [])

    def test_empty_query_with_rewards_scope_returns_rewards(self) -> None:
        result = search_all(self.db_path, "", scope="rewards")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["counts"]["rewards"], 1)
        self.assertEqual(result["rewards"][0]["id"], 10)
        self.assertEqual(result["persons"], [])
        self.assertEqual(result["marks"], [])

    def test_empty_query_with_marks_scope_returns_marks(self) -> None:
        result = search_all(self.db_path, "", scope="marks")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["counts"]["marks"], 1)
        self.assertEqual(result["marks"][0]["id"], 20)
        self.assertEqual(result["persons"], [])
        self.assertEqual(result["rewards"], [])

    def test_person_results_include_photo_document_flags(self) -> None:
        result = search_all(self.db_path, "Андрос", scope="persons")
        person = result["persons"][0]
        self.assertEqual(person["person_foto_flag"], 1)
        self.assertEqual(person["main_foto_flag"], 0)
        self.assertEqual(person["rewards_foto_flag"], 0)
        self.assertEqual(person["book1_foto_flag"], 1)
        self.assertEqual(person["book2_foto_flag"], 0)
        self.assertEqual(person["card1_foto_flag"], 0)
        self.assertEqual(person["card2_foto_flag"], 0)

    def test_search_suggestions_are_loaded_from_database(self) -> None:
        suggestions = search_suggestions(self.db_path)
        self.assertIn("Андросов Леонид Тест", suggestions["persons"])
        self.assertIn("Орден Тестовый", suggestions["rewards"])
        self.assertIn("Орден Тестовый", suggestions["marks"])

    def test_query_with_quotes_is_safe(self) -> None:
        result = search_all(self.db_path, "Андросов ' OR 1=1 --", scope="all")
        self.assertEqual(result["total"], 0)

    def test_legacy_search_get_route_is_registered(self) -> None:
        methods = [
            route.methods
            for route in app.routes
            if getattr(route, "path", None) == "/legacy" and "GET" in getattr(route, "methods", set())
        ]
        self.assertTrue(methods)

    def test_search_templates_disable_browser_autocomplete(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_template = (root / "backend" / "app" / "templates" / "search.html").read_text(encoding="utf-8")
        legacy_template = (root / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn('autocomplete="off"', search_template)
        self.assertIn('autocomplete="off"', legacy_template)
        self.assertIn('scope == "all"', legacy_template)

    def test_search_category_label_uses_reward_name_text(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_template = (root / "backend" / "app" / "templates" / "search.html").read_text(encoding="utf-8")
        legacy_template = (root / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn('value="rewards" {% if scope == "rewards" %}selected{% endif %}>Наименование награды', search_template)
        self.assertIn('value="rewards" {% if scope == "rewards" %}selected{% endif %}>Наименование награды', legacy_template)
        self.assertNotIn('value="rewards" {% if scope == "rewards" %}selected{% endif %}>Награды</option>', search_template)
        self.assertNotIn('value="rewards" {% if scope == "rewards" %}selected{% endif %}>Награды</option>', legacy_template)

    def test_person_search_results_render_user_columns_without_id_header(self) -> None:
        results = search_all(self.db_path, "Андрос", scope="persons")
        rendered = templates.env.get_template("search.html").render(
            request=TemplateRequest(),
            settings=SimpleNamespace(write_mode=False),
            q="Андрос",
            scope="persons",
            mode="contains",
            results=results,
            message="",
            search_suggestions=search_suggestions(self.db_path),
            search_return_to="/search?q=%D0%90%D0%BD%D0%B4%D1%80%D0%BE%D1%81&scope=persons&mode=contains",
        )
        self.assertNotIn("<th>ID</th>", rendered)
        self.assertIn("<th>№</th>", rendered)
        self.assertIn("Фото кавалера", rendered)
        self.assertIn("Фото наградной книжки, сторона 1", rendered)
        self.assertIn("<td>1</td>", rendered)
        self.assertIn("<td>0</td>", rendered)
        self.assertIn("return_to=", rendered)
        self.assertIn("Андросов Леонид Тест", rendered)
        self.assertIn("<datalist id=\"search-suggestions\">", rendered)

    def test_search_csv_uses_browser_save_as_form(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_template = (root / "backend" / "app" / "templates" / "search.html").read_text(encoding="utf-8")
        legacy_template = (root / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn('method="get" action="/search.csv" data-save-as-form', search_template)
        self.assertIn('method="get" action="/search.csv" data-save-as-form', legacy_template)
        self.assertNotIn('action="/search.csv/save"', search_template)
        self.assertNotIn('action="/search.csv/save"', legacy_template)


if __name__ == "__main__":
    unittest.main()
