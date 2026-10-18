from __future__ import annotations

from contextlib import redirect_stdout
import io
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "scripts" / "generate_release_telegram_message.py"
SENDER_PATH = ROOT / "scripts" / "send_release_notification.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ReleaseNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_module("release_notification_generator_test", GENERATOR_PATH)
        self.sender = load_module("release_notification_sender_test", SENDER_PATH)
        self.config = {"REPORT_PRIMARY_CHAT_ID": "1", "REPORT_COPY_CHAT_IDS": "2",
                       "REPORT_PRIMARY_SEND_CONFIRMED": "true"}
        config_patch = patch.object(self.sender.daily, "merged_config", return_value=self.config)
        config_patch.start()
        self.addCleanup(config_patch.stop)

    def _manifest(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "version": "0.1.1",
                    "notes": [
                        "Добавили понятный статус процесса обновления",
                        "Теперь видно, что программа скачивает и устанавливает новую версию",
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def _full_manifest(self, path: Path) -> Path:
        notes = [
            "Добавили фильтры на главном экране “Награды”: теперь можно отбирать кавалеров по званию, стране, категории, подкатегории и наименованию награды",
            "Добавили итоги на главном экране: количество награждённых, количество наград, в наличии / не в наличии, общая цена покупки, текущая цена и последняя покупка",
            "Добавили двойной клик по кавалеру: теперь можно быстрее открыть карточку",
            "Сделали ссылки кликабельными: “Память народа”, “Форум коллекционеров” и другие безопасные ссылки открываются как ссылки",
            "Улучшили поиск: отключили старые подсказки браузера, добавили поиск по награждённым, наградам, знакам и номерам",
            "Пустой запрос теперь работает понятнее: если выбрать категорию “Награждённые”, “Награды” или “Знаки” и оставить поле пустым, показываются все записи выбранной категории",
            "Улучшили переходы в справочники из форм: из карточки награждённого, награды и знака открывается нужный раздел справочника, а возврат ведёт обратно в форму",
            "Исправили возврат из карточки кавалера обратно на главный экран",
            "Добавили понятный статус процесса обновления: после нажатия “Обновить” видно, что программа скачивает и устанавливает новую версию",
        ]
        path.write_text(json.dumps({"version": "0.1.1", "notes": notes}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_release_message_is_human_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._manifest(Path(tmpdir) / "latest.json")
            message = self.generator.build_message("0.1.1", manifest)
        self.assertIn("Награды и награждённые", message)
        self.assertIn("v0.1.1", message)
        self.assertIn("Откройте программу", message)
        self.assertIn("Нажмите «Обновить»", message)
        self.assertIn("Если включён автоматический перезапуск, программа откроется самостоятельно", message)
        self.assertIn("Если программа не запустилась автоматически, откройте её вручную через start_windows.bat", message)
        self.assertIn("Данные и фотографии при обновлении сохраняются", message)
        self.assertNotIn("Закройте окно запуска", message)
        self.assertNotIn("запустите start_windows.bat снова", message)
        for term in ["endpoint", "router", "repository", "commit", "hash", "GitHub Release", "ZIP"]:
            self.assertNotIn(term, message)

    def test_release_notes_fallback_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            notes = Path(tmpdir) / "0.1.1.md"
            notes.write_text("# 0.1.1\n\n- Улучшили понятность обновления.\n", encoding="utf-8")
            message = self.generator.build_message("0.1.1", release_notes=notes)
        self.assertIn("Улучшили понятность обновления", message)

    def test_release_notes_011_include_user_visible_items(self) -> None:
        notes = (ROOT / "release_notes" / "0.1.1.md").read_text(encoding="utf-8")
        for expected in ["фильтры", "итоги", "поиск", "справочник", "возврат", "обновления"]:
            self.assertIn(expected, notes)

    def test_correction_message_contains_required_user_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._full_manifest(Path(tmpdir) / "latest.json")
            message = self.generator.build_message("0.1.1", manifest, correction=True)
        self.assertIn("Уточнение", message)
        self.assertIn("Награды и награждённые", message)
        self.assertIn("v0.1.1", message)
        for expected in ["фильтры", "итоги", "поиск", "Пустой запрос", "справочники", "возврат", "статус процесса обновления"]:
            self.assertIn(expected, message)
        self.assertIn("Откройте программу", message)
        self.assertIn("Данные и фотографии при обновлении сохраняются", message)
        for term in ["endpoint", "router", "repository", "commit", "hash", "GitHub Release", "ZIP"]:
            self.assertNotIn(term, message)

    def test_missing_manifest_handled_safely(self) -> None:
        message = self.generator.build_message(
            "0.1.1",
            manifest=Path("/no/such/latest.json"),
            release_notes=Path("/no/such/0.1.1.md"),
        )
        self.assertIn("В этой версии внесены улучшения и исправления", message)

    def test_release_message_012_contains_release_instructions_and_user_items(self) -> None:
        message = self.generator.build_message("0.1.2", release_notes=ROOT / "release_notes" / "0.1.2.md")
        self.assertIn("Награды и награждённые", message)
        self.assertIn("v0.1.2", message)
        for expected in ["шахмат", "CSV", "Открыть каталог", "Архивировать", "фотограф", "PDF-буклет", "рабочий режим"]:
            self.assertIn(expected, message)
        self.assertIn("Откройте программу", message)
        self.assertIn("Нажмите «Обновить»", message)
        self.assertIn("Данные и фотографии при обновлении сохраняются", message)
        for term in ["endpoint", "router", "repository", "commit", "hash", "GitHub Release", "ZIP"]:
            self.assertNotIn(term, message)

    def test_dry_run_does_not_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._manifest(Path(tmpdir) / "latest.json")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "send_message") as send_message, \
                patch("sys.argv", ["send_release_notification.py", "--version", "0.1.1", "--manifest", str(manifest), "--dry-run"]):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()

    def test_correction_dry_run_does_not_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._full_manifest(Path(tmpdir) / "latest.json")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "send_message") as send_message, \
                patch(
                    "sys.argv",
                    [
                        "send_release_notification.py",
                        "--version",
                        "0.1.1",
                        "--manifest",
                        str(manifest),
                        "--dry-run",
                        "--correction",
                    ],
                ):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()

    def test_send_test_to_copy_only_does_not_send_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._manifest(Path(tmpdir) / "latest.json")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "resolve_token", return_value="TOKEN"), \
                patch.object(self.sender, "send_notification", return_value="77") as send_message, \
                patch.object(self.sender, "LOG_PATH", Path(tmpdir) / "release_notifications.jsonl"), \
                patch("sys.argv", ["send_release_notification.py", "--version", "0.1.1", "--send-test-to-copy-only"]):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_called_once()
        self.assertEqual(send_message.call_args.args[1], 2)

    def test_recovery_dry_run_reports_exact_artifact_without_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            recovery = Path(tmpdir) / "FedorinovRewards_Recovery_v2.0.6.zip"
            recovery.write_bytes(b"exact tested recovery")
            with patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), \
                patch.object(self.sender.daily, "send_message") as send_message, \
                patch.object(self.sender.daily, "send_document") as send_document, \
                patch(
                    "sys.argv",
                    [
                        "send_release_notification.py",
                        "--version",
                        "2.0.6",
                        "--recovery-zip",
                        str(recovery),
                        "--dry-run",
                    ],
                ):
                result = self.sender.main()
        self.assertEqual(result, 0)
        send_message.assert_not_called()
        send_document.assert_not_called()

    def test_recovery_send_uses_document_once_per_recipient_and_logs_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            recovery = root / "FedorinovRewards_Recovery_v2.0.6.zip"
            recovery.write_bytes(b"exact tested recovery")
            log = root / "release_notifications.jsonl"
            with patch.object(
                self.sender.daily,
                "merged_config",
                return_value=self.config,
            ), patch.object(self.sender.daily, "resolve_recipients", return_value=(1, [2])), patch.object(
                self.sender.daily, "resolve_token", return_value="TOKEN"
            ), patch.object(self.sender.daily, "send_message") as send_message, patch.object(
                self.sender.daily, "send_document", side_effect=["101", "102"]
            ) as send_document, patch.object(self.sender, "LOG_PATH", log), patch(
                "sys.argv",
                [
                    "send_release_notification.py",
                    "--version",
                    "2.0.6",
                    "--recovery-zip",
                    str(recovery),
                    "--send",
                ],
            ):
                result = self.sender.main()
            entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if json.loads(line)["status"] == "sent"]
            expected_sha = self.sender.hashlib.sha256(recovery.read_bytes()).hexdigest()
        self.assertEqual(result, 0)
        send_message.assert_not_called()
        self.assertEqual(send_document.call_count, 2)
        self.assertEqual(send_document.call_args_list[0].args[2], recovery.resolve())
        self.assertEqual([item["message_id"] for item in entries], ["101", "102"])
        self.assertTrue(all(item["artifact_name"] == recovery.name for item in entries))
        self.assertTrue(all(item["artifact_sha256"] == expected_sha for item in entries))


    def _deliver(self, log, side_effect, purpose="release", version="2.0.27"):
        output = io.StringIO()
        with patch.object(self.sender, "LOG_PATH", log), patch.object(
            self.sender, "send_notification", side_effect=side_effect
        ) as send, redirect_stdout(output):
            recipients = [("Sergey", 1), ("Owner", 2)] if purpose == "release" else [("Owner", 2)]
            result = self.sender.deliver(version, recipients, "unchanged release text", "TOKEN", purpose=purpose)
        return result, send, output.getvalue()

    def test_preflight_rejects_missing_ambiguous_or_same_recipient_before_network(self):
        invalid = [{}, {"REPORT_PRIMARY_CHAT_ID": "1"},
                   {"REPORT_COPY_CHAT_IDS": "2"},
                   {"REPORT_PRIMARY_CHAT_ID": "1,3", "REPORT_COPY_CHAT_IDS": "2"},
                   {"REPORT_PRIMARY_CHAT_ID": "1", "REPORT_COPY_CHAT_IDS": "2,3"},
                   {"REPORT_PRIMARY_CHAT_ID": "1", "REPORT_COPY_CHAT_IDS": "1"},
                   {"REPORT_PRIMARY_CHAT_ID": "SECRET_ID", "REPORT_COPY_CHAT_IDS": "2"}]
        for config in invalid:
            with self.subTest(config=config), patch.object(self.sender.daily, "merged_config", return_value=config), \
                    patch.object(self.sender, "send_notification") as send, \
                    patch("sys.argv", ["sender", "--version", "2.0.27", "--send"]):
                with self.assertRaises(RuntimeError) as error:
                    self.sender.main()
                self.assertNotIn("SECRET_ID", str(error.exception))
                send.assert_not_called()

    def test_copy_failure_is_partial_fail_and_retry_only_owner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger.jsonl"
            code, send, output = self._deliver(log, ["612", self.sender.DeliveryRejected()])
            self.assertEqual(code, 1)
            self.assertIn("partial FAIL", output)
            self.assertIn("Sergey: sent", output)
            self.assertIn("Owner: failed", output)
            code, send, output = self._deliver(log, ["614"])
            self.assertEqual(code, 0)
            send.assert_called_once_with("TOKEN", 2, "unchanged release text", None)
            self.assertIn("message_id=612", output)
            self.assertIn("message_id=614", output)
            code, send, _ = self._deliver(log, AssertionError("duplicate"))
            self.assertEqual(code, 0)
            send.assert_not_called()

    def test_primary_rejection_retry_only_sergey(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger.jsonl"
            self.assertEqual(self._deliver(log, [self.sender.DeliveryRejected(), "614"])[0], 1)
            code, send, _ = self._deliver(log, ["612"])
            self.assertEqual(code, 0)
            send.assert_called_once_with("TOKEN", 1, "unchanged release text", None)

    def test_uncertain_or_missing_ack_never_retries(self):
        for outcome in [TimeoutError(), RuntimeError("token must never print"), "", "0", "None"]:
            with self.subTest(outcome=type(outcome).__name__), tempfile.TemporaryDirectory() as tmpdir:
                log = Path(tmpdir) / "ledger.jsonl"
                code, _, output = self._deliver(log, ["612", outcome])
                self.assertEqual(code, 2)
                self.assertNotIn("token must never print", output)
                code, send, output = self._deliver(log, AssertionError("unsafe retry"))
                self.assertEqual(code, 2)
                send.assert_not_called()
                self.assertIn("STOP", output)

    def test_interrupted_or_legacy_failed_attempt_stops_before_any_send(self):
        for status in ["attempt_started", "failed", "uncertain", "sent", "unknown"]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                log = Path(tmpdir) / "ledger.jsonl"
                log.write_text(json.dumps({"version": "v2.0.27", "recipient_id": 2, "status": status}) + "\n")
                code, send, _ = self._deliver(log, AssertionError("unsafe send"))
                self.assertEqual(code, 2)
                send.assert_not_called()

    def test_existing_legacy_success_deduplicates_by_version_and_recipient_not_role(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger.jsonl"
            log.write_text("\n".join(json.dumps({"version": "v2.0.27", "recipient_id": rid,
                "recipient_role": "legacy", "status": "sent", "message_id": mid})
                for rid, mid in [(1, "612"), (2, "614")]) + "\n")
            code, send, _ = self._deliver(log, AssertionError("duplicate"))
            self.assertEqual(code, 0)
            send.assert_not_called()
            code, send, _ = self._deliver(log, ["700", "701"], version="2.0.28")
            self.assertEqual(code, 0)
            self.assertEqual(send.call_count, 2)

    def test_identity_test_is_separate_and_cannot_repeat_for_another_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger.jsonl"
            self.assertEqual(self._deliver(log, ["800"], purpose="owner_identity_test")[0], 0)
            code, send, _ = self._deliver(log, AssertionError("second test"),
                                        purpose="owner_identity_test", version="2.0.28")
            self.assertEqual(code, 0)
            send.assert_not_called()
            code, send, _ = self._deliver(log, ["801", "802"])
            self.assertEqual(code, 0)
            self.assertEqual(send.call_count, 2)

    def test_corrupt_ledger_or_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger.jsonl"
            log.write_text('{"truncated":')
            with self.assertRaises(RuntimeError):
                self._deliver(log, AssertionError("send"))
            log.unlink()
            log.with_name(log.name + ".lock").mkdir()
            with self.assertRaises(RuntimeError):
                self._deliver(log, AssertionError("send"))

    def test_journal_intent_exists_before_network_and_log_failure_prevents_send(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger.jsonl"
            def acknowledged(*args):
                entries = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertEqual(entries[-1]["status"], "attempt_started")
                return "900"
            self.assertEqual(self._deliver(log, acknowledged)[0], 0)
            with patch.object(self.sender, "append_log", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    self._deliver(log, AssertionError("send"), version="2.0.28")

    def test_identity_test_content_is_neutral(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(self.sender, "LOG_PATH", Path(tmpdir) / "log"), \
                patch.object(self.sender.daily, "resolve_token", return_value="TOKEN"), \
                patch.object(self.sender, "send_notification", return_value="901") as send, \
                patch("sys.argv", ["sender", "--version", "2.0.27", "--send-test-to-copy-only"]):
            self.assertEqual(self.sender.main(), 0)
            send.assert_called_once()
            self.assertEqual(send.call_args.args[1], 2)
            self.assertIn("Нейтральная проверка связи", send.call_args.args[2])
            self.assertNotIn("2.0.27", send.call_args.args[2])
            self.assertIsNone(send.call_args.args[3])

    def test_api_ack_requires_ok_positive_id_and_matching_chat(self):
        cases = [({"ok": True, "result": {"message_id": 123, "chat": {"id": 2}}}, None),
                 ({"ok": False, "error_code": 403}, self.sender.DeliveryRejected),
                 ({"ok": False, "error_code": 500}, RuntimeError),
                 ({"ok": True, "result": {"message_id": 123, "chat": {"id": 1}}}, RuntimeError),
                 ({"ok": True, "result": {"chat": {"id": 2}}}, RuntimeError)]
        for data, error in cases:
            with self.subTest(data=data), patch.object(self.sender.urllib.request, "urlopen") as open_request:
                open_request.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
                if error:
                    with self.assertRaises(error):
                        self.sender.send_notification("TOKEN", 2, "text", None)
                else:
                    self.assertEqual(self.sender.send_notification("TOKEN", 2, "text", None), "123")

    def test_http_rejection_vs_proxy_server_and_timeout(self):
        for status, body, expected in [(403, b'{"ok":false,"error_code":403}', self.sender.DeliveryRejected),
                                       (502, b'{"ok":false,"error_code":502}', RuntimeError),
                                       (403, b'proxy error', RuntimeError)]:
            with self.subTest(status=status), patch.object(self.sender.urllib.request, "urlopen",
                    side_effect=urllib.error.HTTPError("SECRET_URL", status, "error", {}, io.BytesIO(body))):
                with self.assertRaises(expected) as error:
                    self.sender.send_notification("TOKEN", 2, "text", None)
                self.assertNotIn("SECRET", str(error.exception))


    def test_http_integration_partial_failure_retry_and_repeat_on_temp_ledger(self):
        requests = []
        replies = [(200, {"ok": True, "result": {"message_id": 612, "chat": {"id": 1}}}),
                   (403, {"ok": False, "error_code": 403}),
                   (200, {"ok": True, "result": {"message_id": 614, "chat": {"id": 2}}})]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                requests.append(self.rfile.read(int(self.headers["Content-Length"])).decode())
                status, data = replies.pop(0)
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        real_open = self.sender.urllib.request.urlopen
        def local_open(request, timeout):
            local_request = self.sender.urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/sendMessage", data=request.data, method="POST")
            return real_open(local_request, timeout=timeout)
        try:
            with tempfile.TemporaryDirectory() as tmpdir, patch.object(
                    self.sender, "LOG_PATH", Path(tmpdir) / "ledger.jsonl"), patch.object(
                    self.sender.urllib.request, "urlopen", side_effect=local_open), redirect_stdout(io.StringIO()):
                self.assertEqual(self.sender.deliver("2.0.27", [("Sergey", 1), ("Owner", 2)], "release", "FAKE"), 1)
                self.assertEqual(self.sender.deliver("2.0.27", [("Sergey", 1), ("Owner", 2)], "release", "FAKE"), 0)
                self.assertEqual(self.sender.deliver("2.0.27", [("Sergey", 1), ("Owner", 2)], "release", "FAKE"), 0)
            self.assertEqual(len(requests), 3)
            self.assertEqual([self.sender.urllib.parse.parse_qs(body)["chat_id"] for body in requests],
                             [["1"], ["2"], ["2"]])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_uncertain_primary_reports_owner_pending_and_stops(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            code, send, output = self._deliver(Path(tmpdir) / "ledger", [TimeoutError()])
            self.assertEqual(code, 2)
            send.assert_called_once()
            self.assertIn("Sergey: uncertain", output)
            self.assertIn("Owner: pending", output)

    def test_ack_log_failure_leaves_uncertain_intent_and_never_resends(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger"
            append = self.sender.append_log
            def broken_append(*args, **kwargs):
                if args[3] == "sent":
                    raise OSError("disk full after API success")
                return append(*args, **kwargs)
            with patch.object(self.sender, "append_log", side_effect=broken_append):
                with self.assertRaises(OSError):
                    self._deliver(log, ["612"])
            code, send, _ = self._deliver(log, AssertionError("resend after journal failure"))
            self.assertEqual(code, 2)
            send.assert_not_called()

    def test_legacy_test_copy_never_counts_as_release_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ledger"
            log.write_text(json.dumps({"version": "2.0.27", "recipient_id": 2,
                                     "status": "sent_test_copy_only", "message_id": "600"}) + "\n")
            code, send, _ = self._deliver(log, ["612", "614"])
            self.assertEqual(code, 0)
            self.assertEqual(send.call_count, 2)


if __name__ == "__main__":
    unittest.main()
