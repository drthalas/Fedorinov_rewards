import unittest

from backend.app.services.display import format_birth_year, format_bool, format_date, format_money, pagination, safe_external_url


class DisplayHelperTests(unittest.TestCase):
    def test_format_date(self) -> None:
        self.assertEqual(format_date("1913-05-09"), "09.05.1913")
        self.assertEqual(format_date("1913"), "1913")
        self.assertEqual(format_date(""), "—")
        self.assertEqual(format_date("bad date"), "—")

    def test_format_birth_year(self) -> None:
        self.assertEqual(format_birth_year("1913-05-09"), "1913")
        self.assertEqual(format_birth_year("09.05.1913"), "1913")
        self.assertEqual(format_birth_year("1913"), "1913")
        self.assertEqual(format_birth_year(1913), "1913")
        self.assertEqual(format_birth_year(""), "—")
        self.assertEqual(format_birth_year("bad date"), "—")

    def test_safe_external_url(self) -> None:
        self.assertEqual(safe_external_url("https://example.com/path"), "https://example.com/path")
        self.assertEqual(safe_external_url("http://example.com"), "http://example.com")
        self.assertEqual(safe_external_url("javascript:alert(1)"), "")
        self.assertEqual(safe_external_url("/internal"), "")

    def test_format_money(self) -> None:
        self.assertEqual(format_money(40000), "40 000 ₽")
        self.assertEqual(format_money("115000"), "115 000 ₽")
        self.assertEqual(format_money(None), "—")

    def test_format_bool(self) -> None:
        self.assertEqual(format_bool(True), "Да")
        self.assertEqual(format_bool(False), "Нет")
        self.assertEqual(format_bool(1, "В наличии", "Нет"), "В наличии")

    def test_pagination_bounds(self) -> None:
        page = pagination(total=108, page=-1, page_size=25)
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], 25)
        self.assertEqual(page["total_pages"], 5)
        self.assertTrue(page["has_next"])

        last = pagination(total=108, page=99, page_size=1000)
        self.assertEqual(last["page"], 2)
        self.assertEqual(last["page_size"], 100)
        self.assertFalse(last["has_next"])


if __name__ == "__main__":
    unittest.main()
