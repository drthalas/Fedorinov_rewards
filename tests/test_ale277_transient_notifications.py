from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
import asyncio
import json
import subprocess
import unittest
from unittest.mock import patch

from starlette.datastructures import FormData, UploadFile

from backend.app.routers import photos as photos_router
from backend.app.routers.templates import templates
from backend.app.services.media_lifecycle import MediaCleanupResult
from backend.app.services.notifications import (
    ATTENTION_TIMEOUT_MS,
    SUCCESS_TIMEOUT_MS,
    status_notification,
    transient_notifications,
)
from backend.app.services.photos import PhotoMutationResult


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, query_params: dict[str, str] | None = None):
        self.query_params = query_params or {}


class FakeMultipartRequest:
    def __init__(self, values: list[tuple[str, object]]):
        self._form = FormData(values)

    async def form(self) -> FormData:
        return self._form


class FakeUrlencodedRequest:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class Ale277TransientNotificationTests(unittest.TestCase):
    def test_entity_statuses_are_semantic_and_timed_by_kind(self) -> None:
        cases = {
            "person_updated": ("Кавалер сохранён.", "success", SUCCESS_TIMEOUT_MS),
            "person_deleted": ("Кавалер удалён.", "success", SUCCESS_TIMEOUT_MS),
            "person_delete_blocked": (
                "Нельзя безопасно удалить кавалера: обнаружены внешние ссылки или неоднозначные материалы.",
                "error",
                ATTENTION_TIMEOUT_MS,
            ),
            "reward_updated": ("Награда сохранена.", "success", SUCCESS_TIMEOUT_MS),
            "mark_updated": ("Знак сохранён.", "success", SUCCESS_TIMEOUT_MS),
            "media_cleanup_failed": (
                "Изменения сохранены, но старый файл не удалось удалить. Проверьте журнал приложения.",
                "warning",
                ATTENTION_TIMEOUT_MS,
            ),
            "rank_delete_used": (
                "Нельзя удалить: это звание используется в карточках кавалеров.",
                "error",
                ATTENTION_TIMEOUT_MS,
            ),
            "guide_delete_media_blocked": (
                "Нельзя безопасно удалить элемент справочника: проверьте связанные материалы.",
                "error",
                ATTENTION_TIMEOUT_MS,
            ),
        }
        for marker, expected in cases.items():
            with self.subTest(marker=marker):
                spec = status_notification(marker)
                self.assertIsNotNone(spec)
                self.assertEqual((spec.message, spec.kind, spec.timeout_ms), expected)

    def test_status_created_message_and_cleanup_warning_become_toasts(self) -> None:
        status = transient_notifications(FakeRequest({"status": "person_updated"}))
        created = transient_notifications(
            FakeRequest({"created": "1", "return_to": "/legacy?tab=rewards"}),
            created_message="Кавалер создан.",
        )
        cleanup = transient_notifications(
            FakeRequest({"status": "photo_updated", "media_cleanup": "failed"})
        )

        self.assertEqual(status[0]["message"], "Кавалер сохранён.")
        self.assertEqual(status[0]["query_keys"], ("status",))
        self.assertEqual(created[0]["query_keys"], ("created",))
        self.assertEqual(cleanup[0]["kind"], "warning")
        self.assertEqual(cleanup[0]["query_keys"], ("media_cleanup", "status"))
        self.assertEqual(len(cleanup), 1)

    def test_message_kinds_and_permanent_information_are_distinct(self) -> None:
        cancelled = transient_notifications(FakeRequest({"message": "Сохранение CSV отменено."}), message="Сохранение CSV отменено.")
        failed = transient_notifications(FakeRequest({"error": "Ошибка"}), error_message="Не удалось сохранить файл.")
        permanent = transient_notifications(FakeRequest({"message": "pdf_not_implemented"}), message="pdf_not_implemented")

        self.assertEqual(cancelled[0]["kind"], "warning")
        self.assertEqual(cancelled[0]["timeout_ms"], ATTENTION_TIMEOUT_MS)
        self.assertEqual(failed[0]["kind"], "error")
        self.assertEqual(failed[0]["query_keys"], ("error",))
        self.assertEqual(permanent, [])
        self.assertEqual(transient_notifications(FakeRequest()), [])

    def test_photo_upload_clear_and_cleanup_warning_set_one_shot_markers(self) -> None:
        upload = UploadFile(file=BytesIO(b"image"), filename="photo.jpg")
        upload_request = FakeMultipartRequest(
            [
                ("entity_type", "person"),
                ("entity_id", "77"),
                ("photo_field", "person_foto"),
                ("return_to", "/persons/77/edit?focus=photos&open=main"),
                ("file", upload),
            ]
        )
        with (
            patch.object(photos_router, "get_settings", return_value=object()),
            patch.object(
                photos_router,
                "save_photo_with_result",
                return_value=PhotoMutationResult("Source/77/photo.jpg", MediaCleanupResult("deleted")),
            ),
        ):
            response = asyncio.run(photos_router.photo_upload(upload_request))
        self.assertEqual(
            response.headers["location"],
            "/persons/77/edit?focus=photos&open=main&status=photo_updated",
        )

        clear_request = FakeUrlencodedRequest(
            "entity_type=person&entity_id=77&photo_field=person_foto&return_to=%2Fpersons%2F77%2Fedit%3Ffocus%3Dphotos"
        )
        with (
            patch.object(photos_router, "get_settings", return_value=object()),
            patch.object(
                photos_router,
                "clear_photo_with_result",
                return_value=PhotoMutationResult(None, MediaCleanupResult("failed")),
            ),
        ):
            response = asyncio.run(photos_router.photo_clear(clear_request))
        self.assertEqual(
            response.headers["location"],
            "/persons/77/edit?focus=photos&media_cleanup=failed",
        )

    def test_shared_partial_has_accessible_close_and_correct_roles(self) -> None:
        template = templates.env.get_template("_transient_notifications.html")
        success = template.render(request=FakeRequest({"status": "person_updated"}))
        warning = template.render(request=FakeRequest({"media_cleanup": "failed"}))

        self.assertIn('data-app-toast-timeout="4000"', success)
        self.assertIn('role="status"', success)
        self.assertIn('aria-label="Закрыть уведомление"', success)
        self.assertIn('data-app-toast-query-keys="status"', success)
        self.assertIn('data-app-toast-timeout="8000"', warning)
        self.assertIn('role="alert"', warning)

    def test_url_cleanup_preserves_navigation_state_and_fragment(self) -> None:
        script_path = ROOT / "backend/app/static/transient_notifications.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const callbacks = [];
