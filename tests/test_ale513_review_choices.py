"""TEMP acceptance of the option UI, keeping the signed import contract intact."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import unittest

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import biography_enrichment as bio, manual_import_review as manual, manual_review_choices as choices
from tests import test_ale513_manual_import_review as fixtures


class ChoiceReviewTests(unittest.TestCase):
    setUp = fixtures.ManualReviewTests.setUp
    execute = fixtures.ManualReviewTests.execute
    query = fixtures.ManualReviewTests.query

    def choose(self, token, row_number, submitted):
        return choices.prepare(self.settings, token, row_number,
                               {'review_revision':choices.detail(self.settings,token,row_number)['revision'], **submitted})

    def source_file(self, *, year='1930', biography='', fio=None, identity='ФИО и награда совпали',
                    award='Орден Трудовой Славы I степени', source='https://example.org/biography'):
        original=bio.read_rows(bio.export_workbook(self.settings,'',20))
        rows=[]
        for entry in original:
            v=entry['values']
            v.update({'biography':biography,'source_url':source,'status':'Требует проверки',
                      'Год в карточке':year,'ФИО в карточке':fio if fio is not None else v['ФИО'],
                      'Награда в карточке':award,'Идентификация':identity,
                      'notes':f'Источник подтверждает личность и {award} №18. Год в источнике: {year}.'})
            rows.append([v.get(h,'') for h in bio.HEADERS])
        return bio._workbook(bio.HEADERS,rows)

    def year_fixture(self, **kwargs):
        self.execute("update person set birthday='1945';update rewards set number=18;")
        return bio.preview(self.settings,self.source_file(**kwargs))

    def test_only_disputed_year_two_choices_then_explicit_commit(self):
        token,_=self.year_fixture()
        before=self.db.read_bytes()
        detail=choices.detail(self.settings,token,2)
        self.assertEqual(list(detail['fields']),['birthday'])
        self.assertEqual((detail['fields']['birthday']['current'],detail['fields']['birthday']['proposed']),('1945','1930'))
        self.assertTrue(detail['fields']['birthday']['allowed'])
        self.assertEqual(detail['fields']['birthday']['recommended'],'proposed')
        with TestClient(app) as client:
            base='/data-maintenance/enrichment/biographies'
            response=client.get(f'{base}/review/{token}/2')
            self.assertEqual(response.text.count('type="radio"'),2)
            self.assertNotIn('Решение · ФИО',response.text)
            self.assertNotIn('data-review-field="biography"',response.text)
            self.assertNotIn('checked',response.text)
            response=client.post(f'{base}/review/{token}/2/plan',data={'birthday_choice':'proposed','review_revision':detail['revision']})
            self.assertEqual(response.status_code,200)
            self.assertIn('1945',response.text);self.assertIn('1930',response.text)
            self.assertNotIn('<dt>ФИО</dt>',response.text)
        p,plan=self.choose(token,2,{'birthday_choice':'proposed'})
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(plan['writes'],['birthday'])
        event=manual.commit(self.settings,p)
        self.assertEqual(self.query('select birthday,biography from person'),[('1930',None)])
        self.assertTrue(choices.complete(event))
        self.assertEqual(choices.finished_rows(self.settings,event['file_sha256']),[2])
        self.assertEqual(event,manual.commit(self.settings,p))

    def test_biography_only_and_full_text(self):
        self.execute('update rewards set number=18')
        text='Подтверждённая биография. '*70
        token,_=bio.preview(self.settings,self.source_file(year='1918',biography=text))
        detail=choices.detail(self.settings,token,2)
        self.assertEqual(list(detail['fields']),['biography'])
        with TestClient(app) as client:
            response=client.get(f'/data-maintenance/enrichment/biographies/review/{token}/2')
            self.assertIn('Полный текст',response.text)
            self.assertIn(text,response.text)
            self.assertNotIn('data-review-field="birthday"',response.text)
        p,_=self.choose(token,2,{'biography_choice':'proposed'})
        self.assertEqual(manual.commit(self.settings,p)['writes'],['biography'])
        self.assertEqual(self.query('select biography from person'),[(text,)])

    def test_combined_choices_preserve_rejected_and_pending_fields(self):
        token,_=self.year_fixture(biography='Биография с подтверждённой личностью.',fio='Ермакова Мария Владимировна',identity='Личность подтверждена по награде и номеру')
        self.assertEqual(set(choices.detail(self.settings,token,2)['fields']),set(manual.FIELDS))
        p,_=self.choose(token,2,{'biography_choice':'proposed','birthday_choice':'current'})
        event=manual.commit(self.settings,p)
        self.assertEqual(event['writes'],['biography'])
        self.assertEqual(event['fields']['birthday']['decision'],'reject')
        self.assertEqual(event['fields']['fio']['decision'],'pending')
        self.assertFalse(choices.complete(event))
        self.assertTrue(event['identity_pending'])
        self.assertEqual(choices.finished_rows(self.settings,event['file_sha256']),[])

    def test_genuine_1945_is_selectable_and_preserves_full_date(self):
        self.execute("update person set birthday='1945-05-09';update rewards set number=18;")
        token,_=bio.preview(self.settings,self.source_file(year='1945'))
        d=choices.detail(self.settings,token,2)
        self.assertEqual(list(d['fields']),['birthday'])
        self.assertEqual(d['fields']['birthday']['current'],'1945')
        p,_=self.choose(token,2,{'birthday_choice':'proposed'})
        event=manual.commit(self.settings,p)
        self.assertEqual(event['writes'],[])
        self.assertTrue(choices.complete(event))
        self.assertEqual(self.query('select birthday from person'),[('1945-05-09',)])

    def test_unresolved_identity_and_wrong_award_or_serial_cannot_be_accepted(self):
        for changes in [{'fio':'Другой Иван Иванович'}, {'award':'Другая награда'},
                        {'identity':'Личность не подтверждена'}]:
            with self.subTest(changes=changes):
                token,_=self.year_fixture(biography='Спорный текст.',**changes)
                d=choices.detail(self.settings,token,2)
                self.assertTrue(d['ambiguous'])
                for name in d['fields']:
                    self.assertFalse(d['fields'][name]['allowed'])
                    with self.assertRaises(bio.ValidationError): self.choose(token,2,{name+'_choice':'proposed'})
        token,_=self.year_fixture()
        record=bio.load_preview(self.settings,token)
        record['entries'][0]['values']['notes']='Источник упоминает награду №19 и год1930.'
        bio._save(self.settings,token,record)
        self.assertFalse(choices.detail(self.settings,token,2)['fields']['birthday']['allowed'])
        with self.assertRaises(bio.ValidationError):self.choose(token,2,{'birthday_choice':'proposed'})
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_unresolved_identity_is_not_globally_confirmed_by_keeping_current_values(self):
        token,_=self.year_fixture(fio='Другой Иван Иванович')
        p,_=self.choose(token,2,{'birthday_choice':'current','fio_choice':'current'})
        event=manual.commit(self.settings,p)
        self.assertEqual(event['writes'],[])
        self.assertFalse(choices.complete(event))
        self.assertTrue(event['identity_pending'])

    def test_another_award_or_degree_does_not_confirm_labour_glory_first(self):
        self.execute("update guide_lev_3 set name='Трудовая Слава II степени' where id=5;"
                     "insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(11095,1,2,3,5,99)")
        token,_=self.year_fixture(award='Трудовая Слава II степени')
        record=bio.load_preview(self.settings,token)
        record['entries'][0]['values']['notes']='Личность подтверждена по Трудовой Славе II степени №99; год1930.'
        bio._save(self.settings,token,record)
        self.assertFalse(choices.detail(self.settings,token,2)['fields']['birthday']['allowed'])
        with self.assertRaises(bio.ValidationError):self.choose(token,2,{'birthday_choice':'proposed'})

    def test_hmac_and_concurrent_change_fail_closed(self):
        token,_=self.year_fixture()
        p,_=self.choose(token,2,{'birthday_choice':'proposed'})
        self.execute("update person set biography='Изменено параллельно'")
        with self.assertRaises(bio.ValidationError):manual.commit(self.settings,p)
        self.assertEqual(self.query('select birthday from person'),[('1945',)])
        self.execute('update person set biography=null')
        token,_=self.year_fixture()
        record=bio.load_preview(self.settings,token)
        record['entries'][0]['values']['snapshot_signature']='0'*64
        bio._save(self.settings,token,record)
        with self.assertRaises(bio.ValidationError):self.choose(token,2,{'birthday_choice':'proposed'})

    def test_invalid_choices_no_selection_and_long_biography(self):
        token,_=self.year_fixture()
        for values in [{},{'birthday_choice':'accept'},{'fio_choice':'proposed'}]:
            with self.assertRaises(bio.ValidationError):self.choose(token,2,values)
        token,_=self.year_fixture(biography='😀'*2501)
        self.assertFalse(choices.detail(self.settings,token,2)['fields']['biography']['allowed'])
        with self.assertRaises(bio.ValidationError):self.choose(token,2,{'biography_choice':'proposed'})
        p,_=self.choose(token,2,{'biography_choice':'current'})
        self.assertEqual(manual.commit(self.settings,p)['writes'],[])

    def test_transaction_rollback_idempotency_and_frozen_awards(self):
        token,_=self.year_fixture()
        frozen=self.query('select * from rewards'),self.query('select id,fio,id_rank,comment,person_foto from person')
        p,_=self.choose(token,2,{'birthday_choice':'proposed'})
        self.execute("create trigger fail_audit before insert on logs begin select raise(abort,'TEMP audit failure');end;")
        with self.assertRaises(sqlite3.IntegrityError):manual.commit(self.settings,p)
        self.assertEqual(self.query('select birthday from person'),[('1945',)])
        self.execute('drop trigger fail_audit')
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:manual.commit(self.settings,p),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.query('select count(*) from logs'),[(1,)])
        self.assertEqual(frozen,(self.query('select * from rewards'),self.query('select id,fio,id_rank,comment,person_foto from person')))

    def test_existing_biography_is_preserved_until_explicit_source_selection(self):
        self.execute('update rewards set number=18')
        token,_=bio.preview(self.settings,self.source_file(year='1918',biography='Предлагаемая биография.'))
        self.execute("update person set biography='Существующая биография'")
        p,_=self.choose(token,2,{'biography_choice':'current'})
        self.assertEqual(manual.commit(self.settings,p)['writes'],[])
        self.assertEqual(self.query('select biography from person'),[('Существующая биография',)])
        before=self.db.read_bytes()
        p,plan=self.choose(token,2,{'biography_choice':'proposed'})
        self.assertEqual(plan['fields']['biography']['before'],'Существующая биография')
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(manual.commit(self.settings,p)['writes'],['biography'])

    def test_change_between_view_and_choice_requires_refresh(self):
        self.execute('update rewards set number=18')
        token,_=bio.preview(self.settings,self.source_file(year='1918',biography='Предлагаемый текст.'))
        revision=choices.detail(self.settings,token,2)['revision']
        self.execute("update person set biography='Изменено после открытия'")
        before=self.db.read_bytes()
        with self.assertRaisesRegex(bio.ValidationError,'изменилась после проверки'):
            choices.prepare(self.settings,token,2,{'review_revision':revision,'biography_choice':'current'})
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])


if __name__=='__main__':unittest.main()
