"""Optional, bounded enrichment of already-screened records during off-peak hours."""
import datetime
import json
import os
from pathlib import Path
import re
from html.parser import HTMLParser
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')
START_DATE = '2026-11-24'
DAILY_LIMIT = 30
TRIAL_LIMIT = 120
TRIAL_PER_RUN = 40

def identity_for(item):
    return (item.get('doi') or '').strip().lower() or ('pmid:' + str(item.get('pmid') or ''))

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

class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(); self.values = {}
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'meta':
            values = dict(attrs)
            if values.get('name') and values.get('content'):
                self.values[values['name'].lower()] = values['content']

def find_abstract(item):
    """Try independent sources and verify identifiers before using their text."""
    pmid = str(item.get('pmid') or '')
    doi = (item.get('doi') or '').strip().lower()
    if pmid.isdigit():
        try:
            text = get_abstract(pmid)
            if text: return text, 'https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/'
        except Exception as exc:
            print('Abstract PubMed unavailable:', type(exc).__name__, flush=True)
    if re.fullmatch(r'10[.]3389/[a-z0-9.-]+', doi):
        url = 'https://www.frontiersin.org/articles/' + urllib.parse.quote(doi, safe='/') + '/full'
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; JournalWatch/1.0)'})
            with urllib.request.urlopen(req, timeout=15) as response:
                page = response.read(3000000).decode('utf-8', 'replace')
                final_url = response.geturl()
            meta = Metadata(); meta.feed(page)
            host = (urllib.parse.urlsplit(final_url).hostname or '').lower()
            if host in ('frontiersin.org', 'www.frontiersin.org') and meta.values.get('citation_doi', '').lower() == doi and meta.values.get('citation_abstract'):
                return meta.values['citation_abstract'], final_url
        except Exception as exc:
            print('Abstract Frontiers unavailable:', type(exc).__name__, flush=True)
    if doi:
        try:
            params = urllib.parse.urlencode({'query':'DOI:"' + doi + '"', 'format':'json', 'resultType':'core', 'pageSize':10})
            with urllib.request.urlopen('https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + params, timeout=15) as response:
                results = json.load(response).get('resultList', {}).get('result', [])
            for result in results:
                if result.get('doi', '').lower() == doi and result.get('abstractText'):
                    parser = MetadataText(); parser.feed(result['abstractText'])
                    source_id = result.get('id', '')
                    source = result.get('source', '')
                    if re.fullmatch(r'[A-Za-z0-9]+', source_id) and re.fullmatch(r'[A-Z]+', source):
                        return parser.text(), 'https://europepmc.org/article/' + source + '/' + source_id
        except Exception as exc:
            print('Abstract Europe PMC unavailable:', type(exc).__name__, flush=True)
    return '', ''

class MetadataText(HTMLParser):
    def __init__(self): super().__init__(); self.parts = []
    def handle_data(self, data): self.parts.append(data)
    def text(self): return ' '.join(self.parts).strip()

def enrich(db, candidates, now=None):
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_cache (identity TEXT PRIMARY KEY, title TEXT NOT NULL, zh TEXT NOT NULL, summary TEXT NOT NULL, day TEXT NOT NULL)')
    columns = {r[1] for r in db.execute('PRAGMA table_info(deepseek_cache)')}
    if 'abstract_source' not in columns:
        db.execute("ALTER TABLE deepseek_cache ADD COLUMN abstract_source TEXT NOT NULL DEFAULT ''")
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_attempts (day TEXT NOT NULL, identity TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_trial_attempts (day TEXT NOT NULL, identity TEXT NOT NULL)')
    trial_path = Path(__file__).resolve().parent / 'deepseek_top100.json'
    trial = json.loads(trial_path.read_text(encoding='utf-8')) if trial_path.exists() else []
    trial_rank = {value: index for index, value in enumerate(trial)}
    trial_used = db.execute('SELECT COUNT(*) FROM deepseek_trial_attempts').fetchone()[0]
    trial_run_used = 0
    candidates = sorted(candidates, key=lambda entry: trial_rank.get(identity_for(entry[0]), len(trial_rank)))
    key = os.environ.get('DEEPSEEK_API_KEY', '')
    fixed_now = now
    now = now or datetime.datetime.now(ZONE)
    day = now.astimezone(ZONE).date().isoformat()
    used = db.execute('SELECT COUNT(*) FROM deepseek_attempts WHERE day=?', (day,)).fetchone()[0]
    for item, seen, tier in candidates:
        if not key or not off_peak(fixed_now or datetime.datetime.now(ZONE)):
            break
        identity = identity_for(item)
        is_trial = identity in trial_rank
        if is_trial and (trial_used >= TRIAL_LIMIT or trial_run_used >= TRIAL_PER_RUN or db.execute('SELECT COUNT(*) FROM deepseek_trial_attempts WHERE identity=?', (identity,)).fetchone()[0] >= 2):
            continue
        if not is_trial and (used >= DAILY_LIMIT or not seen or seen < START_DATE):
            continue
        if identity == 'pmid:':
            continue
        cached = db.execute('SELECT summary FROM deepseek_cache WHERE identity=?', (identity,)).fetchone()
        if cached and cached[0]:
            continue
        title = item.get('title', '').strip()
        if not title:
            continue
        stage = 'abstract'
        try:
            abstract, abstract_source = find_abstract(item)
            if cached and not abstract:
                continue
            stage = 'glossary'
            hint = glossary_hint(title + ' ' + abstract)
            prompt = '翻译英文论文标题为简体中文。仅依据提供的摘要用中文简述研究对象、方法和主要结果，不要推测；没有摘要时简介返回空字符串。返回 JSON 对象，字段 zh 和 summary。\n术语参考：' + hint + '\n标题：' + title + '\n摘要：' + abstract[:12000]
            body = json.dumps({'model':'deepseek-flash','messages':[{'role':'user','content':prompt}], 'response_format':{'type':'json_object'}, 'thinking':{'type':'disabled'}, 'max_tokens':800, 'temperature':0.1}).encode('utf-8')
            req = urllib.request.Request('https://api.deepseek.com/chat/completions', data=body, headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json'}, method='POST')
            db.execute('INSERT INTO deepseek_attempts VALUES (?,?)', (day, identity))
            if is_trial:
                db.execute('INSERT INTO deepseek_trial_attempts VALUES (?,?)', (day, identity))
                trial_used += 1
                trial_run_used += 1
            db.commit()
            used += 1
            stage = 'api response'
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.loads(response.read())
            choice = payload['choices'][0]
            content = choice['message']['content']
            stage = 'model JSON (finish_reason=' + str(choice.get('finish_reason', 'unknown')) + ', length=' + str(len(content or '')) + ')'
            result = json.loads(content)
            zh = result.get('zh'); summary = result.get('summary', '')
            if not isinstance(zh, str) or not zh.strip() or not isinstance(summary, str):
                raise ValueError('Invalid model response')
            db.execute('INSERT OR REPLACE INTO deepseek_cache (identity,title,zh,summary,day,abstract_source) VALUES (?,?,?,?,?,?)', (identity, title, zh.strip(), summary.strip() if abstract else '', day, abstract_source))
            db.commit()
        except Exception as exc:
            print('DeepSeek enrichment skipped at', stage + ':', type(exc).__name__, flush=True)
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 402, 403, 429):
                break
            continue
    return {row[0]: (row[1], row[2], row[3]) for row in db.execute('SELECT identity, zh, summary, abstract_source FROM deepseek_cache')}



