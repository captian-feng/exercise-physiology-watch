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
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test'}), patch.object(module.urllib.request, 'urlopen', return_value=Response(json.dumps(answer).encode())) as request:
            result = module.enrich(db, candidate, now)
            self.assertEqual(result['10.1000/example'], ('人体运动', ''))
            module.enrich(db, candidate, now)
            self.assertEqual(request.call_count, 1)

    def test_missing_key_and_old_record_do_not_call_api(self):
        db = sqlite3.connect(':memory:')
        now = datetime.datetime(2026,11,24,7,30,tzinfo=ZoneInfo('Asia/Shanghai'))
        with patch.dict(os.environ, {}, clear=True), patch.object(module.urllib.request, 'urlopen') as request:
            module.enrich(db, [({'doi':'10.1/example','title':'title'},'2026-11-24','core')], now)
            request.assert_not_called()

if __name__ == '__main__':
    unittest.main()

