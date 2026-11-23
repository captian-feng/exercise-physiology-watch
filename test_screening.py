"""Regression tests for the library's inclusion scope.

The library lists human exercise physiology: studies that measure a physiological
or physical-performance outcome in people who exercise. These tests pin the
boundary so psychosocial and molecular work cannot drift back in, while genuine
exercise studies that merely mention anxiety or a gene variant stay.
"""

import unittest

from screening import out_of_scope_reason, relevance_tier


class ScopeTests(unittest.TestCase):
    def test_psychosocial_titles_are_out_of_scope(self):
        titles = [
            "Examination of Performance Anxiety Theories in Sport Psychology Textbooks",
            "Impact of coach-created motivational climate on team resilience",
            "Psychological Self-Report Questionnaires Are Not Associated With Decrements in Physical Performance",
            "The give and take of social support in professional athlete career pathways",
            "Optimism and athlete thriving: the roles of attribution of disciplinary coaching",
            "Talent development in Chinese football: a comparative analysis",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(out_of_scope_reason(title), "心理学、社会科学或教练研究")

    def test_molecular_and_tissue_titles_are_out_of_scope(self):
        titles = [
            "Knockdown of long non-coding RNA dysregulates endothelial function",
            "G6PD-mediated pentose phosphate pathway modulates ferroptosis",
            "ACTN3 rs1815739 is associated with non-contact knee ligament rupture",
            "Transcriptomic profiling of the biceps femoris after a football match",
            "CXCL2 is a modifiable driver of sarcopenic inflammation",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(out_of_scope_reason(title), "纯分子、细胞或组织层面研究")

    def test_exercise_studies_that_mention_anxiety_or_a_gene_are_kept(self):
        titles = [
            "Six weeks of respiratory muscle training enhance pulmonary functions and sprint performance without influencing anxiety and stress",
            "Effects of a year-long aerobic exercise intervention on neuroendocrine, autonomic, and neural correlates of stress and emotion",
            "Association between PBMC mitochondrial respiration and NIRS-derived muscle oxygenation",
            "Effects of whey protein supplementation on muscle damage in power- and endurance-trained athletes",
            "Effect of velocity loss squat induced post-activation performance enhancement",
            "Cerebral oxygen extraction across different exercise intensities",
            "Countermovement jump performance and operational readiness",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertIsNone(out_of_scope_reason(title))

    def test_out_of_scope_records_are_dropped_not_demoted(self):
        item = {"title": "Impact of coach-created motivational climate on team resilience",
                "type": "Journal Article", "journal": "Journal of Sports Sciences"}
        self.assertIsNone(relevance_tier(item))

    def test_in_scope_exercise_record_reaches_core(self):
        item = {"title": "Sprint interval training improves running economy in trained runners",
                "type": "Journal Article", "journal": "Journal of Sports Sciences"}
        self.assertEqual(relevance_tier(item), "core")


    def test_training_method_studies_reach_core(self):
        # A training stimulus is the subject of exercise physiology even when the
        # title names no measured outcome.
        titles = [
            "Biceps femoris long-head motor unit discharge rates during eccentric exercise",
            "Cluster vs. rest-redistribution set configurations on training volume",
            "Effects of lower-leg inclination on the efficacy of the Nordic hamstring exercise",
            "Resistance Training for Cyclists: Scientific Evidence and Practical Recommendations",
            "The Duration of the Repeated-Bout Effect After Eccentric Exercise",
            "Assisted Sprint Training: Individual Adaptations Linked to Force-Velocity",
            "Association Between Hormone Variability and Anaerobic Performance",
            "Anaerobic speed or power reserve as a key determinant of repeatability",
            "Comparison of lower limb muscle activity in water vs. land plyometric exercise",
            "Determination of swimming training intensity zones",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(
                    relevance_tier({"title": title, "type": "", "mesh": ()}), "core")

    def test_training_rule_does_not_resurrect_excluded_work(self):
        for title in [
            "Correction to: Sprint training and performance",
            "Sprint training and skeletal muscle gene expression in mice",
            "Arthroscopic rotator cuff repair in overhead athletes",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(relevance_tier({"title": title, "type": "", "mesh": ()}))


if __name__ == "__main__":
    unittest.main()
