from pathlib import Path
import re
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

    def test_legacy_rewards_person_list_is_keyboard_focusable(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn('class="legacy-list" tabindex="0" role="listbox" aria-label="Список кавалеров" data-person-list', legacy_template)
        self.assertIn('role="option"', legacy_template)
        self.assertIn('aria-selected="{{ \'true\' if selected_person and person.id == selected_person.id else \'false\' }}"', legacy_template)
        self.assertIn(".legacy-list:focus", styles)
        self.assertIn(".legacy-list-row:focus", styles)

    def test_legacy_rewards_person_list_keyboard_navigation(self) -> None:
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()

        self.assertIn("handlePersonListKeydown", script)
        self.assertIn('event.key === "ArrowDown"', script)
        self.assertIn('event.key === "ArrowUp"', script)
        self.assertIn('event.key === "PageDown"', script)
        self.assertIn('event.key === "PageUp"', script)
        self.assertIn('event.key === "Home"', script)
        self.assertIn('event.key === "End"', script)
        self.assertIn("navigateByOffset(1)", script)
        self.assertIn("navigateByOffset(-1)", script)
        self.assertIn("navigateByOffset(pageStep())", script)
        self.assertIn("navigateByOffset(-pageStep())", script)
        self.assertIn('navigateToEdge("start")', script)
        self.assertIn('navigateToEdge("end")', script)
        self.assertIn("event.preventDefault()", script)
        self.assertIn("personList.addEventListener(\"keydown\", handlePersonListKeydown)", script)

    def test_legacy_rewards_typeahead_searches_person_names(self) -> None:
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()

        self.assertIn("typeaheadBuffer", script)
        self.assertIn("typeaheadNavigateTimer", script)
        self.assertIn("handleTypeahead", script)
        self.assertIn("event.key.length !== 1", script)
        self.assertIn("typeaheadBuffer += key", script)
        self.assertIn("startsWith(query)", script)
        self.assertIn("scheduleTypeaheadNavigation(match)", script)
        self.assertIn("window.setTimeout(() =>", script)
        self.assertIn("}, 900)", script)
        self.assertIn("}, 260)", script)
        self.assertIn('replace(/ё/g, "е")', script)

    def test_legacy_rewards_navigation_ignores_form_inputs(self) -> None:
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()

        self.assertIn("isTextInputTarget", script)
        self.assertIn('target.closest("input, textarea, select, [contenteditable=\'true\']")', script)
        self.assertIn("if (isTextInputTarget(event.target))", script)

    def test_legacy_selected_person_scrolls_into_view(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()

        self.assertIn("data-selected-person-row", legacy_template)
        self.assertIn("data-person-list", legacy_template)
        self.assertIn('document.querySelector("[data-selected-person-row]")', script)
        self.assertIn('document.querySelector("[data-person-list]")', script)
        self.assertIn("scrollSelectedPersonIntoList", script)
        self.assertIn("personList.scrollTop", script)
        self.assertIn("personList.getBoundingClientRect()", script)
        self.assertIn("selectedPersonRow.getBoundingClientRect()", script)
        self.assertIn("scrollRowIntoList(row)", script)
        self.assertIn("personList.focus({ preventScroll: true })", script)
        self.assertNotIn("selectedPersonRow.scrollIntoView", script)

    def test_legacy_person_rows_do_not_have_hover_title_links(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()

        self.assertIn("<button class=\"legacy-list-row", legacy_template)
        self.assertIn('type="button" role="option"', legacy_template)
        self.assertIn("data-person-name", legacy_template)
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
        self.assertIn("legacy-person-workspace", legacy_template)
        self.assertIn("legacy-totals-footer", legacy_template)
        self.assertIn(".legacy-person-workspace", styles)
        self.assertIn(".legacy-totals-footer", styles)
        self.assertIn("flex: 0 0 auto", styles)
        self.assertIn("photo-frame", person_detail)
        self.assertIn("photo-placeholder", person_detail)
        self.assertIn(".photo-frame", styles)
        self.assertIn(".photo-placeholder", styles)

    def test_person_delete_requires_explicit_confirmation_in_ui_and_route(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        person_detail = (ROOT / "backend" / "app" / "templates" / "person_detail.html").read_text()
        persons_router = (ROOT / "backend" / "app" / "routers" / "persons.py").read_text()

        expected_text = "Вы точно хотите удалить кавалера? Это действие нельзя отменить."
        self.assertIn(expected_text, legacy_template)
        self.assertIn(expected_text, person_detail)
        self.assertIn('name="confirm" value="true"', legacy_template)
        self.assertIn('name="delete_person_confirm" value="true"', legacy_template)
        self.assertIn('name="delete_person_confirm" value="true"', person_detail)
        self.assertIn('form_values.get("delete_person_confirm") != "true"', persons_router)
        self.assertIn("Действие требует подтверждения.", persons_router)

    def test_photo_frames_do_not_stretch_real_images(self) -> None:
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn("align-items: center", styles)
        self.assertIn("justify-content: center", styles)
        self.assertIn("max-width: 100%", styles)
        self.assertIn("max-height: 100%", styles)
        self.assertIn("object-fit: contain", styles)
        self.assertIn(".photo-placeholder", styles)
        self.assertIn(".legacy-photo-placeholder", styles)
        self.assertNotRegex(styles, re.compile(r"\.photo-frame\s+\.photo\s*\{[^}]*(?<!-)width:\s*100%;[^}]*(?<!-)height:\s*100%", re.S))
        self.assertNotRegex(styles, re.compile(r"\.legacy-photo\s*\{[^}]*(?<!-)width:\s*100%;[^}]*(?<!-)height:\s*100%", re.S))

    def test_photo_galleries_wrap_images_and_placeholders_in_same_frame(self) -> None:
        template_names = [
            "person_detail.html",
            "person_photos.html",
            "reward_detail.html",
            "mark_detail.html",
            "photo_management.html",
        ]

        for template_name in template_names:
            with self.subTest(template=template_name):
                template = (ROOT / "backend" / "app" / "templates" / template_name).read_text()
                self.assertIn("photo-frame", template)
                self.assertIn("photo-placeholder", template)

        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        self.assertIn("legacy-photo-frame", legacy_template)
        self.assertIn("legacy-photo-placeholder", legacy_template)
        self.assertNotIn("legacy-photo placeholder-image", legacy_template)

    def test_legacy_photo_strip_uses_same_external_frame_for_real_and_missing_photos(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn('figure class="legacy-photo-card"', legacy_template)
        self.assertNotIn("placeholder-card' if not has_media_path(path)", legacy_template)
        self.assertIn('<div class="legacy-photo-frame">', legacy_template)
        self.assertRegex(
            legacy_template,
            re.compile(r'<div class="legacy-photo-frame">\s*{% if has_media_path\(path\) %}\s*<a class="photo-link"[^>]*>\s*<img class="legacy-photo"', re.S),
        )
        self.assertRegex(
            legacy_template,
            re.compile(r"{% else %}\s*<div class=\"legacy-photo legacy-photo-placeholder\">Нет фото</div>\s*{% endif %}\s*</div>", re.S),
        )
        self.assertRegex(
            styles,
            re.compile(r"\.legacy-photo-frame\s*\{[^}]*height:\s*170px;[^}]*background:\s*#eef2f6;[^}]*overflow:\s*hidden;", re.S),
        )
        self.assertRegex(
            styles,
            re.compile(r"\.legacy-photo\s*\{[^}]*max-width:\s*100%;[^}]*max-height:\s*100%;[^}]*width:\s*auto;[^}]*height:\s*auto;[^}]*object-fit:\s*contain;", re.S),
        )

    def test_person_cards_have_wrapping_layout_classes(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        person_detail = (ROOT / "backend" / "app" / "templates" / "person_detail.html").read_text()
        booklet = (ROOT / "backend" / "app" / "templates" / "person_booklet.html").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn("person-detail-hero", person_detail)
        self.assertIn("person-summary-strip", person_detail)
        self.assertIn('class="person-title wrap-text"', person_detail)
        self.assertIn("person-detail-list", person_detail)
        self.assertIn("person-card-panel", person_detail)
        self.assertIn("person-links-panel", person_detail)
        self.assertIn("person-main-photo-panel", person_detail)
        self.assertIn("bio-text wrap-text", person_detail)
        self.assertIn("link-wrap", person_detail)
        self.assertIn("legacy-person-heading", legacy_template)
        self.assertIn("legacy-person-title wrap-text", legacy_template)
        self.assertIn("legacy-person-meta wrap-text", legacy_template)
        self.assertIn("comment-text wrap-text", legacy_template)
        self.assertIn(".wrap-text", styles)
        self.assertIn("overflow-wrap: break-word", styles)
        self.assertIn("word-break: normal", styles)
        self.assertIn(".grid.person-detail-grid", styles)
        self.assertIn(".details.person-detail-list", styles)
        self.assertIn(".person-links-panel", styles)
        self.assertIn("grid-template-columns: minmax(420px, 1fr) minmax(340px, 420px)", styles)
        self.assertRegex(
            styles,
            re.compile(r"\.wrap-text,[^{]+\.legacy-person-title\s*\{[^}]*overflow-wrap:\s*break-word;[^}]*word-break:\s*normal;", re.S),
        )
        self.assertRegex(
            styles,
            re.compile(r"\.details\.person-detail-list dd\.link-wrap,[^{]+dd\.link-wrap a\s*\{[^}]*overflow-wrap:\s*anywhere;", re.S),
        )
        self.assertIn(".legacy-person-heading", styles)
        self.assertIn(".person-summary-strip", styles)
        self.assertIn("booklet-title", booklet)
        self.assertIn("booklet-section", booklet)

    def test_person_edit_form_uses_compact_photo_controls(self) -> None:
        person_form = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text()
        photo_management = (ROOT / "backend" / "app" / "templates" / "photo_management.html").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn("compact-person-form", person_form)
        self.assertIn("person-edit-workspace", person_form)
        self.assertIn("person-edit-main", person_form)
        self.assertIn("person-edit-photos", person_form)
        self.assertIn('rows="4"', person_form)
        self.assertIn('rows="3"', person_form)
        self.assertIn("person-notes-section", person_form)
        self.assertIn("person-notes-grid", person_form)
        self.assertIn("photo_manage_compact = true", person_form)
        self.assertIn("photo-manage-section-compact", photo_management)
        self.assertIn(".compact-person-form", styles)
        self.assertIn(".person-edit-workspace", styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(300px, 400px)", styles)
        self.assertIn(".person-edit-photos .photo-manage-section", styles)
        self.assertIn(".photo-manage-section-compact", styles)
        self.assertIn("height: 86px", styles)
        self.assertIn("max-height: 86px", styles)
        self.assertIn("min-height: 86px", styles)
        self.assertIn("min-height: 64px", styles)

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
        self.assertIn("canvas.toBlob", script)
        self.assertIn('"image/jpeg"', script)
        self.assertIn("0.85", script)
        self.assertIn('"clipboard.jpg"', script)
        self.assertIn("Не удалось подготовить JPEG из буфера. Используйте кнопку +.", script)
        self.assertNotIn("clipboard\" + extension", script)


if __name__ == "__main__":
    unittest.main()
