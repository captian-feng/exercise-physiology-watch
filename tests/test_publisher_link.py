import json
import sqlite3
import unittest

import watch


class PublisherLinkTest(unittest.TestCase):
    def test_publisher_url_survives_later_database_updates(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE articles (id INTEGER PRIMARY KEY, doi TEXT, pmid TEXT, fingerprint TEXT, data TEXT, first_seen TEXT)')
        item = {'title':'Example human exercise', 'doi':'10.1000/test', 'url':'https://journal.example/article/123'}
        watch.upsert(db, item, 'Journal', '官网 最新文章', '2026-11-24', True)
        other = {'title':item['title'], 'doi':item['doi'], 'pmid':'123', 'url':'https://pubmed.ncbi.nlm.nih.gov/123/'}
        watch.upsert(db, other, 'Journal', 'PubMed', '2026-11-24', True)
        record = json.loads(db.execute('SELECT data FROM articles').fetchone()[0])
        self.assertEqual(record['publisher_url'], item['url'])
        self.assertEqual(record['pmid'], '123')

    def test_doi_resolver_is_not_saved_as_publisher_page(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE articles (id INTEGER PRIMARY KEY, doi TEXT, pmid TEXT, fingerprint TEXT, data TEXT, first_seen TEXT)')
        watch.upsert(db, {'title':'Example', 'doi':'10.1000/test', 'url':'https://doi.org/10.1000/test'}, 'Journal', '官网 最新', '2026-11-24', True)
        record = json.loads(db.execute('SELECT data FROM articles').fetchone()[0])
        self.assertNotIn('publisher_url', record)

if __name__ == '__main__': unittest.main()

