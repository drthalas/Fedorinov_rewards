"""Focused photo UX contracts; all DB/media writes are isolated TEMP fixtures."""
from contextlib import closing
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import os,sqlite3,unittest
from PIL import Image
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import photos
from backend.app.services.media import resolve_media
from tests import test_ale378_person_create_draft as fixture

class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.db=self.root/'photos.sqlite'
        setup=fixture.PersonCreateDraftTests();setup.db_path=self.db;setup._create_db()
        with sqlite3.connect(self.db) as c:
            c.execute("insert into person(id,fio,birthday,id_rank) values(1,'Фото Тест','1918',1),(2,'Сосед','1920',1)")
            c.execute('insert into rewards(id,person_id,id_name) values(10,1,4)');c.commit()
        for name in ['Source','SourceMark','default']:(self.root/name).mkdir()
        (self.root/'Source/1').mkdir()
        out=BytesIO();Image.new('RGB',(80,60),(50,100,150)).save(out,'PNG');self.image=out.getvalue()
        (self.root/'default/nofoto.jpg').write_bytes(self.image)
        env=patch.dict(os.environ,{'REWARDS_DATA_DIR':str(self.root),'REWARDS_DB_PATH':str(self.db),'WRITE_MODE':'true','READ_ONLY':'false','UPDATE_CHECK_ENABLED':'false','REWARDS_AUDIT_LOG':str(self.root/'audit.log')})
        env.start();self.addCleanup(env.stop);self.client=TestClient(app)
    def query(self,sql):
        with sqlite3.connect(self.db) as c:return c.execute(sql).fetchall()
    def set_photo(self,field,path='Source/1/test.png',table='person',id=1):
        (self.root/path).parent.mkdir(parents=True,exist_ok=True);(self.root/path).write_bytes(self.image)
        with sqlite3.connect(self.db) as c:c.execute(f'update {table} set {field}=? where id=?',(path,id));c.commit()
    def gallery(self):return self.client.get('/persons/1/photos')
    def test_zero_partial_all_and_editor_keeps_missing_slots(self):
        empty=self.gallery();self.assertEqual(empty.status_code,200);self.assertNotIn('data-gallery-photo ',empty.text)
        self.assertIn('Фотографии отсутствуют',empty.text);self.assertNotIn('Нет фото',empty.text)
        self.set_photo('person_foto');self.set_photo('book1_foto','Source/1/book.png')
        with sqlite3.connect(self.db) as c:c.execute("update person set main_foto='Source/1/not-there.png',card1_foto='../outside.png'");c.commit()
        partial=self.gallery();self.assertEqual(partial.text.count('data-gallery-photo '),2);self.assertNotIn('Нет фото',partial.text)
        self.assertNotIn('Фото учётной карточки, страница 1',partial.text)
        editor=self.client.get('/persons/1/edit').text
        self.assertEqual(editor.count('data-photo-editor-slot'),7);self.assertIn('Добавить фотографию: Общее фото наград',editor)
        for field in photos.PERSON_PHOTO_FIELDS:self.set_photo(field.field,'Source/1/'+field.field+'.png')
        for field in photos.REWARD_PHOTO_FIELDS:self.set_photo(field.field,'Source/1/10/'+field.field+'.png','rewards',10)
        # Remove former fixture files, otherwise the existing folder-photo feature
        # correctly includes them as additional photos.
        (self.root/'Source/1/test.png').unlink();(self.root/'Source/1/book.png').unlink()
        full=self.gallery();self.assertEqual(full.text.count('data-gallery-photo '),12)
        slide=self.client.get('/persons/1/photos?index=999').text
        self.assertIn('data-gallery-photo',slide);self.assertIn('Предыдущее',slide);self.assertIn('Следующее',slide)
    def test_strict_gallery_media_missing_vs_default_fallback_and_path_guards(self):
        self.set_photo('person_foto');self.assertEqual(self.client.get('/media?path=Source/1/test.png&required=true').content,self.image)
        for path in ['Source/1/missing.png','../outside.png',str(self.root.parent/'outside.png')]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get('/media',params={'path':path,'required':'true'}).status_code,404)
                self.assertEqual(self.client.head('/media',params={'path':path,'required':'true'}).status_code,404)
                self.assertEqual(self.client.get('/media',params={'path':path}).status_code,200)
        (self.root/'Source/1/test.png').unlink()
        self.assertEqual(self.gallery().text.count('data-gallery-photo '),0)
        self.assertEqual(self.client.get('/media?path=Source/1/test.png&required=true').status_code,404)
    def test_transient_resolution_error_is_not_empty_and_valid_neighbor_remains(self):
        self.set_photo('person_foto');self.set_photo('book1_foto','Source/1/book.png')
        def transient(settings,path):
            if path=='Source/1/test.png':raise OSError('TEMP unavailable')
            return resolve_media(settings,path)
        with patch('backend.app.routers.persons.resolve_media',side_effect=transient):
            response=self.gallery();self.assertEqual(response.status_code,200)
            self.assertIn('data-gallery-unavailable="true"',response.text)
            self.assertEqual(response.text.count('data-gallery-photo '),1)
            self.assertIn('data-gallery-empty role="status" hidden',response.text)
    def test_unreadable_file_is_transient_in_strict_media(self):
        unavailable=SimpleNamespace(fallback=True,fallback_reason="file is not readable")
        with patch('backend.app.routers.media.resolve_media',return_value=unavailable):
            self.assertEqual(self.client.get('/media?path=Source/locked.png&required=true').status_code,503)
            self.assertEqual(self.client.head('/media?path=Source/locked.png&required=true').status_code,503)

    def test_draft_save_failure_clear_and_reload_stay_in_selected_slot(self):
        response=self.client.get('/persons/new');import re
        token=re.search(r'data-draft-token="([^"]+)"',response.text)[1]
        base='/persons/new/draft/'+token+'/photos'
        self.assertTrue(self.client.post(base,data={'photo_field':'person_foto'},files={'file':('test.png',self.image,'image/png')}).json()['ok'])
        before=self.client.get(base+'/person_foto').content
        failed=self.client.post(base,data={'photo_field':'person_foto'},files={'file':('test.png',b'invalid','image/png')})
        self.assertGreaterEqual(failed.status_code,400);self.assertEqual(self.client.get(base+'/person_foto').content,before)
        self.assertEqual(self.query('select person_foto,main_foto from person'),[(None,None),(None,None)])
        loaded=self.client.get('/persons/new/draft/'+token).text
        self.assertIn('data-draft-photo-placeholder hidden',loaded)
        self.assertTrue(self.client.post(base+'/person_foto/clear').json()['ok'])
        self.assertEqual(self.client.get(base+'/person_foto').status_code,404)
    def test_upload_and_failed_replace_preserve_neighbor_and_reload(self):
        self.set_photo('book1_foto','Source/1/book.png')
        data={'entity_type':'person','entity_id':'1','photo_field':'person_foto','return_url':'/persons/1/edit'}
        response=self.client.post('/photos/upload',data=data,files={'file':('test.png',self.image,'image/png')},follow_redirects=False)
        self.assertEqual(response.status_code,303);before=self.query('select person_foto,book1_foto from person')
        self.assertEqual(self.gallery().text.count('data-gallery-photo '),2)
        response=self.client.post('/photos/upload',data=data,files={'file':('bad.png',b'invalid','image/png')})
        self.assertEqual(response.status_code,400);self.assertEqual(self.query('select person_foto,book1_foto from person'),before)
        self.assertEqual(self.gallery().text.count('data-gallery-photo '),2)

if __name__=='__main__':unittest.main()
