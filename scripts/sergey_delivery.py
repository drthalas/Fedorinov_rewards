#!/usr/bin/env python3
"""ALE-528: exact-pilot delivery. No general queue or release implementation."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid

try:
    from .sergey_intake import Store, Linear, TEAM_ID, PROJECT_ID, OWNER_LINEAR_ID, service_lock
    from .sergey_analyst import CodexAnalyst
except ImportError:
    from sergey_intake import Store, Linear, TEAM_ID, PROJECT_ID, OWNER_LINEAR_ID, service_lock
    from sergey_analyst import CodexAnalyst


FORBIDDEN_ISSUES = {"ALE-529", "ALE-530", "ALE-531", "ALE-532"}
ROOT = Path(__file__).resolve().parents[1]


class DeliveryBlocked(RuntimeError):
    pass


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def contract_hash(text: str) -> str:
    return digest(re.sub(r"(?m)^([ \t]*)[-*+] ", r"\1- ", text).strip("\n"))


def private_json(path: Path) -> dict:
    info = path.lstat()
    if path.is_symlink() or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise DeliveryBlocked("private_config_permissions")
    return json.loads(path.read_text())


def validate_config(config: dict):
    if config.get("general_queue") is not False or config.get("release") is not False:
        raise DeliveryBlocked("general_queue_and_release_must_be_disabled")
    if not 300 <= config.get("poll_seconds", 0) <= 600:
        raise DeliveryBlocked("poll_interval_must_be_5_to_10_minutes")
    pilot = config["pilot"]
    if pilot["issue_id"] in FORBIDDEN_ISSUES or not re.fullmatch(r"ALE-\d+", pilot["issue_id"]):
        raise DeliveryBlocked("historical_test_or_invalid_issue")
    if not pilot.get("implement") or not pilot.get("railway_preview") or pilot.get("release") is not False:
        raise DeliveryBlocked("pilot_permissions_invalid")
    if pilot.get("revision", 0) < 1 or not re.fullmatch(r"[a-f0-9]{64}", pilot.get("contract_hash", "")):
        raise DeliveryBlocked("exact_revision_and_contract_required")
    if not re.fullmatch(r"[a-f0-9]{40}", pilot.get("base_head", "")):
        raise DeliveryBlocked("pinned_base_required")
    if pilot["branch"] != f"delivery/{pilot['draft_id']}-r{pilot['revision']}":
        raise DeliveryBlocked("branch_contract_mismatch")
    patch = pilot["patch"]
    if patch["path"].startswith("/") or ".." in Path(patch["path"]).parts:
        raise DeliveryBlocked("invalid_patch_path")


class DeliveryStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists() and path.stat().st_size:
            probe = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                if probe.execute("PRAGMA application_id").fetchone()[0] != 0x414C4435:
                    raise DeliveryBlocked("not_delivery_state_database")
            finally:
                probe.close()
        self.db = sqlite3.connect(path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        os.chmod(path, 0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA application_id=1095517237")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, issue_id TEXT NOT NULL, revision INTEGER NOT NULL,
                contract_hash TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, owner TEXT, fence INTEGER NOT NULL DEFAULT 0,
                lease_until REAL NOT NULL DEFAULT 0, heartbeat REAL, body TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_delivery ON jobs(active) WHERE active=1;
            CREATE TABLE IF NOT EXISTS operations(
                job_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL,
                PRIMARY KEY(job_id,kind));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL, kind TEXT, detail TEXT);
        """)

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback(); raise
        else:
            self.db.commit()

    def event(self, kind, detail):
        self.db.execute("INSERT INTO events(at,kind,detail) VALUES(?,?,?)", (time.time(), kind, detail))

    def job(self):
        row = self.db.execute("SELECT * FROM jobs WHERE active=1").fetchone()
        return dict(row) if row else None

    def claim(self, pilot: dict, owner: str, now=None, lease_seconds=30):
        now = time.time() if now is None else now
        key = f"{pilot['issue_id']}:r{pilot['revision']}:{pilot['contract_hash'][:16]}"
        with self.transaction():
            current = self.job()
            if current and current["id"] != key:
                raise DeliveryBlocked("one_active_job_slot_reserved")
            if not current:
                if self.db.execute("SELECT 1 FROM jobs WHERE id=?", (key,)).fetchone():
                    return None
                self.db.execute("INSERT INTO jobs(id,issue_id,revision,contract_hash,stage,status,body) VALUES(?,?,?,?,?,?,?)",
                                (key, pilot["issue_id"], pilot["revision"], pilot["contract_hash"], "claimed", "active", "{}"))
                self.event("claimed", key)
            current = self.job()
            if current["status"] != "active":
                return None
            if current["owner"] != owner and current["lease_until"] > now:
                return None
            if current["owner"] != owner:
                self.db.execute("UPDATE jobs SET owner=?,fence=fence+1,lease_until=?,heartbeat=? WHERE id=?",
                                (owner, now + lease_seconds, now, key))
            return self.job()

    def renew(self, job: dict, owner: str, now=None):
        now = time.time() if now is None else now
        with self.transaction():
            count = self.db.execute("UPDATE jobs SET heartbeat=?,lease_until=? WHERE id=? AND owner=? AND fence=? AND status='active'",
                                    (now, now + 30, job["id"], owner, job["fence"])).rowcount
            if count != 1:
                raise DeliveryBlocked("lease_lost")

    def checkpoint(self, job: dict, owner: str, stage: str, body: dict, status="active"):
        with self.transaction():
            count = self.db.execute("UPDATE jobs SET stage=?,body=?,status=? WHERE id=? AND owner=? AND fence=? AND lease_until>?",
                                   (stage, json.dumps(body), status, job["id"], owner, job["fence"], time.time())).rowcount
            if count != 1:
                raise DeliveryBlocked("lease_lost")
            self.event("checkpoint", job["id"] + ":" + stage)

    def operation(self, job_id: str, kind: str, status=None, body=None):
        if status is not None:
            self.db.execute("INSERT INTO operations VALUES(?,?,?,?) ON CONFLICT(job_id,kind) DO UPDATE SET status=excluded.status,body=excluded.body",
                            (job_id, kind, status, json.dumps(body or {})))
        row = self.db.execute("SELECT status,body FROM operations WHERE job_id=? AND kind=?", (job_id, kind)).fetchone()
        return {"status": row[0], "body": json.loads(row[1])} if row else None


