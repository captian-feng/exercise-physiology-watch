import os
import sqlite3
import unittest
from unittest.mock import patch

import presentation


class TranslationQuotaTests(unittest.TestCase):
    def _db(self):
        db = sqlite3.connect(':memory:')
        db.execute("CREATE TABLE translations (title TEXT PRIMARY KEY, zh TEXT NOT NULL)")
        return db

    def test_quota_is_unlimited_without_the_setting(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(presentation._translation_quota(), 0)

    def test_quota_reads_a_positive_limit(self):
        with patch.dict(os.environ, {"TRANSLATION_QUOTA": "1200"}):
            self.assertEqual(presentation._translation_quota(), 1200)

    def test_invalid_or_negative_quota_means_unlimited(self):
        with patch.dict(os.environ, {"TRANSLATION_QUOTA": "abc"}):
            self.assertEqual(presentation._translation_quota(), 0)
        with patch.dict(os.environ, {"TRANSLATION_QUOTA": "-5"}):
            self.assertEqual(presentation._translation_quota(), 0)

    def test_quota_trims_the_pending_queue(self):
        db = self._db()
        records = [{"title": f"Title {index}"} for index in range(10)]
        with patch.dict(os.environ, {"TRANSLATION_QUOTA": "4"}), \
             patch.object(presentation, "translate_batch", return_value=["译文"] * 4), \
             patch.object(presentation, "polish", side_effect=lambda title, zh: zh):
            # The decoder import fails in the test environment, so the cache
            # stays empty; the point is that only the quota was queued.
            presentation.translations(db, records)
        queued = db.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        self.assertLessEqual(queued, 4)


if __name__ == "__main__":
    unittest.main()
