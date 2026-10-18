"""Search-to-editor identity and guarded person save contracts on TEMP data."""
from contextlib import closing
from html.parser import HTMLParser
from types import SimpleNamespace
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.repositories.search import search_all
from backend.app.routers.templates import templates
from backend.app.services.photos import save_photo
from tests.test_ale497_photo_editor import image_bytes
from tests import test_search as search_fixture
from tests import test_photo_management as photo_fixture


class Slots(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.slots = {}
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'td':
            self.current = attrs
        if tag == 'button' and 'data-search-photo-edit' in attrs:
            self.slots[self.current['data-search-photo-field']] = (self.current['data-photo-edit-url'], attrs['data-photo-field'])


class SearchPhotoEditorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = search_fixture.SearchRepositoryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        with closing(sqlite3.connect(self.fixture.db_path)) as db:
            db.execute("update person set person_foto='Source/1/person.png', book1_foto='Source/1/book.png', card1_foto='Source/1/card.png' where id=1")
            db.execute("update rewards set front_foto='Source/1/front.png', book1_foto='Source/1/reward-book.png', reward_list='Source/1/document.pdf' where id=10")
            db.commit()

    def render(self, writable=True, exists=True):
        results = search_all(self.fixture.db_path, '', scope='rewards')
        with patch.dict(templates.env.globals, {'media_exists': lambda path: bool(path) and exists}):
            return templates.env.get_template('search.html').render(
                request=search_fixture.TemplateRequest(), settings=SimpleNamespace(write_mode=writable),
                q='', scope='rewards', mode='contains', results=results, message='',
                photo_mode='photos', search_suggestions={}, search_return_to='/search?scope=rewards',
                sort='', dir='asc', search_pagination=None,
                search_sort={'sort': '', 'dir': 'asc', 'urls': {}},
            )

    def test_person_and_reward_document_slots_have_exact_owner_identity(self):
        slots = Slots(self.render()).slots
        self.assertEqual(slots['person_foto_flag'], ('/photos/person/1/edit', 'person_foto'))
        self.assertEqual(slots['person_book1_foto_flag'], ('/photos/person/1/edit', 'book1_foto'))
        self.assertEqual(slots['person_card1_foto_flag'], ('/photos/person/1/edit', 'card1_foto'))
        self.assertEqual(slots['reward_book1_foto_flag'], ('/photos/reward/10/edit', 'book1_foto'))
        self.assertEqual(slots['front_foto_flag'], ('/photos/reward/10/edit', 'front_foto'))
        self.assertNotIn('reward_list_flag', slots)  # unsupported PDF remains view-only

    def test_missing_and_read_only_photos_have_no_editor_action(self):
        self.assertEqual(Slots(self.render(writable=False)).slots, {})
        self.assertEqual(Slots(self.render(exists=False)).slots, {})

    def test_person_http_save_preserves_shared_reward_reference_and_enforces_read_only(self):
        fixture = photo_fixture.PhotoManagementTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        settings = fixture.settings()
        path = save_photo(settings, 'person', 1, 'person_foto', 'test.png', image_bytes())
        with closing(sqlite3.connect(fixture.db_path)) as db:
            db.execute('update rewards set front_foto=? where id=10', (path,))
            db.commit()
        values = {'photo_field': 'person_foto', 'expected_path': path, 'crop': [0, 0, 60, 40], 'brightness': 1.5}
        client = TestClient(app)
        with patch('backend.app.routers.photos.get_settings', return_value=settings):
            response = client.post('/photos/person/1/edit', json=values)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(fixture.fetch_value('person', 1, 'person_foto'), path)
        self.assertEqual(fixture.fetch_value('rewards', 10, 'front_foto'), path)
        self.assertTrue((fixture.root / path).is_file())
        current = fixture.fetch_value('person', 1, 'person_foto')
        values['expected_path'] = current
        with patch('backend.app.routers.photos.get_settings', return_value=fixture.settings(False)):
            self.assertEqual(client.post('/photos/person/1/edit', json=values).status_code, 403)
        self.assertEqual(fixture.fetch_value('person', 1, 'person_foto'), current)
