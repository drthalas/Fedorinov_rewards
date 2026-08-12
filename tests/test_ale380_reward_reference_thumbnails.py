import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app.repositories.persons import list_person_rewards


ROOT = Path(__file__).resolve().parents[1]


class RewardReferenceThumbnailTests(unittest.TestCase):
    def _database(self, root: Path, *, with_image_column: bool) -> Path:
        db_path = root / "Rewards.db"
        image_column = ", image_path text" if with_image_column else ""
        with sqlite3.connect(db_path) as connection:
            connection.executescript(
                f"""
                create table rewards (
                    id integer primary key, person_id integer, id_gos integer,
                    id_catigory integer, id_sub_catigory integer, id_name integer,
                    number text, instock integer, date_purchase text,
                    price_purchase real, price_now real, front_foto text,
                    back_foto text, book1_foto text, book2_foto text, reward_list text
                );
                create table guide_lev_0 (id integer primary key, name text);
                create table guide_lev_1 (id integer primary key, name text);
                create table guide_lev_2 (id integer primary key, name text);
                create table guide_lev_3 (id integer primary key, name text{image_column});
                insert into guide_lev_3 (id, name{', image_path' if with_image_column else ''})
                values (4, 'Орден тестовый'{", 'GuideImages/test.png'" if with_image_column else ''});
                insert into rewards (id, person_id, id_name, number, instock)
                values (8, 3, 4, '42', 1);
                """
            )
        return db_path

    def test_repository_exposes_level_three_reference_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = list_person_rewards(self._database(Path(temp_dir), with_image_column=True), 3)
        self.assertEqual(rows[0]["reward_image_path"], "GuideImages/test.png")

    def test_repository_keeps_legacy_schema_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = list_person_rewards(self._database(Path(temp_dir), with_image_column=False), 3)
        self.assertIsNone(rows[0]["reward_image_path"])

    def test_templates_place_reference_image_in_required_columns(self) -> None:
        legacy = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        detail = (ROOT / "backend/app/templates/person_detail.html").read_text(encoding="utf-8")
        self.assertLess(legacy.index('class="reward-reference-photo-heading"'), legacy.index("<th>Номер</th>"))
        self.assertGreater(detail.index('class="reward-reference-photo-heading"'), detail.index("<th>Государство</th>"))
        self.assertLess(detail.index('class="reward-reference-photo-heading"'), detail.index("<th>Категория</th>"))
        for template in (legacy, detail):
            self.assertIn("reward.reward_image_path and media_exists(reward.reward_image_path)", template)
            self.assertIn('class="reward-reference-thumbnail"', template)


if __name__ == "__main__":
    unittest.main()
