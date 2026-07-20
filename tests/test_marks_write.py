from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.routers import marks as marks_router
from backend.app.routers.templates import templates
from backend.app.repositories.marks_write import (
    MarkValidationError,
    MarkWriteData,
    create_mark,
    delete_mark,
    mark_data_from_mapping,
    update_mark,
)
from backend.app.repositories.marks import get_mark
from backend.app.services.write_guard import WriteBlockedError


class TemplateRequest:
    def __init__(self, path: str):
        self.url = type("URL", (), {"path": path})()

    def url_for(self, name: str, **path_params) -> str:
        if name == "static":
            return f"/static/{path_params.get('path', '')}"
        return f"/{name}"


class MarkWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "database" / "MyDatabase.sqlite"
        self.db_path.parent.mkdir(parents=True)
        os.environ["REWARDS_DATA_DIR"] = str(self.root)
        os.environ["REWARDS_DB_PATH"] = str(self.db_path)
        os.environ["READ_ONLY"] = "false"
        os.environ["WRITE_MODE"] = "true"
        os.environ["REWARDS_AUDIT_LOG"] = str(self.root / "logs" / "audit.log")
        self._create_db()

    def tearDown(self) -> None:
        for key in [
            "REWARDS_DATA_DIR",
            "REWARDS_DB_PATH",
            "READ_ONLY",
            "WRITE_MODE",
            "REWARDS_AUDIT_LOG",
        ]:
            os.environ.pop(key, None)
        self.tmp.cleanup()

    def settings(self, write_mode: bool = True) -> Settings:
        return Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=not write_mode,
            write_mode=write_mode,
        )

    def mark_data(self, **overrides) -> MarkWriteData:
        values = {"id_gos": 1, "id_catigory": 2, "id_sub_catigory": 3, "id_name": 4}
        values.update(overrides)
        return MarkWriteData(**values)

    def _create_db(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                create table mark (
                    id integer primary key autoincrement,
                    id_gos integer,
                    id_catigory integer,
                    id_sub_catigory integer,
                    id_name integer,
                    id_link text,
                    number integer,
                    instock boolean,
                    date_purchase date,
                    price_purchase integer,
                    price_now integer,
                    front_foto varchar,
                    back_foto varchar,
                    book1_foto varchar,
                    book2_foto varchar
                )
                """
            )
            for level in range(4):
                connection.execute(
                    f"""
                    create table guide_lev_{level} (
                        id integer primary key,
                        idl integer,
                        name text
                    )
                    """
                )
                connection.execute(
                    f"insert into guide_lev_{level} (id, idl, name) values (?, ?, ?)",
                    (level + 1, level, f"Guide {level}"),
                )
            connection.execute("insert into guide_lev_1 (id, idl, name) values (90, 999, 'Wrong category')")
            connection.execute("insert into guide_lev_2 (id, idl, name) values (91, 999, 'Wrong subcategory')")
            connection.execute("insert into guide_lev_3 (id, idl, name) values (92, 999, 'Wrong name')")

    def fetch_mark(self, mark_id: int) -> sqlite3.Row | None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute("select * from mark where id = ?", (mark_id,)).fetchone()

    def test_write_mode_disabled_blocks_create_update_delete(self) -> None:
        settings = self.settings(write_mode=False)
        data = self.mark_data(number=1)
        with self.assertRaises(WriteBlockedError):
            create_mark(settings, data)
        with self.assertRaises(WriteBlockedError):
            update_mark(settings, 1, data)
        with self.assertRaises(WriteBlockedError):
            delete_mark(settings, 1, confirm=True)

    def test_create_mark_works(self) -> None:
        mark_id = create_mark(
            self.settings(),
            MarkWriteData(id_gos=1, id_catigory=2, id_sub_catigory=3, id_name=4, number=77, instock=True),
        )
        row = self.fetch_mark(mark_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["number"], 77)
        self.assertEqual(row["instock"], 1)

    def test_update_mark_works(self) -> None:
        mark_id = create_mark(self.settings(), self.mark_data(number=1, price_now=100))
        update_mark(
            self.settings(),
            mark_id,
            MarkWriteData(number=2, price_purchase=500, price_now=700, instock=False),
        )
        row = self.fetch_mark(mark_id)
        self.assertEqual(row["number"], 2)
        self.assertEqual(row["price_purchase"], 500)
        self.assertEqual(row["price_now"], 700)
        self.assertEqual(row["instock"], 0)

    def test_get_mark_returns_guide_ids(self) -> None:
        mark_id = create_mark(
            self.settings(),
            MarkWriteData(id_gos=1, id_catigory=2, id_sub_catigory=3, id_name=4, number=77),
        )
        mark = get_mark(self.db_path, mark_id)
        self.assertIsNotNone(mark)
        self.assertEqual(mark["id_gos"], 1)
        self.assertEqual(mark["id_catigory"], 2)
        self.assertEqual(mark["id_sub_catigory"], 3)
        self.assertEqual(mark["id_name"], 4)

    def test_mark_edit_context_and_template_preselect_guide_ids(self) -> None:
        mark_id = create_mark(
            self.settings(),
            MarkWriteData(id_gos=1, id_catigory=2, id_sub_catigory=3, id_name=4, number=77),
        )
        with patch.object(marks_router.templates, "TemplateResponse", side_effect=lambda request, name, context: context):
            context = marks_router.mark_edit(object(), mark_id)
        self.assertEqual(context["mark"]["id_gos"], 1)
        self.assertEqual(context["mark"]["id_catigory"], 2)
        self.assertEqual(context["mark"]["id_sub_catigory"], 3)
        self.assertEqual(context["mark"]["id_name"], 4)
        rendered = templates.env.get_template("mark_form.html").render(
            request=TemplateRequest(f"/marks/{mark_id}/edit"),
            **context,
        )
        self.assertIn('<option value="1" selected>Guide 0</option>', rendered)
        self.assertIn('<option value="2" selected>Guide 1</option>', rendered)
        self.assertIn('<option value="3" selected>Guide 2</option>', rendered)
        self.assertIn('<option value="4" selected>Guide 3</option>', rendered)
        self.assertNotIn('<option value="90">Wrong category</option>', rendered)
        self.assertNotIn('<option value="91">Wrong subcategory</option>', rendered)
        self.assertNotIn('<option value="92">Wrong name</option>', rendered)

    def test_update_mark_preserves_existing_guide_ids_when_form_omits_them(self) -> None:
        mark_id = create_mark(
            self.settings(),
            MarkWriteData(id_gos=1, id_catigory=2, id_sub_catigory=3, id_name=4, number=77),
        )
        update_mark(
            self.settings(),
            mark_id,
            MarkWriteData(number=88, price_purchase=500, price_now=700, instock=True),
        )
        row = self.fetch_mark(mark_id)
        self.assertEqual(row["number"], 88)
        self.assertEqual(row["price_purchase"], 500)
        self.assertEqual(row["price_now"], 700)
        self.assertEqual(row["instock"], 1)
        self.assertEqual(row["id_gos"], 1)
        self.assertEqual(row["id_catigory"], 2)
        self.assertEqual(row["id_sub_catigory"], 3)
        self.assertEqual(row["id_name"], 4)

    def test_delete_mark_removes_row_and_owned_media_folder(self) -> None:
        media_dir = self.root / "SourceMark" / "1"
        media_dir.mkdir(parents=True)
        (media_dir / "FotoFront.jpg").write_bytes(b"fake")
        mark_id = create_mark(self.settings(), self.mark_data(front_foto="SourceMark/1/FotoFront.jpg"))
        delete_mark(self.settings(), mark_id, confirm=True)
        self.assertIsNone(self.fetch_mark(mark_id))
        self.assertFalse(media_dir.exists())

    def test_delete_mark_with_confirm_works(self) -> None:
        mark_id = create_mark(self.settings(), self.mark_data(number=101))
        delete_mark(self.settings(), mark_id, confirm=True)
        self.assertIsNone(self.fetch_mark(mark_id))

    def test_delete_mark_without_confirm_is_blocked(self) -> None:
        mark_id = create_mark(self.settings(), self.mark_data(number=102))
        with self.assertRaises(MarkValidationError) as blocked:
            delete_mark(self.settings(), mark_id)
        self.assertEqual(str(blocked.exception), "Действие требует подтверждения.")
        self.assertIsNotNone(self.fetch_mark(mark_id))

    def test_dangerous_delete_uses_confirmation_not_backup_marker(self) -> None:
        mark_id = create_mark(self.settings(), self.mark_data(number=103))
        settings = Settings(
            rewards_data_dir=self.root,
            rewards_db_path=self.db_path,
            read_only=False,
            write_mode=True,
        )
        delete_mark(settings, mark_id, confirm=True)
        self.assertIsNone(self.fetch_mark(mark_id))

    def test_sql_handles_quotes_and_text(self) -> None:
        text = "Link 'single' and \"double\""
        mark_id = create_mark(self.settings(), self.mark_data(id_link=text, front_foto="SourceMark/quoted path.jpg"))
        row = self.fetch_mark(mark_id)
        self.assertEqual(row["id_link"], text)
        self.assertEqual(row["front_foto"], "SourceMark/quoted path.jpg")

    def test_empty_mark_is_not_created(self) -> None:
        with self.assertRaises(MarkValidationError) as exc:
            create_mark(self.settings(), MarkWriteData(number=1))
        self.assertEqual(str(exc.exception), "Выберите наименование знака.")

    def test_mark_date_purchase_normalizes_user_format(self) -> None:
        data = mark_data_from_mapping({"id_name": "4", "date_purchase": "05.06.2026"})
        self.assertEqual(data.date_purchase, "2026-06-05")


if __name__ == "__main__":
    unittest.main()
