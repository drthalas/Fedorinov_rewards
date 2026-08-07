import asyncio
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from backend.app.config import Settings
from backend.app.repositories.persons_write import PersonWriteData, create_person_with_rewards
from backend.app.repositories.rewards_write import RewardValidationError, RewardWriteData
from backend.app.routers import persons as persons_router


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, values: dict[str, object]):
        self._body = urlencode(values).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


def template_result(_request, template, context, status_code=200):
    return {"template": template, "context": context, "status_code": status_code}


class Ale357PersonCreateRewardsTests(unittest.TestCase):
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
                insert into guide values (1, 'Звание', null);
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
                """
            )
            for level, values in enumerate(((1, -1, "Страна"), (2, 1, "Категория"), (3, 2, "Подкатегория"), (4, 3, "Награда"))):
                connection.execute(
                    f"create table guide_lev_{level} (id integer primary key, idl integer, name text, rating_rank integer, image_path text)"
                )
                connection.execute(f"insert into guide_lev_{level} values (?, ?, ?, null, null)", values)
            connection.commit()

    def _person(self, fio: str) -> PersonWriteData:
        return PersonWriteData(fio=fio, birthday="1910", id_rank=1)

    def _counts(self) -> tuple[int, int]:
        with closing(sqlite3.connect(self.db_path)) as connection:
            return (
                connection.execute("select count(*) from person").fetchone()[0],
                connection.execute("select count(*) from rewards").fetchone()[0],
            )

    def test_create_without_rewards_remains_supported(self) -> None:
        person_id, reward_ids = create_person_with_rewards(self.settings, self._person("Без наград"), [])
        self.assertGreater(person_id, 0)
        self.assertEqual(reward_ids, ())
        self.assertEqual(self._counts(), (1, 0))

    def test_create_with_one_or_multiple_rewards_is_atomic(self) -> None:
        person_id, reward_ids = create_person_with_rewards(
            self.settings,
            self._person("С наградами"),
            [
                RewardWriteData(id_gos=1, id_catigory=2, id_sub_catigory=3, id_name=4, number=101),
                RewardWriteData(id_gos=1, id_catigory=2, id_sub_catigory=3, id_name=4, number=102),
            ],
        )
        self.assertEqual(len(reward_ids), 2)
        with closing(sqlite3.connect(self.db_path)) as connection:
            owners = connection.execute("select distinct person_id from rewards order by person_id").fetchall()
        self.assertEqual(owners, [(person_id,)])
        self.assertEqual(self._counts(), (1, 2))

    def test_invalid_reward_rolls_back_person_and_folder(self) -> None:
        with self.assertRaises(RewardValidationError):
            create_person_with_rewards(
                self.settings,
                self._person("Не должен сохраниться"),
                [RewardWriteData(id_name=None)],
            )
        self.assertEqual(self._counts(), (0, 0))
        source = self.root / "Source"
        self.assertEqual(list(source.iterdir()) if source.exists() else [], [])

    def test_route_preserves_multiple_reward_rows_after_validation_error(self) -> None:
        request = FakeRequest(
            {
                "fio": "Ошибка награды",
                "birthday": "1910",
                "id_rank": "1",
                "reward_0_id_name": "4",
                "reward_0_number": "11",
                "reward_1_id_name": "",
                "reward_1_number": "22",
            }
        )
        with patch.object(persons_router, "get_settings", return_value=self.settings), patch.object(
            persons_router.templates, "TemplateResponse", side_effect=template_result
        ):
            response = asyncio.run(persons_router.person_create(request))
        self.assertEqual(response["status_code"], 400)
        self.assertEqual([row["number"] for row in response["context"]["pending_rewards"]], ["11", "22"])
        self.assertIn("Проверьте добавляемые награды", response["context"]["error"])
        self.assertEqual(self._counts(), (0, 0))

    def test_create_template_uses_dynamic_rows_without_changing_edit_flow(self) -> None:
        template = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")
        partial = (ROOT / "backend/app/templates/_pending_reward_form.html").read_text(encoding="utf-8")
        script = (ROOT / "backend/app/static/person_create_rewards.js").read_text(encoding="utf-8")
        cascade = (ROOT / "backend/app/static/cascading_guides.js").read_text(encoding="utf-8")
        self.assertIn('{% if mode == "create" %}', template)
        self.assertIn("data-add-pending-reward", template)
        self.assertIn("data-pending-reward-template", template)
        self.assertIn("reward_{{ index }}_id_name", partial)
        self.assertIn("required", partial)
        self.assertIn('new CustomEvent("legacy:content-updated"', script)
        self.assertIn("replaceAll", script)
        self.assertIn('scope.matches(".guide-cascade")', cascade)


if __name__ == "__main__":
    unittest.main()
