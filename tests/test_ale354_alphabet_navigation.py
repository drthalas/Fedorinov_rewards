from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.repositories.legacy_rewards import (
    LEGACY_PERSON_ALPHABET,
    legacy_rewards_alphabet_counts,
    list_legacy_reward_person_group,
    normalized_legacy_rewards_filters,
    normalized_legacy_rewards_sort,
    person_name_initial,
)
from backend.app.routers import legacy as legacy_router


ROOT = Path(__file__).resolve().parents[1]


class Ale354AlphabetRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "MyDatabase.sqlite"
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("create table guide (id integer primary key, name text)")
            connection.execute(
                "create table person (id integer primary key, fio text, birthday text, id_rank integer, main_foto text, person_foto text)"
            )
            connection.execute(
                "create table rewards (id integer primary key, person_id integer, id_gos integer, id_catigory integer, id_sub_catigory integer, id_name integer)"
            )
            connection.execute("insert into guide values (1, 'майор')")
            connection.executemany(
                "insert into person values (?, ?, '1900', 1, '', '')",
                [
                    (1, "  алексей Тест"),
                    (2, "Борис Тест"),
                    (3, "Ёлкин Тест"),
                    (4, "елена Тест"),
                    (5, "Яков Тест"),
                    (6, "Latin Test"),
                ],
            )
            connection.executemany(
                "insert into rewards values (?, ?, 1, 1, 1, 1)",
                [(10, 1), (11, 3), (12, 3)],
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_alphabet_is_single_russian_column_and_yo_normalizes_to_e(self) -> None:
        self.assertEqual(len(LEGACY_PERSON_ALPHABET), 32)
        self.assertNotIn("Ё", LEGACY_PERSON_ALPHABET)
        self.assertEqual(person_name_initial("  ЁЛКИН"), "Е")
        self.assertEqual(person_name_initial("елена"), "Е")

    def test_group_query_returns_only_requested_letter_in_canonical_order(self) -> None:
        rows = list_legacy_reward_person_group(
            self.db_path,
            normalized_legacy_rewards_filters(),
            letter="Ё",
        )
        self.assertEqual([int(row["id"]) for row in rows], [4, 3])
        self.assertEqual([int(row["rewards_count"]) for row in rows], [0, 2])

    def test_global_query_ignores_active_letter_and_searches_all_names(self) -> None:
        rows = list_legacy_reward_person_group(
            self.db_path,
            normalized_legacy_rewards_filters(),
            letter="А",
            query="тест",
        )
        self.assertEqual([int(row["id"]) for row in rows], [1, 2, 4, 3, 5])

    def test_non_default_sort_is_applied_inside_group(self) -> None:
        rows = list_legacy_reward_person_group(
            self.db_path,
            normalized_legacy_rewards_filters(),
            normalized_legacy_rewards_sort("rewards_count", "desc"),
            letter="Е",
        )
        self.assertEqual([int(row["id"]) for row in rows], [3, 4])

    def test_alphabet_counts_are_filter_aware_and_exclude_non_russian_initials(self) -> None:
        counts = legacy_rewards_alphabet_counts(self.db_path, normalized_legacy_rewards_filters())
        self.assertEqual(counts["А"], 1)
        self.assertEqual(counts["Е"], 2)
        self.assertEqual(counts["Я"], 1)
        self.assertEqual(sum(counts.values()), 5)


class Ale354AlphabetUiContractTests(unittest.TestCase):
    def test_variant_a_is_inside_existing_list_and_has_hover_active_disabled_states(self) -> None:
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")
        self.assertIn('data-person-list data-active-letter=', template)
        self.assertIn('class="legacy-alphabet-index"', template)
        self.assertLess(template.index('class="legacy-alphabet-index"'), template.index("{% for person in persons %}"))
        self.assertIn("width: 22px", styles)
        self.assertIn(".legacy-alphabet-letter:not(:disabled):hover", styles)
        self.assertIn(".legacy-alphabet-letter.active", styles)
        self.assertIn(".legacy-alphabet-letter:disabled", styles)

    def test_client_uses_list_fragments_and_keeps_search_server_global(self) -> None:
        script = (ROOT / "backend/app/static/legacy_rewards.js").read_text(encoding="utf-8")
        self.assertIn('headers["X-Legacy-Rewards-List"] = "1"', script)
        self.assertIn('url.searchParams.set("person_q", cleanQuery)', script)
        self.assertIn('url.searchParams.delete("person_q")', script)
        self.assertIn("replaceList: true", script)
        self.assertNotIn("name.includes(query)", script)


class _Request:
    def __init__(self, headers=None) -> None:
        self.headers = headers or {}


class Ale354AlphabetRouteTests(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        db_path = root / "database" / "MyDatabase.sqlite"
        db_path.parent.mkdir(parents=True)
        db_path.touch()
        return Settings(
            rewards_data_dir=root,
            rewards_db_path=db_path,
            read_only=True,
            write_mode=False,
        )

    def test_normal_rewards_route_uses_one_group_and_never_full_list(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = self._settings(Path(tmp))
            captured = {}

            def template_response(_request, name, context):
                captured.update(context)
                return {"name": name, "context": context}

            rows = [{"id": 1, "fio": "А первый", "birthday": "1900", "rewards_count": 0}]
            counts = {letter: (1 if letter == "А" else 0) for letter in LEGACY_PERSON_ALPHABET}
            with (
                patch.object(legacy_router, "get_settings", return_value=settings),
                patch.object(legacy_router, "legacy_rewards_filter_options", return_value={"ranks": [], "countries": [], "categories": [], "subcategories": [], "names": []}),
                patch.object(legacy_router, "legacy_rewards_filter_cascade", return_value={}),
                patch.object(legacy_router, "legacy_rewards_alphabet_counts", return_value=counts),
                patch.object(legacy_router, "list_legacy_reward_person_group", return_value=rows) as group_list,
                patch.object(legacy_router, "list_legacy_reward_persons", create=True) as full_list,
                patch.object(legacy_router, "legacy_rewards_totals", return_value={"persons_total": 1}),
                patch.object(legacy_router, "count_marks", return_value=0),
                patch.object(legacy_router, "list_marks", return_value=[]),
                patch.object(legacy_router.templates, "TemplateResponse", side_effect=template_response),
            ):
                result = legacy_router.legacy_index(_Request(), tab="rewards")

            self.assertEqual(result["name"], "legacy.html")
            self.assertEqual(captured["rewards_active_letter"], "А")
            self.assertEqual(len(captured["persons"]), 1)
            group_list.assert_called_once()
            self.assertEqual(group_list.call_args.kwargs["letter"], "А")
            self.assertEqual(group_list.call_args.kwargs["query"], "")
            full_list.assert_not_called()

    def test_selected_person_letter_wins_and_incompatible_quick_search_is_cleared(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = self._settings(Path(tmp))
            captured = {}

            def template_response(_request, name, context):
                captured.update(context)
                return {"name": name, "context": context}

            selected = {"id": 9, "fio": "Я новый", "birthday": "1900", "rewards_count": 0}
            counts = {letter: (1 if letter == "Я" else 0) for letter in LEGACY_PERSON_ALPHABET}
            with (
                patch.object(legacy_router, "get_settings", return_value=settings),
                patch.object(legacy_router, "get_person", return_value=selected),
                patch.object(legacy_router, "legacy_rewards_filter_options", return_value={"ranks": [], "countries": [], "categories": [], "subcategories": [], "names": []}),
                patch.object(legacy_router, "legacy_rewards_filter_cascade", return_value={}),
                patch.object(legacy_router, "legacy_rewards_alphabet_counts", return_value=counts),
                patch.object(legacy_router, "list_legacy_reward_person_group", return_value=[selected]) as group_list,
                patch.object(legacy_router, "legacy_rewards_totals", return_value={"persons_total": 1}),
                patch.object(legacy_router, "count_marks", return_value=0),
                patch.object(legacy_router, "list_marks", return_value=[]),
                patch.object(legacy_router, "_populate_selected_person_context", side_effect=lambda context, *_args: context.update({"selected_person": selected})),
                patch.object(legacy_router.templates, "TemplateResponse", side_effect=template_response),
            ):
                legacy_router.legacy_index(
                    _Request(),
                    tab="rewards",
                    person_id=9,
                    letter="М",
                    person_q="старый поиск",
                )

            self.assertEqual(captured["rewards_active_letter"], "Я")
            self.assertEqual(captured["person_query"], "")
            self.assertIn("letter=%D0%AF", captured["selected_person_return"])
            group_list.assert_called_once()
            self.assertEqual(group_list.call_args.kwargs["letter"], "Я")
            self.assertEqual(group_list.call_args.kwargs["query"], "")


if __name__ == "__main__":
    unittest.main()
