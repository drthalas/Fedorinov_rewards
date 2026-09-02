from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Ale361PostCreateLayoutTests(unittest.TestCase):
    def test_person_links_use_local_alignment_contract(self) -> None:
        template = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")

        links_section = template.split("<legend>Ссылки</legend>", 1)[1].split("</fieldset>", 1)[0]
        main_section = template.split("<legend>Основные данные</legend>", 1)[1].split("</fieldset>", 1)[0]
        self.assertIn('class="form-grid two-columns person-links-grid"', links_section)
        self.assertNotIn("person-links-grid", main_section)
        self.assertIn(".form-grid.two-columns.person-links-grid {", styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", styles)
        self.assertIn(".person-links-grid > label {", styles)
        self.assertIn("flex-direction: column;", styles)
        self.assertIn(".person-links-grid > label > input {", styles)
        self.assertIn("margin-top: auto;", styles)

    def test_post_create_rewards_keep_only_heading_and_action_when_empty(self) -> None:
        template = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('<h2>Награды</h2>', template)
        self.assertIn(">Добавить награду</a>", template)
        self.assertNotIn("Добавьте нужные награды по одной", template)
        self.assertNotIn("Награды ещё не добавлены", template)
        self.assertNotIn("data-post-create-rewards-empty", template)
        self.assertIn(".person-post-create-rewards-head {", styles)
        self.assertIn("flex-direction: column;", styles)
        self.assertIn("align-self: flex-start;", styles)

    def test_existing_reward_table_and_post_create_link_contract_remain(self) -> None:
        template = (ROOT / "backend" / "app" / "templates" / "person_form.html").read_text(encoding="utf-8")

        self.assertIn("{% if post_create_rewards %}", template)
        self.assertIn("{% for reward in post_create_rewards %}", template)
        self.assertIn("/persons/{{ person.id }}/rewards/new?return_to={{ post_create_url|urlencode }}", template)

    def test_updated_css_uses_a_fresh_static_cache_key(self) -> None:
        templates = (ROOT / "backend" / "app" / "routers" / "templates.py").read_text(encoding="utf-8")

        self.assertIn('STATIC_ASSET_VERSION = "20260902-ale410-reward-label"', templates)


if __name__ == "__main__":
    unittest.main()
