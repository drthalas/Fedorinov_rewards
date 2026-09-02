from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RewardNameAlignmentTests(unittest.TestCase):
    def test_shared_reward_form_keeps_required_marker_inline(self) -> None:
        template = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn(
            '<span>Наименование <span class="required-marker" aria-hidden="true">*</span></span>',
            template,
        )
        scoped = styles.split(
            ".cavalier-reward-form-page .cavalier-form-card label > span > .required-marker",
            1,
        )[1].split("}", 1)[0]
        self.assertIn("display: inline", scoped)
        self.assertIn("margin: 0", scoped)

    def test_both_create_entrypoints_share_the_same_reward_template(self) -> None:
        rewards_router = (ROOT / "backend/app/routers/rewards.py").read_text(encoding="utf-8")
        persons_router = (ROOT / "backend/app/routers/persons.py").read_text(encoding="utf-8")

        self.assertIn('"reward_form.html"', rewards_router)
        self.assertIn('"reward_form.html"', persons_router)

    def test_required_name_and_reference_cascade_contract_are_unchanged(self) -> None:
        template = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")

        self.assertIn("data-reward-reference-cascade", template)
        self.assertIn('name="reference_subcategory_id" data-guide-role="subcategory"', template)
        self.assertIn('name="id_name" data-guide-role="name"', template)
        self.assertIn("data-styled-select-typeahead=\"prefix\" required", template)


if __name__ == "__main__":
    unittest.main()
