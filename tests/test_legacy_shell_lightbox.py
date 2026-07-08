from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LegacyShellLightboxTests(unittest.TestCase):
    def test_legacy_template_uses_dedicated_shell(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()

        self.assertIn('{% extends "legacy_base.html" %}', legacy_template)
        self.assertIn('{% include "_user_nav.html" %}', legacy_base)
        self.assertNotIn("Dashboard", legacy_base)
        self.assertNotIn("Health", legacy_base)
        self.assertNotIn("topbar", legacy_base)

    def test_user_navigation_is_shared_and_owner_facing(self) -> None:
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()
        user_nav = (ROOT / "backend" / "app" / "templates" / "_user_nav.html").read_text()

        self.assertIn('{% include "_user_nav.html" %}', base)
        self.assertIn('{% include "_user_nav.html" %}', legacy_base)
        self.assertIn('class="legacy-tabs"', user_nav)
        for label in ["Награды", "Поиск", "Знаки", "Свод.таблица", "Справочник", "О программе"]:
            self.assertIn(label, user_nav)
        self.assertIn('/guides?return_to=', user_nav)
        self.assertIn("current_url|urlencode", user_nav)
        self.assertIn('active_nav == \'guides\'', user_nav)
        for forbidden in ["Главная", "Диагностика", "Health", "/dashboard", "/health", "topbar"]:
            self.assertNotIn(forbidden, user_nav)
            self.assertNotIn(forbidden, base)

    def test_legacy_rewards_toolbar_keeps_only_person_actions(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()

        self.assertNotIn('/guides?return_to={{ rewards_tab_return|urlencode }}', legacy_template)
        self.assertIn('/persons/new?return_to={{ rewards_tab_return|urlencode }}', legacy_template)
        self.assertIn('/persons/{{ selected_person.id }}/edit?return_to={{ selected_person_return|urlencode }}', legacy_template)
        self.assertIn('action="/persons/{{ selected_person.id }}/delete"', legacy_template)

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
        self.assertIn("data-lightbox-group", script)
        self.assertIn("indexBySource", script)
        self.assertIn("seen[key]", script)
        self.assertIn("collectManifestItems", script)
        self.assertIn("data-lightbox-items", script)
        self.assertIn("JSON.parse", script)
        self.assertIn('document.addEventListener("click"', script)
        self.assertIn('target.closest("a.photo-link, a.photo-clickable")', script)
        self.assertIn("itemSource", script)
        self.assertIn("itemCaption", script)

    def test_static_assets_are_cache_busted(self) -> None:
        templates_py = (ROOT / "backend" / "app" / "routers" / "templates.py").read_text()
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()
        lightbox = (ROOT / "backend" / "app" / "templates" / "_lightbox.html").read_text()
        booklet = (ROOT / "backend" / "app" / "templates" / "person_booklet.html").read_text()

        self.assertIn('STATIC_ASSET_VERSION = "20260703-v012-person-card-scroll"', templates_py)
        self.assertIn("include_query_params(v=STATIC_ASSET_VERSION)", templates_py)
        self.assertIn("static_url('styles.css')", base)
        self.assertIn("static_url('styles.css')", legacy_base)
        self.assertIn("static_url('confirm_submit.js')", base)
        self.assertIn("static_url('confirm_submit.js')", legacy_base)
        self.assertIn("static_url('lightbox.js')", lightbox)
        self.assertIn("static_url('save_as.js')", booklet)

    def test_person_detail_lightbox_uses_complete_photo_group(self) -> None:
        person_detail = (ROOT / "backend" / "app" / "templates" / "person_detail.html").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn("person_lightbox_group", person_detail)
        self.assertIn('data-lightbox-group="{{ person_lightbox_group }}"', person_detail)
        self.assertIn("data-person-complete-slideshow", person_detail)
        self.assertIn("person-lightbox-extra-link", person_detail)
        self.assertIn('type="application/json" data-lightbox-items="{{ person_lightbox_group }}"', person_detail)
        self.assertIn("data-person-full-lightbox-items", person_detail)
        self.assertIn("media_url(photo.path)|tojson", person_detail)
        self.assertIn("data-lightbox-src", person_detail)
        self.assertIn("data-person-folder-extra-photo", person_detail)
        self.assertIn("photo in photos", person_detail)
        self.assertIn("photo in additional_photos", person_detail)
        self.assertIn("person-lightbox-complete-list", styles)
        self.assertIn("clip-path: inset(50%)", styles)

    def test_legacy_rewards_photo_block_uses_complete_person_photo_group(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        legacy_router = (ROOT / "backend" / "app" / "routers" / "legacy.py").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn("selected_person_available_photos", legacy_template)
        self.assertIn("selected_person_document_photos", legacy_template)
        self.assertIn("legacy-document-photo-block", legacy_template)
        self.assertIn("legacy-document-photo-grid", legacy_template)
        self.assertIn("data-legacy-document-photo", legacy_template)
        self.assertIn("legacy_person_lightbox_group", legacy_template)
        self.assertIn('data-lightbox-group="{{ legacy_person_lightbox_group }}"', legacy_template)
        self.assertIn('type="application/json" data-lightbox-items="{{ legacy_person_lightbox_group }}"', legacy_template)
        self.assertIn("data-legacy-person-full-lightbox-items", legacy_template)
        self.assertIn("data-legacy-person-complete-slideshow", legacy_template)
        self.assertIn("person-lightbox-extra-link", legacy_template)
        self.assertIn("media_url(photo.path)|tojson", legacy_template)
        self.assertIn("/persons/{{ selected_person.id }}/photos?return_to={{ selected_person_return|urlencode }}", legacy_template)
        self.assertIn("_legacy_person_photo_items", legacy_router)
        self.assertIn("_legacy_document_photo_items", legacy_router)
        self.assertIn("_unique_available_photo_items", legacy_router)
        self.assertIn("LEGACY_DOCUMENT_PHOTO_SLOTS", legacy_router)
        self.assertIn("Учётная карточка, сторона 1", legacy_router)
        self.assertIn("Учётная карточка, сторона 2", legacy_router)
        self.assertIn("Наградная книжка, сторона 1", legacy_router)
        self.assertIn("Наградная книжка, сторона 2", legacy_router)
        self.assertIn("person_folder_image_items", legacy_router)
        self.assertIn("selected_person_full_photos", legacy_router)
        self.assertIn("selected_person_photos + selected_person_document_photos + selected_person_additional_photos", legacy_router)
        self.assertIn(".legacy-document-photo-block", styles)
        self.assertIn(".legacy-document-photo-grid", styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", styles)
        self.assertIn(".legacy-document-photo-frame", styles)
        self.assertIn("height: 96px", styles)
        self.assertIn(".legacy-show-all-photos-link", styles)

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
        self.assertIn("Быстрый поиск по ФИО", legacy_template)
        self.assertIn("Введите первые буквы ФИО", legacy_template)
        self.assertIn("data-person-quick-search data-person-search-primary", legacy_template)
        self.assertIn("Enter открывает первое совпадение.", legacy_template)
        self.assertIn("data-person-name", legacy_template)
        self.assertIn("data-person-empty", legacy_template)
        self.assertIn("Ничего не найдено.", legacy_template)
        self.assertIn("data-legacy-rewards-layout", legacy_template)
        self.assertIn("data-legacy-person-workspace", legacy_template)
        self.assertIn("toLocaleLowerCase(\"ru-RU\")", script)
        self.assertIn("name.includes(query)", script)
        self.assertIn("quickSearch.addEventListener(\"keydown\"", script)
        self.assertIn('event.key === "Enter"', script)
        self.assertIn("navigateToPersonRow(firstMatch)", script)
        self.assertIn("quick-search-match-row", script)

    def test_legacy_rewards_loading_state_and_ajax_navigation(self) -> None:
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        script = (ROOT / "backend" / "app" / "static" / "legacy_rewards.js").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn('data-legacy-person-workspace aria-live="polite" aria-busy="false"', legacy_template)
        self.assertIn("Загрузка карточки кавалера…", script)
        self.assertIn("Не удалось загрузить карточку кавалера. Попробуйте выбрать кавалера ещё раз.", script)
        self.assertIn("showLoadingState", script)
        self.assertIn("showErrorState", script)
        self.assertIn("window.fetch(url", script)
        self.assertIn("replaceRewardsLayout", script)
        self.assertIn("legacy:content-updated", script)
        self.assertIn(".legacy-loading-state", styles)
        self.assertIn(".legacy-error-state", styles)
        self.assertIn('setAttribute("role", role || "status")', script)
        self.assertIn('showWorkspaceState("legacy-error-state", ERROR_TEXT, "alert")', script)

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
        self.assertIn("TYPEAHEAD_RESET_MS = 3200", script)
        self.assertIn("TYPEAHEAD_NAVIGATION_DELAY_MS = 2600", script)
        self.assertIn("handleTypeahead", script)
        self.assertIn("event.key.length !== 1", script)
        self.assertIn("typeaheadBuffer += key", script)
        self.assertIn("startsWith(query)", script)
        self.assertIn("scheduleTypeaheadNavigation(match)", script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn('event.key === "Backspace"', script)
        self.assertIn("typeaheadBuffer = typeaheadBuffer.slice(0, -1)", script)
        self.assertIn("window.setTimeout(() =>", script)
        self.assertIn("TYPEAHEAD_RESET_MS", script)
        self.assertIn("TYPEAHEAD_NAVIGATION_DELAY_MS", script)
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
        self.assertIn('scope.querySelector("[data-selected-person-row]")', script)
        self.assertIn('scope.querySelector("[data-person-list]")', script)
        self.assertIn("scrollSelectedPersonIntoList", script)
        self.assertIn("personList.scrollTop", script)
        self.assertIn("personList.getBoundingClientRect()", script)
        self.assertIn("selectedPersonRow.getBoundingClientRect()", script)
        self.assertIn("scrollRowIntoList(row)", script)
        self.assertIn("the visible search field is the primary quick-search path", script)
        self.assertNotIn("document.activeElement === document.body", script)
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
        self.assertIn("data-legacy-rewards-scroll", legacy_template)
        self.assertIn('aria-label="Перечень наград"', legacy_template)
        self.assertIn(".legacy-rewards-table-scroll", styles)
        self.assertIn(".legacy-rewards-block .legacy-block-head", styles)
        self.assertIn("flex: 1 1 clamp(220px, 34vh, 340px)", styles)
        self.assertIn("min-height: clamp(190px, 28vh, 220px)", styles)
        self.assertIn("max-height: none", styles)
        self.assertIn("scrollbar-gutter: stable", styles)
        self.assertIn("overscroll-behavior: contain", styles)
        self.assertIn("padding-bottom: 8px", styles)
        self.assertIn("legacy-photo-frame", legacy_template)
        self.assertIn("legacy-photo-placeholder", legacy_template)
        self.assertIn(".legacy-photo-frame", styles)
        self.assertIn(".legacy-photo-placeholder", styles)
        self.assertIn("legacy-person-workspace", legacy_template)
        self.assertIn("legacy-totals-footer", legacy_template)
        self.assertEqual(legacy_template.count("Показать все фото"), 1)
        self.assertIn('class="button legacy-show-all-photos-link"', legacy_template)
        self.assertIn('/persons/{{ selected_person.id }}/photos?return_to={{ selected_person_return|urlencode }}', legacy_template)
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
        confirm_js = (ROOT / "backend" / "app" / "static" / "confirm_submit.js").read_text()

        expected_text = "Вы точно хотите удалить кавалера? Это действие нельзя отменить."
        self.assertIn(expected_text, legacy_template)
        self.assertIn(expected_text, person_detail)
        self.assertIn('data-confirm-submit="person-delete"', legacy_template)
        self.assertIn('data-confirm-submit="person-delete"', person_detail)
        self.assertIn('name="confirm" value=""', legacy_template)
        self.assertIn('name="confirm" value=""', person_detail)
        self.assertIn('name="delete_person_confirm" value=""', legacy_template)
        self.assertIn('name="delete_person_confirm" value=""', person_detail)
        self.assertIn('form_values.get("delete_person_confirm") != "true"', persons_router)
        self.assertIn("Действие требует подтверждения.", persons_router)
        self.assertIn('setInputValue(form, "delete_person_confirm", "true")', confirm_js)

    def test_reward_delete_requires_confirmation_in_ui_and_route(self) -> None:
        base = (ROOT / "backend" / "app" / "templates" / "base.html").read_text()
        legacy_base = (ROOT / "backend" / "app" / "templates" / "legacy_base.html").read_text()
        legacy_template = (ROOT / "backend" / "app" / "templates" / "legacy.html").read_text()
        person_detail = (ROOT / "backend" / "app" / "templates" / "person_detail.html").read_text()
        reward_detail = (ROOT / "backend" / "app" / "templates" / "reward_detail.html").read_text()
        rewards_router = (ROOT / "backend" / "app" / "routers" / "rewards.py").read_text()
        confirm_js = (ROOT / "backend" / "app" / "static" / "confirm_submit.js").read_text()

        expected_text = "Вы действительно хотите удалить награду?"
        self.assertIn(expected_text, legacy_template)
        self.assertIn(expected_text, person_detail)
        self.assertIn(expected_text, reward_detail)
        self.assertIn('/rewards/{{ reward.id }}/delete', person_detail)
        self.assertIn("static_url('confirm_submit.js')", base)
        self.assertIn("static_url('confirm_submit.js')", legacy_base)
        self.assertIn('data-confirm-submit="reward-delete"', legacy_template)
        self.assertIn('data-confirm-submit="reward-delete"', person_detail)
        self.assertIn('data-confirm-submit="reward-delete"', reward_detail)
        self.assertIn('name="confirm" value=""', legacy_template)
        self.assertIn('name="confirm" value=""', person_detail)
        self.assertIn('name="confirm" value=""', reward_detail)
        self.assertIn('name="delete_reward_confirm" value=""', legacy_template)
        self.assertIn('name="delete_reward_confirm" value=""', person_detail)
        self.assertIn('name="delete_reward_confirm" value=""', reward_detail)
        self.assertIn(
            'action="/rewards/{{ reward.id }}/delete" data-confirm-submit="reward-delete" data-confirm-message="Вы действительно хотите удалить награду?">\n'
            '            <input type="hidden" name="confirm" value="">',
            person_detail,
        )
        self.assertIn('name="return_to" value="/persons/{{ person.id }}"', person_detail)
        self.assertIn('form_values.get("delete_reward_confirm") != "true" or form_values.get("confirm") != "true"', rewards_router)
        self.assertIn("event.preventDefault()", confirm_js)
        self.assertIn('setInputValue(form, "confirm", "")', confirm_js)
        self.assertIn('setInputValue(form, "confirm", "true")', confirm_js)
        self.assertIn('setInputValue(form, "delete_reward_confirm", "true")', confirm_js)
        self.assertNotIn('@router.get("/rewards/{reward_id}/delete"', rewards_router)

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
        self.assertNotIn("person-card-panel", person_detail)
        self.assertIn("person-links-panel", person_detail)
        self.assertIn("person-main-photo-panel", person_detail)
        self.assertIn("compact-person-detail", person_detail)
        self.assertIn("compact-person-detail-grid", person_detail)
        self.assertIn("person-detail-rewards-wrap", person_detail)
        self.assertIn("additional-person-photos", person_detail)
        self.assertIn("data-person-folder-extra-photos", person_detail)
        self.assertIn("person-detail-rewards-section", person_detail)
        self.assertIn("person-detail-photo-section", person_detail)
        self.assertIn("person-detail-photo-grid", person_detail)
        self.assertLess(person_detail.index("person-detail-rewards-section"), person_detail.index("person-detail-photo-section"))
        self.assertIn("data-person-complete-slideshow", person_detail)
        self.assertIn("bio-text wrap-text", person_detail)
        self.assertIn("data-history-back", person_detail)
        self.assertIn('data-history-fallback="{{ return_to or \'/persons\' }}"', person_detail)
        self.assertIn("compact-link-value", person_detail)
        self.assertIn("compact-external-link", person_detail)
        self.assertIn('title="{{ person.link1 }}"', person_detail)
        self.assertIn(">Память народа</a>", person_detail)
        self.assertIn(">Форум коллекционеров</a>", person_detail)
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
        self.assertIn(".compact-link-value", styles)
        self.assertIn(".compact-external-link", styles)
        self.assertIn(".compact-person-detail", styles)
        self.assertIn(".compact-photo-grid .photo-frame", styles)
        self.assertIn(".person-detail-photo-grid", styles)
        self.assertIn("min-height: calc(100vh - 16px)", styles)
        self.assertIn(".compact-person-detail *", styles)
        self.assertIn("box-sizing: border-box", styles)
        self.assertIn("overflow: visible", styles)
        self.assertIn("align-items: stretch", styles)
        self.assertIn("grid-auto-rows: clamp(188px, 26vh, 204px)", styles)
        self.assertIn(".compact-person-detail-grid > .panel", styles)
        self.assertIn("flex-direction: column", styles)
        self.assertIn("grid-template-rows: repeat(2, minmax(112px, auto))", styles)
        self.assertIn("grid-auto-flow: column", styles)
        self.assertIn("max-height: min(30vh, 252px)", styles)
        self.assertIn("height: 76px", styles)
        self.assertIn("aspect-ratio: auto", styles)
        self.assertIn("height: auto", styles)
        self.assertIn("flex: 1 1 auto", styles)
        self.assertIn("min-height: 0", styles)
        self.assertIn(".compact-main-photo-panel .photo-frame .photo-placeholder", styles)
        self.assertIn("height: 100%", styles)
        self.assertIn(".person-detail-rewards-wrap", styles)
        self.assertIn("max-height: clamp(210px, 32vh, 300px)", styles)
        self.assertIn("scrollbar-gutter: stable", styles)
        self.assertIn(
            "grid-template-columns: minmax(260px, 0.78fr) minmax(360px, 1.35fr) minmax(280px, 0.9fr)",
            styles,
        )
        self.assertRegex(
            styles,
            re.compile(r"\.wrap-text,[^{]+\.legacy-person-title\s*\{[^}]*overflow-wrap:\s*break-word;[^}]*word-break:\s*normal;", re.S),
        )
        self.assertRegex(
            styles,
            re.compile(r"\.person-links-panel \.details\.person-detail-list\s*\{[^}]*grid-template-columns:\s*minmax\(130px,\s*180px\) minmax\(0,\s*1fr\);", re.S),
        )
        self.assertRegex(
            styles,
            re.compile(r"\.compact-external-link,[^{]+\.compact-link-text\s*\{[^}]*text-overflow:\s*ellipsis;[^}]*white-space:\s*nowrap;[^}]*overflow-wrap:\s*normal;[^}]*word-break:\s*normal;", re.S),
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
        self.assertIn('state.guideCascadeInitialized === "true"', script)
        self.assertIn('container.dataset.guideCascadeInitialized = "true"', script)
        self.assertIn('document.addEventListener("legacy:content-updated"', script)

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
        self.assertIn("data-history-back", script)
        self.assertIn("window.history.back()", script)
        self.assertIn("document.referrer", script)
        self.assertIn("internalFallback", script)

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
