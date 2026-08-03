from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from backend.app.repositories.legacy_rewards import (
    legacy_rewards_filter_options,
    legacy_rewards_totals,
    list_legacy_reward_persons,
    normalized_legacy_rewards_filters,
    normalized_legacy_rewards_sort,
    person_name_sort_key,
)


class LegacyRewardsFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "MyDatabase.sqlite"
        self._create_db()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_db(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("create table guide (id integer primary key, name text)")
            for level in range(4):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, idl integer, name text)")
            connection.execute(
                """
                create table person (
                    id integer primary key,
                    fio text,
                    birthday text,
                    id_rank integer,
                    main_foto text,
                    person_foto text
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
                    instock text,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer
                )
                """
            )
            connection.execute("insert into guide values (1, 'капитан')")
            connection.execute("insert into guide values (2, 'майор')")
            connection.execute("insert into guide_lev_0 values (1, -1, 'СССР')")
            connection.execute("insert into guide_lev_1 values (1, 1, 'Ордена')")
            connection.execute("insert into guide_lev_1 values (9, 9, 'Чужая категория')")
            connection.execute("insert into guide_lev_2 values (1, 1, 'Боевые')")
            connection.execute("insert into guide_lev_2 values (9, 9, 'Чужая подкатегория')")
            connection.execute("insert into guide_lev_3 values (1, 1, 'Орден Красной Звезды')")
            connection.execute("insert into guide_lev_3 values (2, 1, 'Медаль За отвагу')")
            connection.execute("insert into guide_lev_3 values (9, 9, 'Чужое наименование')")
            connection.execute("insert into person values (1, 'Капитан Тест', '1913-05-09', 1, '', '')")
            connection.execute("insert into person values (2, 'Майор Тест', '1914-01-01', 2, '', '')")
            connection.execute("insert into person values (3, 'Капитан без ордена', '1915', 1, '', '')")
            connection.execute(
                "insert into rewards values (10, 1, 1, 1, 1, 1, 'true', '2024-01-01', 100, 200)"
            )
            connection.execute(
                "insert into rewards values (11, 1, 1, 1, 1, 2, 'false', '2024-02-01', 300, 400)"
            )
            connection.execute(
                "insert into rewards values (12, 2, 1, 1, 1, 1, 'true', '2024-03-01', 500, 600)"
            )
            connection.commit()
        finally:
            connection.close()

    def test_empty_filters_show_all_persons(self) -> None:
        rows = list_legacy_reward_persons(self.db_path, normalized_legacy_rewards_filters())
        self.assertEqual([row["id"] for row in rows], [3, 1, 2])
        self.assertEqual([row["fio"] for row in rows], ["Капитан без ордена", "Капитан Тест", "Майор Тест"])

    def test_default_person_order_uses_canonical_russian_key_not_creation_order(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            rows = [
                (20, "яков Тест", "1901", 1, "", ""),
                (21, "алексей Тест", "1901", 1, "", ""),
                (22, "Москва Тест", "1901", 1, "", ""),
                (23, "Ёлкин Тест", "1901", 1, "", ""),
                (24, "Елкин Тест", "1901", 1, "", ""),
                (25, "Анна-Мария Тест", "1901", 1, "", ""),
                (26, "Анна Мария Тест", "1901", 1, "", ""),
                (27, "ЕЛКИН ТЕСТ", "1901", 1, "", ""),
            ]
            connection.executemany("insert into person values (?, ?, ?, ?, ?, ?)", rows)
            connection.commit()
        finally:
            connection.close()

        result = list_legacy_reward_persons(self.db_path, normalized_legacy_rewards_filters())
        qa_rows = [row for row in result if int(row["id"]) >= 20]

        self.assertEqual(
            [int(row["id"]) for row in qa_rows],
            [21, 26, 25, 23, 24, 27, 22, 20],
        )
        self.assertEqual(person_name_sort_key("  ЁЛКИН Тест  "), "елкин тест")
        self.assertLess(person_name_sort_key("Анна Мария"), person_name_sort_key("Анна-Мария"))

    def test_non_default_sort_keeps_alphabetical_ties_and_existing_edit_repositions_only_target(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("insert into person values (30, 'Я новый', '1901', 1, '', '')")
            connection.execute("insert into person values (31, 'А новый', '1902', 1, '', '')")
            connection.execute("insert into rewards values (30, 30, 1, 1, 1, 1, 'true', '', 0, 0)")
            connection.execute("insert into rewards values (31, 30, 1, 1, 1, 1, 'true', '', 0, 0)")
            connection.execute("insert into rewards values (32, 30, 1, 1, 1, 1, 'true', '', 0, 0)")
            connection.commit()
        finally:
            connection.close()

        filters = normalized_legacy_rewards_filters()
        by_rewards = list_legacy_reward_persons(
            self.db_path,
            filters,
            normalized_legacy_rewards_sort("rewards_count", "desc"),
        )
        self.assertEqual(int(by_rewards[0]["id"]), 30)
        zero_reward_names = [row["fio"] for row in by_rewards if int(row["rewards_count"]) == 0]
        self.assertEqual(zero_reward_names, sorted(zero_reward_names, key=person_name_sort_key))

        before = [int(row["id"]) for row in list_legacy_reward_persons(self.db_path, filters)]
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("update person set fio = 'АА изменённый' where id = 30")
            connection.commit()
        finally:
            connection.close()
        after = [int(row["id"]) for row in list_legacy_reward_persons(self.db_path, filters)]

        self.assertNotEqual(before.index(30), after.index(30))
        self.assertEqual([person_id for person_id in before if person_id != 30], [person_id for person_id in after if person_id != 30])

    def test_rank_filter(self) -> None:
        rows = list_legacy_reward_persons(self.db_path, normalized_legacy_rewards_filters(rank_id="1"))
        self.assertEqual([row["id"] for row in rows], [3, 1])

    def test_reward_tree_filter(self) -> None:
        rows = list_legacy_reward_persons(self.db_path, normalized_legacy_rewards_filters(name_id="1"))
        self.assertEqual([row["id"] for row in rows], [1, 2])

    def test_combined_rank_and_reward_filter(self) -> None:
        rows = list_legacy_reward_persons(self.db_path, normalized_legacy_rewards_filters(rank_id="1", name_id="1"))
        self.assertEqual([row["id"] for row in rows], [1])

    def test_totals_change_with_filters(self) -> None:
        all_totals = legacy_rewards_totals(self.db_path, normalized_legacy_rewards_filters())
        filtered = legacy_rewards_totals(self.db_path, normalized_legacy_rewards_filters(rank_id="1", name_id="1"))
        self.assertEqual(all_totals["persons_total"], 3)
        self.assertEqual(all_totals["rewards_total"], 3)
        self.assertEqual(filtered["persons_total"], 1)
        self.assertEqual(filtered["rewards_total"], 1)
        self.assertEqual(filtered["price_purchase_sum"], 100)

    def test_empty_string_filters_normalize_to_all(self) -> None:
        filters = normalized_legacy_rewards_filters(rank_id="", country_id="", category_id="", subcategory_id="", name_id="")
        self.assertIsNone(filters.rank_id)
        self.assertIsNone(filters.country_id)
        self.assertEqual(len(list_legacy_reward_persons(self.db_path, filters)), 3)

    def test_filter_options_are_cascaded_by_selected_parent(self) -> None:
        empty_options = legacy_rewards_filter_options(self.db_path, normalized_legacy_rewards_filters())
        self.assertEqual(empty_options["categories"], [])
        self.assertEqual(empty_options["subcategories"], [])
        self.assertEqual(empty_options["names"], [])

        country_options = legacy_rewards_filter_options(
            self.db_path,
            normalized_legacy_rewards_filters(country_id="1"),
        )
        self.assertEqual([row["id"] for row in country_options["categories"]], [1])
        self.assertEqual(country_options["subcategories"], [])

        category_options = legacy_rewards_filter_options(
            self.db_path,
            normalized_legacy_rewards_filters(country_id="1", category_id="1", subcategory_id="1"),
        )
        self.assertEqual([row["id"] for row in category_options["subcategories"]], [1])
        self.assertEqual([row["id"] for row in category_options["names"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
