import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.sergey_intake import Store,Intake
from scripts.sergey_delivery import DeliveryStore,DeliveryBlocked
from scripts.sergey_production import ProductionRunner,LiveAdapter,STAGES,ReadRetry,arm
from scripts import send_release_notification as sender


class Crash(BaseException):pass


class API:
    def __init__(self):
        self.remote={};self.calls=[];self.crash=None;self.lost=None;self.conflict=None;self.read_failure=False
    def local(self,b):pass
    def scope(self,b):pass
    def baseline(self,b,**kwargs):pass
    def reconcile(self,stage,b):
        if self.read_failure:self.read_failure=False;raise ReadRetry('read_unavailable')
        if self.conflict==stage:raise DeliveryBlocked('remote_artifact_conflict')
        if stage=='parity':
            if not self.remote.get('publish'):raise ReadRetry('parity_pending')
            return {'anonymous':True}
        return self.remote.get(stage)
    def execute(self,stage,b):
        self.calls.append(stage)
        self.remote[stage]=({'message_id':101 if stage=='notify_primary' else 202,'status':'sent'}
                            if stage.startswith('notify_') else {'exact':True})
        if self.crash==stage:self.crash=None;raise Crash()
        if self.lost==stage:self.lost=None;raise RuntimeError('response_lost')
        return self.remote[stage]


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.state=DeliveryStore(self.root/'delivery.sqlite3');self.intake=Store(self.root/'intake.sqlite3')
        pilot={'issue_id':'ALE-533','revision':2,'contract_hash':'a'*64};self.job=self.state.claim(pilot,'TEMP')
        self.binding={'version':'2.0.33','issue':'ALE-533','revision':2,'source_head':'a'*40,
                      'package_head':'b'*40,'zip_sha256':'c'*64,'size':123,'updater_pass_sha256':'d'*64}
        self.record=arm(self.intake,22,self.binding)
        self.intake.db.execute("UPDATE outbox SET status='sent',result=? WHERE key=?",
                              (json.dumps({'message_id':500}),self.record['outbox_key']))
        self.api=API()
    def tearDown(self):self.intake.db.close();self.state.db.close();self.temp.cleanup()
    def press(self,*,user=22,token=None,message=500,update=1):
        Intake(self.intake,11,22).process({'update_id':update,'callback_query':{
            'id':str(update),'from':{'id':user},'data':'prod:yes:'+(token or self.record['token']),
            'message':{'message_id':message,'chat':{'id':user,'type':'private'}}}})
    def runner(self):return ProductionRunner(self.state,self.intake,self.api,self.binding)
    def finish(self,r):
        for _ in range(25):
            r.next_tick=0
            if r.tick(self.job):return
        self.fail('Pipeline did not complete')
    def test_no_mutation_before_real_owner_callback_and_invalid_callbacks_do_nothing(self):
        r=self.runner();r.tick(self.job)
        for i,kwargs in enumerate([{'user':11},{'token':'stale'},{'message':999}],1):
            self.press(update=i,**kwargs);r.tick(self.job)
        self.assertEqual(self.api.calls,[]);self.assertIsNone(self.state.operation(self.job['id'],'production'))
    def test_restart_after_every_mutation_reconciles_without_repeating(self):
        self.press()
        for stage in [s for s in STAGES if s!='parity']:
            r=self.runner();self.api.crash=stage
            while self.api.crash:
                r.next_tick=0
                with self.subTest(stage=stage):
                    try:r.tick(self.job)
                    except Crash:break
            self.state.db.close();self.intake.db.close()
            self.state=DeliveryStore(self.root/'delivery.sqlite3');self.intake=Store(self.root/'intake.sqlite3')
        self.finish(self.runner())
        self.assertEqual(self.api.calls,[s for s in STAGES if s!='parity'])
        self.press(update=50);self.runner().tick(self.job)
        self.assertEqual(len(self.api.calls),len(STAGES)-1)
        self.assertEqual(self.intake.db.execute("SELECT count(*) FROM outbox WHERE key LIKE 'production-complete:%'").fetchone()[0],1)
    def test_unknown_api_result_reconciles_existing_target(self):
        self.press();self.api.lost='record';self.finish(self.runner())
        self.assertEqual(self.api.calls.count('record'),1)
    def test_read_failure_retries_without_mutation_and_pause_holds(self):
        self.press();r=self.runner();self.intake.set_meta('delivery_paused','1');r.tick(self.job)
        self.assertEqual(self.api.calls,[])
        self.intake.set_meta('delivery_paused','0');self.api.read_failure=True;r.tick(self.job)
        self.assertEqual(self.api.calls,[]);self.finish(r)
    def test_conflicting_archive_blocks_before_stable_publication(self):
        self.press();self.api.conflict='archive';r=self.runner()
        for _ in range(10):r.next_tick=0;r.tick(self.job)
        self.assertEqual(self.state.operation(self.job['id'],'production')['status'],'blocked')
        self.assertNotIn('archive',self.api.calls);self.assertNotIn('publish',self.api.calls)
        self.assertEqual(self.intake.db.execute("SELECT count(*) FROM outbox WHERE key LIKE 'production-blocker:%'").fetchone()[0],1)
    def test_complete_checkpoint_recovers_missing_owner_report(self):
        self.press();r=self.runner()
        with patch.object(r,'complete_report',side_effect=Crash):
            with self.assertRaises(Crash):self.finish(r)
        self.assertEqual(self.state.operation(self.job['id'],'production')['status'],'complete')
        self.assertTrue(self.runner().tick(self.job))
        self.assertEqual(self.intake.db.execute("SELECT count(*) FROM outbox WHERE key LIKE 'production-complete:%'").fetchone()[0],1)
    def test_changed_binding_or_expired_or_paused_button_cannot_authorize(self):
        self.intake.set_meta('paused','1');self.press();self.assertEqual(json.loads(self.intake.meta('production_approval'))['state'],'waiting')
        self.intake.set_meta('paused','0')
        record=json.loads(self.intake.meta('production_approval'));record['expires']=1;self.intake.set_meta('production_approval',json.dumps(record));self.press(update=2)
        self.assertEqual(json.loads(self.intake.meta('production_approval'))['state'],'expired')
        r=self.runner();r.binding={**self.binding,'zip_sha256':'changed'};r.tick(self.job);self.assertEqual(self.api.calls,[])

    def test_other_approved_binding_cannot_reuse_existing_run_receipts(self):
        self.press();self.runner().tick(self.job)
        before=list(self.api.calls);self.binding={**self.binding,'zip_sha256':'new artifact'}
        self.record=arm(self.intake,22,self.binding)
        self.intake.db.execute("UPDATE outbox SET status='sent',result=? WHERE key=?",
                              (json.dumps({'message_id':501}),self.record['outbox_key']))
        self.press(message=501,update=2);self.runner().tick(self.job)
        self.assertEqual(self.api.calls,before)
        self.assertEqual(self.state.operation(self.job['id'],'production')['body']['blocker'],'production_run_binding_conflict')
    def test_existing_matching_asset_is_read_only_and_conflicting_asset_is_never_overwritten(self):
        a=LiveAdapter.__new__(LiveAdapter);content=b'TEMP exact ZIP';expected=hashlib.sha256(content).hexdigest()
        release={'assets':[{'id':123,'name':'archive.zip','size':len(content)}]}
        with patch.object(a,'api',return_value=content) as call:
            self.assertEqual(a.asset(release,'archive.zip',expected,len(content))['asset_id'],123)
            call.assert_called_once()
        with patch.object(a,'api',return_value=b'conflicting ZIP'):
            with self.assertRaises(DeliveryBlocked):a.asset(release,'archive.zip',expected,len(content))
    def test_conflicting_tag_and_main_are_rejected_before_merge(self):
        a=LiveAdapter.__new__(LiveAdapter);b={'expected_main':'a','package_head':'b','previous_release_id':1}
        with patch.object(a,'refs',return_value={'refs/heads/main':'other'}):
            with self.assertRaisesRegex(DeliveryBlocked,'main_shifted'):a.baseline(b)
        with patch.object(a,'refs',return_value={'refs/heads/main':'a','refs/tags/v2.0.33':'other'}):
            with self.assertRaisesRegex(DeliveryBlocked,'tag_conflict'):a.baseline(b)
    def test_draft_exists_before_upload_and_publish_occurs_after_both_assets(self):
        self.press();self.finish(self.runner())
        for prior,later in [('record','archive'),('archive','manifest'),('manifest','publish'),('publish','notify_primary')]:
            self.assertLess(self.api.calls.index(prior),self.api.calls.index(later))

    def test_actual_delivery_tick_continues_after_intake_callback_without_manual_runner(self):
        from scripts.sergey_delivery import DeliveryWorker
        from tests.test_sergey_delivery import config
        cfg=config(self.root);cfg['pilot'].update(issue_id='ALE-533',revision=2,contract_hash='a'*64,
                                                branch='delivery/'+'b'*32+'-r2')
        self.state.checkpoint(self.job,'TEMP','preview_ready',{'source_head':'a'*40},'preview_ready')
        worker=DeliveryWorker(self.state,cfg,{'linear_api_key':'fake','owner_user_id':22},None)
        worker.production=self.runner()
        try:
            with patch.object(worker,'validate_issue'):
                worker.tick();self.assertEqual(self.api.calls,[])
                self.press()
                for _ in range(15):worker.production.next_tick=0;worker.tick()
            self.assertEqual(self.state.operation(self.job['id'],'production')['status'],'complete')
            self.assertEqual(self.api.calls.count('notify_primary'),1)
            self.assertEqual(self.api.calls.count('notify_copy'),1)
        finally:worker.intake.db.close()


