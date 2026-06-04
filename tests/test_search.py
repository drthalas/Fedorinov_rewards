from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from backend.app.main import app
from backend.app.repositories.search import search_all


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
        with sqlite3.connect(self.db_path) as connection:
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
                "insert into person (id, fio, birthday, id_rank) values (1, 'Андросов Леонид Тест', '1913-05-09', 1)"
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


if __name__ == "__main__":
    unittest.main()
