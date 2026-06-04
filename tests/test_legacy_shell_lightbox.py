from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LegacyShellLightboxTests(unittest.TestCase):
    def test_legacy_template_uses_dedicated_shell(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()

        self.assertIn('{% extends "legacy_base.html" %}', legacy_template)
        self.assertIn("legacy-tabs", legacy_base)
        self.assertNotIn("Dashboard", legacy_base)
        self.assertNotIn("Health", legacy_base)
        self.assertNotIn("topbar", legacy_base)

    def test_lightbox_is_loaded_by_base_layouts(self) -> None:
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "lightbox.js").read_text()

        self.assertIn('{% include "_lightbox.html" %}', base)
        self.assertIn('{% include "_lightbox.html" %}', legacy_base)
        self.assertIn("event.preventDefault()", script)
        self.assertIn("Escape", script)


if __name__ == "__main__":
    unittest.main()
