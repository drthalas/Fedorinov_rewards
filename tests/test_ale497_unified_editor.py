from contextlib import closing
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.app.services.photo_editor import edit_photo
from backend.app.services.photos import save_photo, PhotoConflictError
from backend.app.services.person_create_drafts import (
    edit_staged_photo, new_draft_token, stage_photo, stage_reward_photo,
    staged_photo_path, staged_reward_photo_path, start_reward, load_draft,
)
from tests import test_photo_management as photos_fixture
from tests import test_ale378_person_create_draft as draft_fixture
from tests.test_ale497_photo_editor import image_bytes


class UnifiedEditorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = photos_fixture.PhotoManagementTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.settings = self.fixture.settings()
        self.root = self.fixture.root
        self.db = self.fixture.db_path
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("create table guide(id integer primary key, name text, image_path text);"
                                     "create table guide_lev_3(id integer primary key, name text, image_path text);")
            for table in ['guide', 'guide_lev_3']:
                connection.execute(f"insert into {table} values(1, 'Не менять название', 'GuideImages/shared.png')")
            connection.commit()
        (self.root / 'GuideImages').mkdir()
        (self.root / 'GuideImages/shared.png').write_bytes(image_bytes())

    def test_all_persisted_families_edit_selected_slot_only(self):
        for kind, entity_id, field, neighbor, table in [
            ('person', 1, 'person_foto', 'main_foto', 'person'),
            ('reward', 10, 'reward_list', 'book1_foto', 'rewards'),
            ('mark', 20, 'front_foto', 'back_foto', 'mark'),
        ]:
            with self.subTest(kind=kind):
                original = save_photo(self.settings, kind, entity_id, field, 'a.png', image_bytes())
                with closing(sqlite3.connect(self.db)) as connection:
                    connection.execute(f'update {table} set {neighbor}=? where id=?', (original, entity_id))
                    connection.commit()
                result = edit_photo(self.settings, kind, entity_id, field, original, [5, 5, 60, 40], .5)
                self.assertNotEqual(result.path, original)
                self.assertTrue((self.root / original).exists())
                self.assertEqual(self.fixture.fetch_value(table, entity_id, neighbor), original)
                with Image.open(self.root / result.path) as image:
                    self.assertEqual(image.size, (60, 40))
                    self.assertEqual(image.getpixel((0, 0)), (50, 40, 30, 128))

    def test_guides_preserve_shared_image_and_unsaved_metadata(self):
        for kind, table in [('rank', 'guide'), ('guide', 'guide_lev_3')]:
            result = edit_photo(self.settings, kind, 1, 'image_path', 'GuideImages/shared.png', [0, 0, 60, 40], 1)
            self.assertTrue((self.root / result.path).exists())
            with closing(sqlite3.connect(self.db)) as connection:
                self.assertEqual(connection.execute(f'select name from {table} where id=1').fetchone()[0], 'Не менять название')
            with self.assertRaises(PhotoConflictError):
                edit_photo(self.settings, kind, 1, 'image_path', 'GuideImages/shared.png', [0, 0, 60, 40], 1)

    def test_guide_sql_failure_leaves_original_and_no_orphan(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("create trigger fail before update on guide begin select raise(ABORT,'test'); end")
            connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            edit_photo(self.settings, 'rank', 1, 'image_path', 'GuideImages/shared.png', [0, 0, 60, 40], 1)
        self.assertEqual(list((self.root / 'GuideImages').iterdir()), [self.root / 'GuideImages/shared.png'])
        self.assertEqual(self.fixture.fetch_value('guide', 1, 'image_path'), 'GuideImages/shared.png')

    def test_generic_endpoint_whitelists_targets_and_slot_names(self):
        client = TestClient(app)
        values = {'photo_field': 'image_path', 'expected_path': 'GuideImages/shared.png', 'crop': [0, 0, 60, 40], 'brightness': 1}
        with patch('backend.app.routers.photos.get_settings', return_value=self.settings):
            response = client.post('/photos/rank/1/edit', json=values)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(client.post('/photos/not_a_table/1/edit', json=values).status_code, 400)
            values['photo_field'] = 'name'
            self.assertEqual(client.post('/photos/rank/1/edit', json=values).status_code, 400)

    def test_staged_person_and_reward_publish_without_sqlite_writes(self):
        fixture = draft_fixture.PersonCreateDraftTests(); fixture.setUp()
        try:
            token = new_draft_token(); reward = start_reward(fixture.settings, token)
            original = image_bytes()
            stage_photo(fixture.settings, token, 'person_foto', 'a.png', original)
            stage_reward_photo(fixture.settings, token, reward, 'front_foto', 'a.png', original)
            before = fixture.db_path.read_bytes()
            for field, reward_token in [('person_foto', None), ('front_foto', reward)]:
                revision = edit_staged_photo(fixture.settings, token, field, sha256(original).hexdigest(), [0, 0, 60, 40], 1.5, reward_token)
                path = (staged_reward_photo_path(fixture.settings, token, reward, field) if reward_token
                        else staged_photo_path(fixture.settings, token, field))
                self.assertEqual(sha256(path.read_bytes()).hexdigest(), revision)
                with Image.open(path) as image:self.assertEqual(image.size, (60, 40))
                with self.assertRaises(PhotoConflictError):
                    edit_staged_photo(fixture.settings, token, field, sha256(original).hexdigest(), [0, 0, 60, 40], 1, reward_token)
            self.assertEqual(before, fixture.db_path.read_bytes())
        finally:fixture.tearDown()

    def test_staged_manifest_failure_keeps_original_and_reference(self):
        fixture = draft_fixture.PersonCreateDraftTests(); fixture.setUp()
        try:
            token = new_draft_token(); original = image_bytes()
            stage_photo(fixture.settings, token, 'person_foto', 'a.png', original)
            path = staged_photo_path(fixture.settings, token, 'person_foto')
            before = load_draft(fixture.settings, token)
            with patch('backend.app.services.person_create_drafts._save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    edit_staged_photo(fixture.settings, token, 'person_foto', sha256(original).hexdigest(), [0, 0, 60, 40], 1)
            self.assertEqual(load_draft(fixture.settings, token), before)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])
        finally:fixture.tearDown()
