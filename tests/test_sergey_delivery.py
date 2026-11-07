import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts.sergey_delivery import DeliveryBlocked, DeliveryStore, DeliveryWorker, contract_hash, validate_config, verify_diff
from scripts.sergey_intake import Store, contract


def config(root):
    return {"enabled": True, "general_queue": False, "release": False, "poll_seconds": 300,
            "state": str(root / "delivery.sqlite3"), "intake_state": str(root / "intake.sqlite3"),
            "pilot": {"issue_id": "ALE-999", "issue_uuid": "a" * 32, "draft_id": "b" * 32,
                      "revision": 1, "contract_hash": "c" * 64, "base_head": "d" * 40,
                      "branch": "delivery/" + "b" * 32 + "-r1", "tier": "T1",
                      "implement": True, "railway_preview": True, "release": False,
                      "acceptance": "Read the corrected copy",
                      "patch": {"path": "backend/app/templates/example.html", "old": "old guidance", "new": "new guidance"}}}


class Adapter:
    def __init__(self):self.calls = []
    def implement(self, job):self.calls.append("implement");return {"source_head": "e" * 40, "url": "https://preview.invalid"}
    def deploy(self, job):self.calls.append("deploy");return {"deployment_id": "one"}
    def verify(self, job):self.calls.append("verify");return {"deployed_head": "e" * 40}
    def cancel(self):pass


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.cfg = config(self.root);self.store = DeliveryStore(Path(self.cfg["state"]))
        self.intake = Store(Path(self.cfg["intake_state"]))
    def tearDown(self):
        self.store.db.close();self.intake.db.close();self.temp.cleanup()

    def test_general_queue_release_and_historical_tests_are_permanently_denied(self):
        for issue in ["ALE-529", "ALE-530", "ALE-531", "ALE-532"]:
            value = copy.deepcopy(self.cfg);value["pilot"]["issue_id"] = issue
            with self.assertRaises(DeliveryBlocked):validate_config(value)
        for key in ["general_queue", "release"]:
            value = copy.deepcopy(self.cfg);value[key] = True
            with self.assertRaises(DeliveryBlocked):validate_config(value)
        validate_config(self.cfg)

    def test_one_active_job_and_fencing_survive_reopen(self):
        p = self.cfg["pilot"]
        first = self.store.claim(p, "one", now=100)
        self.assertIsNone(self.store.claim(p, "two", now=101))
        second = self.store.claim(p, "two", now=131)
        self.assertGreater(second["fence"], first["fence"])
        with self.assertRaises(DeliveryBlocked):self.store.renew(first, "one")
        other = {**p, "issue_id": "ALE-1000"}
        with self.assertRaises(DeliveryBlocked):self.store.claim(other, "two", now=132)
        reopened = DeliveryStore(Path(self.cfg["state"]))
        self.assertEqual(reopened.job()["id"], first["id"]);reopened.db.close()

    def test_pause_before_claim_and_cancel_before_implementation(self):
        adapter = Adapter();w = DeliveryWorker(self.store, self.cfg, {"linear_api_key": "fake", "owner_user_id": 22}, adapter)
        self.intake.set_meta("delivery_paused", "1")
        with patch.object(w, "validate_issue"):w.tick()
        self.assertIsNone(self.store.job())
        self.intake.set_meta("delivery_paused", "0")
        with patch.object(w, "validate_issue"):w.tick()
        self.intake.set_meta("delivery_cancel:ALE-999", "1");w.tick()
        self.assertEqual(adapter.calls, []);self.assertEqual(self.store.db.execute("SELECT status FROM jobs").fetchone()[0], "cancelled")
        self.intake.set_meta("delivery_cancel:ALE-999", "0")
        self.assertIsNone(self.store.claim(self.cfg["pilot"], "another"))

    def test_recovery_after_claim_and_notification_do_not_repeat_execution(self):
        adapter = Adapter();creds = {"linear_api_key": "fake", "owner_user_id": 22}
        self.cfg["hold_after_claim"] = True
        old = DeliveryWorker(self.store, self.cfg, creds, adapter)
        with patch.object(old, "validate_issue"):old.tick()
        self.assertEqual(self.store.job()["stage"], "claimed");self.assertEqual(adapter.calls, [])
        self.store.db.execute("UPDATE jobs SET lease_until=0")
        self.cfg["hold_after_claim"] = False
        new = DeliveryWorker(self.store, self.cfg, creds, adapter)
        with patch.object(new, "validate_issue"):
            for _ in range(5):new.tick()
        self.assertEqual(adapter.calls, ["implement", "deploy", "verify"])
        row = self.intake.db.execute("SELECT key FROM outbox WHERE key LIKE 'delivery-preview:%'").fetchone()
        self.assertIsNotNone(row)
        self.store.db.execute("UPDATE jobs SET lease_until=0")
        newest = DeliveryWorker(self.store, self.cfg, creds, adapter)
        self.intake.db.execute("UPDATE outbox SET status='sent',result=? WHERE key=?", (json.dumps({"message_id": 100}), row[0]))
        with patch.object(newest, "validate_issue"):newest.tick();newest.tick()
        self.assertEqual(adapter.calls, ["implement", "deploy", "verify"])
        self.assertEqual(self.intake.db.execute("SELECT count(*) FROM outbox WHERE key LIKE 'delivery-preview:%'").fetchone()[0], 1)
        self.assertEqual(self.store.job()["status"], "preview_ready")

    def test_contract_hash_ignores_only_linear_markdown_normalization(self):
        self.assertEqual(contract_hash("- source\n"), contract_hash("* source"))
        self.assertNotEqual(contract_hash("- source"), contract_hash("- changed"))

    def test_preview_ready_polls_exact_issue_without_reexecution(self):
        adapter=Adapter();w=DeliveryWorker(self.store,self.cfg,{"linear_api_key":"fake","owner_user_id":22},adapter)
        j=self.store.claim(self.cfg['pilot'],w.owner)
        self.store.checkpoint(j,w.owner,'preview_ready',{'source_head':'e'*40},'preview_ready')
        with patch.object(w,'validate_issue') as validate:w.tick();w.tick();validate.assert_called_once()
        self.assertEqual(adapter.calls,[])
        w.next_poll=0
        with patch.object(w,'validate_issue',side_effect=DeliveryBlocked('changed')):w.tick()
        self.assertEqual(self.store.job()['status'],'blocked');self.assertEqual(adapter.calls,[])

    def test_exact_copy_diff_passes_and_extra_files_fail(self):
        work = self.root / "work";work.mkdir()
        def git(*args):return subprocess.run(["git", *args], cwd=work, capture_output=True, text=True, check=True).stdout.strip()
        git("init");git("config", "user.name", "TEMP test");git("config", "user.email", "temp@example.invalid")
        path = work / self.cfg["pilot"]["patch"]["path"];path.parent.mkdir(parents=True)
        path.write_text("<dd>old guidance</dd>\n");git("add", ".");git("commit", "-m", "fixture");base = git("rev-parse", "HEAD")
        path.write_text("<dd>new guidance</dd>\n")
        self.assertEqual(verify_diff(work, base, self.cfg["pilot"])["actual_tier"], "T1")
        (work / "unexpected.txt").write_text("outside")
        with self.assertRaises(DeliveryBlocked):verify_diff(work, base, self.cfg["pilot"])

    def test_markup_and_t3_t4_are_rejected(self):
        work = self.root / "work";work.mkdir()
        def git(*args):return subprocess.run(["git", *args], cwd=work, capture_output=True, text=True, check=True).stdout.strip()
        git("init");git("config", "user.name", "TEMP");git("config", "user.email", "temp@example.invalid")
        path=work/self.cfg["pilot"]["patch"]["path"];path.parent.mkdir(parents=True);path.write_text("old guidance\n")
        git("add", ".");git("commit", "-m", "fixture");base=git("rev-parse", "HEAD")
        p=copy.deepcopy(self.cfg["pilot"]);p["patch"]["new"]="<script>unsafe</script>";path.write_text(p["patch"]["new"]+"\n")
        with self.assertRaises(DeliveryBlocked):verify_diff(work,base,p)
        p["tier"]="T3"
        with self.assertRaises(DeliveryBlocked):verify_diff(work,base,p)


if __name__ == "__main__":unittest.main()