const closeListeners = [];
const toast = {
  dataset: { appToastQueryKeys: "status,media_cleanup", appToastTimeout: "8000" },
  querySelector: () => ({ addEventListener: (_name, callback) => closeListeners.push(callback) }),
  classList: { add: () => {} },
  remove: () => {},
};
global.window = {
  location: { href: "http://127.0.0.1/guides?status=guide_updated&media_cleanup=failed&page=3&filter=ussr&return_to=%2Flegacy%3Ftab%3Drewards&focus=l3-7&open=l0-1%2Cl1-2#guide-tree" },
  history: { state: { keep: true }, replaceState: (_state, _title, url) => { global.cleaned = url; } },
  setTimeout: (callback, delay) => { callbacks.push({ callback, delay }); return callbacks.length; },
  clearTimeout: () => {},
};
global.document = {
  readyState: "complete",
  querySelectorAll: () => [toast],
  addEventListener: () => {},
};
eval(source);
process.stdout.write(JSON.stringify({ cleaned: global.cleaned, timeout: callbacks[0].delay, closeBound: closeListeners.length }));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "notification_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["cleaned"],
            "/guides?page=3&filter=ussr&return_to=%2Flegacy%3Ftab%3Drewards&focus=l3-7&open=l0-1%2Cl1-2#guide-tree",
        )
        self.assertEqual(result["timeout"], ATTENTION_TIMEOUT_MS)
        self.assertEqual(result["closeBound"], 1)

    def test_all_shells_use_shared_overlay_and_old_flow_notices_are_removed(self) -> None:
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")
        guides = (ROOT / "backend/app/templates/guides.html").read_text(encoding="utf-8")
        person = (ROOT / "backend/app/templates/person_detail.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('_transient_notifications.html', base)
        self.assertIn('_transient_notifications.html', legacy_base)
        self.assertIn('transient_notifications.js', base)
        self.assertIn('transient_notifications.js', legacy_base)
        self.assertNotIn("data-guide-toast", guides)
        self.assertNotIn("notice notice-success\">{{ status_message }}", person)
        self.assertIn(".app-toast-region", styles)
        self.assertIn("position: fixed", styles)
        self.assertIn("pointer-events: none", styles)

    def test_static_information_and_validation_notices_remain_inline(self) -> None:
        legacy = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        person_form = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")

        self.assertIn("PDF export будет реализован позже", legacy)
        self.assertIn("Редактирование выключено", legacy)
        self.assertIn('<section class="notice notice-error">{{ error }}</section>', person_form)


if __name__ == "__main__":
    unittest.main()
