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
        self.assertIn("data-lightbox-zoom-in", (ROOT / "backend" / "app" / "templates" / "_lightbox.html").read_text())
        self.assertIn("data-lightbox-reset", (ROOT / "backend" / "app" / "templates" / "_lightbox.html").read_text())
        self.assertIn("pointerdown", script)
        self.assertIn("wheel", script)

    def test_legacy_rewards_has_filters_totals_and_double_click(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()

        self.assertIn("legacy-rewards-filters", legacy_template)
        self.assertIn('name="rank_id"', legacy_template)
        self.assertIn('name="name_id"', legacy_template)
        self.assertIn("legacy-totals-panel", legacy_template)
        self.assertIn("data-detail-url", legacy_template)
        self.assertIn("dblclick", script)

    def test_legacy_rewards_has_quick_person_search(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()

        self.assertIn("legacy-person-search-input", legacy_template)
        self.assertIn('autocomplete="off" data-person-quick-search', legacy_template)
        self.assertIn("data-person-name", legacy_template)
        self.assertIn("data-person-empty", legacy_template)
        self.assertIn("Ничего не найдено.", legacy_template)
        self.assertIn("toLocaleLowerCase(\"ru-RU\")", script)
        self.assertIn("name.includes(query)", script)

    def test_legacy_person_rows_do_not_have_hover_title_links(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()

        self.assertIn("<button class=\"legacy-list-row", legacy_template)
        self.assertIn('type="button" data-person-name', legacy_template)
        self.assertNotIn("legacy-list-row {% if selected_person and person.id == selected_person.id %}selected-row{% endif %}\" href=", legacy_template)

    def test_legacy_rewards_scroll_and_photo_frames_are_present(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        person_detail = (ROOT / "backend" / "app" / "templates" / "person_detail.html").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn("legacy-rewards-table-scroll", legacy_template)
        self.assertIn(".legacy-rewards-table-scroll", styles)
        self.assertIn("max-height: clamp", styles)
        self.assertIn("legacy-photo-frame", legacy_template)
        self.assertIn("legacy-photo-placeholder", legacy_template)
        self.assertIn(".legacy-photo-frame", styles)
        self.assertIn(".legacy-photo-placeholder", styles)
        self.assertIn("photo-frame", person_detail)
        self.assertIn("photo-placeholder", person_detail)
        self.assertIn(".photo-frame", styles)
        self.assertIn(".photo-placeholder", styles)

    def test_cascading_guides_preserve_changed_select_value(self) -> None:
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()
        reward_form = (ROOT / "backend" / "app" / "templates" / "reward_form.html").read_text()
        mark_form = (ROOT / "backend" / "app" / "templates" / "mark_form.html").read_text()
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "cascading_guides.js").read_text()

        self.assertIn("cascading_guides.js", base)
        self.assertIn("cascading_guides.js", legacy_base)
        self.assertIn("data-guide-cascade-options", reward_form)
        self.assertIn("data-guide-cascade-options", mark_form)
        self.assertIn("data-guide-cascade-options", legacy_template)
        self.assertIn('data-guide-role="category"', reward_form)
        self.assertIn('data-guide-role="subcategory"', reward_form)
        self.assertIn('data-guide-role="name"', reward_form)
        self.assertIn('data-guide-role="category"', mark_form)
        self.assertIn('data-guide-role="subcategory"', mark_form)
        self.assertIn('data-guide-role="name"', mark_form)
        self.assertIn('data-guide-role="category"', legacy_template)
        self.assertIn('data-guide-role="subcategory"', legacy_template)
        self.assertIn('data-guide-role="name"', legacy_template)
        self.assertIn('const selectedCategory = changedRole === "country" ? "" : category.value;', script)
        self.assertIn('const selectedSubcategory = changedRole === "country" || changedRole === "category" ? "" : subcategory.value;', script)
        self.assertIn('rebuildSelect(subcategory, rowsFor(options, "subcategory", selectedCategory), selectedSubcategory);', script)
        self.assertIn('rebuildSelect(name, rowsFor(options, "name", selectedSubcategory), selectedName);', script)

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

    def test_clipboard_paste_button_is_active_in_photo_controls(self) -> None:
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text()
        photo_management = (ROOT / "backend" / "app" / "templates" / "photo_management.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "clipboard_paste.js").read_text()

        self.assertIn("clipboard_paste.js", base)
        self.assertIn("data-clipboard-paste", photo_management)
        self.assertIn("navigator.clipboard.read", script)
        self.assertIn("/photos/upload", script)


if __name__ == "__main__":
    unittest.main()
