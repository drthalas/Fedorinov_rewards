from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BrowserSaveAsTests(unittest.TestCase):
    def test_save_as_js_uses_file_system_access_api_and_fallback(self) -> None:
        source = (ROOT / "backend" / "app" / "static" / "save_as.js").read_text(encoding="utf-8")
        self.assertIn("showSaveFilePicker", source)
        self.assertIn("fallbackDownload", source)
        self.assertIn("Ваш браузер не поддерживает выбор места сохранения", source)
        self.assertIn("Файл сохранён.", source)
        self.assertIn("fetch(url, options)", source)

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
        self.assertIn("Архивировать", legacy)


if __name__ == "__main__":
    unittest.main()
