"""T-006: khóa hành vi affiliate.make_link (đã verify thật với Shopee ngày 2026-11-26).
Chạy: python3 test_make_link_regression.py
"""
import os
import unittest

os.environ["SHOPEE_AFF_ID"] = "17300000000"
os.environ.pop("SUB_ID_PAD", None)
os.environ.pop("LINK_TEMPLATE", None)
os.environ.pop("AFF_CAMPAIGN", None)

import affiliate  # noqa: E402

BASE = "https://shopee.vn/universal-link/product/{s}/{i}?utm_source=an_17300000000&utm_medium=affiliates&utm_campaign=-&utm_content={c}"


class MakeLinkRegression(unittest.TestCase):
    def test_golden_links(self):
        cases = [
            ("https://shopee.vn/product/1020310358/24088489429", "fb01", "fb01----", 1020310358, 24088489429),
            ("https://shopee.vn/Ten-SP-i.5501.100001?sp_atk=abc", "fb01-3", "fb01-3---", 5501, 100001),
            ("https://shopee.vn/product/5502/100002", "tt09", "tt09----", 5502, 100002),
            ("https://shopee.vn/product/7/8", "1u-3f-23zt-a7q-", "1u-3f-23zt-a7q-", 7, 8),
            ("https://shopee.vn/product/7/8", "", "0----", 7, 8),
        ]
        for url, sub, content, s, i in cases:
            self.assertEqual(affiliate.make_link(url, sub), BASE.format(s=s, i=i, c=content), (url, sub))

    def test_parse_product_url(self):
        self.assertEqual(affiliate.parse_product_url("https://shopee.vn/product/1/2"), (1, 2))
        self.assertEqual(affiliate.parse_product_url("https://shopee.vn/x-y-i.3.4?z=1"), (3, 4))
        self.assertIsNone(affiliate.parse_product_url("https://example.com/abc"))

    def test_missing_aff_id_raises(self):
        old = os.environ.pop("SHOPEE_AFF_ID")
        try:
            with self.assertRaises(ValueError):
                affiliate.make_link("https://shopee.vn/product/1/2", "x")
        finally:
            os.environ["SHOPEE_AFF_ID"] = old


if __name__ == "__main__":
    unittest.main()
