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
            def __init__(self, payload, url):
                super().__init__(payload); self._url = url
            def geturl(self): return self._url
            @property
            def status(self): return 200
        page = b'<meta name="citation_doi" content="10.3389/fphys.2026.123"><meta name="citation_abstract" content="Human exercise study with physiological outcomes in trained athletes.">'
        def fake_urlopen(request, *args, **kwargs):
            if isinstance(request, str):
                raise OSError('offline')
            target = request.full_url
            if 'frontiersin.org' in target:
                return Page(page, 'https://www.frontiersin.org/example')
            return Page(b'not json', 'https://api.example.org/')
        with patch.object(module, 'get_abstract', side_effect=OSError('offline')), patch.object(module.urllib.request, 'urlopen', side_effect=fake_urlopen):
            text, source = module.find_abstract({'pmid':'123','doi':'10.3389/fphys.2026.123'})
        self.assertEqual(text, 'Human exercise study with physiological outcomes in trained athletes.')
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

    def test_full_pass_fills_missing_summary_and_checkpoints(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE deepseek_cache (identity TEXT PRIMARY KEY, title TEXT NOT NULL, zh TEXT NOT NULL, summary TEXT NOT NULL, day TEXT NOT NULL, abstract_source TEXT NOT NULL DEFAULT "")')
        db.execute("INSERT INTO deepseek_cache VALUES ('10.1/old','Old title','旧标题','','2026-11-24','')")
        answer = {'usage': {}, 'choices': [{'message': {'content': json.dumps({'zh': '人体运动研究', 'summary': '摘要简介'})}}]}
        rows = [({'doi': '10.1/old', 'title': 'Old title'}, '2025-01-01', 'core'),
                ({'doi': '10.1/new', 'title': 'New title'}, '2025-01-01', 'core')]
        env = {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_FULL': '1', 'DEEPSEEK_FULL_WORKERS': '2'}
        with patch.dict(os.environ, env), patch.object(module, 'find_abstract', side_effect=[('a sufficiently long abstract text', 'https://example.org/1'), ('', '')]), patch.object(module.urllib.request, 'urlopen', return_value=Response(json.dumps(answer).encode())) as request:
            result = module.enrich(db, rows, None)
        self.assertEqual(result['10.1/old'][1], '摘要简介')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM deepseek_full_attempts').fetchone()[0], 2)
        with patch.dict(os.environ, env), patch.object(module.urllib.request, 'urlopen') as request:
            module.enrich(db, rows, None)
            request.assert_not_called()

    def test_full_pass_deadline_stops_submitting_new_work(self):
        class Clock:
            def __init__(self):
                self.calls = 0
            def monotonic(self):
                self.calls += 1
                return 0 if self.calls <= 2 else 1801

        db = sqlite3.connect(':memory:')
        rows = [({'doi': '10.2/%d' % i, 'title': 'Title %d' % i}, '2025-01-01', 'core') for i in range(80)]
        calls = []
        def fake_worker(item, key):
            identity = module.identity_for(item)
            calls.append(identity)
            return identity, ('zh', 'summary', item['title'], '', False)
        env = {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_FULL': '1', 'DEEPSEEK_FULL_WORKERS': '2'}
        with patch.dict(os.environ, env), patch.object(module, 'time', Clock()), patch.object(module, '_full_worker', side_effect=fake_worker):
            module.enrich(db, rows, None)
        self.assertLess(len(calls), 20, 'deadline should cancel queued work instead of submitting every record')
        self.assertGreater(len(calls), 0)
        self.assertLessEqual(db.execute('SELECT COUNT(*) FROM deepseek_full_attempts').fetchone()[0], len(calls))

    def test_full_worker_retries_rate_limit(self):
        answer = {'usage': {}, 'choices': [{'message': {'content': json.dumps({'zh': '译文', 'summary': '简介'})}}]}
        err = module.urllib.error.HTTPError('https://api.deepseek.com/chat/completions', 429, 'rate limited', {}, io.BytesIO(b''))
        with patch.object(module, 'find_abstract', return_value=('a sufficiently long abstract text', 'https://example.org/1')), \
             patch.object(module.time, 'sleep') as sleep, \
             patch.object(module.urllib.request, 'urlopen', side_effect=[err, Response(json.dumps(answer).encode())]) as request:
            identity, outcome = module._full_worker({'doi': '10.3/retry', 'title': 'Title'}, 'test')
        self.assertEqual(identity, '10.3/retry')
        self.assertEqual(outcome[1], '简介')
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_error_marked_identity_is_retried(self):
        db = sqlite3.connect(':memory:')
        rows = [({'doi': '10.4/retry', 'title': 'Retry title'}, '2025-01-01', 'core')]
        calls = []
        def fake_worker(item, key):
            identity = module.identity_for(item)
            calls.append(identity)
            if len(calls) == 1:
                raise module.urllib.error.HTTPError('https://api.deepseek.com/chat/completions', 503, 'busy', {}, io.BytesIO(b''))
            return identity, ('译文', '简介', item['title'], '', False)
        env = {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_FULL': '1', 'DEEPSEEK_FULL_WORKERS': '1'}
        with patch.dict(os.environ, env), patch.object(module, '_full_worker', side_effect=fake_worker):
            module.enrich(db, rows, None)
            self.assertEqual(len(calls), 1)
            result = module.enrich(db, rows, None)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['10.4/retry'][1], '简介')

    def test_insufficient_balance_stops_run_without_marking_attempts(self):
        db = sqlite3.connect(':memory:')
        rows = [({'doi': '10.5/%d' % i, 'title': 'Title %d' % i}, '2025-01-01', 'core') for i in range(80)]
        calls = []
        def fake_worker(item, key):
            calls.append(module.identity_for(item))
            raise module.InsufficientBalance('balance exhausted')
        env = {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_FULL': '1', 'DEEPSEEK_FULL_WORKERS': '2'}
        with patch.dict(os.environ, env), patch.object(module, '_full_worker', side_effect=fake_worker):
            module.enrich(db, rows, None)
        self.assertGreater(len(calls), 0)
        self.assertLess(len(calls), 20, 'a 402 balance error should stop the run immediately')
        self.assertEqual(db.execute('SELECT COUNT(*) FROM deepseek_full_attempts').fetchone()[0], 0)

if __name__ == '__main__':
    unittest.main()



