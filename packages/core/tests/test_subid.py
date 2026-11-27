import itertools
import re
import unittest

from cashback_core import subid

SECRET = "unit-test-secret-0123456789"


class SubIdTests(unittest.TestCase):
    def test_roundtrip_all_types(self):
        for t in subid.TYPES:
            s = subid.encode(t, 123, 98765, SECRET)
            d = subid.decode(s, SECRET)
            self.assertEqual((d.status, d.type, d.owner, d.ref), ("ok", t, 123, 98765))

    def test_shape_five_slots_charset_no_dash_in_slot(self):
        for owner, ref in itertools.product([0, 1, 35, 36, 10**6, subid.MAX_ID], repeat=2):
            s = subid.encode("u", owner, ref, SECRET)
            parts = s.split("-")
            self.assertEqual(len(parts), 5)
            self.assertEqual(parts[4], "")
            for p in parts:
                self.assertRegex(p, r"^[0-9a-z]*$")
            self.assertEqual(len(parts[0]), 2)
            self.assertLessEqual(len(parts[1]), 8)
            self.assertLessEqual(len(parts[2]), 8)
            self.assertEqual(len(parts[3]), 3)

    def test_max_length(self):
        s = subid.encode("p", subid.MAX_ID, subid.MAX_ID, SECRET)
        self.assertEqual(len(s), 25)
        self.assertLessEqual(len(s), subid.MAX_TOTAL)

    def test_reject_ids_out_of_range(self):
        for bad in (-1, subid.MAX_ID + 1, 2**53, True, "12", 1.5):
            with self.assertRaises(subid.SubIdError):
                subid.encode("u", bad, 1, SECRET)

    def test_reject_bad_type_and_weak_secret(self):
        with self.assertRaises(subid.SubIdError):
            subid.encode("z", 1, 1, SECRET)
        with self.assertRaises(subid.SubIdError):
            subid.encode("u", 1, 1, "short")

    def test_tampered_owner_is_invalid(self):
        s = subid.encode("u", 100, 5, SECRET)
        forged = s.replace("-" + subid.to_base36(100) + "-", "-" + subid.to_base36(101) + "-")
        self.assertEqual(subid.decode(forged, SECRET).status, "invalid")

    def test_wrong_secret_is_invalid(self):
        s = subid.encode("u", 1, 1, SECRET)
        self.assertEqual(subid.decode(s, "another-secret-0123456789").status, "invalid")

    def test_legacy_and_empty_and_garbage_never_raise(self):
        cases = {"fb01----": "legacy", "fb01-3---": "legacy", "----": "empty", "": "empty",
                 None: "empty", "1u-a-b-c": "legacy", "1u-A-b-abc-": "invalid",
                 "1q-a-b-abc-": "invalid", "1u--b-abc-": "invalid", "1u-a-b-abc-x": "invalid",
                 "1u-a-b-ab-": "invalid", "1u-aaaaaaaaa-b-abc-": "invalid"}
        for raw, status in cases.items():
            self.assertEqual(subid.decode(raw, SECRET).status, status, raw)

    def test_no_personal_data_shape(self):
        s = subid.encode("u", 42, 7, SECRET)
        self.assertIsNone(re.search(r"[@.+]", s))

    def test_deterministic(self):
        self.assertEqual(subid.encode("u", 7, 9, SECRET), subid.encode("u", 7, 9, SECRET))


if __name__ == "__main__":
    unittest.main()
