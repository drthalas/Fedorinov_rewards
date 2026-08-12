import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CavalierRelatedVisualTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_reward_filters_use_accessible_custom_select_fallbacks(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        base = self.read("backend/app/templates/legacy_base.html")
        script = self.read("backend/app/static/custom_select.js")

        filters = template.split('class="legacy-rewards-filters', 1)[1].split("</form>", 1)[0]
        self.assertEqual(filters.count("data-styled-select"), 5)
        self.assertIn("custom_select.js", base)
        self.assertIn('setAttribute("role", "combobox")', script)
        self.assertIn('setAttribute("role", "listbox")', script)
        self.assertIn('event.key === "ArrowDown"', script)
        self.assertIn('event.key === "ArrowUp"', script)
        self.assertIn('event.key === "Enter"', script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn('event.key === "Tab"', script)
        self.assertIn('select.dispatchEvent(new Event("change", { bubbles: true }))', script)
        self.assertIn("MutationObserver", script)

    def test_person_rows_show_birth_year_and_reward_count_by_default(self) -> None:
        template = self.read("backend/app/templates/legacy.html")

        self.assertIn('class="legacy-list-meta"', template)
        self.assertIn("г.р. · {{ person.rewards_count }} нагр.", template)
        self.assertIn("person.birthday|format_birth_year if person.birthday else '—'", template)

    def test_keyboard_navigation_preserves_scroll_and_debounces_requests(self) -> None:
        script = self.read("backend/app/static/legacy_rewards.js")
        styles = self.read("backend/app/static/styles.css")

        self.assertIn("KEYBOARD_NAVIGATION_DELAY_MS = 320", script)
        self.assertIn("scheduleKeyboardNavigation", script)
        self.assertIn("listScrollTop", script)
        self.assertIn("ensureRowVisible", script)
        self.assertIn("personList.scrollTop -= visibleTop - rowRect.top", script)
        self.assertIn("personList.scrollTop += rowRect.bottom - visibleBottom", script)
        self.assertNotIn('behavior: "smooth"', script)
        self.assertIn("currentList.scrollTop = Math.max(0, listScrollTop)", script)
        self.assertIn("currentWorkspace.replaceWith(nextWorkspace)", script)
        self.assertNotIn("currentLayout.replaceWith(nextLayout)", script)
        self.assertIn("window.requestAnimationFrame", script)
        self.assertIn("delete personList.dataset.scrollRestored", script)
        self.assertIn("delete personList.dataset.selectionPriority", script)
        self.assertIn("overflow-anchor: none", styles)
        self.assertIn("scroll-behavior: auto", styles)
        self.assertIn("height: 30px", styles)
        self.assertIn(".legacy-list-row:hover:not(.selected-row)", styles)
        self.assertIn(".legacy-list-row.selected-row", styles)

    def test_selected_person_row_can_toggle_back_to_filtered_empty_state(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        script = self.read("backend/app/static/legacy_rewards.js")

        self.assertIn('data-deselect-url="{{ rewards_tab_return }}"', template)
        self.assertIn('row.getAttribute("aria-selected") === "true"', script)
        self.assertIn("row.dataset.deselectUrl", script)
        self.assertIn("listScrollTop: personList ? personList.scrollTop : 0", script)

    def test_remaining_legacy_tabs_use_archive_theme_and_custom_selects(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        base = self.read("backend/app/templates/legacy_base.html")
        styles = self.read("backend/app/static/styles.css")

        self.assertIn("legacy-rewards-theme legacy-{{ tab|default('rewards', true) }}-theme", base)
        for class_name in ("legacy-search-tab", "legacy-marks-tab", "legacy-summary-tab", "legacy-about-tab"):
            with self.subTest(class_name=class_name):
                self.assertIn(class_name, template)
                self.assertIn(f".{class_name}", styles)
        search_form = template.split('class="legacy-search-form', 1)[1].split("</form>", 1)[0]
        self.assertEqual(search_form.count("data-styled-select"), 2)
        summary_form = template.split('class="summary-filter-form', 1)[1].split("</form>", 1)[0]
        self.assertEqual(summary_form.count("data-styled-select"), 5)

    def test_guides_and_legacy_tabs_share_stable_desktop_shell_geometry(self) -> None:
        styles = self.read("backend/app/static/styles.css")

        polish = styles.split("ALE-248 final polish: one stable archive frame", 1)[1]
        self.assertIn("body.guide-theme", polish)
        self.assertIn("body.guide-theme::before,", polish)
        self.assertIn("body.legacy-rewards-theme::before", polish)
        self.assertIn("width: 83px", polish)
        self.assertIn("padding-left: 85px", polish)
        self.assertIn("height: 100vh", polish)
        self.assertIn("overflow: hidden", polish)
        self.assertIn(".guide-theme .legacy-tabs,", polish)
        self.assertIn(".legacy-rewards-theme .legacy-tabs", polish)
        self.assertIn("height: calc(100vh - 81px)", polish)
        self.assertIn("height: calc(100% - 141px)", polish)
        self.assertIn(".guide-directory-grid", polish)
        self.assertIn("min-height: 0", polish)
        self.assertIn("body.guide-theme::after", polish)
        self.assertIn("body.legacy-rewards-theme::after", polish)
        self.assertIn("mix-blend-mode: normal", polish)

    def test_all_archive_headers_share_the_accepted_emblem_fade(self) -> None:
        styles = self.read("backend/app/static/styles.css")

        polish = styles.split("Use the accepted Guides fade treatment", 1)[1]
        self.assertIn(".guide-theme .legacy-app-header::after,", polish)
        self.assertIn(".legacy-rewards-theme .legacy-app-header::after", polish)
        self.assertIn('background-image: url("/static/assets/guides/top-right-emblem.png")', polish)
        self.assertIn("background-position: left center", polish)
        self.assertIn("background-size: 206px 72px", polish)
        self.assertIn("mask-image: linear-gradient", polish)
        self.assertIn("mix-blend-mode: screen", polish)

    def test_search_summary_contrast_and_summary_button_roles_are_explicit(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        styles = self.read("backend/app/static/styles.css")

        for class_name in (
            "summary-mode-option",
            "summary-primary-action",
            "summary-secondary-action",
            "summary-export-action",
        ):
            with self.subTest(class_name=class_name):
                self.assertIn(class_name, template)
                self.assertIn(f".{class_name}", styles)
        self.assertIn("--archive-form-text: #ddd5c8", styles)
        self.assertIn(".legacy-search-tab .styled-select-value", styles)
        self.assertIn(".legacy-summary-tab .styled-select-value", styles)
        self.assertIn("--archive-form-placeholder: #817a6f", styles)

    def test_marks_related_pages_use_shared_dark_theme(self) -> None:
        detail = self.read("backend/app/templates/mark_detail.html")
        form = self.read("backend/app/templates/mark_form.html")

        for template in (detail, form):
            self.assertIn("cavalier-page-theme", template)
            self.assertIn("cavalier-mark-theme", template)
        self.assertNotIn("Знак #{{ mark.id }}", detail)
        self.assertNotIn("<dt>ID</dt>", detail)
        self.assertNotIn("#{{ mark.id }}", form)
        self.assertEqual(form.count("data-styled-select"), 4)

    def test_related_pages_use_shared_dark_cavalier_theme(self) -> None:
        templates = {
            name: self.read(f"backend/app/templates/{name}")
            for name in ("person_detail.html", "person_photos.html", "person_form.html", "reward_detail.html", "reward_form.html")
        }

        for name, template in templates.items():
            with self.subTest(template=name):
                self.assertIn("cavalier-page-theme", template)
                self.assertIn("guide-theme", template)

        self.assertNotIn("<dt>ID</dt>", templates["person_detail.html"])
        self.assertNotIn("ID награды", templates["reward_detail.html"])
        self.assertNotIn("<dt>ID</dt>", templates["reward_detail.html"])
        self.assertIn("cavalier-form-card", templates["reward_form.html"])
        self.assertIn("data-reward-duplicate-check", templates["reward_form.html"])
        self.assertIn('data-confirm-submit="reward-delete"', templates["reward_detail.html"])
        self.assertIn("cavalier-photos-page", templates["person_photos.html"])

    def test_reward_form_only_exposes_name_as_editable_reference_field(self) -> None:
        reward_form = self.read("backend/app/templates/reward_form.html")
        reference_fields = self.read("backend/app/static/reward_reference_fields.js")

        self.assertEqual(reward_form.count('select name="id_name"'), 1)
        self.assertIn('data-styled-select data-styled-select-typeahead="prefix"', reward_form)
        self.assertNotIn('name="id_gos"', reward_form)
        self.assertNotIn('name="id_catigory"', reward_form)
        self.assertNotIn('name="id_sub_catigory"', reward_form)
        self.assertNotIn('name="id_link"', reward_form)
        self.assertIn('data-guide-role="name"', reward_form)
        self.assertEqual(reward_form.count('readonly aria-readonly="true"'), 4)
        self.assertIn('select.dispatchEvent(new Event("change"', self.read("backend/app/static/custom_select.js"))
        self.assertIn('nameSelect.addEventListener("change", updateDerivedFields)', reference_fields)


if __name__ == "__main__":
    unittest.main()
