import asyncio
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlencode

from backend.app.config import Settings
from backend.app.repositories.persons_write import PersonWriteData
from backend.app.services.person_create_drafts import (
    add_reward,
    commit_draft,
    discard_reward,
    discard_draft,
    load_draft,
    load_reward,
    new_draft_token,
    save_reward,
    stage_reward_photo,
    stage_photo,
    start_reward,
)


ROOT = Path(__file__).resolve().parents[1]
from tests.image_fixtures import JPEG_BYTES


class PersonCreateDraftTests(unittest.TestCase):
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
                insert into guide values (1, 'Генерал', null);
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
                create table guide_lev_3 (id integer primary key, idl integer, name text, image_path text);
                create table guide_lev_4 (id integer primary key, idl integer, name text);
                insert into guide_lev_0 values (1, -1, 'СССР');
                insert into guide_lev_1 values (2, 1, 'Ордена');
                insert into guide_lev_2 values (3, 2, 'Военные');
                insert into guide_lev_3 values (4, 3, 'Орден Победы', null);
                insert into guide_lev_4 values (5, 4, 'Вариант');
                """
            )
            connection.commit()

    def _counts(self) -> tuple[int, int]:
        with closing(sqlite3.connect(self.db_path)) as connection:
            return (
                connection.execute("select count(*) from person").fetchone()[0],
                connection.execute("select count(*) from rewards").fetchone()[0],
            )

    def test_draft_photo_and_reward_do_not_touch_live_data_before_final_save(self) -> None:
        token = new_draft_token()
        stage_photo(self.settings, token, "person_foto", "owner.jpg", JPEG_BYTES)
        add_reward(self.settings, token, {"id_name": "4", "number": "101", "instock": "on"})

        self.assertEqual(self._counts(), (0, 0))
        self.assertFalse((self.root / "Source").exists())

        person_id = commit_draft(self.settings, token, PersonWriteData("ALE378 Draft", "1910", 1))

        self.assertEqual(person_id, 1)
        self.assertEqual(self._counts(), (1, 1))
        with closing(sqlite3.connect(self.db_path)) as connection:
            person_photo = connection.execute("select person_foto from person where id = 1").fetchone()[0]
            reward = connection.execute("select person_id, id_name, number from rewards").fetchone()
        self.assertTrue((self.root / person_photo).is_file())
        self.assertEqual(reward, (1, 4, 101))
        self.assertFalse((self.root / ".fedorinov-create-drafts" / token).exists())

    def test_cancel_removes_staged_media_without_live_rows_or_orphans(self) -> None:
        token = new_draft_token()
        stage_photo(self.settings, token, "main_foto", "owner.jpg", JPEG_BYTES)
        add_reward(self.settings, token, {"id_name": "4", "number": "102"})

        discard_draft(self.settings, token)

        self.assertEqual(self._counts(), (0, 0))
        self.assertFalse((self.root / ".fedorinov-create-drafts" / token).exists())
        self.assertFalse((self.root / "Source").exists())

    def test_full_reward_form_data_and_photo_remain_draft_until_final_save(self) -> None:
        token = new_draft_token()
        reward_token = start_reward(self.settings, token)
        save_reward(
            self.settings,
            token,
            reward_token,
            {
                "id_name": "4",
                "number": "303",
                "date_purchase": "05.06.2026",
                "price_purchase": "1200",
                "price_now": "1800",
                "instock": "on",
            },
        )
        stage_reward_photo(
            self.settings,
            token,
            reward_token,
            "front_foto",
            "front.jpg",
            JPEG_BYTES,
        )

        self.assertEqual(self._counts(), (0, 0))
        self.assertTrue(load_reward(self.settings, token, reward_token)["photos"]["front_foto"])

        person_id = commit_draft(self.settings, token, PersonWriteData("ALE378 Full Reward", "1916", 1))
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "select person_id, id_name, number, date_purchase, price_purchase, price_now, instock, front_foto "
                "from rewards"
            ).fetchone()
        self.assertEqual(row[:7], (person_id, 4, 303, "2026-06-05", 1200, 1800, 1))
        self.assertTrue((self.root / row[7]).is_file())

    def test_cancel_reward_form_removes_only_that_staged_reward(self) -> None:
        token = new_draft_token()
        stage_photo(self.settings, token, "person_foto", "person.jpg", JPEG_BYTES)
        reward_token = start_reward(self.settings, token)
        stage_reward_photo(self.settings, token, reward_token, "front_foto", "front.jpg", JPEG_BYTES)

        discard_reward(self.settings, token, reward_token)

        draft = load_draft(self.settings, token)
        self.assertEqual(draft["rewards"], [])
        self.assertIn("person_foto", draft["photos"])
        self.assertFalse((self.root / ".fedorinov-create-drafts" / token / "rewards" / reward_token).exists())
        self.assertEqual(self._counts(), (0, 0))

    def test_multiple_full_rewards_accumulate_before_final_person_save(self) -> None:
        token = new_draft_token()
        for number in (401, 402, 403):
            reward_token = start_reward(self.settings, token)
            save_reward(
                self.settings,
                token,
                reward_token,
                {"id_name": "4", "number": str(number), "date_purchase": "06.06.2026"},
            )

        self.assertEqual(self._counts(), (0, 0))
        person_id = commit_draft(self.settings, token, PersonWriteData("ALE378 Multiple Rewards", "1917", 1))

        with closing(sqlite3.connect(self.db_path)) as connection:
            rewards = connection.execute(
                "select person_id, id_name, number from rewards order by number"
            ).fetchall()
        self.assertEqual(
            rewards,
            [(person_id, 4, 401), (person_id, 4, 402), (person_id, 4, 403)],
        )

    def test_atomic_failure_rolls_back_person_rewards_and_final_media(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "insert into person (fio, birthday, id_rank) values ('Existing', '1910', 1)"
            )
            connection.execute(
                "insert into rewards (person_id, id_name, number) values (1, 4, 777)"
            )
            connection.commit()
        token = new_draft_token()
        stage_photo(self.settings, token, "person_foto", "owner.jpg", JPEG_BYTES)
        add_reward(self.settings, token, {"id_name": "4", "number": "777"})

        with self.assertRaisesRegex(ValueError, "уже есть"):
            commit_draft(self.settings, token, PersonWriteData("ALE378 Rollback", "1911", 1))

        self.assertEqual(self._counts(), (1, 1))
        self.assertFalse((self.root / "Source" / "2").exists())
        self.assertEqual(len(load_draft(self.settings, token)["rewards"]), 1)

    def test_duplicate_final_submit_creates_no_second_person(self) -> None:
        first = new_draft_token()
        second = new_draft_token()
        data = PersonWriteData("ALE378 Duplicate", "1912", 1)
        commit_draft(self.settings, first, data)

        with self.assertRaisesRegex(ValueError, "уже существует"):
            commit_draft(self.settings, second, data)

        self.assertEqual(self._counts(), (1, 0))

    def test_create_template_exposes_full_draft_workspace_before_save(self) -> None:
        template = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")
        reward_template = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")
        script = (ROOT / "backend/app/static/person_create_draft.js").read_text(encoding="utf-8")

        self.assertIn("data-person-draft", template)
        self.assertIn("data-draft-photo-trigger", template)
        self.assertIn('formaction="/persons/new/draft/{{ draft_token }}/rewards/new"', template)
        self.assertIn("Добавить награду", template)
        primary_actions = template.split('<div class="actions{% if mode == \'create\' %} person-create-actions{% endif %}">', 1)[1].split("</div>", 1)[0]
        self.assertLess(primary_actions.index("Сохранить"), primary_actions.index("Добавить награду"))
        draft_rewards = template.split('class="form-section person-create-draft-rewards"', 1)[1]
        self.assertNotIn("Добавить награду", draft_rewards.split("</section>", 1)[0])
        self.assertIn('action="/persons/new/draft/{{ draft_token }}/cancel"', template)
        top_nav = template.split('class="local-back-nav compact-actions{% if mode == \'create\' %} person-create-navigation{% endif %}"', 1)[1].split("</div>", 1)[0]
        self.assertIn("← Назад", top_nav)
        self.assertIn(">Отмена</button>", top_nav)
        self.assertEqual(template.count(">Отмена</button>"), 1)
        self.assertIn('mode == "draft"', reward_template)
        self.assertIn("data-draft-photo-base", reward_template)
        self.assertIn("data-reward-reference-derived", reward_template)
        self.assertIn("Дата покупки", reward_template)
        self.assertIn("Цена покупки", reward_template)
        self.assertIn("photoBase", script)

    def test_create_action_groups_use_shared_baseline_alignment(self) -> None:
        template = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("person-create-navigation", template)
        self.assertIn("person-create-actions", template)
        self.assertIn(".person-create-navigation,\n.person-create-actions", styles)
        self.assertIn("align-items: stretch", styles)
        self.assertIn("min-height: 36px", styles)


if __name__ == "__main__":
    unittest.main()
