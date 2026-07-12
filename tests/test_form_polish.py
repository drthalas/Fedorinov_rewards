from pathlib import Path
from tempfile import TemporaryDirectory
import asyncio
import os
import re
import sqlite3
import unittest
from datetime import date
from urllib.parse import urlencode
from unittest.mock import patch

from jinja2 import Environment

from backend.app.routers import guides as guides_router
from backend.app.routers import marks as marks_router
from backend.app.routers import persons as persons_router
from backend.app.routers import rewards as rewards_router
from backend.app.repositories.guides_write import GuideValidationError, rank_data_from_mapping


class FakeRequest:
    def __init__(self, values: dict[str, object]):
        self._body = urlencode(values).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


def _template_result(_request, name: str, context: dict[str, object], **kwargs):
    return {
        "template": name,
        "context": context,
        "status_code": kwargs.get("status_code", 200),
    }


class FormPolishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_DATA_DIR"] = str(self.root)
        os.environ["REWARDS_DB_PATH"] = str(self.db_path)
        os.environ["READ_ONLY"] = "false"
        os.environ["WRITE_MODE"] = "true"
        os.environ["REQUIRE_BACKUP_BEFORE_WRITE"] = "false"
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.log")
        self._create_db()

    def tearDown(self) -> None:
        for key in [
            "REWARDS_DATA_DIR",
            "REWARDS_DB_PATH",
            "READ_ONLY",
            "WRITE_MODE",
            "REQUIRE_BACKUP_BEFORE_WRITE",
            "REWARDS_AUDIT_LOG",
        ]:
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key, name text)")
            connection.execute(
                """
                create table person (
                    id integer primary key,
                    fio text,
                    birthday text,
                    id_rank integer,
                    link1 text,
                    link2 text,
                    comment text,
                    biography text,
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
                    id_link text,
                    number integer,
                    instock boolean,
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
            connection.execute(
                """
                create table mark (
                    id integer primary key,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link text,
                    number integer,
                    instock boolean,
                    date_purchase text,
                    price_purchase integer,
                    price_now integer,
                    front_foto text,
                    back_foto text,
                    book1_foto text,
                    book2_foto text
                )
                """
            )
            for level in range(5):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, idl integer, name text)")
            connection.executemany("insert into guide (id, name) values (?, ?)", [(1, "Капитан"), (2, "Майор")])
            connection.execute("insert into guide_lev_0 (id, idl, name) values (1, -1, 'СССР')")
            connection.execute("insert into guide_lev_1 (id, idl, name) values (2, 1, 'Ордена')")
            connection.execute("insert into guide_lev_2 (id, idl, name) values (3, 2, 'Боевые')")
            connection.execute("insert into guide_lev_3 (id, idl, name) values (4, 3, 'Орден Красной Звезды')")
            connection.execute("insert into guide_lev_1 (id, idl, name) values (90, 999, 'Лишняя категория')")
            connection.execute("insert into guide_lev_2 (id, idl, name) values (91, 999, 'Лишняя подкатегория')")
            connection.execute("insert into guide_lev_3 (id, idl, name) values (92, 999, 'Лишнее наименование')")
            connection.execute(
                """
                insert into person (id, fio, birthday, id_rank, link1, link2, comment, biography)
                values (1, 'Иванов Иван Иванович', '1913-05-09', 1, '', '', '', '')
                """
            )
            connection.execute(
                """
                insert into rewards (id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number, date_purchase)
                values (10, 1, 1, 2, 3, 4, 123, '2026-01-02')
                """
            )
            connection.execute(
                """
                insert into mark (id, id_gos, id_catigory, id_sub_catigory, id_name, number, date_purchase)
                values (20, 1, 2, 3, 4, 456, '2026-01-03')
                """
            )

    def test_person_form_error_is_russian_and_preserves_values(self) -> None:
        request = FakeRequest(
            {
                "fio": "Петров Пётр",
                "birthday": "не дата",
                "id_rank": "1",
                "link1": "https://example.test/person",
                "comment": "Комментарий",
                "biography": "Биография",
                "return_to": "/legacy?tab=rewards&person_id=1",
            }
        )
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=_template_result):
            response = asyncio.run(persons_router.person_create(request))
        context = response["context"]
        self.assertEqual(response["status_code"], 400)
        self.assertEqual(context["error"], "Укажите год рождения в формате ГГГГ.")
        self.assertEqual(context["person"]["fio"], "Петров Пётр")
        self.assertEqual(context["person"]["link1"], "https://example.test/person")
        self.assertEqual(context["person"]["comment"], "Комментарий")
        self.assertEqual(context["person"]["biography"], "Биография")
        self.assertEqual(context["return_to"], "/legacy?tab=rewards&person_id=1")

    def test_successful_person_create_redirects_to_edit_with_created_message(self) -> None:
        request = FakeRequest(
            {
                "fio": "Петров Пётр Петрович",
                "birthday": "1914",
                "id_rank": "1",
                "return_to": "/legacy?tab=rewards",
            }
        )
        response = asyncio.run(persons_router.person_create(request))
        location = response.headers["location"]
        self.assertTrue(location.startswith("/persons/2/edit?"))
        self.assertIn("created=1", location)
        self.assertIn("return_to=%2Flegacy%3Ftab%3Drewards", location)

        with patch.object(persons_router.templates, "TemplateResponse", side_effect=_template_result):
            edit_response = persons_router.person_edit(object(), 2, return_to="/legacy?tab=rewards", created="1")
        context = edit_response["context"]
        self.assertEqual(context["created_message"], "Кавалер создан. Теперь можно добавить фотографии и документы.")
        self.assertEqual(context["return_to"], "/legacy?tab=rewards")

    def test_person_edit_contains_photo_controls_and_next_actions(self) -> None:
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=_template_result):
            response = persons_router.person_edit(object(), 1, return_to="/persons")
        context = response["context"]
        labels = [item["label"] for item in context["photo_controls"]]
        self.assertIn("Фото кавалера", labels)
        self.assertIn("Главное фото", labels)
        self.assertIn("Общее фото наград", labels)
        self.assertIn("Фото учётной карточки, страница 1", labels)
        self.assertIn("Фото учётной карточки, страница 2", labels)

        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "person_form.html").read_text(
            encoding="utf-8"
        )
        photo_template = (
            Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "photo_management.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Добавить фото и документы", template)
        self.assertIn("Добавить награду", template)
        self.assertIn("Год рождения", template)
        self.assertIn("format_birth_year_input", template)
        self.assertIn('placeholder="ГГГГ"', template)
        self.assertIn('inputmode="numeric"', template)
        self.assertNotIn('type="date"', template)
        self.assertNotIn("ДД.ММ.ГГГГ", template)
        self.assertNotIn("Вернуться к карточке", template)
        self.assertIn("id=\"{{ photo_entity_type }}-photo-management\"", photo_template)
        self.assertIn("Вставить из буфера", photo_template)
        self.assertIn("photo-upload-form", photo_template)

    def test_person_edit_heading_omits_technical_id(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "person_form.html").read_text(
            encoding="utf-8"
        )
        heading = re.search(r"<h1>.*?</h1>", template, re.S)
        self.assertIsNotNone(heading)

        rendered = Environment(autoescape=True).from_string(heading.group(0)).render(mode="edit", person={"id": 115})
        self.assertEqual(rendered, "<h1>Изменить награжденного</h1>")
        self.assertNotIn("#115", rendered)
        self.assertNotIn("115", rendered)
        self.assertNotIn("#{{ person.id }}", template)

        create_heading = Environment(autoescape=True).from_string(heading.group(0)).render(mode="create", person={})
        self.assertEqual(create_heading, "<h1>Добавить награжденного</h1>")

    def test_person_form_omits_rank_guide_helpers(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "person_form.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("/guides?section=ranks", template)
        self.assertNotIn("/guides/ranks/new", template)
        self.assertIn('select name="id_rank" data-styled-select required', template)

    def test_reward_form_preserves_cascading_guides_after_validation_error(self) -> None:
        request = FakeRequest(
            {
                "id_gos": "1",
                "id_catigory": "2",
                "id_sub_catigory": "3",
                "id_name": "",
                "number": "12345",
                "price_now": "700",
                "return_to": "/legacy?tab=rewards&person_id=1",
            }
        )
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            response = asyncio.run(rewards_router.reward_create(request, 1))
        context = response["context"]
        self.assertEqual(response["status_code"], 400)
        self.assertEqual(context["error"], "Выберите наименование награды.")
        self.assertEqual(context["reward"]["number"], "12345")
        self.assertEqual(context["reward"]["price_now"], "700")
        self.assertEqual(context["return_to"], "/legacy?tab=rewards&person_id=1")
        self.assertEqual([item["id"] for item in context["guides"]["categories"]], [2])
        self.assertEqual([item["id"] for item in context["guides"]["subcategories"]], [3])
        self.assertEqual([item["id"] for item in context["guides"]["names"]], [4])

    def test_new_reward_page_shows_person_context(self) -> None:
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            response = rewards_router.reward_new(object(), 1, return_to="/persons/1/edit")
        context = response["context"]
        self.assertEqual(context["person"]["fio"], "Иванов Иван Иванович")
        self.assertEqual(context["reward"]["date_purchase"], date.today().isoformat())
        self.assertEqual(context["return_to"], "/persons/1/edit")

        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "reward_form.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Добавить награду", template)
        self.assertIn("Кавалер: {{ person.fio|dash }}", template)
        self.assertNotIn("Добавление награды для кавалера", template)

    def test_successful_reward_create_redirects_to_edit_with_created_message(self) -> None:
        request = FakeRequest(
            {
                "id_gos": "1",
                "id_catigory": "2",
                "id_sub_catigory": "3",
                "id_name": "4",
                "number": "98765",
                "return_to": "/legacy?tab=rewards&person_id=1",
            }
        )
        response = asyncio.run(rewards_router.reward_create(request, 1))
        location = response.headers["location"]
        self.assertTrue(location.startswith("/rewards/11/edit?"))
        self.assertIn("created=1", location)
        self.assertIn("return_to=%2Flegacy%3Ftab%3Drewards%26person_id%3D1", location)

        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            edit_response = rewards_router.reward_edit(
                object(),
                11,
                return_to="/legacy?tab=rewards&person_id=1",
                created="1",
            )
        context = edit_response["context"]
        self.assertEqual(context["created_message"], "Награда добавлена. Теперь можно добавить фотографии и документы.")
        labels = [item["label"] for item in context["photo_controls"]]
        self.assertIn("Фото награды: аверс", labels)
        self.assertIn("Фото награды: реверс", labels)
        self.assertIn("Фото книжки, сторона 1", labels)
        self.assertIn("Фото книжки, сторона 2", labels)
        self.assertIn("Наградной лист", labels)

    def test_reward_edit_contains_next_actions(self) -> None:
        template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "reward_form.html").read_text(
            encoding="utf-8"
        )
        detail_template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "reward_detail.html").read_text(
            encoding="utf-8"
        )
        person_template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "person_detail.html").read_text(
            encoding="utf-8"
        )
        legacy_template = (Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "legacy.html").read_text(
            encoding="utf-8"
        )
        photo_template = (
            Path(__file__).resolve().parents[1] / "backend" / "app" / "templates" / "photo_management.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Изменить награду: {{ reward_edit_name }}", template)
        self.assertNotIn("Изменить награду #", template)
        self.assertIn("← Назад", template)
        self.assertIn("data-escape-back", template)
        self.assertIn("Редактировать фото и документы", template)
        self.assertIn("Добавить ещё награду", template)
        self.assertNotIn("К карточке кавалера", template)
        self.assertNotIn("К списку наград", template)
        self.assertIn("/legacy?tab=rewards", template)
        self.assertIn(">Назад</a>", detail_template)
        self.assertIn('data-escape-back href="{{ reward_back_url }}"', detail_template)
        self.assertNotIn("К карточке кавалера", detail_template)
        self.assertNotIn("К списку наград", detail_template)
        self.assertNotIn("← к владельцу", detail_template)
        self.assertIn('aria-label="Открыть награду"', person_template)
        self.assertIn('aria-label="Изменить награду"', person_template)
        self.assertIn('aria-label="Удалить награду"', person_template)
        self.assertIn("/rewards/{{ reward.id }}?return_to={{ person_card_return|urlencode }}", person_template)
        self.assertIn("/rewards/{{ reward.id }}/edit?return_to={{ person_card_return|urlencode }}", person_template)
        self.assertIn("/rewards/{{ reward.id }}?return_to={{ selected_person_return|urlencode }}", legacy_template)
        self.assertIn("id=\"{{ photo_entity_type }}-photo-management\"", photo_template)

    def test_reward_detail_shows_human_title_and_safe_back(self) -> None:
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            response = rewards_router.reward_detail(object(), 10, return_to="/legacy?tab=rewards&person_id=1")

        context = response["context"]
        self.assertEqual(context["reward_name"], "Орден Красной Звезды")
        self.assertEqual(context["reward_heading"], "Награда: Орден Красной Звезды")
        self.assertEqual(context["return_to"], "/legacy?tab=rewards&person_id=1")
        self.assertEqual(context["reward_back_url"], "/legacy?tab=rewards&person_id=1")

    def test_reward_detail_356_title_contains_order_slavy(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("insert into guide_lev_3 (id, idl, name) values (5, 3, 'Орден Славы III степени')")
            connection.execute(
                """
                insert into rewards (id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number, date_purchase)
                values (356, 1, 1, 2, 3, 5, 356, '2026-01-04')
                """
            )
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            response = rewards_router.reward_detail(object(), 356, return_to="/legacy?tab=rewards&person_id=1")

        self.assertIn("Орден Славы III степени", response["context"]["reward_heading"])
        self.assertNotEqual(response["context"]["reward_heading"], "Награда #356")

    def test_reward_detail_falls_back_to_id_when_name_missing(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                insert into rewards (id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number)
                values (99, 1, 1, 2, 3, null, 99)
                """
            )
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            response = rewards_router.reward_detail(object(), 99)

        self.assertEqual(response["context"]["reward_name"], "")
        self.assertEqual(response["context"]["reward_heading"], "Награда")
        self.assertEqual(response["context"]["reward_back_url"], "/legacy?tab=rewards&person_id=1")

    def test_reward_detail_rejects_external_return_to(self) -> None:
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            response = rewards_router.reward_detail(object(), 10, return_to="https://evil.example")

        self.assertEqual(response["context"]["return_to"], "")
        self.assertEqual(response["context"]["reward_back_url"], "/legacy?tab=rewards&person_id=1")

    def test_reward_edit_rejects_external_return_to(self) -> None:
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            response = rewards_router.reward_edit(object(), 10, return_to="https://evil.example/rewards")

        self.assertEqual(response["context"]["return_to"], "")

    def test_reward_form_has_duplicate_number_status_ui(self) -> None:
        root = Path(__file__).resolve().parents[1]
        base_template = (root / "backend" / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        reward_template = (root / "backend" / "app" / "templates" / "reward_form.html").read_text(encoding="utf-8")
        duplicate_js = (root / "backend" / "app" / "static" / "reward_duplicate_check.js").read_text(encoding="utf-8")
        person_detail = (root / "backend" / "app" / "templates" / "person_detail.html").read_text(encoding="utf-8")

        self.assertIn("reward_duplicate_check.js", base_template)
        self.assertIn("data-reward-duplicate-check", reward_template)
        self.assertIn("data-current-reward-id", reward_template)
        self.assertIn("data-reward-number", reward_template)
        self.assertIn("data-reward-duplicate-status", reward_template)
        self.assertIn("Выберите наименование награды для проверки номера", duplicate_js)
        self.assertIn("Номер свободен", duplicate_js)
        self.assertIn("Такая награда с этим номером уже есть в базе", duplicate_js)
        self.assertIn("/rewards/check-duplicate", duplicate_js)
        self.assertIn("Вы действительно хотите удалить награду?", person_detail)

    def test_mark_form_preserves_cascading_guides_after_validation_error(self) -> None:
        request = FakeRequest(
            {
                "id_gos": "1",
                "id_catigory": "2",
                "id_sub_catigory": "3",
                "id_name": "",
                "number": "54321",
                "price_purchase": "500",
                "return_to": "/legacy?tab=marks&mark_id=20",
            }
        )
        with patch.object(marks_router.templates, "TemplateResponse", side_effect=_template_result):
            response = asyncio.run(marks_router.mark_create(request))
        context = response["context"]
        self.assertEqual(response["status_code"], 400)
        self.assertEqual(context["error"], "Выберите наименование знака.")
        self.assertEqual(context["mark"]["number"], "54321")
        self.assertEqual(context["mark"]["price_purchase"], "500")
        self.assertEqual(context["return_to"], "/legacy?tab=marks&mark_id=20")
        self.assertEqual([item["id"] for item in context["guides"]["categories"]], [2])
        self.assertEqual([item["id"] for item in context["guides"]["subcategories"]], [3])
        self.assertEqual([item["id"] for item in context["guides"]["names"]], [4])

    def test_new_reward_and_mark_default_purchase_date_is_today(self) -> None:
        with patch.object(rewards_router.templates, "TemplateResponse", side_effect=_template_result):
            reward_response = rewards_router.reward_new(object(), 1)
        with patch.object(marks_router.templates, "TemplateResponse", side_effect=_template_result):
            mark_response = marks_router.mark_new(object())
        self.assertEqual(reward_response["context"]["reward"]["date_purchase"], date.today().isoformat())
        self.assertEqual(mark_response["context"]["mark"]["date_purchase"], date.today().isoformat())

    def test_empty_guide_item_is_blocked_with_russian_message(self) -> None:
        with self.assertRaises(GuideValidationError) as exc:
            rank_data_from_mapping({"name": ""})
        self.assertEqual(str(exc.exception), "Заполните название.")

        request = FakeRequest({"name": "", "return_to": "/guides?section=ranks"})
        with patch.object(guides_router.templates, "TemplateResponse", side_effect=_template_result):
            response = asyncio.run(guides_router.rank_create(request))
        context = response["context"]
        self.assertEqual(response["status_code"], 400)
        self.assertEqual(context["error"], "Заполните название.")
        self.assertEqual(context["rank"]["name"], "")
        self.assertEqual(context["return_to"], "/guides?section=ranks")

    def test_no_english_backup_write_error_in_templates(self) -> None:
        templates_dir = Path(__file__).resolve().parents[1] / "backend" / "app" / "templates"
        html = "\n".join(path.read_text(encoding="utf-8") for path in templates_dir.glob("*.html"))
        forbidden = (
            "Create a fresh backup before making changes",
            "Read only",
            "Write mode",
            "Changes saved",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, html)


if __name__ == "__main__":
    unittest.main()
