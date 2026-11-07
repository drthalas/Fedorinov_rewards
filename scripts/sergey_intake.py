#!/usr/bin/env python3
"""ALE-528: isolated, text-first Telegram intake. No delivery/release executor.

Only stdlib dependencies. Runtime data must live outside the product DB/media.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import getpass
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import uuid


QUESTIONS = (
    ("screen", "Где нужна доработка: экран, путь в меню или адрес страницы?"),
    ("actual", "Что происходит сейчас? Опишите шаги и наблюдаемый результат."),
    ("expected", "Какой результат нужен вместо этого?"),
    ("frozen", "Что обязательно сохранить без изменений? Если ограничений нет, напишите «нет»."),
    ("acceptance", "Как проверить готовность: какие действия выполнить и что должно получиться?"),
    ("surface", "Что затрагивает задача? Напишите: «только документация», «локальный интерфейс» "
     "или опишите другое. Укажите, если нужны изменения данных, обновления, доступа или Windows."),
)
TEAM_ID = "cc0f1982-1457-48af-967b-d56a672ee8ae"
PROJECT_ID = "d7ae5979-8aa5-4bc9-a6ee-479c898e15c2"
PARENT_ID = "d05f2c4e-b1be-4ab3-a1bb-98ddd7a2c205"
OWNER_LINEAR_ID = "0b34be60-67c7-46a0-925c-607afdc3180d"
LABEL_IDS = {
    "origin": "eaa83323-49ce-444c-8318-269629aa1f79",
    "T1": "6d2b7221-d983-465b-a152-90e9bcab715a",
    "T2": "48b2d173-a091-4777-9780-2be932c9c474",
    "T3": "e3687560-eefb-40d9-87bf-ee7e07344f46",
    "T4": "d1a2ee57-dc7d-4804-ab10-a434e92b40da",
}
SECRET_PATTERNS = (
    r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b",
    r"\b(?:lin_api_|sk-|ghp_|github_pat_)[A-Za-z0-9_-]{10,}\b",
    r"(?i)\b(?:bearer|token|password|api_key|пароль|токен)\s*[:= ]\s*\S+",
)


def safe_text(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        value = re.sub(pattern, "[СЕКРЕТ СКРЫТ]", value)
    return value


def classify(draft: dict) -> tuple[str, str]:
    """Conservative proposal, never an execution authorization."""
    text = " ".join([draft["request"], *draft["answers"].values()]).lower()
    if re.search(r"updat|recover|packag|migrat|schema|signing|auth|secret|windows|"
                 r"обновлен|обновить|восстанов|упаков|миграц|схем|удален|удалить|"
                 r"удалён|подпис|авторизац|секрет|парол|токен|sqlite|баз[ауые]|медиа", text):
        return "T4", "Данные или защищённая системная область: требуется Александр."
    surface = draft["answers"].get("surface", "").strip().lower().rstrip(".")
    if surface == "только документация":
        return "T1", "Заявлена только документация; исполнитель проверяет фактический diff."
    if surface == "локальный интерфейс":
        return "T2", "Заявлен узкий локальный интерфейс; зависимости и diff требуют перепроверки."
    return "T3", "Сложность или границы неоднозначны: требуется Александр."


class Store:
    def __init__(self, path: Path, *, read_only: bool = False):
        application_id = 0x414C4535
        if path.is_symlink():
            raise ApiError("State must not be a symlink")
        if path.exists() and path.stat().st_size:
            # Inspect without writes before journal mode, permissions or migrations.
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as probe:
                if probe.execute("PRAGMA application_id").fetchone()[0] != application_id:
                    raise ApiError("Refusing non-intake database; select a dedicated new state path")
        if read_only:
            self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            self.db.row_factory = sqlite3.Row
            return
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path, isolation_level=None, timeout=15)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(f"PRAGMA application_id={application_id}")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS updates(id INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS drafts(
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(
                key TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', result TEXT, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
        """)

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def meta(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, value))

    def save(self, draft: dict):
        self.db.execute("INSERT OR REPLACE INTO drafts VALUES(?,?,?)",
                        (draft["id"], draft["user_id"], json.dumps(draft, ensure_ascii=False)))

    def current(self, user_id: int) -> dict | None:
        row = self.db.execute("SELECT body FROM drafts WHERE id=? AND user_id=?",
                              (self.meta(f"current:{user_id}"), user_id)).fetchone()
        return json.loads(row[0]) if row else None

    def enqueue(self, key: str, kind: str, payload: dict):
        self.db.execute("INSERT OR IGNORE INTO outbox(key,kind,payload,updated) VALUES(?,?,?,?)",
                        (key, kind, json.dumps(payload, ensure_ascii=False), time.time()))

    def event(self, kind: str, detail: str):
        # Deliberately no raw API errors, credentials, chat IDs or message bodies.
        self.db.execute("INSERT INTO events(at,kind,detail) VALUES(?,?,?)", (time.time(), kind, detail))

    def claim(self) -> dict | None:
        with self.transaction():
            row = self.db.execute("SELECT * FROM outbox WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                self.db.execute("UPDATE outbox SET status='sending', updated=? WHERE key=?", (time.time(), row["key"]))
                return dict(row)
        return None

    def recover(self):
        with self.transaction():
            self.db.execute("UPDATE outbox SET status='uncertain',updated=? WHERE status='sending'", (time.time(),))

    def status(self) -> dict:
        return {"paused": self.meta("paused") == "1", "offset": int(self.meta("offset", "0")),
                "heartbeat_unix": self.meta("heartbeat"),
                "linear_connection": self.meta("linear_connection", "not_checked"),
                "outbox": [dict(r) for r in self.db.execute(
                    "SELECT kind,status,count(*) AS count FROM outbox GROUP BY kind,status")],
                "delivery_executor": "not_connected", "physical_updater_gate": "not_connected"}


def summary(draft: dict) -> str:
    answers = draft["answers"]
    return (f"Задача: {draft['request']}\nГде: {answers['screen']}\nСейчас: {answers['actual']}\n"
            f"Нужно: {answers['expected']}\nСохранить: {answers['frozen']}\n"
            f"Проверка: {answers['acceptance']}\nОбласть: {answers['surface']}\n"
            f"Предварительный tier: {draft['tier']}. {draft['tier_reason']}\n"
            "Создать эту задачу в Linear? Это подтверждает постановку задачи; исполнение ещё не подключено.")


def buttons(draft: dict) -> list:
    return [[{"text": title, "callback_data": f"{action}:{draft['id']}:{draft['revision']}"}]
            for title, action in [("Создать задачу", "create"), ("Уточнить", "edit"), ("Отмена", "cancel")]]


def contract(draft: dict) -> dict:
    sources = "\n".join(f"- Telegram message_id={s['message_id']}, update_id={s['update_id']}: {s['text']}"
                        for s in draft["sources"])
    role = "Сергея" if draft["role"] == "sergey" else "Александра (Owner)"
    test_only = "TEST/ALE-528" in draft["request"]
    test_guard = ("## TEST/ALE-528 — только E2E\n\n"
                  f"Фактический инициатор: {role}. Сценарий имитирует запрос Сергея.\n"
                  "EXECUTION_ALLOWED=false\nRELEASE_ALLOWED=false\n"
                  "Не реализовывать и не выпускать. После проверки перевести задачу в отменённый статус.\n\n"
                  if test_only else "")
    return {
        # Draft IDs are already uuid4 and are persisted before confirmation.
        # Linear explicitly requires v4: a deterministic uuid5 is rejected.
        "id": str(uuid.UUID(draft["id"])),
        "title": f"[{draft['tier']}] {draft['request'][:110]}",
        "tier": draft["tier"],
        "test_only": test_only,
        "description": (
            test_guard +
            f"## Подтверждённая постановка от {role}\n\n{summary(draft)}\n\n"
            f"## Происхождение\n\nДиалог `{draft['id']}`, revision `{draft['revision']}`. "
            "Автор Linear — подключённая интеграция; происхождение не подменяет автора. "
            f"Явное подтверждение: update_id={draft['confirmation_update']}.\n\n"
            f"## Исходные сообщения и ответы\n\n{sources}\n\n"
            "Private Telegram не даёт общедоступных ссылок: материалы связаны по message_id/update_id "
            "и сохраняются в защищённом локальном журнале диалога.\n\n"
            "## Ограничения исполнения\n\n"
            "Статус: intake-only, автоматическое исполнение выключено до Owner acceptance системы. "
            "Tier предварительный по docs/context/LINEAR_PROCESS.md. Исполнитель повторно проверяет "
            "сложность, фактический diff и зависимости; неоднозначность и T3/T4 передаются Александру. "
            "Updater/recovery/packaging, schema/migrations, удаление данных, signing/auth/secrets "
            "и Windows system behavior требуют Owner. Все write-тесты только TEMP.\n\n"
            "## Последующие gates (не подключены)\n\n"
            "Railway exact HEAD + revision → явная приёмка Сергея → candidate exact HEAD → "
            "самостоятельный physical Windows updater gate → production → штатный notification journal. "
            "Любое изменение HEAD/контракта инвалидирует приёмку. Без product PASS и physical updater "
            "PASS production запрещён. Общие repo rules сохраняются."
        ),
    }


class Intake:
    def __init__(self, store: Store, sergey_id: int, owner_id: int):
        if min(sergey_id, owner_id) <= 0 or sergey_id == owner_id:
            raise ValueError("Нужны два различных проверенных Telegram user ID")
        self.store = store
        self.roles = {sergey_id: "sergey", owner_id: "owner"}

    def process(self, update: dict):
        s = self.store
        update_id = int(update["update_id"])
        with s.transaction():
            if s.db.execute("SELECT 1 FROM updates WHERE id=?", (update_id,)).fetchone():
                return
            s.db.execute("INSERT INTO updates VALUES(?)", (update_id,))
            s.set_meta("offset", str(max(update_id + 1, int(s.meta("offset", "0")))))
            callback = update.get("callback_query")
            message = (callback or {}).get("message") if callback else update.get("message")
            actor = (callback or message or {}).get("from", {})
            user_id = actor.get("id")
            chat = (message or {}).get("chat", {})
            if (user_id not in self.roles or actor.get("is_bot") or chat.get("type") != "private"
                    or chat.get("id") != user_id):
                s.event("input_rejected", "unauthorized_or_unsupported")
                return
            s.event("input_accepted", json.dumps({
                "update_id": update_id, "message_id": message.get("message_id"),
                "role": self.roles[user_id], "kind": "callback" if callback else "message"}))
            if callback:
                s.enqueue(f"ack:{update_id}", "telegram_ack", {"callback_query_id": callback["id"]})

            def reply(text: str, keyboard: list | None = None):
                payload = {"chat_id": user_id, "text": text}
                if keyboard:
                    payload["reply_markup"] = {"inline_keyboard": keyboard}
                s.enqueue(f"reply:{update_id}", "telegram", payload)

            text = safe_text(str((message or {}).get("text", "")).strip()) if not callback else ""
            draft = s.current(user_id)
            if text in {"/pause", "/resume"}:
                if self.roles[user_id] != "owner":
                    reply("Пауза и возобновление доступны Александру.")
                else:
                    s.set_meta("paused", "1" if text == "/pause" else "0")
                    reply("Приём приостановлен." if text == "/pause" else "Приём возобновлён.")
                return
            if text == "/status":
                if draft and draft["state"] == "summary" and s.meta("paused") != "1":
                    reply(summary(draft), buttons(draft))
                    return
                uncertain = s.db.execute("SELECT count(*) FROM outbox WHERE status='uncertain'").fetchone()[0]
                reply(f"Приём: {'пауза' if s.meta('paused') == '1' else 'включён'}. "
                      f"Диалог: {draft['state'] if draft else 'нет'}. "
                      f"{draft.get('issue_url', '') if draft else ''} "
                      f"Linear: {'ожидает подключения' if s.meta('linear_connection') == 'not_connected' else 'проверяется сервисом'}. "
                      f"Операций для сверки Александром: {uncertain}. Исполнение и updater gate не подключены.")
                return
            if s.meta("paused") == "1":
                reply("Приём на паузе Александра. Подтверждения сохранены; новые задачи не создаются.")
                return
            if callback:
                parts = callback.get("data", "").split(":")
                if (len(parts) != 3 or not draft or parts[1] != draft["id"]
                        or parts[2] != str(draft["revision"]) or draft["state"] != "summary"):
                    reply("Эта кнопка уже обработана или резюме изменилось. Используйте /status.")
                    return
                if parts[0] == "create":
                    draft["state"] = "confirmed"
                    draft["confirmation_update"] = update_id
                    s.save(draft)
                    s.enqueue(f"linear:{draft['id']}", "linear", {"draft_id": draft["id"], **contract(draft)})
                    s.event("confirmed", draft["id"])
                    if s.meta("linear_connection") == "not_connected":
                        reply("Подтверждение сохранено локально. Linear ожидает подключения; "
                              "задача там ещё не создана. Ссылку пришлю после подтверждённой записи.")
                    else:
                        reply("Подтверждение сохранено. Создаю задачу в Linear; ссылку пришлю после ответа сервиса.")
                elif parts[0] == "edit":
                    draft.update(state="asking", answers={}, revision=draft["revision"] + 1)
                    s.save(draft)
                    reply("Уточним постановку заново. " + QUESTIONS[0][1])
                elif parts[0] == "cancel":
                    draft["state"] = "cancelled"
                    s.save(draft)
                    reply("Создание отменено. Для новой задачи — /new.")
                return
            if text == "/cancel":
                if draft and draft["state"] in {"asking", "summary"}:
                    draft["state"] = "cancelled"
                    s.save(draft)
                    reply("Создание отменено.")
                else:
                    reply("Нет неподтверждённой задачи. Подтверждённую запись отменяет Александр в Linear.")
                return
            if text in {"/start", "/new"}:
                if draft and draft["state"] in {"asking", "summary", "confirmed"}:
                    reply("Уже есть диалог. Продолжите ответы, /status или /cancel до подтверждения.")
                else:
                    s.set_meta(f"current:{user_id}", "")
                    reply("Опишите одну доработку. Не присылайте пароли или токены. "
                          "Текстовый пилот: голос пока нужно расшифровать вручную, скриншот можно приложить как контекст.")
                return
            if (message or {}).get("photo"):
                if not draft or draft["state"] not in {"asking", "summary"}:
                    reply("Сначала опишите задачу текстом, затем приложите скриншот.")
                else:
                    # Store opaque Telegram reference only, never token-bearing getFile URLs.
                    draft.setdefault("attachments", []).append({
                        "message_id": message["message_id"], "file_id": message["photo"][-1]["file_id"]})
                    draft["sources"].append({"message_id": message["message_id"], "update_id": update_id,
                                             "text": "[Скриншот: контекст; визуально ещё не проанализирован]"})
                    if draft["state"] == "summary":
                        draft.update(state="asking", answers={}, revision=draft["revision"] + 1)
                    s.save(draft)
                    reply("Скриншот связан с диалогом. Опишите важное на нём текстом. "
                          + QUESTIONS[len(draft["answers"])][1])
                return
            if not text:
                reply("Для текстового пилота пришлите текст или ручную расшифровку голоса. Ответ не засчитан.")
                return
            if len(text) > 450:
                reply("Сократите ответ до 450 символов, чтобы резюме целиком поместилось в сообщение.")
                return
            if text.lower().strip(". !") in {"не знаю", "непонятно", "как обычно", "сам реши", "потом", "?"}:
                reply("Нужно конкретное наблюдаемое описание. " +
                      (QUESTIONS[len(draft["answers"])][1] if draft and draft["state"] == "asking"
                       else "Опишите одну доработку и её результат."))
                return
            if text.startswith("/"):
                reply("Команды: /new, /status, /cancel. Александр: /pause, /resume.")
                return
            if draft and draft["state"] in {"summary", "confirmed", "created"}:
                reply("Используйте кнопки под резюме, /status или /new после завершения диалога.")
                return
            source = {"message_id": message["message_id"], "update_id": update_id, "text": text}
            if not draft or draft["state"] == "cancelled":
                draft = {"id": uuid.uuid4().hex, "user_id": user_id, "role": self.roles[user_id],
                         "request": text, "answers": {}, "sources": [source], "revision": 1, "state": "asking"}
                s.set_meta(f"current:{user_id}", draft["id"])
                reply(QUESTIONS[0][1])
            else:
                draft["sources"].append(source)
                draft["answers"][QUESTIONS[len(draft["answers"])][0]] = text
                if len(draft["answers"]) == len(QUESTIONS):
                    draft["tier"], draft["tier_reason"] = classify(draft)
                    draft["state"] = "summary"
                    reply(summary(draft), buttons(draft))
                else:
                    reply(QUESTIONS[len(draft["answers"])][1])
            s.save(draft)


class ApiError(RuntimeError):
    pass


def request_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 40) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except Exception:
        # URL may contain a bot token. Never propagate exception text or chains.
        raise ApiError("API transport failure; result may be uncertain") from None


