from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GuideFormClippingLayoutTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_guide_forms_load_scoped_scroll_styles_after_main_styles(self) -> None:
        base = self.read("backend/app/templates/base.html")
        level_form = self.read("backend/app/templates/guide_level_form.html")
        rank_form = self.read("backend/app/templates/rank_form.html")

        self.assertIn("{% block extra_head %}{% endblock %}", base)
        self.assertGreater(base.index("{% block extra_head %}"), base.index("static_url('styles.css')"))
        for template in (level_form, rank_form):
            with self.subTest(template=template[:40]):
                self.assertIn("static_url('guide_form_scroll.css')", template)

    def test_scroll_override_is_limited_to_guide_form_pages(self) -> None:
        styles = self.read("backend/app/static/guide_form_scroll.css")

        self.assertIn("body.guide-form-theme .page", styles)
        self.assertIn("overflow-y: auto", styles)
        self.assertIn("body.guide-form-theme .guide-form-page", styles)
        self.assertIn("height: auto", styles)
        self.assertIn("padding-bottom: 40px", styles)
        self.assertNotIn("body.guide-theme .page", styles)


if __name__ == "__main__":
    unittest.main()
