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

    def test_categories(self):
        cases = {
            "系统综述与证据整合": {"title": "Exercise training: a systematic review and meta-analysis"},
            "方案与注册": {"title": "Protocol for a randomized controlled trial"},
            "指南、共识与立场文件": {"title": "Consensus statement on athlete monitoring"},
            "原创研究或常规期刊论文": {"title": "A randomized controlled trial of interval training"},
            "类型待确认": {"title": "New perspectives on exercise"},
        }
        for expected, item in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(article_type_for(item), expected)


if __name__ == "__main__":
    unittest.main()
