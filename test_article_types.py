"""Regression tests for article-format classification."""

import unittest

from article_types import article_type_for


class ArticleTypeTests(unittest.TestCase):
    def test_conference_beats_generic_journal_article(self):
        self.assertEqual(article_type_for({"title": "Poster abstract: sprint performance", "type": "journal-article"}),
                         "会议摘要、海报与会议论文")

    def test_crossref_conference_type_is_recognised(self):
        self.assertEqual(article_type_for({"title": "Wearable sensor study", "type": "conference-paper"}),
                         "会议摘要、海报与会议论文")

    def test_source_type_beats_title_appearance(self):
        self.assertEqual(article_type_for({"title": "Effects of training", "type": "Editorial, Journal Article"}),
                         "评论、社论与勘误")

    def test_generic_journal_type_is_unknown(self):
        self.assertEqual(article_type_for({"title": "Exercise and performance", "type": "Journal Article"}), "类型待确认")

    def test_physiological_response_is_not_an_editorial(self):
        item = {"title": "Cardiovascular response to exercise: a randomized controlled trial", "type": "Journal Article"}
        self.assertEqual(article_type_for(item), "原创研究")

    def test_letter_response_is_editorial(self):
        self.assertEqual(article_type_for({"title": "Response to the editor"}), "评论、社论与勘误")

    def test_categories(self):
        cases = {
            "系统综述与证据整合": {"title": "Exercise training: a systematic review and meta-analysis"},
            "方案与注册": {"title": "Protocol for a randomized controlled trial"},
            "指南、共识与立场文件": {"title": "Consensus statement on athlete monitoring"},
            "原创研究": {"title": "A randomized controlled trial of interval training"},
            "类型待确认": {"title": "New perspectives on exercise"},
        }
        for expected, item in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(article_type_for(item), expected)

    def test_supplement_issue_without_pages_is_a_meeting_abstract(self):
        for issue in ("S1", "10S", "Suppl 2"):
            with self.subTest(issue=issue):
                item = {"title": "Sprint performance in elite athletes", "issue": issue, "page": ""}
                self.assertEqual(article_type_for(item), "会议摘要、海报与会议论文")

    def test_paged_article_in_a_supplement_stays_uncertain(self):
        item = {"title": "Effects of training on strength", "issue": "S1", "page": "100-108"}
        self.assertEqual(article_type_for(item), "类型待确认")

    def test_regular_issue_is_not_a_meeting_abstract(self):
        item = {"title": "Exercise and performance", "issue": "10", "page": ""}
        self.assertEqual(article_type_for(item), "类型待确认")

    def test_missing_page_key_does_not_imply_a_meeting_abstract(self):
        # PubMed records omit the page field, so an absent key must not be read
        # as an empty page range (Sports Medicine publishes paged S1 articles).
        item = {"title": "Fueling Women's Football: practical nutrition strategies", "issue": "S1"}
        self.assertEqual(article_type_for(item), "类型待确认")

    def test_paged_supplement_article_is_not_a_meeting_abstract(self):
        item = {"title": "Physical activity after therapy", "issue": "S2", "page": "1873-1881"}
        self.assertEqual(article_type_for(item), "类型待确认")


    def test_reply_titles_are_editorial_whatever_the_addressee(self):
        titles = [
            "Response to Lolli: Context-Specific Variability in Elite Sport",
            "Reply to Marciano and Rossiter: Balancing muscle oxygen consumption",
            "Response to Horvath Comment on Leo and Mujika: Agreement Between",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(
                    article_type_for({"title": title, "type": "Journal Article"}),
                    "评论、社论与勘误")

    def test_response_words_in_a_study_title_are_not_editorial(self):
        titles = [
            "Responders and non-responders to exercise training",
            "Responses of heart rate to incremental exercise",
            "Reply time and reaction performance in sprinters",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(
                    article_type_for({"title": title, "type": "Journal Article"}),
                    "类型待确认")


    def test_single_page_in_a_supplement_is_a_meeting_abstract(self):
        # JSS prints its conference abstracts one per page, e.g. 40-40.
        item = {"title": "D2.S1.1(3) Does hip abductor strength training change running biomechanics",
                "issue": "sup1", "page": "40-40"}
        self.assertEqual(article_type_for(item), "会议摘要、海报与会议论文")

    def test_multi_page_article_in_a_supplement_is_not_a_meeting_abstract(self):
        item = {"title": "Eccentric exercise and muscle damage", "issue": "sup1", "page": "40-48"}
        self.assertEqual(article_type_for(item), "类型待确认")

    def test_conference_code_decides_when_pages_are_absent(self):
        with_code = {"title": "D2.P4 Small steps, big gains", "issue": "sup1"}
        self.assertEqual(article_type_for(with_code), "会议摘要、海报与会议论文")
        without_code = {"title": "Effects of training on strength", "issue": "sup1"}
        self.assertEqual(article_type_for(without_code), "类型待确认")


if __name__ == "__main__":
    unittest.main()
