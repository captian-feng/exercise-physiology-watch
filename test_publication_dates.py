"""Regression tests for date provenance in article ingestion."""
import json
import sqlite3
import unittest
from unittest.mock import patch
import watch

class PublicationDateTests(unittest.TestCase):
    def database(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE articles(id INTEGER PRIMARY KEY, doi TEXT, pmid TEXT, fingerprint TEXT, data TEXT, first_seen TEXT)")
        return db

    def test_preprint_dates_do_not_contaminate_journal_version(self):
        paper = {"title":"Exercise study","doi":"10.1234/paper","date":"2024-02-02"}
        preprint = {"title":"Exercise study","doi":"10.1101/preprint","date":"2023-01-01","online_date":"2023-01-01"}
        for items in ((paper, preprint), (preprint, paper)):
            with self.subTest(first=items[0]["doi"]):
                db = self.database()
                for item in items:
                    watch.upsert(db,item,"Journal","test","2024-01-01",True)
                value = json.loads(db.execute("SELECT data FROM articles").fetchone()[0])
                self.assertEqual(value["doi"],paper["doi"])
                self.assertEqual(value["date"],paper["date"])
                self.assertNotIn("online_date",value)
                db.close()

    def test_pubmed_selects_only_electronic_date(self):
        xml = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Exercise</ArticleTitle><ArticleDate DateType="Print"><Year>2026</Year><Month>12</Month><Day>01</Day></ArticleDate><ArticleDate DateType="Electronic"><Year>2025</Year><Month>11</Month><Day>21</Day></ArticleDate></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'''
        with patch.object(watch,"pubmed_ids",return_value=iter(["123"])), patch.object(watch,"fetch",return_value=xml):
            items = list(watch.pubmed("exercise","2025-01-01"))
        self.assertEqual(items[0]["online_date"],"2025-11-21")

if __name__ == "__main__":
    unittest.main()