class Telegram:
    def __init__(self, token: str):
        self.token = token

    def call(self, method: str, payload: dict) -> dict | list | bool:
        data = request_json(f"https://api.telegram.org/bot{self.token}/{method}", payload)
        if not data.get("ok"):
            raise ApiError("Telegram API rejected request")
        return data["result"]

    def preflight(self):
        identity = self.call("getMe", {})
        if self.call("getWebhookInfo", {}).get("url"):
            raise ApiError("Webhook configured; polling disabled, no automatic deletion")
        return identity["id"]


class Linear:
    def __init__(self, token: str, labels: dict):
        self.token, self.labels = token, labels

    def call(self, query: str, variables: dict) -> dict:
        data = request_json("https://api.linear.app/graphql", {"query": query, "variables": variables},
                            {"Authorization": self.token})
        if data.get("errors") or "data" not in data:
            raise ApiError("Linear API rejected request; inspect securely, no blind retry")
        return data["data"]

    def preflight(self):
        # Fail before the first write if client-generated issue IDs are unsupported.
        data = self.call('{ __type(name:"IssueCreateInput") { inputFields { name } } }', {})
        if "id" not in {f["name"] for f in data["__type"]["inputFields"]}:
            raise ApiError("Linear IssueCreateInput.id unavailable; dedup contract unsupported")
        query = ('query($team:String!,$project:String!,$parent:String!){'
                 'viewer{id} team(id:$team){id} project(id:$project){id} '
                 'issue(id:$parent){id team{id} project{id}}}')
        scope = self.call(query, {"team": TEAM_ID, "project": PROJECT_ID, "parent": PARENT_ID})
        if (scope.get("viewer", {}).get("id") != OWNER_LINEAR_ID
                or (scope.get("team") or {}).get("id") != TEAM_ID
                or (scope.get("project") or {}).get("id") != PROJECT_ID
                or (scope.get("issue") or {}).get("id") != PARENT_ID
                or (scope["issue"].get("team") or {}).get("id") != TEAM_ID
                or (scope["issue"].get("project") or {}).get("id") != PROJECT_ID):
            raise ApiError("Linear identity/team/project mismatch; no writes allowed")

    def create(self, payload: dict) -> dict:
        if uuid.UUID(payload["id"]).version != 4:
            raise ApiError("Linear create requires a persisted UUID v4; request not sent")
        result = self.call("mutation($input:IssueCreateInput!){issueCreate(input:$input){success issue{id identifier url}}}",
                           {"input": {"id": payload["id"], "title": payload["title"],
                                      "description": payload["description"], "teamId": TEAM_ID,
                                      "projectId": PROJECT_ID, "parentId": PARENT_ID,
                                      "labelIds": [self.labels["origin"], self.labels[payload["tier"]]]}})["issueCreate"]
        if not result.get("success") or not result.get("issue"):
            raise ApiError("Linear create unconfirmed")
        return result["issue"]

    def find(self, issue_id: str) -> dict | None:
        return self.call("query($id:String!){issue(id:$id){id identifier url description}}", {"id": issue_id})["issue"]


