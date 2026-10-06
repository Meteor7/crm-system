import unittest
from rayher_crm.services.document_links import scorecard_url


class TestDocumentLinks(unittest.TestCase):
    def test_valid_references_and_blank(self):
        for value in ("", "https://example.com/card?a=1&b=2#deal", "http://intranet:8080/card"):
            self.assertEqual(scorecard_url(value), value)
        self.assertEqual(scorecard_url(None), "")

    def test_invalid_references(self):
        for value in ("/relative", "//example.com", "javascript:alert(1)", "https://user:pass@example.com",
                      "https://example.com:99999", "https://example.com/a b", "https://example.com\\path",
                      "https://example.com/\ncard", 12, "https://[", "https://example.com/" + "a" * 2048):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scorecard_url(value)
