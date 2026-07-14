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
        self.assertIn("Файл скачан. Браузер не передаёт приложению путь папки загрузок", source)
        self.assertIn("Файл сохранён. Браузер не передаёт приложению путь выбранной папки", source)
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

    def test_save_as_success_offers_open_copy_link_without_promising_folder_open(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        self.assertIn("function appendOpenCopyLink", source)
        self.assertIn("save-as-open-copy-link", source)
        self.assertIn('link.target = "_blank"', source)
        self.assertIn("showSavedMessage(form, result.blob, result.filename, \"picker\")", source)
        self.assertIn("Браузер не передаёт приложению путь выбранной папки", source)
        self.assertIn("не разрешает открыть её автоматически", source)
        self.assertIn("откройте файл из выбранной папки вручную или используйте ссылку “Открыть копию файла”", source)
        self.assertNotIn("Открыть папку", source)
        self.assertNotIn("Папка открыта", source)

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
        legacy = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text(encoding="utf-8")
        self.assertIn('action="/persons/{{ selected_person.id }}/archive-folder.zip" data-save-as-form', legacy)
        self.assertIn('data-save-as-filename="{{ selected_person_archive_filename }}"', legacy)
        self.assertIn('data-save-as-mime="application/zip"', legacy)
        self.assertIn("Архивировать", legacy)


if __name__ == "__main__":
    unittest.main()
