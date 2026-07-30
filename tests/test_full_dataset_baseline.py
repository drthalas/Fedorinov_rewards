import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "full_dataset_baseline.py"
SPEC = importlib.util.spec_from_file_location("full_dataset_baseline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FullDatasetBaselineTests(unittest.TestCase):
    def test_timed_request_records_windows_connection_reset(self):
        with patch.object(
            MODULE.urllib.request,
            "urlopen",
            side_effect=ConnectionResetError(10054, "connection reset"),
        ):
            result = MODULE.timed_request(
                "http://127.0.0.1:18188",
                "/legacy?tab=rewards",
                1,
            )

        self.assertIsNone(result["status"])
        self.assertEqual(result["bytes"], 0)
        self.assertEqual(result["error"], "ConnectionResetError")

    def test_fixture_targets_do_not_expose_private_values(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "fixture.sqlite"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executescript(
                    """
                    create table person (
                        id integer primary key,
                        person_foto text
                    );
                    create table rewards (
                        id integer primary key,
                        person_id integer
                    );
                    insert into person(id, person_foto) values
                        (10, null),
                        (20, 'Source/private/photo.jpg'),
                        (30, null);
                    insert into rewards(id, person_id) values
                        (1, 20),
                        (2, 30),
                        (3, 30),
                        (4, 30);
                    """
                )
                connection.commit()

            targets = MODULE.fixture_targets(db_path)

            self.assertEqual(targets["no_rewards_id"], 10)
            self.assertEqual(targets["ordinary_id"], 30)
            self.assertEqual(targets["heavy_id"], 30)
            self.assertEqual(targets["heavy_reward_count"], 3)
            self.assertEqual(targets["media_path"], "Source/private/photo.jpg")
            public = {
                "heavy_reward_count": targets["heavy_reward_count"],
            }
            self.assertNotIn("private", str(public))


if __name__ == "__main__":
    unittest.main()
