from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sqlite3
import unittest

from backend.app.main import app
from backend.app.repositories.search import search_all, search_suggestions
from backend.app.routers.search import _search_csv_text
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
                insert into rewards (
                    id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number, instock,
                    date_purchase, price_purchase, price_now, front_foto, back_foto, id_link, book1_foto, book2_foto, reward_list
                )
                values (
                    10, 1, 1, 1, 1, 1, 777, 1,
                    '2024-01-02', 500, 700, 'Source/1/10/front.jpg', '', 'archive-link',
                    'Source/1/10/book1.jpg', '', 'Source/1/10/list.jpg'
                )
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

    def test_search_reward_number_scope_finds_only_by_number(self) -> None:
        by_number = search_all(self.db_path, "777", scope="reward_numbers")
        self.assertEqual(by_number["scope"], "reward_numbers")
        self.assertEqual(by_number["counts"]["rewards"], 1)
        self.assertEqual(by_number["rewards"][0]["number"], 777)

        by_name = search_all(self.db_path, "Орден", scope="reward_numbers")
        self.assertEqual(by_name["counts"]["rewards"], 0)

    def test_empty_query_with_reward_number_scope_does_not_load_everything(self) -> None:
        result = search_all(self.db_path, "", scope="reward_numbers")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["rewards"], [])

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

    def test_reward_results_include_photo_document_flags_and_internal_paths_for_preview(self) -> None:
        result = search_all(self.db_path, "Орден", scope="rewards")
        reward = result["rewards"][0]
        self.assertEqual(reward["person_book1_foto_flag"], 1)
        self.assertEqual(reward["person_book2_foto_flag"], 0)
        self.assertEqual(reward["person_card1_foto_flag"], 0)
        self.assertEqual(reward["person_card2_foto_flag"], 0)
        self.assertEqual(reward["front_foto_flag"], 1)
        self.assertEqual(reward["back_foto_flag"], 0)
        self.assertEqual(reward["reward_book1_foto_flag"], 1)
        self.assertEqual(reward["reward_book2_foto_flag"], 0)
        self.assertEqual(reward["reward_list_flag"], 1)
        self.assertEqual(reward["front_foto"], "Source/1/10/front.jpg")
        self.assertEqual(reward["reward_book1_foto"], "Source/1/10/book1.jpg")

    def test_search_sorting_by_columns(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into person (id, fio, birthday, id_rank) values (2, 'Белов Борис', '1910-01-01', 1)")
            connection.execute(
                """
                insert into rewards (
                    id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number, instock,
                    date_purchase, price_purchase, price_now
                )
                values (11, 2, 1, 1, 1, 1, 111, 1, '2026-05-01', 1000, 1200)
                """
            )
        by_number = search_all(self.db_path, "", scope="rewards", sort_by="number", sort_dir="asc")
        self.assertEqual([row["number"] for row in by_number["rewards"]], [111, 777])
        by_birth = search_all(self.db_path, "", scope="rewards", sort_by="birthday", sort_dir="desc")
        self.assertEqual(by_birth["rewards"][0]["fio"], "Андросов Леонид Тест")

    def test_search_results_are_paginated_with_range_metadata(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            for idx in range(2, 63):
                connection.execute(
                    """
                    insert into rewards (
                        id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number, instock
                    )
                    values (?, 1, 1, 1, 1, 1, ?, 1)
                    """,
                    (idx + 100, idx),
                )

        first_page = search_all(self.db_path, "", scope="rewards", limit=50, page=1, sort_by="number", sort_dir="asc")
        second_page = search_all(self.db_path, "", scope="rewards", limit=50, page=2, sort_by="number", sort_dir="asc")
        last_page = search_all(self.db_path, "", scope="rewards", limit=50, page=99, sort_by="number", sort_dir="asc")

        self.assertEqual(first_page["total"], 62)
        self.assertEqual(first_page["range_start"], 1)
        self.assertEqual(first_page["range_end"], 50)
        self.assertEqual(first_page["page"], 1)
        self.assertEqual(first_page["pages"], 2)
        self.assertEqual(len(first_page["rewards"]), 50)
        self.assertEqual(second_page["range_start"], 51)
        self.assertEqual(second_page["range_end"], 62)
        self.assertEqual(second_page["page"], 2)
        self.assertEqual(len(second_page["rewards"]), 12)
        self.assertEqual(last_page["page"], 2)

    def test_search_suggestions_are_loaded_from_database(self) -> None:
        suggestions = search_suggestions(self.db_path)
        self.assertIn("Андросов Леонид Тест", suggestions["persons"])
        self.assertIn("Орден Тестовый", suggestions["rewards"])
        self.assertEqual(suggestions["reward_numbers"], [])
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
        styles = (root / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('class="search-scope-control"', search_template)
        self.assertIn('class="search-scope-control"', legacy_template)
        self.assertIn('value="rewards" title="Наименование награды" {% if scope == "rewards" %}selected{% endif %}>Наименование награды', search_template)
        self.assertIn('value="rewards" title="Наименование награды" {% if scope == "rewards" %}selected{% endif %}>Наименование награды', legacy_template)
        self.assertIn('value="reward_numbers" title="Номер награды" {% if scope == "reward_numbers" %}selected{% endif %}>Номер награды', search_template)
        self.assertIn('value="reward_numbers" title="Номер награды" {% if scope == "reward_numbers" %}selected{% endif %}>Номер награды', legacy_template)
        self.assertIn("minmax(240px, 280px)", styles)
        self.assertIn(".search-scope-control select", styles)
        self.assertNotIn('value="rewards" {% if scope == "rewards" %}selected{% endif %}>Награды</option>', search_template)
        self.assertNotIn('value="rewards" {% if scope == "rewards" %}selected{% endif %}>Награды</option>', legacy_template)

    def test_search_templates_render_pagination_controls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_template = (root / "backend" / "app" / "templates" / "search.html").read_text(encoding="utf-8")
        legacy_template = (root / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn("search_pagination_controls", search_template)
        self.assertIn("search_pagination_controls", legacy_template)
        self.assertIn("Показаны {{ pagination.range_start }}–{{ pagination.range_end }} из {{ pagination.total }}", search_template)
        self.assertIn("Предыдущая", search_template)
        self.assertIn("Следующая", search_template)
        self.assertIn("Последняя", search_template)
        self.assertIn('data-sync-row-height data-row-height-storage-key="search-results-row-height"', search_template)
        self.assertIn('data-sync-row-height data-row-height-storage-key="search-results-row-height"', legacy_template)

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
            sort="",
            dir="asc",
            search_pagination=None,
            search_sort={"sort": "", "dir": "asc", "urls": {"fio": "#", "rank_name": "#", "birthday": "#", "person_foto_flag": "#", "main_foto_flag": "#", "rewards_foto_flag": "#", "book1_foto_flag": "#", "book2_foto_flag": "#", "card1_foto_flag": "#", "card2_foto_flag": "#"}},
        )
        self.assertNotIn("<th>ID</th>", rendered)
        self.assertIn("<th>№</th>", rendered)
        self.assertIn("Фото кавалера", rendered)
        self.assertIn("Фото наградной книжки, сторона 1", rendered)
        self.assertIn("search-photo-flag\">1</span>", rendered)
        self.assertIn("search-photo-flag\">0</span>", rendered)
        self.assertIn("return_to=", rendered)
        self.assertIn("Андросов Леонид Тест", rendered)
        self.assertIn("<datalist id=\"search-suggestions\">", rendered)

    def test_reward_search_results_render_document_columns_and_sort_links(self) -> None:
        results = search_all(self.db_path, "Орден", scope="rewards", sort_by="number", sort_dir="asc")
        sort_urls = {
            "fio": "/search?q=Орден&scope=rewards&mode=contains&sort=fio&dir=asc",
            "rank_name": "#",
            "birthday": "#",
            "person_book1_foto_flag": "#",
            "person_book2_foto_flag": "#",
            "person_card1_foto_flag": "#",
            "person_card2_foto_flag": "#",
            "name": "#",
            "number": "/search?q=Орден&scope=rewards&mode=contains&sort=number&dir=desc",
            "date_purchase": "#",
            "price_purchase": "#",
            "price_now": "#",
            "front_foto_flag": "#",
            "back_foto_flag": "#",
            "reward_book1_foto_flag": "#",
            "reward_book2_foto_flag": "#",
            "reward_list_flag": "#",
        }
        rendered = templates.env.get_template("search.html").render(
            request=TemplateRequest(),
            settings=SimpleNamespace(write_mode=False),
            q="Орден",
            scope="rewards",
            mode="contains",
            sort="number",
            dir="asc",
            results=results,
            message="",
            search_suggestions=search_suggestions(self.db_path),
            search_return_to="/search?q=%D0%9E%D1%80%D0%B4%D0%B5%D0%BD&scope=rewards&mode=contains&sort=number&dir=asc",
            search_pagination=None,
            search_sort={"sort": "number", "dir": "asc", "urls": sort_urls},
        )
        self.assertIn("Фото учётной карточки, страница 1", rendered)
        self.assertIn("Фото книжки награды, сторона 1", rendered)
        self.assertIn("Фото книжки награды, сторона 2", rendered)
        self.assertIn("Фото награды: аверс", rendered)
        self.assertIn("Наградной лист", rendered)
        self.assertIn("sort=number", rendered)
        self.assertIn("return_to=", rendered)
        self.assertIn("sort%3Dnumber", rendered)
        self.assertIn("search-photo-flag\">1</span>", rendered)
        self.assertNotIn("Source/1/10/front.jpg", rendered)

    def test_search_photo_mode_renders_preview_links_with_existing_lightbox(self) -> None:
        results = search_all(self.db_path, "Орден", scope="rewards")
        original_media_exists = templates.env.globals["media_exists"]
        templates.env.globals["media_exists"] = lambda path: isinstance(path, str) and path.endswith(("front.jpg", "book1.jpg"))
        try:
            rendered = templates.env.get_template("search.html").render(
                request=TemplateRequest(),
                settings=SimpleNamespace(write_mode=False),
                q="Орден",
                scope="rewards",
                mode="contains",
                sort="",
                dir="asc",
                photo_mode="photos",
                results=results,
                message="",
                search_suggestions=search_suggestions(self.db_path),
                search_return_to="/search?q=%D0%9E%D1%80%D0%B4%D0%B5%D0%BD&scope=rewards&mode=contains&photo_mode=photos",
                search_pagination=None,
                search_sort={"sort": "", "dir": "asc", "urls": {"front_foto_flag": "#", "reward_book1_foto_flag": "#"}},
            )
        finally:
            templates.env.globals["media_exists"] = original_media_exists
        self.assertIn('name="photo_mode" value="flags"', rendered)
        self.assertIn('name="photo_mode" value="photos" checked', rendered)
        self.assertIn("search-photo-preview-link", rendered)
        self.assertIn("search-photo-preview", rendered)
        self.assertIn("search-results-table--photo-mode", rendered)
        self.assertIn("search-photo-cell--preview", rendered)
        self.assertIn("search-photo-frame", rendered)
        self.assertIn("search-photo-placeholder", rendered)
        self.assertIn("photo-link", rendered)
        self.assertIn("data-lightbox-caption", rendered)
        self.assertIn("Фото книжки награды, сторона 1", rendered)
        self.assertIn("Source%2F1%2F10%2Ffront.jpg", rendered)
        self.assertNotIn(">Source/1/10/front.jpg<", rendered)

    def test_search_photo_mode_uses_compact_uniform_frames(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_template = (root / "backend" / "app" / "templates" / "search.html").read_text(encoding="utf-8")
        legacy_template = (root / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        styles = (root / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("search-results-table--photo-mode", search_template)
        self.assertIn("search-results-table--photo-mode", legacy_template)
        self.assertIn("search-photo-preview-link search-photo-frame", search_template)
        self.assertIn("search-photo-preview-link search-photo-frame", legacy_template)
        self.assertIn("search-photo-frame search-photo-placeholder", search_template)
        self.assertIn("search-photo-frame search-photo-placeholder", legacy_template)
        self.assertIn("--search-photo-frame-size: 44px", styles)
        self.assertIn("width: min(var(--search-photo-frame-size, 44px), calc(100% - 6px))", styles)
        self.assertIn("height: var(--search-photo-frame-size, 44px)", styles)
        self.assertIn("max-width: calc(100% - 4px)", styles)
        self.assertIn("max-height: calc(100% - 4px)", styles)
        self.assertIn("height: 50px", styles)
        self.assertIn("object-fit: contain", styles)
        self.assertIn("width: auto !important", styles)
        self.assertIn("height: auto !important", styles)

    def test_search_flags_mode_remains_default_and_resizable_table_is_present(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_template = (root / "backend" / "app" / "templates" / "search.html").read_text(encoding="utf-8")
        legacy_template = (root / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        search_js = (root / "backend" / "app" / "static" / "search_results.js").read_text(encoding="utf-8")
        styles = (root / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('name="photo_mode" value="flags"', search_template)
        self.assertIn('name="photo_mode" value="photos"', search_template)
        self.assertIn('name="photo_mode" value="flags"', legacy_template)
        self.assertIn('data-resizable-table', search_template)
        self.assertIn('data-resizable-table', legacy_template)
        self.assertIn("search-column-resize-handle", search_js)
        self.assertIn("search-row-resize-handle", search_js)
        self.assertIn("data-resize-hint", search_js)
        self.assertIn("Изменить ширину колонки", search_js)
        self.assertIn("Изменить высоту строки", search_js)
        self.assertIn("pointerdown", search_js)
        self.assertIn(".search-column-resize-handle::after", styles)
        self.assertIn(".search-row-resize-handle::after", styles)
        self.assertIn("cursor: col-resize", styles)
        self.assertIn("cursor: row-resize", styles)
        self.assertIn("search-photo-preview", styles)
        self.assertIn("object-fit: contain", styles)
        self.assertIn("applyRowPhotoFrameSize", search_js)
        self.assertIn("--search-photo-frame-size", search_js)
        self.assertIn("MAX_PHOTO_FRAME_SIZE", search_js)

    def test_search_row_resize_syncs_all_rows_and_persists_for_next_page(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_js = (root / "backend" / "app" / "static" / "search_results.js").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_ROW_HEIGHT_STORAGE_KEY", search_js)
        self.assertIn("data-sync-row-height", search_js)
        self.assertIn("applyTableRowHeight", search_js)
        self.assertIn("localStorage.setItem(rowHeightStorageKey(table)", search_js)
        self.assertIn("localStorage.getItem(rowHeightStorageKey(table))", search_js)
        self.assertIn("Array.from(table.querySelectorAll(\"tbody tr\"))", search_js)

    def test_search_csv_includes_reward_photo_document_columns(self) -> None:
        text = _search_csv_text("Орден", "rewards", "contains", "number", "asc", db_path=self.db_path)
        self.assertTrue(text.startswith("\ufeff"))
        self.assertIn("Фото наградной книжки, сторона 1", text)
        self.assertIn("Фото учётной карточки, страница 1", text)
        self.assertIn("Фото книжки награды, сторона 1", text)
        self.assertIn("Фото книжки награды, сторона 2", text)
        self.assertIn("Фото награды: аверс", text)
        self.assertIn("Наградной лист", text)
        self.assertIn("Орден Тестовый", text)
        self.assertIn(";1;", text)
        self.assertNotRegex(text, r"(?i)(^|;)true(;|$)")
        self.assertNotRegex(text, r"(?i)(^|;)false(;|$)")
        self.assertNotIn("<img", text)
        self.assertNotIn("Source/1/10/front.jpg", text)
        self.assertNotIn("SourceMark", text)

    def test_search_csv_exports_more_than_current_page(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            for idx in range(2, 63):
                connection.execute(
                    """
                    insert into rewards (
                        id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number, instock
                    )
                    values (?, 1, 1, 1, 1, 1, ?, 1)
                    """,
                    (idx + 100, idx),
                )

        text = _search_csv_text("", "rewards", "contains", "number", "asc", db_path=self.db_path)
        self.assertGreaterEqual(len(text.splitlines()), 63)
        self.assertIn(";62;", text)

    def test_search_csv_uses_excel_semicolon_delimiter(self) -> None:
        text = _search_csv_text("Орден", "rewards", "contains", "number", "asc", db_path=self.db_path)
        first_line = text.splitlines()[0]
        self.assertTrue(first_line.startswith("\ufeffГруппа;ID;ФИО;Звание / специальность"))
        self.assertNotIn("Группа,ID,ФИО", first_line)

    def test_search_csv_uses_browser_save_as_form(self) -> None:
        root = Path(__file__).resolve().parents[1]
        search_template = (root / "backend" / "app" / "templates" / "search.html").read_text(encoding="utf-8")
        legacy_template = (root / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn('method="get" action="/search.csv" data-save-as-form', search_template)
        self.assertIn('method="get" action="/search.csv" data-save-as-form', legacy_template)
        self.assertIn('data-save-as-filename="search_results.csv"', search_template)
        self.assertIn('data-save-as-filename="search_results.csv"', legacy_template)
        self.assertIn('data-save-as-mime="text/csv"', search_template)
        self.assertIn('data-save-as-mime="text/csv"', legacy_template)
        self.assertIn('name="sort" value="{{ sort }}"', search_template)
        self.assertIn('name="dir" value="{{ dir }}"', search_template)
        self.assertIn('name="sort" value="{{ sort }}"', legacy_template)
        self.assertIn('name="dir" value="{{ dir }}"', legacy_template)
        self.assertNotIn('action="/search.csv/save"', search_template)
        self.assertNotIn('action="/search.csv/save"', legacy_template)


if __name__ == "__main__":
    unittest.main()
