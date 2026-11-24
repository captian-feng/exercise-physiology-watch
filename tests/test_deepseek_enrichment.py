import datetime
import io
import json
import os
import sqlite3
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import deepseek_enrichment as module


class Response(io.BytesIO):
    pass


class TestEnrichment(unittest.TestCase):
    def test_off_peak_boundaries(self):
        zone = ZoneInfo('Asia/Shanghai')
        for hour, minute, expected in [(7,30,True),(9,0,False),(12,0,True),(13,0,True),(14,0,False),(18,0,True)]:
            self.assertEqual(module.off_peak(datetime.datetime(2026,11,24,hour,minute,tzinfo=zone)), expected)

    def test_cache_and_missing_abstract(self):
        db = sqlite3.connect(':memory:')
        now = datetime.datetime(2026,11,24,7,30,tzinfo=ZoneInfo('Asia/Shanghai'))
        candidate = [({'doi':'10.1000/example', 'title':'Exercise in humans'}, '2026-11-24', 'core')]
        answer = {'choices':[{'message':{'content':json.dumps({'zh':'人体运动','summary':'不应展示'})}}]}
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test', 'DEEPSEEK_TRIAL_ENABLED':'1'}), patch.object(module, 'find_abstract', return_value=('', '')), patch.object(module.urllib.request, 'urlopen', return_value=Response(json.dumps(answer).encode())) as request:
            result = module.enrich(db, candidate, now)
            self.assertEqual(result['10.1000/example'], ('人体运动', '', ''))
            module.enrich(db, candidate, now)
            self.assertEqual(request.call_count, 1)

    def test_missing_key_and_old_record_do_not_call_api(self):
        db = sqlite3.connect(':memory:')
        now = datetime.datetime(2026,11,24,7,30,tzinfo=ZoneInfo('Asia/Shanghai'))
        with patch.dict(os.environ, {}, clear=True), patch.object(module.urllib.request, 'urlopen') as request:
            module.enrich(db, [({'doi':'10.1/example','title':'title'},'2026-11-24','core')], now)
            request.assert_not_called()

    def test_pubmed_failure_uses_publisher_abstract(self):
        class Page(Response):
            def geturl(self): return 'https://www.frontiersin.org/example'
        page = b'<meta name="citation_doi" content="10.3389/fphys.2026.123"><meta name="citation_abstract" content="Human exercise study.">'
        with patch.object(module, 'get_abstract', side_effect=OSError('offline')), patch.object(module.urllib.request, 'urlopen', return_value=Page(page)):
            text, source = module.find_abstract({'pmid':'123','doi':'10.3389/fphys.2026.123'})
        self.assertEqual(text, 'Human exercise study.')
        self.assertIn('frontiersin.org', source)

    def test_bad_record_does_not_stop_next(self):
        db = sqlite3.connect(':memory:')
        now = datetime.datetime(2026,11,24,7,30,tzinfo=ZoneInfo('Asia/Shanghai'))
        rows = [({'doi':'10.1/one','title':'one'}, '2026-11-24', 'core'), ({'doi':'10.1/two','title':'two'}, '2026-11-24', 'core')]
        answer = {'choices':[{'message':{'content':json.dumps({'zh':'译文','summary':'简介'})}}]}
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test', 'DEEPSEEK_TRIAL_ENABLED':'1'}), patch.object(module, 'find_abstract', return_value=('study text', 'https://pubmed.ncbi.nlm.nih.gov/1/')), patch.object(module.urllib.request, 'urlopen', side_effect=[Response(b'invalid'), Response(json.dumps(answer).encode())]):
            result = module.enrich(db, rows, now)
        self.assertNotIn('10.1/one', result)
        self.assertEqual(result['10.1/two'][0], '译文')

    def test_approved_trial_allows_old_record_and_tracks_budget(self):
        db = sqlite3.connect(':memory:')
        now = datetime.datetime(2026,11,24,7,30,tzinfo=ZoneInfo('Asia/Shanghai'))
        candidate = [({'doi':'10.1/trial','title':'trial'}, '2025-01-01', 'core')]
        answer = {'choices':[{'message':{'content':json.dumps({'zh':'译文','summary':'简介'})}}]}
        path = module.Path(__file__).resolve().parent.parent / 'deepseek_top100.json'
        old = path.read_text(encoding='utf-8') if path.exists() else None
        try:
            path.write_text(json.dumps(['10.1/trial']), encoding='utf-8')
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test', 'DEEPSEEK_TRIAL_ENABLED':'1'}), patch.object(module, 'find_abstract', return_value=('text', 'https://pubmed.ncbi.nlm.nih.gov/1/')), patch.object(module.urllib.request, 'urlopen', return_value=Response(json.dumps(answer).encode())):
                self.assertEqual(module.enrich(db, candidate, now)['10.1/trial'][0], '译文')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deepseek_trial_attempts').fetchone()[0], 1)
        finally:
            if old is None: path.unlink()
            else: path.write_text(old, encoding='utf-8')

    def test_peak_override_only_processes_pinned_trial(self):
        db = sqlite3.connect(':memory:')
        now = datetime.datetime(2026,11,24,15,0,tzinfo=ZoneInfo('Asia/Shanghai'))
        candidates = [({'doi':'10.1/trial','title':'trial'}, '2025-01-01', 'core'), ({'doi':'10.1/new','title':'new'}, '2026-11-24', 'core')]
        answer = {'choices':[{'message':{'content':json.dumps({'zh':'译文','summary':'简介'})}}]}
        path = module.Path(__file__).resolve().parent.parent / 'deepseek_top100.json'
        old = path.read_text(encoding='utf-8') if path.exists() else None
        try:
            path.write_text(json.dumps(['10.1/trial']), encoding='utf-8')
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test', 'DEEPSEEK_PEAK_TRIAL':'1', 'DEEPSEEK_TRIAL_ENABLED':'1'}), patch.object(module, 'find_abstract', return_value=('text', 'https://pubmed.ncbi.nlm.nih.gov/1/')), patch.object(module.urllib.request, 'urlopen', return_value=Response(json.dumps(answer).encode())) as request:
                result = module.enrich(db, candidates, now)
            self.assertEqual(request.call_count, 1)
            self.assertIn('10.1/trial', result)
            self.assertNotIn('10.1/new', result)
        finally:
            if old is None: path.unlink()
            else: path.write_text(old, encoding='utf-8')

if __name__ == '__main__':
    unittest.main()



