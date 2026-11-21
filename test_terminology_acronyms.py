"""Regression checks for glossary acronym correction."""
import unittest

import terminology


class AcronymCorrectionTests(unittest.TestCase):
    def test_shared_acronym_is_not_replaced_even_with_full_names(self):
        title = "Mean arterial pressure (MAP) and maximal aerobic power (MAP)"
        translation = "平均动脉压 (MAP) 和最大有氧功率 (MAP)"
        self.assertEqual(terminology.correct(title, translation), translation)

    def test_shared_acronym_on_its_own_is_not_matched(self):
        for acronym in ("MAP", "CRP", "FVC"):
            with self.subTest(acronym=acronym):
                self.assertEqual(terminology.matched_terms(acronym), [])

    def test_unambiguous_acronym_is_still_translated(self):
        self.assertEqual(terminology.correct("Root mean square error (RMSE)", "RMSE"), "均方根误差")

    def test_two_letter_acronym_is_left_intact(self):
        self.assertEqual(terminology.correct("Tidal volume (VT)", "潮气量 (VT)"), "潮气量 (VT)")


if __name__ == "__main__":
    unittest.main()
