import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from scripts.sergey_intake import (
    ApiError, Intake, Linear, Store, Telegram, classify, config, dispatch_one,
    protected_config, reconcile_linear, request_json, safe_text, service_lock,
    install_linear_key, OWNER_LINEAR_ID, TEAM_ID, PROJECT_ID, PARENT_ID,
    equivalent_linear_description,
)


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def call(self, method, payload):
        self.sent.append((method, payload))
        return {"message_id": len(self.sent)}


class FakeLinear:
    def __init__(self):
        self.calls = []
        self.issues = {}
        self.lose_response = False

    def create(self, payload):
        self.calls.append(payload)
        result = {"id": payload["id"], "identifier": "TEST-1", "url": "https://linear.app/test/issue/TEST-1",
                  "description": payload["description"]}
        self.issues[payload["id"]] = result
        if self.lose_response:
            raise ApiError("simulated uncertain result")
        return result

    def find(self, issue_id):
        return self.issues.get(issue_id)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "intake.sqlite3"
        self.store = Store(self.path)
        self.intake = Intake(self.store, 11, 22)
        self.seq = 0
        self.telegram, self.linear = FakeTelegram(), FakeLinear()

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def message(self, text=None, user=11, **fields):
        self.seq += 1
        message = {"from": {"id": user}, "chat": {"id": user, "type": "private"},
                   "message_id": self.seq, **fields}
        if text is not None:
            message["text"] = text
        return {"update_id": self.seq, "message": message}

    def send(self, text=None, **fields):
        update = self.message(text, **fields)
        self.intake.process(update)
        return update

    def ready(self):
        for text in ["Исправить опечатку в инструкции", "docs/help", "Написано «нагрд»", "Написать «наград»",
                     "Остальные абзацы", "Открыть инструкцию, увидеть правильное слово", "только документация"]:
            self.send(text)
        return self.store.current(11)

    def callback(self, action="create", draft=None, user=11):
        draft = draft or self.store.current(user)
        self.seq += 1
        update = {"update_id": self.seq, "callback_query": {"id": f"cb{self.seq}", "from": {"id": user},
                  "data": f"{action}:{draft['id']}:{draft['revision']}",
                  "message": {"message_id": 1000, "chat": {"id": user, "type": "private"}}}}
        self.intake.process(update)
        return update

    def drain(self):
        for _ in range(100):
            if not dispatch_one(self.store, self.telegram, self.linear):
                return
        self.fail("outbox did not drain")

    def count(self, kind):
        return self.store.db.execute("SELECT count(*) FROM outbox WHERE kind=?", (kind,)).fetchone()[0]

    def test_full_text_flow_requires_explicit_confirmation_and_preserves_origin(self):
        draft = self.ready()
        self.assertEqual((draft["state"], draft["tier"]), ("summary", "T1"))
        self.drain()
        self.assertEqual(self.linear.calls, [])
        self.assertIn("Создать задачу", str(self.telegram.sent))
        self.callback()
        self.drain()
        self.assertEqual(len(self.linear.calls), 1)
        self.assertEqual(uuid.UUID(self.linear.calls[0]["id"]).version, 4)
        self.assertEqual(self.linear.calls[0]["id"], str(uuid.UUID(draft["id"])))
        self.assertEqual(self.store.current(11)["state"], "created")
        description = self.linear.calls[0]["description"]
        for value in ["от Сергея", draft["id"], "revision `1`", "message_id=1", "фактический diff", "physical updater"]:
            self.assertIn(value, description)

    def test_owner_e2e_contract_blocks_execution_and_records_real_transport_ids(self):
        for text in ["TEST/ALE-528: исправить опечатку", "Справка", "Опечатка", "Исправить", "Остальное",
                     "Прочитать тестовый абзац", "только документация"]:
            self.send(text, user=22)
        self.callback(user=22)
        self.drain()
        payload = self.linear.calls[0]
        self.assertTrue(payload["test_only"])
        self.assertIn("EXECUTION_ALLOWED=false", payload["description"])
        self.assertIn("RELEASE_ALLOWED=false", payload["description"])
        self.assertIn("Фактический инициатор: Александра (Owner)", payload["description"])
        events = [json.loads(r[0]) for r in self.store.db.execute("SELECT detail FROM events WHERE kind='input_accepted'")]
        self.assertEqual(len(events), 8)
        self.assertEqual(events[0]["message_id"], 1)
        self.assertEqual(events[-1]["kind"], "callback")

    def test_restart_and_replayed_message_do_not_advance_answers(self):
        first = self.send("Опечатка")
        self.store.db.close()
        self.store = Store(self.path)
        self.intake = Intake(self.store, 11, 22)
        self.intake.process(first)
        self.assertEqual(self.store.current(11)["answers"], {})
        self.send("Инструкция")
        self.assertEqual(len(self.store.current(11)["answers"]), 1)
        self.assertEqual(self.store.meta("offset"), "3")

    def test_duplicate_update_and_repeated_button_create_one_issue(self):
        self.ready()
        update = self.callback()
        self.intake.process(update)
        self.callback()
        self.drain()
        self.assertEqual(len(self.linear.calls), 1)
        self.assertEqual(self.count("linear"), 1)

    def test_edit_and_old_confirmation_button(self):
        old = copy.deepcopy(self.ready())
        self.callback("edit")
        self.callback(draft=old)
        self.assertEqual(self.count("linear"), 0)
        self.assertEqual(self.store.current(11)["revision"], 2)
        for text in ["help", "ошибка", "исправить", "остальное", "прочитать", "только документация"]:
            self.send(text)
        self.callback(draft=old)
        self.assertEqual(self.count("linear"), 0)
        self.callback()
        self.assertEqual(self.count("linear"), 1)

    def test_cancel_is_not_confirmation(self):
        self.ready()
        self.callback("cancel")
        self.callback()
        self.drain()
        self.assertEqual(self.linear.calls, [])
        self.assertEqual(self.store.current(11)["state"], "cancelled")

    def test_cross_user_and_group_callback_cannot_confirm(self):
        draft = self.ready()
        self.callback(draft=draft, user=22)
        self.callback(draft=draft, user=99)
        update = self.message("Подмена")
        update["message"]["chat"] = {"id": -100, "type": "group"}
        self.intake.process(update)
        self.assertEqual(self.count("linear"), 0)
        self.assertIsNone(self.store.current(99))

    def test_pause_blocks_pending_linear_write_and_is_owner_only(self):
        self.ready()
        self.callback()
        self.send("/pause")
        self.assertNotEqual(self.store.meta("paused"), "1")
        self.send("/pause", user=22)
        self.drain()
        self.assertEqual(self.linear.calls, [])
        self.send("/resume", user=22)
        self.drain()
        self.assertEqual(len(self.linear.calls), 1)

    def test_explicit_intake_only_keeps_confirmation_pending_then_resumes_once(self):
        self.store.set_meta("linear_connection", "not_connected")
        self.ready()
        self.callback()
        for _ in range(30):
            if not dispatch_one(self.store, self.telegram, None):
                break
        self.assertEqual(self.store.current(11)["state"], "confirmed")
        self.assertEqual(self.linear.calls, [])
        self.assertIn("задача там ещё не создана", str(self.telegram.sent))
        row = self.store.db.execute("SELECT status FROM outbox WHERE kind='linear'").fetchone()
        self.assertEqual(row[0], "pending")
        self.store.set_meta("linear_connection", "connected")
        self.drain()
        self.drain()
        self.assertEqual(len(self.linear.calls), 1)
        self.assertEqual(self.store.current(11)["state"], "created")

    def test_full_mode_still_requires_linear_credential(self):
        values = {"SERGEY_INTAKE_BOT_TOKEN": "withheld", "SERGEY_INTAKE_SERGEY_USER_ID": "11",
                  "SERGEY_INTAKE_OWNER_USER_ID": "22"}
        with self.assertRaisesRegex(ApiError, "LINEAR_API_KEY"):
            config(values)
        self.assertEqual(config(values, require_linear=False)["LINEAR_API_KEY"], "")

    def test_ambiguous_create_is_reconciled_read_only_after_restart(self):
        self.ready()
        self.callback()
        self.linear.lose_response = True
        self.drain()
        self.assertEqual(self.store.current(11)["state"], "confirmed")
        for issue in self.linear.issues.values():
            issue["description"] = issue["description"].replace("\n- Telegram", "\n* Telegram") + "\n"
        self.store.recover()
        self.drain()
        self.assertEqual(len(self.linear.calls), 1)

        self.assertEqual(reconcile_linear(self.store, self.linear), 1)
        self.assertEqual(reconcile_linear(self.store, self.linear), 0)
        self.drain()
        self.assertEqual(self.store.current(11)["state"], "created")
        self.assertEqual(len(self.linear.calls), 1)

    def test_recovery_markdown_normalization_preserves_content_and_indentation(self):
        self.assertTrue(equivalent_linear_description("* source\n", "- source"))
        self.assertFalse(equivalent_linear_description("* changed\n", "- source"))
        self.assertFalse(equivalent_linear_description("  * source\n", "- source"))

    def test_crash_before_result_keeps_unsent_work_uncertain(self):
        self.send("Задача")
        item = self.store.claim()
        self.assertIsNotNone(item)
        self.store.recover()
        self.drain()
        self.assertEqual(self.telegram.sent, [])
        self.assertEqual(self.store.status()["outbox"][0]["status"], "uncertain")

    def test_telegram_timeout_never_blindly_retries(self):
        self.send("Задача")
        with patch.object(self.telegram, "call", side_effect=ApiError("timeout")) as call:
            self.drain()
            self.drain()
        self.assertEqual(call.call_count, 1)

    def test_transaction_rolls_back_input_offset_and_draft_on_failure(self):
        update = self.message("Задача")
        with patch.object(self.store, "save", side_effect=RuntimeError("disk failure")):
            with self.assertRaises(RuntimeError):
                self.intake.process(update)
        self.assertEqual(self.store.meta("offset", "0"), "0")
        self.assertEqual(self.count("telegram"), 0)
        self.intake.process(update)
        self.assertEqual(self.store.current(11)["request"], "Задача")

    def test_second_service_is_excluded_and_lock_is_released(self):
        lock = self.path.with_suffix(".lock")
        with service_lock(lock):
            with self.assertRaises(ApiError):
                with service_lock(lock):
                    self.fail("second writer entered")
        with service_lock(lock):
            pass

    def test_actual_process_crash_releases_lock_without_retrying_claim(self):
        self.send("Задача")
        script = """
import os, sys
from pathlib import Path
from scripts.sergey_intake import Store, service_lock
p = Path(sys.argv[1])
with service_lock(p.with_suffix('.lock')):
    s = Store(p)
    assert s.claim() is not None
    os._exit(17)
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.path)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 17, result.stderr.decode())
        with service_lock(self.path.with_suffix(".lock")):
            self.store.recover()
        self.drain()
        self.assertEqual(self.telegram.sent, [])

    def test_read_only_status_works_while_service_owns_lock(self):
        with service_lock(self.path.with_suffix(".lock")):
            reader = Store(self.path, read_only=True)
            try:
                self.assertEqual(reader.status()["offset"], 0)
            finally:
                reader.db.close()

    def test_credentials_file_rejects_shared_permissions(self):
        path = self.path.parent / "credentials.json"
        path.write_text(json.dumps({"SERGEY_INTAKE_BOT_TOKEN": "withheld"}))
        path.chmod(0o644)
        with self.assertRaisesRegex(ApiError, "0600"):
            protected_config(path)

    def test_linear_key_install_is_atomic_private_and_preserves_other_settings(self):
        path = self.path.parent / "credentials.json"
        before = {"SERGEY_INTAKE_BOT_TOKEN": "test-only", "SERGEY_INTAKE_SERGEY_USER_ID": 11,
                  "SERGEY_INTAKE_OWNER_USER_ID": 22}
        path.write_text(json.dumps(before)); path.chmod(0o600)
        key = "lin_api_" + "x" * 32
        with patch.object(Linear, "preflight"):
            install_linear_key(path, key)
        self.assertEqual(json.loads(path.read_text()), {**before, "SERGEY_INTAKE_LINEAR_API_KEY": key})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(path.parent.glob(".credentials-*")), [])
        original = path.read_bytes()
        with patch.object(Linear, "preflight", side_effect=ApiError("Denied")):
            with self.assertRaises(ApiError):
                install_linear_key(path, "lin_api_" + "y" * 32)
        self.assertEqual(path.read_bytes(), original)

    def test_preflight_checks_actual_owner_and_project_without_writes(self):
        schema = {"__type": {"inputFields": [{"name": "id"}]}}
        scope = {"viewer": {"id": OWNER_LINEAR_ID}, "team": {"id": TEAM_ID},
                 "project": {"id": PROJECT_ID},
                 "issue": {"id": PARENT_ID, "team": {"id": TEAM_ID}, "project": {"id": PROJECT_ID}}}
        client = Linear("withheld", {})
        with patch.object(client, "call", side_effect=[schema, scope]) as call:
            client.preflight()
        self.assertTrue(all("mutation" not in c.args[0] for c in call.call_args_list))
        scope["viewer"]["id"] = "wrong-user"
        with patch.object(client, "call", side_effect=[schema, scope]):
            with self.assertRaisesRegex(ApiError, "mismatch"):
                client.preflight()

    def test_status_reissues_summary_and_ambiguity_does_not_advance(self):
        self.send("Опечатка")
        self.send("не знаю")
        self.assertEqual(self.store.current(11)["answers"], {})
        self.send("/cancel")
        self.ready()
        self.send("/status")
        payload = json.loads(self.store.db.execute("SELECT payload FROM outbox ORDER BY rowid DESC LIMIT 1").fetchone()[0])
        self.assertIn("inline_keyboard", payload["reply_markup"])
        self.assertEqual(self.count("linear"), 0)

    def test_rejects_non_intake_database_without_mutation(self):
        other = self.path.parent / "product.sqlite3"
        with sqlite3.connect(other) as db:
            db.execute("CREATE TABLE person(id INTEGER)")
        original = other.read_bytes()
        with self.assertRaises(ApiError):
            Store(other)
        self.assertEqual(other.read_bytes(), original)

    def test_secret_redaction_before_persistence(self):
        secret = "123456789:" + "a" * 30
        self.send("Опечатка " + secret)
        self.assertNotIn(secret, self.store.current(11)["request"])
        self.assertIn("[СЕКРЕТ СКРЫТ]", self.store.current(11)["request"])
        self.assertNotIn("lin_api_" + "a" * 30, safe_text("lin_api_" + "a" * 30))

    def test_photo_is_context_not_an_answer_and_invalidates_old_summary(self):
        old = copy.deepcopy(self.ready())
        self.send(photo=[{"file_id": "opaque-context"}])
        self.callback(draft=old)
        draft = self.store.current(11)
        self.assertEqual((draft["state"], draft["revision"]), ("asking", 2))
        self.assertEqual(self.count("linear"), 0)
        self.assertEqual(draft["attachments"][0]["file_id"], "opaque-context")

    def test_voice_is_not_silently_consumed_as_an_answer(self):
        self.send("Задача")
        self.send(voice={"file_id": "voice"})
        self.assertEqual(self.store.current(11)["answers"], {})

    def test_owner_origin_is_not_falsely_attributed_to_sergey(self):
        for text in ["Текст", "Экран", "Сейчас", "Нужно", "Нет", "Проверить", "только документация"]:
            self.send(text, user=22)
        self.callback(user=22)
        self.drain()
        self.assertIn("от Александра (Owner)", self.linear.calls[0]["description"])

    def test_safety_classification_never_relies_on_claimed_t1_alone(self):
        draft = self.ready()
        for text in ["Удалить записи", "migrations", "updater", "auth", "Windows", "схема SQLite"]:
            draft["request"] = text
            self.assertEqual(classify(draft)[0], "T4")
        draft["request"] = "Новая функция"
        draft["answers"]["surface"] = "всё приложение"
        self.assertEqual(classify(draft)[0], "T3")
        draft["answers"]["surface"] = "локальный интерфейс"
        self.assertEqual(classify(draft)[0], "T2")

    def test_config_errors_and_transport_do_not_disclose_values(self):
        with self.assertRaises(ApiError) as error:
            config({})
        self.assertIn("SERGEY_INTAKE_BOT_TOKEN", str(error.exception))
        with patch("urllib.request.urlopen", side_effect=RuntimeError("token-in-url")):
            with self.assertRaises(ApiError) as error:
                request_json("https://invalid/token-in-url", {})
        self.assertNotIn("token-in-url", str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_api_adapters_use_expected_protocol_without_impersonating_author(self):
        draft = self.ready()
        self.callback()
        payload = json.loads(self.store.db.execute("SELECT payload FROM outbox WHERE kind='linear'").fetchone()[0])
        client = Linear("withheld", {"origin": "source-id", "T1": "tier-id"})
        result = {"id": payload["id"], "url": "https://linear.app/test/issue/TEST-1"}
        with patch.object(client, "call", return_value={"issueCreate": {"success": True, "issue": result}}) as call:
            self.assertEqual(client.create(payload), result)
        inputs = call.call_args.args[1]["input"]
        self.assertEqual(inputs["labelIds"], ["source-id", "tier-id"])
        self.assertEqual(inputs["id"], payload["id"])
        self.assertNotIn("createdBy", inputs)
        with patch.object(Telegram("withheld"), "call", side_effect=[{}, {"url": "https://webhook.invalid"}]) as call:
            bot = Telegram("withheld")
            bot.call = call
            with self.assertRaises(ApiError):
                bot.preflight()


if __name__ == "__main__":
    unittest.main()
