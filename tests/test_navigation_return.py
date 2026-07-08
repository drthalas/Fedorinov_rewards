from pathlib import Path
from tempfile import TemporaryDirectory
import asyncio
import os
import sqlite3
import unittest
from urllib.parse import urlencode

from fastapi import HTTPException

from backend.app.routers.dashboard import dashboard, dashboard_head
from backend.app.routers.marks import mark_update
from backend.app.routers.persons import person_update
from backend.app.routers.rewards import reward_delete, reward_duplicate_check, reward_update
from backend.app.routers.templates import photo_view_url
from backend.app.services.navigation import safe_return_to, with_status


class FakeRequest:
    def __init__(self, values: dict[str, object]):
        self._body = urlencode(values).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class ReturnNavigationTests(unittest.TestCase):
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
        connection = sqlite3.connect(self.db_path)
        try:
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
            connection.execute("insert into person (id, fio, birthday, id_rank) values (1, 'Test Person', '1913-05-09', 1)")
            connection.execute(
                """
                insert into rewards (id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number)
                values (10, 1, 1, 1, 1, 2, 100)
                """
            )
            connection.execute(
                """
                insert into mark (id, id_gos, id_catigory, id_sub_catigory, id_name, number)
                values (20, 1, 1, 1, 2, 200)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def test_dashboard_redirects_to_legacy_rewards(self) -> None:
        response = dashboard(None)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/legacy?tab=rewards")

    def test_dashboard_head_redirects_to_legacy_rewards(self) -> None:
        response = dashboard_head()
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/legacy?tab=rewards")

    def test_return_to_sanitizer_accepts_internal_url(self) -> None:
        self.assertEqual(safe_return_to("/legacy?tab=rewards"), "/legacy?tab=rewards")

    def test_return_to_sanitizer_rejects_external_url(self) -> None:
        self.assertEqual(safe_return_to("http://example.com", "/fallback"), "/fallback")
        self.assertEqual(safe_return_to("//example.com", "/fallback"), "/fallback")

    def test_with_status_preserves_return_to_query(self) -> None:
        self.assertEqual(
            with_status("/legacy?tab=rewards&person_id=1", "updated"),
            "/legacy?tab=rewards&person_id=1&status=updated",
        )

    def test_photo_view_url_preserves_return_to(self) -> None:
        url = photo_view_url("Source/1/Foto.jpg", "Фото", "/legacy?tab=rewards&person_id=1")
        self.assertIn("return_to=%2Flegacy%3Ftab%3Drewards%26person_id%3D1", url)

    def test_person_edit_post_respects_safe_return_to(self) -> None:
        request = FakeRequest(
            {
                "fio": "Updated Person",
                "birthday": "09.05.1913",
                "id_rank": "1",
                "return_to": "/legacy?tab=rewards&person_id=1",
            }
        )
        response = asyncio.run(person_update(request, 1))
        self.assertEqual(response.headers["location"], "/legacy?tab=rewards&person_id=1&status=updated")

    def test_reward_edit_post_respects_safe_return_to(self) -> None:
        request = FakeRequest({"number": "101", "return_to": "/legacy?tab=rewards&person_id=1"})
        response = asyncio.run(reward_update(request, 10))
        self.assertEqual(response.headers["location"], "/legacy?tab=rewards&person_id=1&status=updated")

    def test_reward_delete_without_explicit_confirmation_does_not_delete(self) -> None:
        request = FakeRequest({"confirm": "true", "return_to": "/persons/1"})
        with self.assertRaises(HTTPException) as blocked:
            asyncio.run(reward_delete(request, 10))
        self.assertEqual(blocked.exception.status_code, 400)
        self.assertEqual(blocked.exception.detail, "Действие требует подтверждения.")
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute("select id from rewards where id = 10").fetchone()
        self.assertIsNotNone(row)

    def test_reward_delete_from_person_card_returns_to_same_person(self) -> None:
        request = FakeRequest({"confirm": "true", "delete_reward_confirm": "true", "return_to": "/persons/1"})
        response = asyncio.run(reward_delete(request, 10))
        self.assertEqual(response.headers["location"], "/persons/1?status=reward_deleted")
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute("select id from rewards where id = 10").fetchone()
        self.assertIsNone(row)

    def test_reward_duplicate_check_returns_free_status(self) -> None:
        result = reward_duplicate_check(id_name="2", number="101")

        self.assertFalse(result["duplicate"])
        self.assertEqual(result["message"], "Номер свободен")

    def test_reward_duplicate_check_returns_existing_record(self) -> None:
        result = reward_duplicate_check(id_name="2", number="100")

        self.assertTrue(result["duplicate"])
        self.assertIn("Награда с таким наименованием и номером уже есть в базе.", result["message"])
        self.assertEqual(result["existing_reward_id"], 10)
        self.assertEqual(result["existing_person_id"], 1)
        self.assertEqual(result["existing_person_name"], "Test Person")
        self.assertEqual(result["existing_url"], "/persons/1")

    def test_reward_duplicate_check_excludes_current_reward(self) -> None:
        result = reward_duplicate_check(id_name="2", number="100", current_reward_id="10")

        self.assertFalse(result["duplicate"])
        self.assertEqual(result["message"], "Номер свободен")

    def test_reward_duplicate_check_handles_empty_number_and_missing_name(self) -> None:
        empty_number = reward_duplicate_check(id_name="2", number="")
        missing_name = reward_duplicate_check(id_name="", number="100")

        self.assertFalse(empty_number["duplicate"])
        self.assertEqual(empty_number["message"], "")
        self.assertFalse(missing_name["duplicate"])
        self.assertEqual(missing_name["message"], "Выберите наименование награды для проверки номера")

    def test_mark_edit_post_respects_safe_return_to(self) -> None:
        request = FakeRequest({"number": "201", "return_to": "/legacy?tab=marks&mark_id=20"})
        response = asyncio.run(mark_update(request, 20))
        self.assertEqual(response.headers["location"], "/legacy?tab=marks&mark_id=20&status=updated")

    def test_mark_edit_post_preserves_guide_ids_when_payload_omits_them(self) -> None:
        request = FakeRequest({"number": "202", "price_now": "700", "return_to": "/legacy?tab=marks&mark_id=20"})
        asyncio.run(mark_update(request, 20))
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("select * from mark where id = 20").fetchone()
        self.assertEqual(row["number"], 202)
        self.assertEqual(row["price_now"], 700)
        self.assertEqual(row["id_gos"], 1)
        self.assertEqual(row["id_catigory"], 1)
        self.assertEqual(row["id_sub_catigory"], 1)
        self.assertEqual(row["id_name"], 2)


if __name__ == "__main__":
    unittest.main()
