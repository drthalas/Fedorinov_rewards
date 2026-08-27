from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RewardFormDesktopLayoutTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_reward_form_uses_one_data_left_photo_right_workspace(self) -> None:
        template = self.read("backend/app/templates/reward_form.html")
        workspace = template.split('<div class="reward-edit-workspace">', 1)[1]

        self.assertLess(workspace.index('<div class="reward-edit-main">'), workspace.index('<aside class="reward-edit-photos">'))
        self.assertIn('class="edit-form legacy-edit-form cavalier-form-card"', workspace)
        self.assertIn("data-reward-reference-cascade", workspace)
        self.assertIn("data-draft-photo-trigger", workspace)
        self.assertIn('{% include "photo_management.html" %}', workspace)

    def test_layout_does_not_change_reward_field_or_photo_semantics(self) -> None:
        template = self.read("backend/app/templates/reward_form.html")

        for field in (
            "reference_country_id",
            "reference_category_id",
            "reference_subcategory_id",
            "id_name",
            "number",
            "date_purchase",
            "price_purchase",
            "price_now",
            "instock",
        ):
            self.assertIn(f'name="{field}"', template)
        self.assertIn("data-reward-reference-link", template)
        self.assertIn("data-draft-photo-input", template)
        self.assertIn('accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"', template)
        self.assertIn('data-write-pending-label="Сохраняем…"', template)

    def test_desktop_is_two_columns_and_narrow_viewport_stacks(self) -> None:
        styles = self.read("backend/app/static/styles.css")
        scoped = styles.split(".cavalier-reward-form-page .reward-edit-workspace", 1)[1]

        self.assertIn("grid-template-columns: minmax(520px, 1.15fr) minmax(360px, 0.85fr)", scoped)
        self.assertIn(".cavalier-reward-form-page .reward-edit-main .form-grid.two-columns", scoped)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", scoped)
        self.assertIn(".cavalier-reward-form-page .reward-edit-photos .photo-manage-section", scoped)
        self.assertIn("margin-top: 0", scoped)
        self.assertIn("@media (max-width: 980px)", scoped)
        responsive = scoped.split("@media (max-width: 980px)", 1)[1]
        self.assertIn("grid-template-columns: minmax(0, 1fr)", responsive)


if __name__ == "__main__":
    unittest.main()
