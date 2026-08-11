from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RewardReferenceContractTests(unittest.TestCase):
    def test_reward_form_has_one_reference_input_and_four_derived_outputs(self) -> None:
        template = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")

        self.assertIn('select name="id_name"', template)
        self.assertEqual(template.count("data-reward-reference-field="), 4)
        for field in ("id_gos", "id_catigory", "id_sub_catigory", "id_link"):
            self.assertNotIn(f'name="{field}"', template)
        for instance_field in ("number", "date_purchase", "price_purchase", "price_now", "instock"):
            self.assertIn(f'name="{instance_field}"', template)

    def test_reference_sync_runs_after_name_change_and_partial_content_update(self) -> None:
        script = (ROOT / "backend/app/static/reward_reference_fields.js").read_text(encoding="utf-8")

        self.assertIn('nameSelect.addEventListener("change", updateDerivedFields)', script)
        self.assertIn('document.addEventListener("legacy:content-updated"', script)
        self.assertIn('reference[key] == null ? "" : String(reference[key])', script)

    def test_base_loads_reward_reference_sync(self) -> None:
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("reward_reference_fields.js", base)


if __name__ == "__main__":
    unittest.main()