class NotificationJournalTests(unittest.TestCase):
    def test_existing_sent_and_restart_after_positive_api_receipt_do_not_resend(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'release_notifications.jsonl'
            with patch.object(sender.daily,'send_message',return_value='123') as send:
                first=sender.send_one_durable('2.0.33','primary',11,'message','fake',p,confirmed=True)
                second=sender.send_one_durable('2.0.33','primary',11,'message','fake',p,confirmed=True)
                self.assertEqual(first,second);self.assertEqual(send.call_count,1)
                sender.send_one_durable('2.0.33','copy',22,'message','fake',p,confirmed=True)
                self.assertEqual(send.call_count,2)
    def test_lost_response_or_crash_never_blind_retries(self):
        for error in [RuntimeError('timeout'),Crash()]:
            with tempfile.TemporaryDirectory() as temp:
                p=Path(temp)/'release_notifications.jsonl'
                with patch.object(sender.daily,'send_message',side_effect=error) as send:
                    with self.assertRaises((RuntimeError,Crash)):sender.send_one_durable('2.0.33','primary',11,'message','fake',p,confirmed=True)
                    with self.assertRaisesRegex(RuntimeError,'uncertain'):sender.send_one_durable('2.0.33','primary',11,'message','fake',p,confirmed=True)
                    self.assertEqual(send.call_count,1)
                sender.append_log('2.0.33','primary',11,'sent','message',message_id='known-positive-receipt',log_path=p)
                with patch.object(sender.daily,'send_message') as send:
                    self.assertEqual(sender.send_one_durable('2.0.33','primary',11,'message','fake',p,confirmed=True)['status'],'sent');send.assert_not_called()
    def test_no_approval_no_send_and_history_conflict_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'release_notifications.jsonl'
            with self.assertRaises(RuntimeError):sender.send_one_durable('2.0.33','primary',11,'message','fake',p)
            sender.append_log('2.0.33','primary',11,'sent','different message',message_id='123',log_path=p)
            with patch.object(sender.daily,'send_message') as send:
                with self.assertRaisesRegex(RuntimeError,'history_conflict'):sender.send_one_durable('2.0.33','primary',11,'message','fake',p,confirmed=True)
                send.assert_not_called()

class LiveParityTests(unittest.TestCase):
    def test_public_parity_is_anonymous_and_detects_stale_manifest_or_wrong_zip(self):
        import io
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=b'original accepted ZIP';(root/'archive.zip').write_bytes(archive)
            manifest=json.dumps({'download_url':'https://github.com/drthalas/Fedorinov_rewards/releases/download/v2.0.33/archive.zip'}).encode();(root/'latest.json').write_bytes(manifest)
            a=LiveAdapter.__new__(LiveAdapter);a.config={'manifest':str(root/'latest.json'),'artifact':str(root/'archive.zip')}
            b={'zip_sha256':hashlib.sha256(archive).hexdigest(),'manifest_sha256':hashlib.sha256(manifest).hexdigest()}
            seen=[]
            def read(request,**kwargs):
                self.assertNotIn('Authorization',request.headers);seen.append(request.full_url)
                return io.BytesIO(manifest if request.full_url.endswith('latest.json') else archive)
            with patch('urllib.request.urlopen',side_effect=read):self.assertTrue(a.reconcile('parity',b)['anonymous'])
            self.assertEqual(len(seen),2)
            with patch('urllib.request.urlopen',return_value=io.BytesIO(b'stale')):
                with self.assertRaises(ReadRetry):a.reconcile('parity',b)
            with patch('urllib.request.urlopen',side_effect=[io.BytesIO(manifest),io.BytesIO(b'wrong ZIP')]):
                with self.assertRaises(DeliveryBlocked):a.reconcile('parity',b)

    def test_real_temp_git_cas_cannot_overwrite_concurrent_main(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/'work';work.mkdir();remote=root/'remote.git'
            def git(*args,cwd=work):return subprocess.check_output(['git',*args],cwd=cwd,stderr=subprocess.DEVNULL,text=True).strip()
            git('init','--bare',str(remote),cwd=root);git('init');git('config','user.name','TEMP');git('config','user.email','temp@example.invalid')
            (work/'file').write_text('base');git('add','.');git('commit','-m','base');base=git('rev-parse','HEAD')
            git('remote','add','origin',str(remote));git('push','origin','HEAD:refs/heads/main')
            (work/'file').write_text('accepted');git('commit','-am','candidate');candidate=git('rev-parse','HEAD')
            git('checkout','--detach',base);(work/'file').write_text('concurrent');git('commit','-am','concurrent');other=git('rev-parse','HEAD');git('push','origin','HEAD:refs/heads/main')
            a=LiveAdapter.__new__(LiveAdapter);a.work=work
            with self.assertRaises(ReadRetry):a.execute('merge',{'expected_main':base,'package_head':candidate})
            self.assertEqual(git('rev-parse','refs/heads/main',cwd=remote),other)