def verify_diff(worktree: Path, base: str, pilot: dict) -> dict:
    def git(*args):
        return subprocess.run(["git", *args], cwd=worktree, capture_output=True, text=True, check=True).stdout
    patch = pilot["patch"]
    paths = git("diff", "--name-only", base).splitlines()
    if paths != [patch["path"]] or git("ls-files", "--others", "--exclude-standard").strip():
        raise DeliveryBlocked("actual_diff_outside_approved_paths")
    before = git("show", f"{base}:{patch['path']}")
    after = (worktree / patch["path"]).read_text()
    if before.count(patch["old"]) != 1 or after != before.replace(patch["old"], patch["new"], 1):
        raise DeliveryBlocked("actual_diff_outside_exact_contract")
    path = patch["path"]
    protected = ["updat", "recover", "packag", "migrat", "schema", "auth", "config", "requirements", "version", "AGENTS", "signing"]
    if any(p.lower() in path.lower() for p in protected):
        raise DeliveryBlocked("protected_area_requires_owner")
    if pilot["tier"] == "T1":
        if not (path.startswith("docs/") or path.startswith("backend/app/templates/")):
            raise DeliveryBlocked("t1_not_documentation_copy")
        if any(c in patch["old"] + patch["new"] for c in "\n<>={}%"):
            raise DeliveryBlocked("t1_code_or_markup_change")
    elif pilot["tier"] == "T2":
        if not path.startswith(("backend/app/templates/", "backend/app/static/")):
            raise DeliveryBlocked("t2_backend_or_system_change")
        if re.search(r"fetch\(|localStorage|DELETE|/updates/|sqlite|password|secret", patch["new"], re.I):
            raise DeliveryBlocked("t2_dependency_or_security_change")
        if path.endswith(".js") or re.search(r"cookie|token|credentials|https?://|<script|on\w+\s*=|eval\(", patch["new"], re.I):
            raise DeliveryBlocked("t2_dependency_or_security_change")
    else:
        raise DeliveryBlocked("t3_t4_escalation")
    git("diff", "--check", base)
    return {"actual_tier": pilot["tier"], "paths": paths, "before_sha256": digest(before), "after_sha256": digest(after)}


