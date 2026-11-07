import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.sergey_intake import Intake, Store, analysis_one
from scripts.sergey_analyst import AnalysisError, CodexAnalyst, validate_result


def ready():
    return {"title": "Исправить опечатку в справке", "screen": "Справка, тестовый абзац",
            "actual": "Написано нагрд", "expected": "Написать наград", "scope": ["Один тестовый абзац"],
            "acceptance": ["В абзаце видно слово наград"], "frozen": ["Остальные абзацы"],
            "surface": "только документация", "tier": "T1", "tier_reason": "Изменение только документации",
            "ready": True, "questions": [], "image_observations": []}


class FakeEngine:
    def __init__(self, result=None):
        self.result = result or ready()
        self.inputs = []

    def analyze(self, draft):
        self.inputs.append(copy.deepcopy(draft))
        return draft, copy.deepcopy(self.result)


class ContextualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "intake.sqlite3")
        self.intake = Intake(self.store, 11, 22, contextual=True)
        self.seq = 0

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def send(self, text=None, user=22, **fields):
        self.seq += 1
        message = {"message_id": self.seq, "from": {"id": user},
                   "chat": {"id": user, "type": "private"}, **fields}
        if text is not None:
            message["text"] = text
        update = {"update_id": self.seq, "message": message}
        self.intake.process(update)
        return update

    def callback(self, draft, action="create"):
        self.seq += 1
        self.intake.process({"update_id": self.seq, "callback_query": {"id": str(self.seq), "from": {"id": 22},
            "message": {"message_id": 100, "chat": {"id": 22, "type": "private"}},
            "data": f"{action}:{draft['id']}:{draft['revision']}"}})

    def linear_count(self):
        return self.store.db.execute("SELECT count(*) FROM outbox WHERE kind='linear'").fetchone()[0]

    def test_full_context_proposal_still_requires_real_confirmation(self):
        update = self.send("TEST/ALE-528: исправить опечатку в справке, остальные абзацы frozen")
        self.intake.process(update)
        engine = FakeEngine()
        self.assertTrue(analysis_one(self.store, engine))
        self.assertEqual(self.store.current(22)["state"], "summary")
        self.assertEqual(self.linear_count(), 0)
        self.assertFalse(analysis_one(self.store, engine))
        self.callback(self.store.current(22))
        self.callback(self.store.current(22))
        self.assertEqual(self.linear_count(), 1)
        payload = json.loads(self.store.db.execute("SELECT payload FROM outbox WHERE kind='linear'").fetchone()[0])
        self.assertIn("TEST/ALE-528", payload["title"])
        self.assertIn("Scope:", payload["description"])
        self.assertIn("Александра (Owner)", payload["description"])

    def test_only_missing_questions_and_correction_keep_history(self):
        result = ready(); result.update(ready=False, questions=["Какой абзац нужно сохранить?"])
        self.send("Поменять текст справки")
        engine = FakeEngine(result)
        analysis_one(self.store, engine)
        self.assertEqual(self.store.current(22)["state"], "asking")
        self.send("Сохранить остальные абзацы")
        engine.result = ready()
        analysis_one(self.store, engine)
        self.assertEqual(len(engine.inputs[-1]["sources"]), 2)
        self.assertEqual(engine.inputs[-1]["analysis"]["questions"], ["Какой абзац нужно сохранить?"])
        old = copy.deepcopy(self.store.current(22))
        self.send("Уточнение: исправить только заголовок")
        self.callback(old)
        self.assertEqual(self.linear_count(), 0)
        analysis_one(self.store, engine)
        self.callback(old)
        self.assertEqual(self.linear_count(), 0)
        self.callback(self.store.current(22))
        self.assertEqual(self.linear_count(), 1)

    def test_stale_model_result_cannot_overwrite_new_revision(self):
        self.send("Первоначальная задача")
        engine = FakeEngine()
        def concurrent_change(draft):
            self.send("Изменённое требование")
            return draft, ready()
        with patch.object(engine, "analyze", side_effect=concurrent_change):
            analysis_one(self.store, engine)
        self.assertEqual(self.store.current(22)["state"], "analyzing")
        self.assertEqual(self.store.db.execute("SELECT status FROM analysis_jobs ORDER BY rowid").fetchone()[0], "superseded")
        analysis_one(self.store, engine)
        self.assertEqual(self.store.current(22)["state"], "summary")

    def test_cancel_during_model_run_prevents_late_proposal(self):
        self.send("Задача")
        def cancel(draft):
            self.send("/cancel")
            return draft, ready()
        with patch.object(FakeEngine(), "analyze", side_effect=cancel) as call:
            engine = FakeEngine(); engine.analyze = call
            analysis_one(self.store, engine)
        self.assertEqual(self.store.current(22)["state"], "cancelled")
        self.assertEqual(self.linear_count(), 0)

    def test_model_failure_has_bounded_explicit_retry_and_no_issue(self):
        self.send("Постановка")
        engine = FakeEngine()
        with patch.object(engine, "analyze", side_effect=AnalysisError("codex_model_not_supported")):
            analysis_one(self.store, engine)
            self.assertEqual(self.store.current(22)["state"], "analysis_failed")
            self.send("/retry")
            analysis_one(self.store, engine)
            self.send("/retry")
            self.assertFalse(analysis_one(self.store, engine))
        self.assertEqual(self.store.db.execute("SELECT attempts FROM analysis_jobs").fetchone()[0], 2)
        self.assertEqual(self.linear_count(), 0)

    def test_interrupted_read_only_analysis_recovers_once(self):
        self.send("Постановка")
        engine = FakeEngine()
        with patch.object(engine, "analyze", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                analysis_one(self.store, engine)
        self.store.recover_analysis()
        analysis_one(self.store, engine)
        self.assertEqual(self.store.current(22)["state"], "summary")
        self.assertEqual(self.store.db.execute("SELECT attempts FROM analysis_jobs").fetchone()[0], 2)

    def test_allowlist_and_size_limits_apply_before_media_processing(self):
        self.send(user=99, voice={"file_id": "not-for-processing", "duration": 3})
        self.send(voice={"file_id": "too-long", "duration": 181})
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM analysis_jobs").fetchone()[0], 0)
        self.send(caption="TEST/ALE-528 synthetic voice", voice={"file_id": "voice", "duration": 5})
        self.assertEqual(self.store.current(22)["sources"][0]["media"]["kind"], "voice")

    def test_code_risk_guard_can_raise_model_tier(self):
        self.send("Удалить записи SQLite")
        analysis_one(self.store, FakeEngine())
        self.assertEqual(self.store.current(22)["tier"], "T4")

    def test_incomplete_and_malformed_model_contracts_fail_closed(self):
        for value in [{}, {**ready(), "ready": "true"}, {**ready(), "acceptance": []},
                      {**ready(), "ready": False, "questions": []}, {**ready(), "title": "bad\u200b§§§§"}]:
            with self.assertRaises(AnalysisError):validate_result(value)

    def test_media_download_rejects_path_traversal_without_network(self):
        engine = CodexAnalyst(Path(__file__).resolve().parents[1], Path(self.temp.name) / "private", None)
        class FakeTelegram:
            token = "not-real"
            def call(self, method, payload):return {"file_path": "../sensitive"}
        engine.telegram = FakeTelegram()
        with self.assertRaisesRegex(AnalysisError, "invalid_attachment_path"):
            engine.download("test", {"message_id": 1, "media": {"file_id": "opaque", "kind": "photo"}})

    def test_image_and_transcription_evidence_come_from_real_attachment_pipeline(self):
        folder = Path(self.temp.name)
        image = folder / "image.jpg"; image.write_bytes(b"\xff\xd8fake image")
        audio = folder / "audio.ogg"; audio.write_bytes(b"audio fixture")
        engine = CodexAnalyst(Path(__file__).resolve().parents[1], folder / "private", None)
        draft = {"id": "test", "sources": [
            {"message_id": 1, "text": "picture", "media": {"kind": "photo", "file_id": "image"}},
            {"message_id": 2, "text": "voice", "caption": "synthetic", "media": {"kind": "voice", "file_id": "audio"}}]}
        with patch.object(engine, "download", side_effect=[image, audio]), patch.object(engine, "transcribe", return_value={"text": "Из вложения", "engine": "whisper.cpp"}):
            prepared, images = engine.prepare(draft)
        self.assertEqual(images, [image])
        self.assertIn("Из вложения", prepared["sources"][1]["text"])
        self.assertNotIn("transcription", draft["sources"][1])


if __name__ == "__main__":
    unittest.main()
