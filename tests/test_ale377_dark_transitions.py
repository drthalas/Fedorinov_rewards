import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DarkTransitionTests(unittest.TestCase):
    def test_guides_and_reward_form_set_dark_document_theme_before_body_paint(self) -> None:
        guides = (ROOT / "backend/app/templates/guides.html").read_text(encoding="utf-8")
        reward_form = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")

        self.assertIn('class="document-loading"', base)
        self.assertIn("{% block document_theme_attribute %}", base)
        self.assertIn('data-document-theme="guide"', guides)
        self.assertIn('data-document-theme="guide"', reward_form)
        self.assertIn('data-document-theme="legacy-rewards"', legacy_base)

    def test_existing_curtain_uses_dark_theme_on_both_transition_surfaces(self) -> None:
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('html[data-document-theme="legacy-rewards"]', styles)
        self.assertIn('html[data-document-theme="guide"]', styles)
        self.assertIn(".guide-theme .document-transition-curtain", styles)
        self.assertIn(".guide-theme .document-transition-status", styles)
        self.assertIn(".guide-theme .document-transition-spinner", styles)

    def test_transition_fix_does_not_add_a_second_loading_surface(self) -> None:
        guides = (ROOT / "backend/app/templates/guides.html").read_text(encoding="utf-8")
        reward_form = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")

        self.assertNotIn("document-transition-curtain", guides)
        self.assertNotIn("document-transition-curtain", reward_form)


if __name__ == "__main__":
    unittest.main()
