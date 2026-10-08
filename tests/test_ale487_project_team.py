import sqlite3
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.routers import legacy
from tests import test_ale474_summary_booklets as fixture


class ProjectTeamTests(unittest.TestCase):
    _create_db = fixture.SummaryBookletsTests._create_db
    def setUp(self):
        fixture.SummaryBookletsTests.setUp(self)
        with sqlite3.connect(self.db_path) as db:
            db.execute('create table mark as select * from rewards where 0')
    tearDown = fixture.SummaryBookletsTests.tearDown

    def test_team_and_frozen_forms_in_all_update_states(self):
        for state in (None, dict(error='Ошибка проверки'), dict(update_available=False),
                      dict(update_available=True, current_version='2.0.23', latest_version='9.9.9')):
            with self.subTest(state=state), patch.object(legacy, 'get_settings', return_value=self.settings), \
                 patch.object(legacy, 'check_for_updates', return_value=state), TestClient(app) as client:
                response = client.get('/legacy?tab=about' + ('&check_updates=1' if state else ''))
                self.assertEqual(response.status_code, 200)
                text = response.text
                ordered = ['Команда проекта', 'Автор проекта', 'Федоринов С. А.', 'Электронная почта',
                           'mailto:fedorinov@yandex.ru', 'Разработка', 'Ерыпалов Ю. А.', 'Николаев А. Г.']
                self.assertEqual([text.index(x) for x in ordered], sorted(text.index(x) for x in ordered))
                self.assertEqual(text.count('mailto:'), 1)
                self.assertIn('>fedorinov@yandex.ru</a>', text)
                for field in ('Название', 'Текущая версия', 'Режим', 'Редактирование', 'Резервные копии', 'Папка данных', 'Commit'):
                    self.assertIn(f'<dt>{field}</dt>', text)
                self.assertIn('action="/legacy/about/title"', text)
                self.assertIn('href="/legacy?tab=about&check_updates=1"', text)
                if state and state.get('update_available'):
                    self.assertIn('action="/updates/apply"', text)
                    self.assertIn('data-update-progress', text)
                self.assertIn('Это preview рабочей версии', text)