def complete_linear(store: Store, item: dict, result: dict):
    payload = json.loads(item["payload"])
    if result.get("id") != payload["id"] or not str(result.get("url", "")).startswith("https://linear.app/"):
        raise ApiError("Linear returned unexpected identity")
    row = store.db.execute("SELECT body FROM drafts WHERE id=?", (payload["draft_id"],)).fetchone()
    draft = json.loads(row[0])
    draft.update(state="created", issue_id=result["id"], issue_url=result["url"])
    store.save(draft)
    store.enqueue(f"created:{draft['id']}", "telegram", {
        "chat_id": draft["user_id"], "text": f"Задача создана: {result['url']}\n"
        f"{draft['tier']}. Исполнение ещё не подключено. Для новой задачи — /new."})
    store.event("linear_created", draft["id"])


def dispatch_one(store: Store, telegram: Telegram, linear: Linear | None) -> bool:
    # Pause also blocks confirmed-but-not-yet-dispatched Linear writes.
    if store.meta("paused") == "1" or linear is None:
        with store.transaction():
            row = store.db.execute("SELECT * FROM outbox WHERE status='pending' AND kind!='linear' ORDER BY rowid LIMIT 1").fetchone()
            item = dict(row) if row else None
            if item:
                store.db.execute("UPDATE outbox SET status='sending',updated=? WHERE key=?", (time.time(), item["key"]))
    else:
        item = store.claim()
    if not item:
        return False
    payload = json.loads(item["payload"])
    try:
        if item["kind"] == "linear":
            result = linear.create(payload)
        else:
            method = "answerCallbackQuery" if item["kind"] == "telegram_ack" else "sendMessage"
            result = telegram.call(method, payload)
        with store.transaction():
            if item["kind"] == "linear":
                complete_linear(store, item, result)
            stored = {"message_id": result.get("message_id")} if item["kind"] == "telegram" else result
            store.db.execute("UPDATE outbox SET status='sent',result=?,updated=? WHERE key=?",
                             (json.dumps(stored), time.time(), item["key"]))
            store.event("outbound_sent", item["key"])
    except Exception:
        with store.transaction():
            store.db.execute("UPDATE outbox SET status='uncertain',updated=? WHERE key=?", (time.time(), item["key"]))
            store.event("outbound_uncertain", item["key"])
        # A Telegram timeout cannot safely be retried: sendMessage has no idempotency key.
    return True


