"""Missing-biography filtering preserves the original without-awards population list."""
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
PATH = BASE + '/without-biographies'


class MissingBiographyFilterTests(unittest.TestCase):
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
                (4,'Г Две награды'),(5,'Д Некорректная запись'),(6,'Е Другой тип'),(7,'Ж Пустая биография');
            update person set biography='Заполненная биография' where id in (2,4);
            update person set biography='  ' where id in (5,7);
            insert into rewards(person_id,id_name) values
                (2,5),(3,4),(3,4),(4,4),(4,5),(5,null),(5,99999),(6,50),(7,4),(7,4),(null,4);
        """)

    def test_original_award_list_and_biography_counter(self):
        before = self.db.read_bytes()
        default, pager = service.people_without_awards(self.settings)
        self.assertEqual([p['id'] for p in default], [1, 5])
        self.assertEqual(pager['total'], 2)
        all_empty, pager = service.people_without_biographies(self.settings)
        self.assertEqual([p['id'] for p in all_empty], [1, 3, 5, 6, 7])
        self.assertEqual(pager['total'], 5)
        selected, pager = service.people_without_biographies(self.settings, name_id=4)
        self.assertEqual([p['id'] for p in selected], [3, 7])
        self.assertEqual(pager['total'], 2)
        self.assertEqual(service.population_statistics(self.settings),
                         {'total': 7, 'filled': 2, 'empty': 5, 'without_awards': 2})
        with TestClient(app) as client:
            original = client.get(BASE + '/without-awards', params={'name_id': 4})
            self.assertEqual(original.status_code, 200)
            self.assertIn('data-without-awards-total>2', original.text)
            self.assertNotIn('select name="name_id"', original.text)
            self.assertNotIn('Без награды:', original.text)
            self.assertIn('data-without-biographies-link', client.get(BASE).text)
        self.assertEqual(self.db.read_bytes(), before)

    def test_filter_pagination_card_return_and_reset(self):
        with sqlite3.connect(self.db) as connection:
            connection.executemany('insert into person(id,fio) values(?,?)',
                                   [(i, f'Кавалер {i}') for i in range(100, 131)])
            connection.execute('insert into rewards(person_id,id_name) select id,4 from person where id between 100 and 130')
        before = self.db.read_bytes()
        origin = BASE + '/preview/' + 'a' * 64 + '?details=true'
        with TestClient(app) as client:
            response = client.get(PATH, params={'name_id': 4, 'page': 100, 'return_to': origin})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Кавалеры без биографий с наградой «Орден Трудовой Славы I степени»', response.text)
            self.assertIn('data-without-biographies-total>33', response.text)
            self.assertEqual(response.text.count('data-without-biographies-person'), 8)
            urls = re.findall(r'data-without-biographies-person href="([^"]+)"', response.text)
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
            self.assertIn('data-without-biographies-total>33', restored.text)
            self.assertEqual(restored.text.count('data-without-biographies-person'), 8)
            reset = unescape(re.search(r'data-without-biographies-reset href="([^"]+)"', response.text)[1])
            self.assertNotIn('name_id', parse_qs(urlsplit(reset).query))
            reset_response = client.get(reset)
            self.assertIn('Всего без биографий:', reset_response.text)
            self.assertIn('data-without-biographies-total>36', reset_response.text)
            self.assertEqual(client.get(BASE + '/statistics').json()['without_awards'], 2)
        self.assertEqual(self.db.read_bytes(), before)

    def test_unknown_award_rejected_and_same_label_in_other_category_is_distinct(self):
        with TestClient(app) as client:
            self.assertEqual(client.get(PATH, params={'name_id': 99999}).status_code, 400)
            self.assertEqual(client.get(PATH, params={'name_id': -1}).status_code, 422)
            self.assertEqual(client.get(PATH, params={'name_id': 2**80}).status_code, 422)
            response = client.get(PATH, params={'name_id': 50})
            self.assertEqual(response.status_code, 200)
            self.assertIn('/persons/6?', response.text)
            self.assertNotIn('/persons/3?', response.text)
            self.assertIn('data-without-biographies-total>1', response.text)

    def test_empty_named_absence(self):
        self.execute("update person set biography='Заполнено' where id in (3,7)")
        with TestClient(app) as client:
            response = client.get(PATH, params={'name_id': 4})
            self.assertEqual(response.status_code, 200)
            self.assertIn('data-without-biographies-total>0', response.text)
            self.assertIn('Кавалеров без биографий по выбранным условиям нет.', response.text)
            self.assertEqual(response.text.count('data-without-biographies-person'), 0)
