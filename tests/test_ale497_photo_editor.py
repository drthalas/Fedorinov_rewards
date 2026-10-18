from contextlib import closing
from io import BytesIO
import sqlite3
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.photo_editor import edit_reward_photo, edited_image
from backend.app.services.photos import PhotoValidationError, PhotoConflictError, save_photo
from backend.app.services.write_guard import WriteBlockedError
from tests import test_photo_management as fixtures


def image_bytes(size=(120, 80), color=(100, 80, 60, 128)):
    stream = BytesIO()
    Image.new("RGBA", size, color).save(stream, "PNG")
    return stream.getvalue()


class PhotoEditorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PhotoManagementTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.settings = self.fixture.settings()
        self.root = self.fixture.root
        self.db = self.fixture.db_path
        self.original = save_photo(self.settings, "reward", 10, "front_foto", "test.png", image_bytes())

    def path(self):
        return self.fixture.fetch_value("rewards", 10, "front_foto")

    def edit(self, **kwargs):
        return edit_reward_photo(self.settings, 10, "front_foto", kwargs.pop("path", self.original),
                                 kwargs.pop("crop", [10, 5, 60, 40]), kwargs.pop("brightness", 1.5))

    def test_crop_brightness_alpha_and_repeated_urls(self):
        first = self.edit()
        with Image.open(self.root / first.path) as image:
            self.assertEqual(image.size, (60, 40))
            self.assertEqual(image.getpixel((0, 0)), (150, 120, 90, 128))
        self.assertFalse((self.root / self.original).exists())
        paths = [self.original, first.path]
        for _ in range(3):
            result = self.edit(path=self.path(), crop=[0, 0, 60, 40], brightness=1)
            paths.append(result.path)
        self.assertEqual(len(paths), len(set(paths)))

    def test_shared_source_is_preserved_and_neighbor_unchanged(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("update rewards set back_foto=? where id=10", (self.original,))
            connection.commit()
        self.edit()
        self.assertTrue((self.root / self.original).exists())
        self.assertEqual(self.fixture.fetch_value("rewards", 10, "back_foto"), self.original)

    def test_missing_source_does_not_edit_placeholder(self):
        (self.root / self.original).unlink()
        (self.root / "default").mkdir()
        Image.new("RGB", (120, 80)).save(self.root / "default/nofoto.jpg")
        with self.assertRaises(PhotoValidationError):
            self.edit()
        self.assertEqual(self.path(), self.original)

    def test_stale_editor_cannot_overwrite_new_photo(self):
        self.edit()
        current = self.path()
        with self.assertRaises(PhotoConflictError):
            self.edit()
        self.assertEqual(self.path(), current)

    def test_conflict_checked_again_in_write_transaction(self):
        real_transform = edited_image
        def competing_save(*args):
            result = real_transform(*args)
            save_photo(self.settings, "reward", 10, "front_foto", "new.png", image_bytes())
            return result
        with patch("backend.app.services.photo_editor.edited_image", side_effect=competing_save):
            with self.assertRaises(PhotoConflictError):
                self.edit()
        self.assertNotEqual(self.path(), self.original)
        self.assertEqual(len(list((self.root / "Source/1/10").glob("*.png"))), 1)

    def test_sqlite_failure_rolls_back_and_discards_new_file(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("create trigger reject_edit before update on rewards begin select raise(ABORT, 'test'); end")
            connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.edit()
        self.assertEqual(self.path(), self.original)
        self.assertEqual(list((self.root / "Source/1/10").glob("*.png")), [self.root / self.original])

    def test_file_failure_keeps_source_and_reference(self):
        with patch("backend.app.services.photos.write_collision_safe_media", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.edit()
        self.assertEqual(self.path(), self.original)
        self.assertTrue((self.root / self.original).exists())

    def test_validation_and_read_only_do_not_write(self):
        for crop, brightness in [([-1, 0, 5, 5], 1), ([0, 0, 0, 1], 1), ([0, 0, 121, 1], 1), ([0, 0, 1, 1], float("nan"))]:
            with self.subTest(crop=crop, brightness=brightness), self.assertRaises(PhotoValidationError):
                self.edit(crop=crop, brightness=brightness)
        with self.assertRaises(WriteBlockedError):
            edit_reward_photo(self.fixture.settings(False), 10, "front_foto", self.original, [0, 0, 1, 1], 1)
        self.assertEqual(self.path(), self.original)

    def test_exif_orientation_and_invalid_image(self):
        source = Image.new("RGB", (30, 20), (100, 80, 60))
        exif = source.getexif(); exif[274] = 6
        output = BytesIO(); source.save(output, "JPEG", exif=exif)
        with Image.open(BytesIO(edited_image(output.getvalue(), [0, 0, 20, 30], 1))) as result:
            self.assertEqual(result.size, (20, 30))
        with self.assertRaises(PhotoValidationError):
            edited_image(b"not an image", [0, 0, 1, 1], 1)

    def test_http_failure_preserves_original_and_returns_message(self):
        client = TestClient(app)
        values = {"photo_field": "front_foto", "expected_path": self.original, "crop": [0, 0, 60, 40], "brightness": 1}
        with patch("backend.app.routers.photos.get_settings", return_value=self.settings), \
                patch("backend.app.services.photos.write_collision_safe_media", side_effect=OSError("disk full")):
            response = client.post("/rewards/10/photos/edit", json=values)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Исходное фото сохранено", response.json()["detail"])
        self.assertEqual(self.path(), self.original)

    def test_invalid_slot_is_rejected(self):
        with self.assertRaises(PhotoValidationError):
            edit_reward_photo(self.settings, 10, "person_id", self.original, [0, 0, 1, 1], 1)
        self.assertEqual(self.path(), self.original)

    def test_http_contract_validation_and_conflict(self):
        client = TestClient(app)
        values = {"photo_field": "front_foto", "expected_path": self.original, "crop": [0, 0, 60, 40], "brightness": 0.5}
        with patch("backend.app.routers.photos.get_settings", return_value=self.settings):
            response = client.post("/rewards/10/photos/edit", json=values)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["ok"])
            self.assertIn("/media?path=", response.json()["url"])
            self.assertEqual(client.post("/rewards/10/photos/edit", json=values).status_code, 409)
            values["crop"] = [0.5, 0, 1, 1]
            self.assertEqual(client.post("/rewards/10/photos/edit", json=values).status_code, 422)
