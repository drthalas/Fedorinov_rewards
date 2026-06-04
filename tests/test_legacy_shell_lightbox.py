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

    def test_legacy_rewards_has_filters_totals_and_double_click(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()

        self.assertIn("legacy-rewards-filters", legacy_template)
        self.assertIn('name="rank_id"', legacy_template)
        self.assertIn('name="name_id"', legacy_template)
        self.assertIn("legacy-totals-panel", legacy_template)
        self.assertIn("data-detail-url", legacy_template)
        self.assertIn("dblclick", script)

    def test_escape_back_script_is_loaded_on_forms(self) -> None:
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()
        person_form = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text()
        reward_form = (ROOT / "backend" / "app" / "templates" / "reward_form.html").read_text()
        mark_form = (ROOT / "backend" / "app" / "templates" / "mark_form.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "escape_back.js").read_text()

        self.assertIn("escape_back.js", base)
        self.assertIn("escape_back.js", legacy_base)
        self.assertIn("data-escape-back", person_form)
        self.assertIn("data-escape-back", reward_form)
        self.assertIn("data-escape-back", mark_form)
        self.assertIn(".photo-lightbox.is-open", script)


if __name__ == "__main__":
    unittest.main()
