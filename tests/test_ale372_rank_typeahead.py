from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RankTypeaheadContractTests(unittest.TestCase):
    def test_rank_select_enables_shared_prefix_typeahead(self) -> None:
        template = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")

        self.assertIn(
            'select name="id_rank" data-styled-select data-styled-select-typeahead="prefix" required',
            template,
        )
        self.assertEqual(template.count('name="id_rank"'), 1)
        self.assertNotIn('type="search"', template)

    def test_typeahead_filter_remains_visible_until_close_or_new_prefix(self) -> None:
        script = (ROOT / "backend/app/static/custom_select.js").read_text(encoding="utf-8")

        timer_body = script.split("function scheduleTypeaheadReset()", 1)[1].split("function prefixMatches", 1)[0]
        close_body = script.split("function close(options)", 1)[1].split("function setActive", 1)[0]
        self.assertIn('typeaheadBuffer = ""', timer_body)
        self.assertNotIn("option.hidden = false", timer_body)
        self.assertIn("resetTypeahead()", close_body)
        self.assertIn('event.key === "Backspace"', script)


if __name__ == "__main__":
    unittest.main()