class DeliveryWorker:
    def __init__(self, state: DeliveryStore, config: dict, credentials: dict, adapter):
        validate_config(config)
        self.state, self.config, self.credentials, self.adapter = state, config, credentials, adapter
        self.owner = str(uuid.uuid4())
        self.intake = Store(Path(config["intake_state"]))
        self.linear = Linear(credentials["linear_api_key"], {})
        self.stop = threading.Event()
        self.next_poll = 0

    def validate_issue(self):
        p = self.config["pilot"]
        issue = self.linear.call("query($id:String!){issue(id:$id){id identifier description state{type} creator{id} team{id} project{id}}}", {"id": p["issue_uuid"]})["issue"]
        if (not issue or issue["identifier"] != p["issue_id"] or issue["identifier"] in FORBIDDEN_ISSUES
                or issue["creator"]["id"] != OWNER_LINEAR_ID or issue["team"]["id"] != TEAM_ID
                or issue["project"]["id"] != PROJECT_ID or issue["state"]["type"] in {"canceled", "completed"}
                or "## TEST/ALE-528" in issue["description"]
                or "## DELIVERY PILOT/ALE-528" not in issue["description"]
                or p["base_head"] not in issue["description"]
                or not self.matches_contract(issue["description"])):
            raise DeliveryBlocked("linear_contract_or_identity_changed")
        row = self.intake.db.execute("SELECT body FROM drafts WHERE id=?", (p["draft_id"],)).fetchone()
        draft = json.loads(row[0]) if row else {}
        if (draft.get("role") != "owner" or draft.get("state") != "created" or draft.get("revision") != p["revision"]
                or draft.get("issue_id") != p["issue_uuid"] or not draft.get("confirmation_update")
                or draft.get("tier") != p["tier"] or draft.get("tier") not in {"T1", "T2"}):
            raise DeliveryBlocked("intake_confirmation_mismatch")
        return issue

    def matches_contract(self, description):
        p = self.config["pilot"]
        if contract_hash(description) == p["contract_hash"]:
            return True
        # An explicit Owner acceptance header may be pinned after preview. It must
        # preserve the entire original contract, and cannot authorize execution.
        job = self.state.job()
        prefix, separator, original = description.partition("\n---\n")
        return bool(job and job["stage"] == "preview_ready"
                    and p.get("accepted_issue_hash") == contract_hash(description)
                    and prefix.startswith("## Owner feature PASS") and separator
                    and contract_hash(original.lstrip("\n")) == p["contract_hash"])

    def controls(self):
        p = self.config["pilot"]
        if self.intake.meta("delivery_cancel:" + p["issue_id"]) == "1":
            return "cancel"
        if self.intake.meta("paused") == "1" or self.intake.meta("delivery_paused") == "1":
            return "pause"
        return "run"

    def status(self, job):
        if job:
            body = json.loads(job["body"])
            text = f"{job['issue_id']} r{job['revision']}: {job['status']}/{job['stage']}. " + body.get("url", "") + " HEAD " + body.get("source_head", "")
            if body.get("blocker"):text += " Blocker: " + body["blocker"]
        else:
            text = "Delivery: один exact pilot; ожидание poll."
        self.intake.set_meta("delivery_status", text + " Общая очередь и release выключены.")

    def tick(self):
        job = self.state.job()
        self.status(job)
        control = self.controls()
        if control == "cancel" and job:
            with self.state.transaction():
                self.state.db.execute("UPDATE jobs SET status='cancelled',active=0,lease_until=0 WHERE id=?", (job["id"],))
                self.state.event("cancelled", job["id"])
            return
        if control != "run" or not self.config.get("enabled", False):
            return
        if job and job["status"] == "preview_ready":
            if time.time() >= self.next_poll:
                self.next_poll = time.time() + self.config["poll_seconds"]
                try:self.validate_issue()
                except Exception:
                    body = json.loads(job["body"]);body["blocker"] = "preview_contract_changed_or_unreadable"
                    with self.state.transaction():
                        self.state.db.execute("UPDATE jobs SET status='blocked',body=? WHERE id=? AND status='preview_ready'", (json.dumps(body),job["id"]))
                        self.state.event("preview_invalidated", job["id"])
            return
        if job and job["status"] != "active":
            return
        if not job:
            if time.time() < self.next_poll:return
            self.next_poll = time.time() + self.config["poll_seconds"]
            self.validate_issue()
        job = self.state.claim(self.config["pilot"], self.owner)
        if not job:return
        self.state.renew(job, self.owner)
        if job["stage"] == "claimed" and self.config.get("hold_after_claim"):
            return
        self.validate_issue()
        body = json.loads(job["body"])
        stage = job["stage"]
        if stage == "claimed":
            self.state.checkpoint(job, self.owner, "implementing", body)
            return
        if stage == "implementing":
            body.update(self.adapter.implement(job))
            self.state.checkpoint(job, self.owner, "deploying", body)
        elif stage == "deploying":
            result = self.adapter.deploy({**job, "body": json.dumps(body)})
            if result:
                body.update(result); self.state.checkpoint(job, self.owner, "deployed", body)
        elif stage == "deployed":
            body.update(self.adapter.verify({**job, "body": json.dumps(body)}))
            self.state.checkpoint(job, self.owner, "notifying", body)
        elif stage == "notifying":
            key = "delivery-preview:" + job["id"] + ":" + body["source_head"]
            with self.intake.transaction():
                self.intake.enqueue(key, "telegram", {"chat_id": self.credentials["owner_user_id"],
                    "text": f"{job['issue_id']} — DELIVERY PILOT готов к проверке.\n{body['url']}\n"
                    f"HEAD: {body['source_head']}\nПроверка: {self.config['pilot']['acceptance']}\n"
                    "Данные/медиа/авторизация сохранены. Release и общая очередь выключены."})
            row = self.intake.db.execute("SELECT status,result FROM outbox WHERE key=?", (key,)).fetchone()
            if row["status"] == "sent":
                body["notification_message_id"] = json.loads(row["result"])["message_id"]
                self.state.checkpoint(job, self.owner, "preview_ready", body, "preview_ready")
            elif row["status"] == "uncertain":
                raise DeliveryBlocked("notification_uncertain_no_retry")

    def heartbeat(self):
        store = DeliveryStore(Path(self.config["state"]))
        try:
            while not self.stop.wait(5):
                job = store.job()
                if job and job["owner"] == self.owner and job["status"] == "active":
                    try:store.renew(job, self.owner)
                    except DeliveryBlocked:self.stop.set()
        finally:store.db.close()

    def run(self):
        thread = threading.Thread(target=self.heartbeat, daemon=True); thread.start()
        try:
            while not self.stop.is_set():
                try:self.tick()
                except Exception as error:
                    code = str(error) if re.fullmatch(r"[a-z_]+", str(error)) else "delivery_failed"
                    if code in {"paused", "cancelled"}:
                        self.state.event(code, "checkpoint_held");continue
                    job = self.state.job()
                    if job and job["owner"] == self.owner:
                        body = json.loads(job["body"]); body["blocker"] = code
                        self.state.checkpoint(job, self.owner, job["stage"], body, "blocked")
                    self.state.event("blocked", code)
                self.stop.wait(2)
        finally:
            self.stop.set();thread.join(timeout=6)
            self.adapter.cancel()
            self.state.db.execute("UPDATE jobs SET lease_until=0 WHERE owner=?", (self.owner,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "status"])
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args();os.umask(0o077)
    config = private_json(args.config);validate_config(config)
    state = DeliveryStore(Path(config["state"]))
    if args.action == "status":
        print(json.dumps(state.job(), ensure_ascii=False));return 0
    credentials = private_json(Path(config["credentials"]))
    try:
        from .sergey_delivery_railway import PreviewAdapter
    except ImportError:
        from sergey_delivery_railway import PreviewAdapter
    with service_lock(Path(config["state"]).with_suffix(".lock")):
        adapter = PreviewAdapter(state, config, credentials)
        worker = DeliveryWorker(state, config, credentials, adapter)
        def stop(signum, frame):
            worker.stop.set();adapter.cancel();raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        try:worker.run()
        except KeyboardInterrupt:pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
