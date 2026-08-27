from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.app.repositories.reward_reference import list_reward_references


ROOT = Path(__file__).resolve().parents[1]


class RewardReferenceSortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "rewards.sqlite"
        connection = sqlite3.connect(self.db_path)
        try:
            connection.executescript(
                """
                create table guide_lev_0 (id integer primary key, name text);
                create table guide_lev_1 (id integer primary key, idl integer, name text);
                create table guide_lev_2 (id integer primary key, idl integer, name text);
                create table guide_lev_3 (id integer primary key, idl integer, name text);
                create table guide_lev_4 (id integer primary key, idl integer, name text);
                insert into guide_lev_0 values (1, 'Страна');
                insert into guide_lev_1 values (1, 1, 'Категория');
                insert into guide_lev_2 values (1, 1, 'Подкатегория');
                insert into guide_lev_3 values (9, 1, 'якорь');
                insert into guide_lev_3 values (8, 1, 'Ёлка');
                insert into guide_lev_3 values (7, 1, 'ель');
                insert into guide_lev_3 values (6, 1, 'Арка');
                """
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reward_names_use_casefolded_russian_alphabetical_order(self) -> None:
        rows = list_reward_references(self.db_path)
        self.assertEqual([row["id_name"] for row in rows], [6, 8, 7, 9])


class RewardNameTypeaheadContractTests(unittest.TestCase):
    def test_typeahead_release_uses_a_fresh_static_cache_key(self) -> None:
        templates = (ROOT / "backend/app/routers/templates.py").read_text(encoding="utf-8")
        self.assertIn(
            'STATIC_ASSET_VERSION = "20260827-ale407-text-editors"',
            templates,
        )

    def test_reward_name_enables_prefix_typeahead_without_new_search_input(self) -> None:
        template = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")
        self.assertIn('data-styled-select-typeahead="prefix"', template)
        self.assertNotIn('type="search"', template)

    def test_shared_styled_select_uses_prefix_matching_and_russian_normalization(self) -> None:
        script = (ROOT / "backend/app/static/custom_select.js").read_text(encoding="utf-8")
        self.assertIn('select.dataset.styledSelectTypeahead === "prefix"', script)
        self.assertIn('.toLocaleLowerCase("ru-RU").replaceAll("ё", "е")', script)
        self.assertIn("startsWith(normalizedQuery)", script)
        self.assertIn("option.hidden = !matches.has(index)", script)
        self.assertIn("visibleOptionButtons()[0]", script)
        self.assertIn('event.key === "Backspace"', script)

    def test_hidden_typeahead_options_override_the_base_display_rule(self) -> None:
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        base_rule = styles.index(".styled-select-option {")
        hidden_rule = styles.index(".styled-select-option[hidden] {")
        self.assertGreater(hidden_rule, base_rule)
        self.assertIn("display: none;", styles[hidden_rule : hidden_rule + 80])


if __name__ == "__main__":
    unittest.main()
