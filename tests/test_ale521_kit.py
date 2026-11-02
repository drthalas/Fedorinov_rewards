"""Only new kit safety/immutable-reading behavior; not the prior import suite."""
import hashlib,json,sqlite3,unittest
from pathlib import Path
from scripts.diagnose_enrichment_import import diagnose
from tests import test_ale513_workspace as fixture

class KitTests(unittest.TestCase):
    setUp=fixture.WorkspaceTests.setUp
    execute=fixture.WorkspaceTests.execute
    query=fixture.WorkspaceTests.query
    mixed=fixture.WorkspaceTests.mixed
    def test_immutable_valid_invalid_stale_missing_and_no_writes(self):
        from backend.app.services import biography_enrichment as b
        self.mixed();key=self.root/'signing.key'
        def run(content):
            before=self.db.read_bytes();exists=key.exists();value=key.read_bytes() if exists else None
            d=diagnose(self.settings,content,state_root=self.root)
            self.assertEqual(before,self.db.read_bytes());self.assertEqual(exists,key.exists())
            if exists:self.assertEqual(value,key.read_bytes())
            self.assertFalse(Path(str(self.db)+'-wal').exists());self.assertFalse(Path(str(self.db)+'-shm').exists())
            return d
        valid=run(self.content);self.assertFalse(valid['fatal']);self.assertEqual(valid['hmac_valid_rows'],8)
        v=b.read_rows(self.content)[0]['values'];v['snapshot_signature']='0'*64
        bad=run(b._workbook(b.HEADERS,[[v.get(h,'') for h in b.HEADERS]]));self.assertEqual(bad['failure_counts'],{'signature_invalid':1})
        self.execute("update rewards set number=111111 where person_id=1")
        stale=run(self.content);self.assertEqual(stale['failure_counts'],{'identity_mismatch_unconfirmed':1})
        self.assertEqual(stale['live_consistency'],'not_proven_no_live_SQLite_lock')
        key.unlink();missing=run(self.content);self.assertEqual(missing['hmac_not_tested_rows'],8);self.assertFalse(key.exists())
    def test_wal_refused_without_creating_sidecars(self):
        self.mixed()
        with sqlite3.connect(self.db) as connection:connection.execute('pragma journal_mode=wal')
        paths=set(self.root.iterdir())
        with self.assertRaisesRegex(ValueError,'wal_mode_not_supported'):
            diagnose(self.settings,self.content,state_root=self.root)
        self.assertEqual(paths,set(self.root.iterdir()))
