from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RewardReferenceContractTests(unittest.TestCase):
    def test_reward_form_has_cascade_filters_and_canonical_name_input(self) -> None:
        template = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")

        self.assertIn('select name="id_name"', template)
        self.assertIn('value="{{ item.id_name }}"', template)
        self.assertIn("item.id_name|string == reward.id_name|string", template)
        for field in ("country", "category", "subcategory"):
            self.assertIn(f'data-reward-reference-filter="{field}"', template)
        self.assertEqual(template.count("data-reward-reference-field="), 1)
        self.assertNotIn('name="id_link"', template)
        self.assertIn("data-reward-reference-link", template)
        self.assertIn('readonly aria-readonly="true"', template)
        for instance_field in ("number", "date_purchase", "price_purchase", "price_now", "instock"):
            self.assertIn(f'name="{instance_field}"', template)

    def test_reference_sync_runs_after_name_change_and_partial_content_update(self) -> None:
        script = (ROOT / "backend/app/static/reward_reference_fields.js").read_text(encoding="utf-8")

        self.assertIn('countrySelect.addEventListener("change"', script)
        self.assertIn('categorySelect.addEventListener("change"', script)
        self.assertIn('subcategorySelect.addEventListener("change"', script)
        self.assertIn('nameSelect.addEventListener("change", updateDerivedFields)', script)
        self.assertIn('document.addEventListener("legacy:content-updated"', script)
        self.assertIn('reference.id_link == null ? "" : String(reference.id_link)', script)

    def test_base_loads_reward_reference_sync(self) -> None:
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("reward_reference_fields.js", base)


if __name__ == "__main__":
    unittest.main()
