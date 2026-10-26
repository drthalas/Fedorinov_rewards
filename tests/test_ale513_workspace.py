"""Single screen staging and atomic import. SQLite/media fixtures are TEMP only."""
from contextlib import closing
from io import BytesIO
from pathlib import Path
import sqlite3
import unittest
from fastapi.testclient import TestClient
from tests import test_ale513_manual_import_review as fixtures
from backend.app.main import app
from backend.app.services import biography_enrichment as bio, enrichment_workflow as flow, manual_review_choices as choices


class WorkspaceTests(unittest.TestCase):
    setUp=fixtures.ManualReviewTests.setUp
    execute=fixtures.ManualReviewTests.execute
    query=fixtures.ManualReviewTests.query

    def mixed(self, count=7):
        self.execute("update person set birthday='1954';delete from rewards where person_id!=11095;")
        with closing(sqlite3.connect(self.db)) as c:
            for n in range(1,count+1):
                year='1945' if n in [1,3] else '1932' if n==5 else '1918'
                c.execute('insert into person(id,fio,birthday,id_rank) values(?,?,?,10)',(n,f'Тестов Человек Номер{n}',year))
                c.execute('insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(?,1,2,3,4,?)',(n,10+n))
            c.commit()
        rows=[]
        for entry in bio.read_rows(bio.export_workbook(self.settings,'',5000)):
            v=entry['values'];pid=int(v['person_id']);year=v['Год рождения']
            source_year='1930' if pid==1 else '1931' if pid==5 else year
            serial='725' if pid==11095 else str(10+pid)
            v.update(biography='Проверенная биография кавалера.',source_url=f'https://warheroes.ru/hero/hero.asp?Hero_id={pid}',status='Требует проверки',
                notes=f'Полное ФИО, точная I степень №{serial}, год {source_year} сверены с карточкой.',
                **{'ФИО в карточке':'Ермакова Мария Владимировна' if pid==11095 else v['ФИО'],
                   'Год в карточке':source_year,'Награда в карточке':'Орден Трудовой Славы I степени',
                   'Идентификация':'Личность не подтверждена' if pid==11095 else 'Подтверждена'})
            if pid==6:v.update(biography='',source_url='',notes='')
            if pid==7:v['notes']='В источнике только другая награда №999; ФИО не подтверждено.'
            rows.append([v.get(h,'') for h in bio.HEADERS])
        self.content=bio._workbook(bio.HEADERS,rows)
        return bio.preview(self.settings,self.content)[0]

    def submit(self,token,row,**values):
        d=choices.detail(self.settings,token,row)
        return flow.stage(self.settings,token,row,{'review_revision':d['revision'],**values})

    def test_two_bucket_workspace_has_no_row_decisions(self):
        token=self.mixed();v=flow.workspace(self.settings,token)
        self.assertEqual(v['counts'],{'ready':6,'insufficient':2})
        before=self.db.read_bytes()
        with self.assertRaises(bio.ValidationError):flow.stage(self.settings,token,v['rows'][0]['row'],{'identity_choice':'same'})
        self.assertEqual(self.db.read_bytes(),before)

if __name__=='__main__':unittest.main()