def equivalent_linear_description(actual: str, expected: str) -> bool:
    # Linear canonicalizes unordered list markers and the final newline.
    # Keep every content character and indentation; semantic edits stay blocked.
    def canonical(text: str) -> str:
        return re.sub(r"(?m)^([ \t]*)[-*+] ", r"\1- ", text).strip("\n")
    return canonical(actual) == canonical(expected)


def reconcile_linear(store: Store, linear: Linear) -> int:
    """Read-only lookup after uncertain create. Never repeat issueCreate."""
    count = 0
    for row in store.db.execute("SELECT * FROM outbox WHERE status='uncertain' AND kind='linear'").fetchall():
        payload = json.loads(row["payload"])
        try:
            result = linear.find(payload["id"])
            if not result or not equivalent_linear_description(result.get("description", ""), payload["description"]):
                continue
            with store.transaction():
                complete_linear(store, dict(row), result)
                store.db.execute("UPDATE outbox SET status='sent',updated=? WHERE key=?", (time.time(), row["key"]))
            count += 1
        except ApiError:
            continue
    return count


@contextmanager
def service_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a") as handle:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ApiError("Intake service already running for this state") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def config(environ: dict, *, require_linear: bool = True) -> dict:
    prefix = "SERGEY_INTAKE_"
    names = ["BOT_TOKEN", "SERGEY_USER_ID", "OWNER_USER_ID"]
    if require_linear:
        names.append("LINEAR_API_KEY")
    missing = [prefix + n for n in names if not environ.get(prefix + n)]
    if missing:
        raise ApiError("Missing protected configuration: " + ", ".join(missing))
    try:
        result = {n: environ[prefix + n] for n in names}
        result["LINEAR_API_KEY"] = environ.get(prefix + "LINEAR_API_KEY", "")
        result["LABEL_IDS"] = json.loads(environ[prefix + "LABEL_IDS"]) if environ.get(prefix + "LABEL_IDS") else LABEL_IDS
        for key in ["origin", "T1", "T2", "T3", "T4"]:
            uuid.UUID(result["LABEL_IDS"][key])
        result["SERGEY_USER_ID"] = int(result["SERGEY_USER_ID"])
        result["OWNER_USER_ID"] = int(result["OWNER_USER_ID"])
        if min(result["SERGEY_USER_ID"], result["OWNER_USER_ID"]) <= 0 or result["SERGEY_USER_ID"] == result["OWNER_USER_ID"]:
            raise ValueError
        return result
    except (ValueError, KeyError, TypeError):
        raise ApiError("Invalid protected configuration; values withheld") from None


