from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BrowserSaveAsTests(unittest.TestCase):
    def test_save_as_js_uses_file_system_access_api_and_fallback(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        self.assertIn("showSaveFilePicker", source)
        self.assertIn("openSaveFilePicker", source)
        self.assertIn("fallbackDownload", source)
        self.assertIn("Ваш браузер не поддерживает выбор места сохранения", source)
        self.assertIn("Файл сохранён.", source)
        self.assertIn("fetch(url, options)", source)
        self.assertIn("Не удалось открыть окно сохранения. Попробуйте обычную загрузку файла или другой браузер.", source)
        self.assertIn('form.getAttribute("data-save-as-success-message")', source)
        self.assertIn("Открыть копию файла", source)

    def test_file_picker_is_opened_before_fetch_to_keep_user_gesture(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        submit_handler = source.split('document.addEventListener("submit"', 1)[1]
        picker_index = submit_handler.index("fileHandle = await openSaveFilePicker")
        save_index = submit_handler.index("await saveResponse")
        fetch_index = source.index("const response = await fetch")
        picker_definition_index = source.index("return await window.showSaveFilePicker")
        self.assertLess(picker_index, save_index)
        self.assertLess(picker_definition_index, fetch_index)

    def test_user_gesture_error_is_not_shown_as_raw_user_message(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        self.assertIn("Must be handling a user gesture", source)
        self.assertIn("console.warn", source)
        self.assertIn("Не удалось открыть окно сохранения. Попробуйте обычную загрузку файла или другой браузер.", source)
        self.assertNotIn("setMessage(form, error && error.message ? error.message : \"Не удалось открыть окно сохранения", source)

    def test_fallback_download_creates_link_and_clicks_it(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        fallback = source.split("function fallbackDownload", 1)[1].split("function requestFromForm", 1)[0]
        self.assertIn('document.createElement("a")', fallback)
        self.assertIn("link.download = filename || \"download\"", fallback)
        self.assertIn("document.body.appendChild(link)", fallback)
        self.assertIn("link.click()", fallback)
        self.assertIn("URL.revokeObjectURL(url)", fallback)

    def test_save_as_success_is_compact_and_does_not_offer_a_second_download(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        actions = (ROOT / "backend" / "app" / "templates" / "_person_file_actions.html").read_text(encoding="utf-8")
        self.assertIn("function showSavedMessage(form, blob, filename, mode)", source)
        self.assertIn('data-save-as-success-message="Архив сохранён."', actions)
        custom_branch = source.split('const customMessage = form.getAttribute("data-save-as-success-message")', 1)[1]
        custom_branch = custom_branch.split('if (mode === "fallback")', 1)[0]
        self.assertIn('setMessage(form, customMessage, "success")', custom_branch)
        self.assertIn('form.getAttribute("data-save-as-open-copy") === "true"', custom_branch)
        self.assertIn("appendOpenCopyLink(form, blob, filename)", custom_branch)
        self.assertIn("return;", custom_branch)
        self.assertNotIn("data-save-as-open-copy", actions)
        self.assertNotIn("Открыть папку", source)
        self.assertEqual(source.count("link.click()"), 1)

    def test_missing_file_system_access_api_starts_blob_download(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        submit_handler = source.split('document.addEventListener("submit"', 1)[1]
        unsupported_branch = submit_handler.split('if (!("showSaveFilePicker" in window))', 1)[1].split("const pickerMimeType", 1)[0]
        self.assertIn("event.preventDefault()", submit_handler)
        self.assertIn("await downloadWithFallback(form, request, pickerFilename)", unsupported_branch)
        self.assertIn("fallbackDownload(blob, filename)", source)
        self.assertNotIn("window.alert", unsupported_branch)

    def test_picker_abort_is_cancel_only_after_observable_dialog_interaction(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        submit_handler = source.split('document.addEventListener("submit"', 1)[1]
        classifier = source.split("function pickerAbortWasExplicitCancel", 1)[1].split(
            "async function writeFileHandle", 1
        )[0]
        self.assertIn('error.name !== "AbortError"', classifier)
        self.assertIn("observation.browserLostFocus", classifier)
        self.assertIn("observation.pageWasHidden", classifier)
        self.assertIn("observation.elapsedMs >= 500", classifier)
        self.assertIn("pickerAbortWasExplicitCancel(error, pickerObservation)", submit_handler)
        self.assertIn('setMessage(form, "Сохранение отменено.", "cancel")', submit_handler)
        self.assertIn("await downloadWithFallback(form, request, pickerFilename)", submit_handler)
        self.assertIn("await downloadAfterPickerFailure(form, request, pickerFilename)", submit_handler)
        self.assertIn('return extensionFromFilename(filename) === ".zip" ? "ZIP" : "Файл"', source)

    def test_invalid_picker_handle_falls_back_without_reporting_cancel(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        submit_handler = source.split('document.addEventListener("submit"', 1)[1]
        invalid_handle_branch = submit_handler.split(
            'if (!fileHandle || typeof fileHandle.createWritable !== "function")', 1
        )[1].split('setMessage(form, "Подготовка файла', 1)[0]
        self.assertIn("await downloadAfterPickerFailure(form, request, pickerFilename)", invalid_handle_branch)
        self.assertNotIn("Сохранение отменено.", invalid_handle_branch)

    def test_save_as_js_is_loaded_in_base_and_legacy_layouts(self) -> None:
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text(encoding="utf-8")
        booklet = (ROOT / "backend" / "app" / "templates" / "person_booklet.html").read_text(encoding="utf-8")
        self.assertIn("save_as.js", base)
        self.assertIn("save_as.js", legacy_base)
        self.assertIn("save_as.js", booklet)

    def test_archive_button_uses_browser_save_as_zip_route(self) -> None:
        actions = (ROOT / "backend" / "app" / "templates" / "_person_file_actions.html").read_text(encoding="utf-8")
        self.assertIn('action="/persons/{{ person.id }}/archive-folder.zip" data-save-as-form', actions)
        self.assertIn('data-save-as-filename="{{ archive_filename }}"', actions)
        self.assertIn('data-save-as-mime="application/zip"', actions)
        self.assertIn("Архивировать", actions)


if __name__ == "__main__":
    unittest.main()
