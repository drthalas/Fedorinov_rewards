from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.routers import persons as persons_router


class PersonDetailReturnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        self._previous_env = {
            key: os.environ.get(key)
            for key in ["REWARDS_DATA_DIR", "REWARDS_DB_PATH", "WRITE_MODE", "READ_ONLY"]
        }
        os.environ["REWARDS_DATA_DIR"] = str(self.root)
        os.environ["REWARDS_DB_PATH"] = str(self.db_path)
        os.environ["WRITE_MODE"] = "true"
        os.environ["READ_ONLY"] = "false"
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
                    person_foto text,
                    main_foto text,
                    rewards_foto text,
                    book1_foto text,
                    book2_foto text,
                    card1_foto text,
                    card2_foto text,
                    link1 text,
                    link2 text,
                    comment text,
                    biography text
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
                    instock text,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text,
                    reward_list text
                )
                """
            )
            connection.execute("insert into guide values (1, 'капитан')")
            connection.execute(
                """
                insert into person (
                    id, fio, birthday, id_rank, person_foto, main_foto, rewards_foto,
                    book1_foto, book2_foto, card1_foto, card2_foto, link1, link2, comment, biography
                )
                values (2, 'Васильев Тест', '1913-05-09', 1, '', '', '', '', '', '', '', '', '', '', '')
                """
            )
            connection.commit()
        finally:
            connection.close()

    def test_person_detail_back_link_uses_safe_return_to(self) -> None:
        return_to = "/legacy?tab=rewards&person_id=2"
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_detail(object(), 2, return_to=return_to)
        self.assertEqual(context["return_to"], return_to)

    def test_person_detail_rejects_unsafe_return_to(self) -> None:
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_detail(object(), 2, return_to="http://evil.com")
        self.assertEqual(context["return_to"], "")

    def test_person_detail_rejects_nested_person_return_to(self) -> None:
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_detail(object(), 2, return_to="/persons/2/rewards/new")
        self.assertEqual(context["return_to"], "")

    def test_person_detail_edit_and_photos_preserve_safe_return_to(self) -> None:
        return_to = "/legacy?tab=rewards&person_id=2"
        encoded = quote(return_to, safe="")
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "person_detail.html").read_text(encoding="utf-8")
        self.assertIn("{% set person_back_url = return_to or '/legacy?tab=rewards&person_id=' ~ person.id %}", template)
        self.assertIn(
            "{% set person_card_return = '/persons/' ~ person.id ~ ('?return_to=' ~ return_to|urlencode if return_to else '') %}",
            template,
        )
        self.assertIn("/persons/{{ person.id }}/edit{% if return_to %}?return_to={{ return_to|urlencode }}{% endif %}", template)
        self.assertIn("/persons/{{ person.id }}/rewards/new?return_to={{ person_card_return|urlencode }}", template)
        self.assertIn("/persons/{{ person.id }}/photos?return_to={{ person_card_return|urlencode }}", template)
        self.assertTrue(encoded.startswith("%2Flegacy%3Ftab%3Drewards"))

    def test_person_detail_has_only_local_safe_back_link(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "person_detail.html").read_text(encoding="utf-8")
        script = (Path(__file__).resolve().parents[1] / "backend" / "app" / "static" / "escape_back.js").read_text(encoding="utf-8")

        self.assertIn('data-escape-back href="{{ person_back_url }}"', template)
        self.assertNotIn("data-history-back", template)
        self.assertIn("← Назад", template)
        nav_block = template.split('<p class="person-detail-nav local-back-nav compact-actions">', 1)[1].split("</p>", 1)[0]
        self.assertNotIn("к списку", nav_block)
        self.assertNotIn("Все фото", nav_block)
        self.assertNotIn("Сформировать буклет", nav_block)
        self.assertIn("window.history.back()", script)
        self.assertIn("document.referrer", script)
        self.assertIn("internalFallback", script)
        self.assertIn('fallback.startsWith("//")', script)

    def test_person_detail_removes_duplicate_card_info_panel(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "person_detail.html").read_text(encoding="utf-8")

        self.assertIn("person-summary-strip", template)
        self.assertNotIn("<dt>ID</dt>", template)
        self.assertNotIn("Награжденный #", template)
        self.assertIn("Краткая биография", template)
        self.assertNotIn("person-card-panel", template)
        self.assertNotIn("<h2>Карточка</h2>", template)


if __name__ == "__main__":
    unittest.main()
