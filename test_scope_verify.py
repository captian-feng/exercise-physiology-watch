"""Tests for the online scope-verification layer.

These cover the decision logic and the cache/budget behaviour without touching the
network: `judge` is pure, and `Verifier` is exercised with a pre-seeded cache.
"""

import pathlib
import tempfile
import unittest

import scope_verify
from screening import needs_verification

HUMAN_RUNNING = (
    "Twelve trained male runners completed six weeks of sprint interval training. "
    "Maximal oxygen uptake increased by 6% and 10-km time trial performance improved. "
    "Blood lactate at 14 km/h decreased after training."
)
CELL_STUDY = (
    "C2C12 myotubes were cultured and treated with serum from exercised mice. "
    "Western blot showed increased phosphorylation of AMPK in the cultured cells."
)
PSYCH_STUDY = (
    "Two hundred athletes completed questionnaires measuring motivation and anxiety. "
    "Structural equation modelling showed that coach-created climate predicted burnout."
)
SURVEY_STUDY = (
    "Runners completed a questionnaire about heat preparation strategies before a "
    "100-mile ultramarathon. Fluid intake and sodium use were summarised descriptively."
)


class JudgeTests(unittest.TestCase):
    def test_human_exercise_study_is_admitted(self):
        include, why = scope_verify.judge(
            "Sprint interval training and 10-km performance in runners", HUMAN_RUNNING)
        self.assertTrue(include, why)

    def test_cell_study_is_rejected(self):
        include, why = scope_verify.judge(
            "Exercise serum and AMPK signalling in myotubes", CELL_STUDY)
        self.assertFalse(include)
        self.assertIn("animal or cell", why)

    def test_psychosocial_study_is_rejected(self):
        include, why = scope_verify.judge(
            "Motivation, anxiety and burnout in athletes", PSYCH_STUDY)
        self.assertFalse(include)
        self.assertIn("psychosocial", why)

    def test_questionnaire_study_is_rejected_even_with_physiology_words(self):
        include, why = scope_verify.judge(
            "Heat preparation strategies: a questionnaire study", SURVEY_STUDY)
        self.assertFalse(include)
        self.assertIn("not a primary study", why)

    def test_review_type_is_rejected(self):
        include, why = scope_verify.judge(
            "Applied sport science of basketball", HUMAN_RUNNING, types=["Review"])
        self.assertFalse(include)

    def test_molecular_title_needs_a_whole_body_measurement(self):
        abstract = ("One hundred athletes were genotyped for ACTN3. Carriers had a "
                    "different injury history in the cohort.")
        include, _ = scope_verify.judge(
            "The genetic landscape of injury-resistant variants in athletes", abstract)
        self.assertFalse(include)

        with_measure = ("One hundred athletes were genotyped for ACTN3 and completed a "
                        "countermovement jump test; jump height and peak power differed "
                        "between genotypes.")
        include, _ = scope_verify.judge(
            "ACTN3 genotype and jump performance in athletes", with_measure)
        self.assertTrue(include)

    def test_animal_mesh_is_rejected(self):
        include, why = scope_verify.judge(
            "Treadmill running and muscle adaptation", HUMAN_RUNNING,
            mesh=["Animals", "Mice"])
        self.assertFalse(include)
        self.assertIn("animal", why)


class NeedsVerificationTests(unittest.TestCase):
    def test_ambiguous_title_asks_for_verification(self):
        # No named population and no exercise stimulus: still needs a look.
        item = {"title": "Gene expression and metabolic regulation"}
        self.assertTrue(needs_verification(item))

    def test_human_population_with_exercise_needs_no_verification(self):
        # A marker measured in named participants after exercise is a human study.
        item = {"title": "Gene expression after exercise in trained men"}
        self.assertFalse(needs_verification(item))

    def test_clear_exercise_title_needs_no_verification(self):
        item = {"title": "Sprint interval training improves running economy"}
        self.assertFalse(needs_verification(item))

    def test_editorial_title_needs_no_verification(self):
        item = {"title": "Correction to: Sprint training and performance"}
        self.assertFalse(needs_verification(item))


class VerifierTests(unittest.TestCase):
    def test_cached_verdict_is_reused_without_a_lookup(self):
        with tempfile.TemporaryDirectory() as work:
            path = pathlib.Path(work) / "cache.json"
            path.write_text('{"doi:10.1/x": {"include": true, "why": "cached"}}',
                            encoding="utf-8")
            verifier = scope_verify.Verifier(path=path)
            item = {"title": "anything", "doi": "10.1/x"}
            self.assertEqual(verifier.verify(item), "core")
            self.assertEqual(verifier.lookups, 0)

    def test_exhausted_budget_leaves_records_out(self):
        with tempfile.TemporaryDirectory() as work:
            path = pathlib.Path(work) / "cache.json"
            verifier = scope_verify.Verifier(cache={}, budget=0, path=path)
            item = {"title": "Exercise and gene expression", "doi": "10.1/unqueried"}
            self.assertIsNone(verifier.verify(item))
            self.assertEqual(verifier.cache, {})

    def test_record_without_identifier_is_never_admitted(self):
        verifier = scope_verify.Verifier(cache={}, budget=5)
        self.assertIsNone(verifier.verify({"title": "Exercise and gene expression"}))


if __name__ == "__main__":
    unittest.main()