def protected_config(path: Path | None, *, require_linear: bool = True) -> dict:
    values = {}
    if path:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ApiError("Credentials file must be a regular owner-only file (0600)")
        try:
            values = json.loads(path.read_text())
            if not isinstance(values, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            raise ApiError("Invalid credentials file; contents withheld") from None
    values.update({k: v for k, v in os.environ.items() if k.startswith("SERGEY_INTAKE_")})
    return config(values, require_linear=require_linear)


def install_linear_key(path: Path, token: str):
    """Validate read-only, then atomically replace one private credential field."""
    if not re.fullmatch(r"lin_api_[A-Za-z0-9_-]{20,}", token):
        raise ApiError("Invalid Linear personal key format; value withheld")
    cfg = protected_config(path, require_linear=False)
    Linear(token, cfg["LABEL_IDS"]).preflight()
    values = json.loads(path.read_text())
    values["SERGEY_INTAKE_LINEAR_API_KEY"] = token
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".credentials-", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            json.dump(values, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def serve_linear_key(path: Path):
    """One-shot loopback-only secret input. No request logging or external assets."""
    csrf = secrets.token_urlsafe(32)
    done = False

    class PrivateServer(HTTPServer):
        def handle_error(self, request, client_address):
            print("Local key input connection interrupted; diagnostic contents suppressed", flush=True)

    class KeyInput(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def page(self, status: int, body: str):
            content = ("<!doctype html><html lang='ru'><meta charset='utf-8'>"
                       "<meta name='viewport' content='width=device-width'>"
                       "<title>ALE-528 · локальный ввод ключа</title>"
                       "<style>body{font:18px system-ui;max-width:650px;margin:60px auto;padding:24px}"
                       "input,button{font:inherit;padding:12px;margin:8px 0;width:100%;box-sizing:border-box}"
                       "small{color:#555}</style><h1>ALE-528 · ключ Linear</h1>" + body + "</html>").encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path != "/" or self.headers.get("Host") != origin.removeprefix("http://"):
                self.page(404, "<p>Страница недоступна.</p>")
                return
            self.page(200, "<p>Вставьте новый Personal API key в скрытое поле. Ключ проверяется "
                      "через api.linear.app и сохраняется только в локальный файл 0600.</p>"
                      "<p>Права: Read + Create and update issues, только команда Alex.</p>"
                      f"<form method='post' action='/'><input type='hidden' name='csrf' value='{csrf}'>"
                      "<label>Ключ Linear<input name='key' type='password' autocomplete='off' "
                      "spellcheck='false' maxlength='200' required autofocus></label>"
                      "<button type='submit'>Проверить и сохранить локально</button></form>"
                      "<small>Не вводите ключ в чат. Нет сторонних скриптов, аналитики или журналирования запросов.</small>")

        def do_POST(self):
            nonlocal done
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if (self.path != "/" or self.headers.get("Origin") != origin
                        or self.headers.get("Host") != origin.removeprefix("http://")
                        or self.headers.get_content_type() != "application/x-www-form-urlencoded"
                        or not 0 < size <= 1024):
                    self.page(403, "<p>Запрос отклонён. Откройте локальную форму заново.</p>")
                    return
                fields = urllib.parse.parse_qs(self.rfile.read(size).decode())
                if not secrets.compare_digest(fields.get("csrf", [""])[0], csrf):
                    self.page(403, "<p>Запрос отклонён.</p>")
                    return
                install_linear_key(path, fields.get("key", [""])[0].strip())
            except Exception:
                self.page(400, "<p>Ключ не сохранён: проверьте формат, права, аккаунт и доступ к проекту. "
                          "Значение и подробности не журналируются. Вернитесь назад для повторного ввода.</p>")
                return
            done = True
            print("Linear key validated and saved privately; local input finished", flush=True)
            self.page(200, "<h2>Ключ сохранён</h2><p>Аккаунт Owner, команда Alex, проект и схема проверены. "
                      "Поле ввода очищено. Сообщите в чате «готово», не отправляя сам ключ.</p>")

    with PrivateServer(("127.0.0.1", 0), KeyInput) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        server.timeout = 1
        deadline = time.monotonic() + 900
        print("Local private key input: " + origin, flush=True)
        while not done and time.monotonic() < deadline:
            server.handle_request()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "check-config", "set-linear-key", "serve-linear-key", "status", "run", "reconcile"])
    parser.add_argument("--state", type=Path, required=True, help="Dedicated private intake SQLite; never product DB")
    parser.add_argument("--credentials-file", type=Path, help="Private 0600 JSON, outside Git; environment overrides")
    parser.add_argument("--intake-only", action="store_true", help="Explicit Telegram-only mode; confirmed Linear writes remain pending")
    args = parser.parse_args()
    if args.intake_only and args.action == "reconcile":
        parser.error("reconcile requires the Linear connection")
    os.umask(0o077)
    try:
        if args.action == "serve-linear-key":
            if not args.credentials_file:
                raise ApiError("--credentials-file required")
            protected_config(args.credentials_file, require_linear=False)
            serve_linear_key(args.credentials_file)
            return 0
        if args.action == "set-linear-key":
            if not args.credentials_file or not sys.stdin.isatty():
                raise ApiError("Use a local interactive terminal and --credentials-file; key input must not be echoed")
            token = getpass.getpass("Linear API key (hidden input; paste then Return): ").strip()
            install_linear_key(args.credentials_file, token)
            print("Linear identity/team/project and schema verified; key saved privately (0600).")
            return 0
        if args.action == "check-config":
            protected_config(args.credentials_file, require_linear=not args.intake_only)
            print("Configuration present; identity and API validation require run")
            return 0
        if args.action == "status":
            store = Store(args.state, read_only=True)
            print(json.dumps(store.status(), ensure_ascii=False))
            return 0
        with service_lock(args.state.with_suffix(".lock")):
            store = Store(args.state)
            if args.action == "init":
                with store.transaction():
                    if store.meta("initialized") != "1":
                        store.set_meta("initialized", "1")
                        store.set_meta("paused", "1")
                        store.event("initialized", "paused_until_owner_resume")
                print("Dedicated intake state initialized; Owner pause enabled")
                return 0
            if store.meta("initialized") != "1":
                raise ApiError("Initialize dedicated state with init before connecting the bot")
            cfg = protected_config(args.credentials_file, require_linear=not args.intake_only)
            bot = Telegram(cfg["BOT_TOKEN"])
            linear = None if args.intake_only else Linear(cfg["LINEAR_API_KEY"], cfg["LABEL_IDS"])
            if linear:
                linear.preflight()
            store.set_meta("linear_connection", "connected" if linear else "not_connected")
            store.recover()
            if args.action == "reconcile":
                print(json.dumps({"reconciled": reconcile_linear(store, linear)}))
                return 0
            bot_id = str(bot.preflight())
            binding = json.dumps([bot_id, cfg["SERGEY_USER_ID"], cfg["OWNER_USER_ID"]])
            if store.meta("identity") and store.meta("identity") != binding:
                raise ApiError("Bot/allowlist identity changed; use separate state after explicit review")
            store.set_meta("identity", binding)
            intake = Intake(store, cfg["SERGEY_USER_ID"], cfg["OWNER_USER_ID"])
            print("Intake running; delivery executor and physical updater gate disconnected", flush=True)
            while True:
                try:
                    updates = bot.call("getUpdates", {"offset": int(store.meta("offset", "0")),
                                       "timeout": 25, "allowed_updates": ["message", "callback_query"]})
                    for update in updates:
                        intake.process(update)
                    for _ in range(100):
                        if not dispatch_one(store, bot, linear):
                            break
                    store.set_meta("heartbeat", str(time.time()))
                except ApiError:
                    store.event("poll_failed", "safe_retry_read_only")
                    time.sleep(5)
    except (ApiError, ValueError) as exc:
        print(str(exc))
        return 2
    except (OSError, sqlite3.Error):
        print("Local state/configuration failure; inspect paths and permissions securely")
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
