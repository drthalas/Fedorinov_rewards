"""Absent-award filtering is read-only and preserves the original population list."""
from html import unescape
import re
import sqlite3
import unittest
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import biography_enrichment as service
from tests import test_ale523 as fixture

BASE = fixture.BASE
PATH = BASE + '/without-awards'


class MissingAwardFilterTests(unittest.TestCase):
    execute = fixture.Ale523Tests.execute
    query = fixture.Ale523Tests.query

    def setUp(self):
        fixture.Ale523Tests.setUp(self)
        self.execute("""
            delete from rewards;
            delete from person;
            insert or replace into guide_lev_3(id,idl,name) values(5,3,'Медаль Другая');
            insert into guide_lev_1(id,idl,name) values(20,1,'Юбилейные');
            insert into guide_lev_2(id,idl,name) values(30,20,'Знаки');
            insert into guide_lev_3(id,idl,name)
                select 50,30,name from guide_lev_3 where id=4;
            insert into person(id,fio) values
                (1,'А Без наград'),(2,'Б Другая награда'),(3,'В Выбранная награда'),
                (4,'Г Две награды'),(5,'Д Некорректная запись'),(6,'Е Другой тип');
            insert into rewards(person_id,id_name) values
                (2,5),(3,4),(3,4),(4,4),(4,5),(5,null),(5,99999),(6,50),(null,4);
        """)

    def test_named_absence_includes_other_awards_and_preserves_default_counter(self):
        before = self.db.read_bytes()
        default, pager = service.people_without_awards(self.settings)
        self.assertEqual([p['id'] for p in default], [1, 5])
        self.assertEqual(pager['total'], 2)
        selected, pager = service.people_without_awards(self.settings, name_id=4)
        self.assertEqual([p['id'] for p in selected], [1, 2, 5, 6])
        self.assertEqual(pager['total'], 4)
        self.assertEqual(service.population_statistics(self.settings)['without_awards'], 2)
        self.assertEqual(self.db.read_bytes(), before)

    def test_filter_pagination_card_return_and_reset(self):
        with sqlite3.connect(self.db) as connection:
            connection.executemany('insert into person(id,fio) values(?,?)',
                                   [(i, f'Кавалер {i}') for i in range(100, 131)])
        before = self.db.read_bytes()
        origin = BASE + '/preview/' + 'a' * 64 + '?details=true'
        with TestClient(app) as client:
            response = client.get(PATH, params={'name_id': 4, 'page': 100, 'return_to': origin})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Без награды: Орден Трудовой Славы I степени', response.text)
            self.assertIn('data-without-awards-total>35', response.text)
            self.assertEqual(response.text.count('data-without-awards-person'), 10)
            urls = re.findall(r'data-without-awards-person href="([^"]+)"', response.text)
            card_url = unescape(urls[0])
            target = parse_qs(urlsplit(card_url).query)['return_to'][0]
            query = parse_qs(urlsplit(target).query)
            self.assertEqual(query['page'], ['2'])
            self.assertEqual(query['name_id'], ['4'])
            self.assertEqual(query['country_id'], ['1'])
            self.assertEqual(query['category_id'], ['2'])
            self.assertEqual(query['subcategory_id'], ['3'])
            self.assertEqual(query['return_to'], [origin])
            card = client.get(card_url)
            self.assertEqual(card.status_code, 200)
            self.assertIn(target, unescape(card.text))
            restored = client.get(target)
            self.assertIn('data-without-awards-total>35', restored.text)
            self.assertEqual(restored.text.count('data-without-awards-person'), 10)
            reset = unescape(re.search(r'data-without-awards-reset href="([^"]+)"', response.text)[1])
            self.assertNotIn('name_id', parse_qs(urlsplit(reset).query))
            reset_response = client.get(reset)
            self.assertIn('Всего без наград:', reset_response.text)
            self.assertIn('data-without-awards-total>33', reset_response.text)
            self.assertEqual(client.get(BASE + '/statistics').json()['without_awards'], 33)
        self.assertEqual(self.db.read_bytes(), before)

    def test_unknown_award_rejected_and_same_label_in_other_category_is_distinct(self):
        with TestClient(app) as client:
            self.assertEqual(client.get(PATH, params={'name_id': 99999}).status_code, 400)
            self.assertEqual(client.get(PATH, params={'name_id': -1}).status_code, 422)
            self.assertEqual(client.get(PATH, params={'name_id': 2**80}).status_code, 422)
            response = client.get(PATH, params={'name_id': 50})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('/persons/6?', response.text)
            self.assertIn('/persons/3?', response.text)
            self.assertIn('data-without-awards-total>5', response.text)

    def test_empty_named_absence(self):
        self.execute('insert into rewards(person_id,id_name) select id,4 from person;')
        with TestClient(app) as client:
            response = client.get(PATH, params={'name_id': 4})
            self.assertEqual(response.status_code, 200)
            self.assertIn('data-without-awards-total>0', response.text)
            self.assertIn('Кавалеров без выбранной награды нет.', response.text)
            self.assertEqual(response.text.count('data-without-awards-person'), 0)
