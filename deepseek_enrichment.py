"""Optional, bounded enrichment of already-screened records during off-peak hours."""
import datetime
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')
START_DATE = '2026-11-24'
DAILY_LIMIT = 30

def glossary_hint(text):
    path = Path(__file__).resolve().parent / 'exercise_glossary.json'
    if not path.exists():
        return ''
    terms = json.loads(path.read_text(encoding='utf-8')).get('terms', [])
    matches = []
    for term in terms:
        en, zh = term.get('en', ''), term.get('zh', '')
        if en and zh and re.search(r'(?<!\w)' + re.escape(en) + r'(?!\w)', text, re.I):
            matches.append(en + '：' + zh)
    return '；'.join(matches[:30])

def off_peak(now):
    now = now.astimezone(ZONE)
    if now.weekday() >= 5:
        return True
    minutes = now.hour * 60 + now.minute
    return not (9 * 60 <= minutes < 12 * 60 or 14 * 60 <= minutes < 18 * 60)

def get_abstract(pmid):
    params = urllib.parse.urlencode({'db': 'pubmed', 'id': pmid, 'retmode': 'xml'})
    with urllib.request.urlopen('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?' + params, timeout=15) as response:
        root = ET.fromstring(response.read())
    article = root.find('PubmedArticle')
    if article is None or article.findtext('./MedlineCitation/PMID') != pmid:
        raise ValueError('PubMed identity mismatch')
    return ' '.join(' '.join(n.itertext()) for n in article.findall('./MedlineCitation/Article/Abstract/AbstractText')).strip()

def enrich(db, candidates, now=None):
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_cache (identity TEXT PRIMARY KEY, title TEXT NOT NULL, zh TEXT NOT NULL, summary TEXT NOT NULL, day TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_attempts (day TEXT NOT NULL, identity TEXT NOT NULL)')
    key = os.environ.get('DEEPSEEK_API_KEY', '')
    fixed_now = now
    now = now or datetime.datetime.now(ZONE)
    day = now.astimezone(ZONE).date().isoformat()
    used = db.execute('SELECT COUNT(*) FROM deepseek_attempts WHERE day=?', (day,)).fetchone()[0]
    for item, seen, tier in candidates:
        if not key or not off_peak(fixed_now or datetime.datetime.now(ZONE)) or used >= DAILY_LIMIT:
            break
        identity = (item.get('doi') or '').strip().lower() or ('pmid:' + str(item.get('pmid') or ''))
        if identity == 'pmid:' or not seen or seen < START_DATE:
            continue
        if db.execute('SELECT 1 FROM deepseek_cache WHERE identity=?', (identity,)).fetchone():
            continue
        title = item.get('title', '').strip()
        if not title:
            continue
        try:
            pmid = str(item.get('pmid') or '')
            abstract = get_abstract(pmid) if pmid.isdigit() else ''
            hint = glossary_hint(title + ' ' + abstract)
            prompt = '翻译英文论文标题为简体中文。仅依据提供的摘要用中文简述研究对象、方法和主要结果，不要推测；没有摘要时简介返回空字符串。返回 JSON 对象，字段 zh 和 summary。\n术语参考：' + hint + '\n标题：' + title + '\n摘要：' + abstract[:12000]
            body = json.dumps({'model':'deepseek-flash','messages':[{'role':'user','content':prompt}], 'response_format':{'type':'json_object'}, 'thinking':{'type':'disabled'}, 'max_tokens':500, 'temperature':0.1}).encode('utf-8')
            req = urllib.request.Request('https://api.deepseek.com/chat/completions', data=body, headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json'}, method='POST')
            db.execute('INSERT INTO deepseek_attempts VALUES (?,?)', (day, identity))
            db.commit()
            used += 1
            with urllib.request.urlopen(req, timeout=45) as response:
                content = json.loads(response.read())['choices'][0]['message']['content']
            result = json.loads(content)
            zh = result.get('zh'); summary = result.get('summary', '')
            if not isinstance(zh, str) or not zh.strip() or not isinstance(summary, str):
                raise ValueError('Invalid model response')
            db.execute('INSERT OR REPLACE INTO deepseek_cache VALUES (?,?,?,?,?)', (identity, title, zh.strip(), summary.strip() if abstract else '', day))
            db.commit()
        except Exception as exc:
            print('DeepSeek enrichment skipped:', type(exc).__name__, flush=True)
            break
    return {row[0]: (row[1], row[2]) for row in db.execute('SELECT identity, zh, summary FROM deepseek_cache')}

