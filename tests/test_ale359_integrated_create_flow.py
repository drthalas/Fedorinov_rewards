import asyncio
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from backend.app.config import Settings
from backend.app.repositories.persons_write import (
    DUPLICATE_PERSON_MESSAGE,
    PersonValidationError,
    PersonWriteData,
    create_person,
)
from backend.app.repositories.rewards_write import RewardWriteData, create_reward
from backend.app.routers import persons as persons_router


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, values: dict[str, object]):
        self._body = urlencode(values).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


def template_result(_request, template, context, status_code=200):
    return {"template": template, "context": context, "status_code": status_code}


class Ale359IntegratedCreateFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.log")
        self.settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
        )
        self._create_db()

    def tearDown(self) -> None:
        os.environ.pop("REWARDS_AUDIT_LOG", None)
        self.tmp.cleanup()

    def _create_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executescript(
                """
                create table guide (id integer primary key, name text, image_path text);
                insert into guide values (1, 'Звание один', null);
                insert into guide values (2, 'Звание два', null);
                create table person (
                    id integer primary key autoincrement, fio text, birthday text, id_rank integer,
                    person_foto text, main_foto text, rewards_foto text, book1_foto text,
                    book2_foto text, card1_foto text, card2_foto text,
                    link1 text, link2 text, comment text, biography text
                );
                create table rewards (
                    id integer primary key autoincrement, person_id integer,
                    id_gos integer, id_catigory integer, id_sub_catigory integer, id_name integer,
                    id_link text, number integer, instock integer, date_purchase text,
                    price_purchase integer, price_now integer, front_foto text, back_foto text,
                    book1_foto text, book2_foto text, reward_list text
                );
                create table guide_lev_0 (id integer primary key, idl integer, name text);
                create table guide_lev_1 (id integer primary key, idl integer, name text);
                create table guide_lev_2 (id integer primary key, idl integer, name text);
                create table guide_lev_3 (id integer primary key, idl integer, name text);
                create table guide_lev_4 (id integer primary key, idl integer, name text);
                insert into guide_lev_0 values (1, -1, 'Страна');
                insert into guide_lev_1 values (2, 1, 'Категория');
                insert into guide_lev_2 values (3, 2, 'Подкатегория');
                insert into guide_lev_3 values (4, 3, 'Награда');
                """
            )
            connection.commit()

    def _person(self, fio: str, *, birthday: str = "1910", rank: int = 1) -> PersonWriteData:
        return PersonWriteData(fio=fio, birthday=birthday, id_rank=rank)

    def _counts(self) -> tuple[int, int]:
        with closing(sqlite3.connect(self.db_path)) as connection:
            return (
                connection.execute("select count(*) from person").fetchone()[0],
                connection.execute("select count(*) from rewards").fetchone()[0],
            )

    def test_primary_create_is_now_final_and_redirects_to_selected_person(self) -> None:
        template = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text(encoding="utf-8")
        self.assertIn("data-person-draft", template)
        self.assertIn("data-draft-reward-open", template)
        self.assertIn("data-draft-photo-trigger", template)

        request = FakeRequest(
            {
                "fio": "ALE359 Первый",
                "birthday": "1910",
                "id_rank": "1",
                "return_to": "/legacy?tab=rewards",
            }
        )
        with patch.object(persons_router, "get_settings", return_value=self.settings):
            response = asyncio.run(persons_router.person_create(request))
        location = response.headers["location"]
        self.assertEqual(response.status_code, 303)
        self.assertEqual(location, "/legacy?tab=rewards&person_id=1&status=person_created")
        self.assertEqual(self._counts(), (1, 0))

    def test_post_create_keeps_photo_controls_and_add_reward_after_each_reward(self) -> None:
        person_id = create_person(self.settings, self._person("ALE359 Награды"))
        post_create_return = persons_router._person_created_edit_url(
            person_id,
            f"/legacy?tab=rewards&person_id={person_id}",
        )

        for number in (101, 102):
            create_reward(
                self.settings,
                person_id,
                RewardWriteData(
                    id_gos=1,
                    id_catigory=2,
                    id_sub_catigory=3,
                    id_name=4,
                    number=number,
                ),
            )

        with patch.object(persons_router, "get_settings", return_value=self.settings), patch.object(
            persons_router.templates, "TemplateResponse", side_effect=template_result
        ):
            response = persons_router.person_edit(
                object(),
                person_id,
                return_to=f"/legacy?tab=rewards&person_id={person_id}",
                created="1",
            )
        context = response["context"]
        self.assertTrue(context["post_create"])
        self.assertEqual(len(context["post_create_rewards"]), 2)
        self.assertEqual([row["number"] for row in context["post_create_rewards"]], [101, 102])
        self.assertEqual(len(context["photo_controls"]), 7)
        self.assertEqual(context["post_create_url"], post_create_return)

        template = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text(encoding="utf-8")
        self.assertIn("/rewards/new?return_to={{ post_create_url|urlencode }}", template)
        self.assertIn('photo_manage_return_url = post_create_url if post_create else ""', template)
        photo_template = (ROOT / "backend" / "app" / "templates" / "photo_management.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("photo_manage_return_url|default('')", photo_template)

    def test_regular_edit_does_not_enter_post_create_flow(self) -> None:
        person_id = create_person(self.settings, self._person("ALE359 Обычное редактирование"))
        with patch.object(persons_router, "get_settings", return_value=self.settings), patch.object(
            persons_router.templates, "TemplateResponse", side_effect=template_result
        ):
            response = persons_router.person_edit(object(), person_id, return_to="/persons", created="")
        self.assertFalse(response["context"]["post_create"])
        self.assertEqual(response["context"]["post_create_rewards"], [])
        self.assertEqual(response["context"]["created_message"], "")

    def test_exact_duplicate_is_blocked_without_blocking_namesakes(self) -> None:
        create_person(self.settings, self._person("  Иванов   Иван Иванович  "))

        with self.assertRaisesRegex(PersonValidationError, DUPLICATE_PERSON_MESSAGE):
            create_person(self.settings, self._person("иванов иван иванович"))

        create_person(self.settings, self._person("Иванов Иван Иванович", birthday="1911"))
        create_person(self.settings, self._person("Иванов Иван Иванович", rank=2))
        create_person(self.settings, self._person("Иванов Иван Петрович"))
        self.assertEqual(self._counts(), (4, 0))
        self.assertEqual(sorted(path.name for path in (self.root / "Source").iterdir()), ["1", "2", "3", "4"])

    def test_duplicate_route_preserves_primary_form_and_reports_clear_error(self) -> None:
        create_person(self.settings, self._person("ALE359 Дубликат"))
        request = FakeRequest(
            {
                "fio": "ALE359 Дубликат",
                "birthday": "1910",
                "id_rank": "1",
                "return_to": "/legacy?tab=rewards",
            }
        )
        with patch.object(persons_router, "get_settings", return_value=self.settings), patch.object(
            persons_router.templates, "TemplateResponse", side_effect=template_result
        ):
            response = asyncio.run(persons_router.person_create(request))
        self.assertEqual(response["status_code"], 400)
        self.assertEqual(response["context"]["error"], DUPLICATE_PERSON_MESSAGE)
        self.assertEqual(response["context"]["person"]["fio"], "ALE359 Дубликат")
        self.assertEqual(self._counts(), (1, 0))

    def test_post_create_final_save_returns_to_selected_main_state(self) -> None:
        person_id = create_person(self.settings, self._person("ALE359 Финал"))
        request = FakeRequest(
            {
                "fio": "ALE359 Финал сохранён",
                "birthday": "1910",
                "id_rank": "1",
                "post_create": "1",
                "return_to": f"/legacy?tab=rewards&person_id={person_id}",
            }
        )
        with patch.object(persons_router, "get_settings", return_value=self.settings):
            response = asyncio.run(persons_router.person_update(request, person_id))
        self.assertEqual(
            response.headers["location"],
            f"/legacy?tab=rewards&person_id={person_id}&status=person_updated",
        )


if __name__ == "__main__":
    unittest.main()
