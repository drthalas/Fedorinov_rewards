import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.sergey_acceptance import arm, require_approval, snapshot
from scripts.sergey_intake import Intake, Store
from scripts.sergey_delivery import DeliveryStore, DeliveryWorker, contract_hash
from tests.test_sergey_delivery import config


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "intake.sqlite3"
        self.store = Store(self.path)
        self.build = dict(issue="ALE-533", revision=2, source_head="62c4307c60d3078a97c23bfc1f73059c2f4aba65",
                          deployed_head="62c4307c60d3078a97c23bfc1f73059c2f4aba65", deployment_id="deployment",
                          issue_contract_hash="a"*64, framework_scope_hash="b"*64, url="https://example.invalid")
        self.record = arm(self.store, 22, self.build)
        self.store.db.execute("UPDATE outbox SET status='sent',result=? WHERE key=?",
                              (json.dumps({"message_id": 500}), self.record["outbox_key"]))
    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()
    def press(self, token=None, user=22, message=500, action="yes", update=1):
        Intake(self.store, 11, 22).process({"update_id": update, "callback_query": {
            "id": str(update), "from": {"id": user}, "data": f"gate:{action}:{token or self.record['token']}",
            "message": {"message_id": message, "chat": {"type": "private", "id": user}}}})
    def test_real_path_reopen_and_repeated_confirmation_are_idempotent(self):
        self.press()
        approved = require_approval(self.store, self.build)
        self.assertEqual(approved["callback_update_id"], 1)
        self.store.db.close(); self.store = Store(self.path)
        self.press(update=2)
        self.assertEqual(require_approval(self.store, self.build)["callback_update_id"], 1)
        arm(self.store, 22, self.build)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE key LIKE 'acceptance:%'").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE kind='acceptance_owner_approved'").fetchone()[0], 1)
    def test_wrong_owner_token_message_and_action_do_not_approve(self):
        for i, kwargs in enumerate([dict(user=11), dict(token="old"), dict(message=501), dict(action="garbage")], 1):
            self.press(update=i, **kwargs)
            with self.assertRaises(ValueError): require_approval(self.store, self.build)
    def test_changed_contract_head_or_deployment_invalidates_permission(self):
        self.press()
        for key in ["source_head", "deployed_head", "deployment_id", "issue_contract_hash", "framework_scope_hash", "revision"]:
            changed = copy.deepcopy(self.build); changed[key] = "changed"
            with self.assertRaises(ValueError): require_approval(self.store, changed)
    def test_changed_scope_rearms_and_old_button_is_stale(self):
        changed = {**self.build, "framework_scope_hash": "c"*64}
        arm(self.store, 22, changed)
        self.press()
        with self.assertRaises(ValueError): require_approval(self.store, changed)
    def test_pause_cancel_and_unknown_send_receipt_fail_closed(self):
        for i, key in enumerate(["paused", "delivery_paused", "delivery_cancel:ALE-533"], 1):
            self.store.set_meta(key, "1"); self.press(update=i)
            with self.assertRaises(ValueError): require_approval(self.store, self.build)
            self.store.set_meta(key, "0")
        self.store.db.execute("UPDATE outbox SET status='uncertain' WHERE key=?", (self.record["outbox_key"],))
        self.press(update=4)
        with self.assertRaises(ValueError): require_approval(self.store, self.build)
    def test_defer_and_expiry_are_durable(self):
        self.press(action="no")
        self.press(update=2)
        with self.assertRaises(ValueError): require_approval(self.store, self.build)
        self.assertEqual(json.loads(self.store.meta("acceptance_current"))["state"], "deferred")
    def test_expired_button_cannot_approve(self):
        with patch("scripts.sergey_acceptance.time.time", return_value=self.record["expires"]+1):
            self.press()
        self.assertEqual(json.loads(self.store.meta("acceptance_current"))["state"], "expired")
    def test_owner_header_requires_pin_and_unchanged_original_preview_contract(self):
        cfg = config(Path(self.temp.name)); state = DeliveryStore(Path(cfg["state"]))
        original = "## DELIVERY PILOT/ALE-528\noriginal"
        cfg["pilot"]["contract_hash"] = contract_hash(original)
        accepted = "## Owner feature PASS\naccepted\n\n---\n\n"+original
        worker = DeliveryWorker(state, cfg, {"linear_api_key": "fake", "owner_user_id": 22}, None)
        job = state.claim(cfg["pilot"], worker.owner)
        self.assertFalse(worker.matches_contract(accepted))
        cfg["pilot"]["accepted_issue_hash"] = contract_hash(accepted)
        self.assertFalse(worker.matches_contract(accepted))
        state.checkpoint(job, worker.owner, "preview_ready", {}, "preview_ready")
        self.assertTrue(worker.matches_contract(accepted))
        changed = accepted+"changed"
        cfg["pilot"]["accepted_issue_hash"] = contract_hash(changed)
        self.assertFalse(worker.matches_contract(changed))
        worker.intake.db.close();state.db.close()

    def test_snapshot_checks_actual_revision_and_current_successful_deployment(self):
        root=Path(self.temp.name);cfg=config(root)
        cfg['pilot'].update(issue_id='ALE-533',revision=2,branch='delivery/'+'b'*32+'-r2')
        cfg['credentials']=str(root/'credentials.json');cfg['linked_directory']=str(root)
        secret=root/'credentials.json'
        secret.write_text(json.dumps({'linear_api_key':'fake','owner_user_id':22,
                                     'preview_auth':{'username':'TEMP','password':'TEMP'}}));secret.chmod(0o600)
        state=DeliveryStore(Path(cfg['state']));job=state.claim(cfg['pilot'],'test')
        body={'source_head':self.build['source_head'],'worktree':str(root),'deployment_id':'deployment'}
        state.checkpoint(job,'test','preview_ready',body,'preview_ready');state.db.close()
        framework={'issue':{'description':'## ACTIVE — после Owner feature PASS\n'+self.build['source_head'],
                            'state':{'type':'started'}}}
        def command(args,**kwargs):
            if args[0]=='railway':return json.dumps([{'id':'deployment','status':'SUCCESS'}])
            return '' if args[1]=='status' else self.build['source_head']
        deployed={'source_head':self.build['source_head'],'delivery_issue':'ALE-533','contract_revision':2}
        with patch.object(DeliveryWorker,'validate_issue',return_value={'description':'accepted issue'}), \
             patch('scripts.sergey_intake.Linear.call',return_value=framework), \
             patch('subprocess.check_output',side_effect=command), \
             patch('urllib.request.urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps(deployed).encode())):
            self.assertEqual(snapshot(cfg)['deployment_id'],'deployment')
            deployed['contract_revision']=1
            with self.assertRaisesRegex(ValueError,'deployment or framework'):snapshot(cfg)
