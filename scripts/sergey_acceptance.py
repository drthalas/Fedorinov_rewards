"""Durable Owner permission for an exact preview; never executes an update."""
from __future__ import annotations

import hashlib
import json
import secrets
import time


def identity(build):
    return hashlib.sha256(json.dumps(build, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def arm(store, owner_id, build):
    required = {"issue", "revision", "source_head", "deployed_head", "deployment_id",
                "issue_contract_hash", "framework_scope_hash", "url"}
    if (set(build) != required or build["issue"] != "ALE-533" or build["revision"] != 2
            or build["source_head"] != build["deployed_head"]
            or build["source_head"] != "62c4307c60d3078a97c23bfc1f73059c2f4aba65"):
        raise ValueError("Exact accepted ALE-533 build required")
    fingerprint = identity(build)
    with store.transaction():
        old = json.loads(store.meta("acceptance_current", "null"))
        if old and old["fingerprint"] == fingerprint:
            return old  # Restart/repeated setup never sends a second request.
        record = {"fingerprint": fingerprint, "token": secrets.token_hex(12), "build": build,
                  "owner_id": owner_id, "state": "waiting", "created": time.time(),
                  "expires": time.time() + 86400}
        record["outbox_key"] = "acceptance:" + fingerprint
        store.set_meta("acceptance_current", json.dumps(record))
        store.enqueue(record["outbox_key"], "telegram", {
            "chat_id": owner_id,
            "text": ("ALE-533 revision 2: ваша приёмка Railway зафиксирована.\n"
                     f"Product HEAD: {build['source_head']}\n{build['url']}\n\n"
                     "Лично подтвердите следующий этап: собрать candidate из этой product-линии "
                     "с минимальными version metadata, затем отдельно пройти штатный updater "
                     "на COPEW-04C68047F через существующий BAT и Edge. Перед apply — свободные "
                     "writers и свежий проверенный backup; REAL без тестовых записей.\n"
                     "Framework-код в пакет не входит. Production и общая очередь выключены. "
                     "Подтверждение действует только для указанной сборки, 24 часа."),
            "reply_markup": {"inline_keyboard": [[
                {"text": "Разрешить candidate + Windows", "callback_data": "gate:yes:" + record["token"]}],
                [{"text": "Отложить", "callback_data": "gate:no:" + record["token"]}]]}})
        store.event("acceptance_armed", fingerprint)
        return record


def callback(store, update, user_id, role):
    """Called inside Intake's update transaction, after normal allowlist checks."""
    query = update["callback_query"]
    parts = query.get("data", "").split(":")
    record = json.loads(store.meta("acceptance_current", "null"))
    invalid = "Кнопка недействительна или уже обработана. Новый этап не запущен."
    if (role != "owner" or len(parts) != 3 or parts[1] not in {"yes", "no"}
            or not record or record["owner_id"] != user_id
            or parts[2] != record["token"] or record["state"] != "waiting"):
        return invalid
    row = store.db.execute("SELECT status,result FROM outbox WHERE key=?", (record["outbox_key"],)).fetchone()
    message = query.get("message", {})
    receipt = json.loads(row["result"] or "{}") if row else {}
    if (not row or row["status"] != "sent" or message.get("message_id") != receipt.get("message_id")
            or store.meta("paused") == "1" or store.meta("delivery_paused") == "1"
            or store.meta("delivery_cancel:" + record["build"]["issue"]) == "1"):
        return invalid
    if time.time() > record["expires"]:
        record["state"] = "expired"
        store.set_meta("acceptance_current", json.dumps(record))
        return "Подтверждение истекло. Нужна новая проверка сборки."
    record.update(state="owner_approved" if parts[1] == "yes" else "deferred",
                  callback_update_id=update["update_id"], callback_id=query["id"],
                  message_id=message["message_id"], approved_at=time.time())
    store.set_meta("acceptance_current", json.dumps(record))
    store.event("acceptance_" + record["state"], record["fingerprint"])
    return ("Ваше разрешение candidate + physical Windows updater сохранено для ALE-533 r2 / "
            + record["build"]["source_head"] + ". Перед сборкой агент повторно сверит HEAD и scope. "
            "Production выключен.") if parts[1] == "yes" else "Этап отложен. Candidate/updater не запущены."


def require_approval(store, build):
    """Caller supplies freshly verified Linear + source + deployed identity before each stage."""
    record = json.loads(store.meta("acceptance_current", "null"))
    if (not record or record["state"] != "owner_approved" or not record.get("callback_update_id")
            or record["fingerprint"] != identity(build) or time.time() > record["expires"]
            or store.meta("paused") == "1" or store.meta("delivery_paused") == "1"
            or store.meta("delivery_cancel:" + build["issue"]) == "1"):
        raise ValueError("Fresh exact Owner Telegram approval required")
    return record


def framework_scope(description, config):
    """Explicit Owner reduction may prepend a pinned header; accepted scope stays byte-bound."""
    try:
        from .sergey_delivery import contract_hash
    except ImportError:
        from sergey_delivery import contract_hash
    reduction = config.get("framework_scope_reduction")
    if not reduction:
        return description
    header, separator, original = description.partition("\n---\n")
    original = original.lstrip("\n")
    if (not separator or not header.startswith("## ACTIVE — сократить candidate/updater проверки по риску")
            or contract_hash(header) != reduction["header_hash"]
            or contract_hash(original) != reduction["previous_scope_hash"]):
        raise ValueError("Owner scope reduction pin changed")
    return original


def snapshot(config):
    """Read-only live preflight. No packaging, Windows contact, or publication."""
    import base64
    from pathlib import Path
    import subprocess
    import urllib.request
    try:
        from .sergey_delivery import DeliveryStore, DeliveryWorker, contract_hash, private_json, validate_config
        from .sergey_delivery_railway import ORIGIN, SERVICE, ENVIRONMENT
    except ImportError:
        from sergey_delivery import DeliveryStore, DeliveryWorker, contract_hash, private_json, validate_config
        from sergey_delivery_railway import ORIGIN, SERVICE, ENVIRONMENT
    validate_config(config)
    credentials = private_json(Path(config["credentials"]))
    state = DeliveryStore(Path(config["state"]))
    worker = DeliveryWorker(state, config, credentials, None)
    try:
        issue = worker.validate_issue()
        framework = worker.linear.call("query($id:String!){issue(id:$id){description state{type}}}", {"id": "ALE-528"})["issue"]
        if framework:
            framework["description"] = framework_scope(framework["description"], config)
        job = state.job()
        if not job or job["stage"] != "preview_ready" or job["status"] != "preview_ready":
            raise ValueError("Verified preview-ready job required")
        body = json.loads(job["body"])
        worktree = Path(body["worktree"])
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=worktree, text=True, timeout=30).strip()
        if git("status", "--porcelain") or git("rev-parse", "HEAD") != body["source_head"]:
            raise ValueError("Product worktree changed")
        auth = credentials["preview_auth"]
        request = urllib.request.Request(ORIGIN + "/preview/identity", headers={
            "Authorization": "Basic " + base64.b64encode((auth["username"] + ":" + auth["password"]).encode()).decode()})
        with urllib.request.urlopen(request, timeout=30) as response:
            deployed = json.load(response)
        # Read the platform's current deployment too; a stale URL/receipt cannot approve a newer build.
        output = subprocess.check_output(["railway", "deployment", "list", "--json", "--service", SERVICE,
                                         "--environment", ENVIRONMENT], cwd=config["linked_directory"], text=True, timeout=30)
        deployments = json.loads(output)
        if (not deployments or deployments[0]["id"] != body["deployment_id"]
                or deployments[0]["status"] != "SUCCESS"
                or deployed.get("source_head") != body["source_head"]
                or deployed.get("delivery_issue") != config["pilot"]["issue_id"]
                or deployed.get("contract_revision") != config["pilot"]["revision"]
                or not framework or framework["state"]["type"] in {"canceled", "completed"}
                or not framework["description"].startswith("## ACTIVE — после Owner feature PASS")
                or body["source_head"] not in framework["description"].split("\n---\n")[0]):
            raise ValueError("Current deployment or framework scope mismatch")
        return {"issue": config["pilot"]["issue_id"], "revision": config["pilot"]["revision"],
                "source_head": body["source_head"], "deployed_head": deployed["source_head"],
                "deployment_id": body["deployment_id"], "url": ORIGIN + "/legacy?tab=about",
                "issue_contract_hash": contract_hash(issue["description"]),
                "framework_scope_hash": contract_hash(framework["description"])}
    finally:
        worker.intake.db.close()
        state.db.close()


def main():
    import argparse
    from pathlib import Path
    try:
        from .sergey_delivery import private_json
        from .sergey_intake import Store
    except ImportError:
        from sergey_delivery import private_json
        from sergey_intake import Store
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["arm", "check", "status"])
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    cfg = private_json(args.config)
    store = Store(Path(cfg["intake_state"]))
    try:
        if args.action == "status":
            record = json.loads(store.meta("acceptance_current", "null"))
        else:
            build = snapshot(cfg)
            record = (arm(store, private_json(Path(cfg["credentials"]))["owner_user_id"], build)
                      if args.action == "arm" else require_approval(store, build))
        print(json.dumps({"state": record["state"] if record else "not_armed",
                          "build": record["build"] if record else None,
                          "callback_update_id": record.get("callback_update_id") if record else None}))
    finally:
        store.db.close()


if __name__ == "__main__":
    main()
