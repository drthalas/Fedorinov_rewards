from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.routers import legacy as legacy_router
from backend.app.routers import persons as persons_router
from backend.app.routers.templates import templates


class FakeRequest:
    def __init__(self, path: str = "/legacy", values: dict[str, object] | None = None):
        self.url = type("URL", (), {"path": path})()
        self._body = urlencode(values or {}).encode("utf-8")

    async def body(self) -> bytes:
        return self._body

    def url_for(self, name: str, **path_params) -> str:
        if name == "static":
            return f"/static/{path_params.get('path', '')}"
        return f"/{name}"


class LegacyRewardsPhotoSlideshowTests(unittest.TestCase):
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
        os.environ["WRITE_MODE"] = "false"
        os.environ["READ_ONLY"] = "true"
        self._create_db()

    def tearDown(self) -> None:
        for key, value in self._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _create_db(self) -> None:
        person_dir = self.root / "Source" / "77"
        person_dir.mkdir(parents=True)
        for name in [
            "person.jpg",
            "main.jpg",
            "reward-front.jpg",
            "folder-extra-a.jpg",
            "folder-extra-b.png",
            "unsafe.pdf",
        ]:
            (person_dir / name).write_bytes(b"image")

        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table guide (id integer primary key, name text)")
            connection.execute("insert into guide values (1, 'старшина')")
            for level in range(4):
                connection.execute(f"create table guide_lev_{level} (id integer primary key, idl integer, name text)")
                connection.execute(f"insert into guide_lev_{level} values (1, 0, 'Guide {level}')")
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
            connection.execute(
                """
                create table mark (
                    id integer primary key,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link integer,
                    number text,
                    instock text,
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
            connection.execute(
                """
                insert into person (
                    id, fio, birthday, id_rank, person_foto, main_foto, rewards_foto,
                    book1_foto, book2_foto, card1_foto, card2_foto, link1, link2, comment, biography
                )
                values (
                    77, 'Вукалович Семен Петрович', '1912-01-01', 1,
                    'Source/77/person.jpg', 'Source/77/main.jpg', '',
                    '', '', '', '', '', '', '', ''
                )
                """
            )
            connection.execute(
                """
                insert into rewards (
                    id, person_id, id_gos, id_catigory, id_sub_catigory, id_name, number,
                    instock, date_purchase, price_purchase, price_now,
                    front_foto, back_foto, book1_foto, book2_foto, reward_list
                )
                values (
                    700, 77, 1, 1, 1, 1, '77', '1', '2026-01-01', 100, 120,
                    'Source/77/reward-front.jpg', '', '', '', ''
                )
                """
            )
            connection.commit()

    def test_legacy_rewards_visible_thumbnails_open_full_person_manifest(self) -> None:
        with patch.object(legacy_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = legacy_router.legacy_index(FakeRequest(), tab="rewards", person_id=77)
        rendered = templates.env.get_template("legacy.html").render(request=FakeRequest(), **context)

        self.assertIn("legacy-person-77-all", rendered)
        self.assertIn("data-legacy-person-full-lightbox-items", rendered)
        self.assertIn('data-lightbox-group="legacy-person-77-all"', rendered)
        self.assertIn("data-legacy-person-complete-slideshow", rendered)
        self.assertIn("Source%2F77%2Freward-front.jpg", rendered)
        self.assertIn("Source%2F77%2Ffolder-extra-a.jpg", rendered)
        self.assertIn("Source%2F77%2Ffolder-extra-b.png", rendered)
        self.assertNotIn("unsafe.pdf", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertIn("/persons/77/photos?return_to=/legacy%3Ftab%3Drewards%26person_id%3D77", rendered)

    def test_person_photos_return_link_uses_safe_legacy_rewards_return_to(self) -> None:
        return_to = "/legacy?tab=rewards&person_id=77"
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_photos(FakeRequest(path="/persons/77/photos"), 77, return_to=return_to)
        rendered = templates.env.get_template("person_photos.html").render(
            request=FakeRequest(path="/persons/77/photos"),
            **context,
        )

        self.assertEqual(context["return_to"], return_to)
        self.assertIn('href="/legacy?tab=rewards&amp;person_id=77"', rendered)
        self.assertIn("Source%2F77%2Ffolder-extra-a.jpg", rendered)

    def test_person_photos_rejects_external_return_to(self) -> None:
        with patch.object(persons_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = persons_router.person_photos(FakeRequest(path="/persons/77/photos"), 77, return_to="https://evil.example")
        rendered = templates.env.get_template("person_photos.html").render(
            request=FakeRequest(path="/persons/77/photos"),
            **context,
        )

        self.assertEqual(context["return_to"], "")
        self.assertNotIn("evil.example", rendered)
        self.assertIn('href="/persons/77"', rendered)


if __name__ == "__main__":
    unittest.main()
