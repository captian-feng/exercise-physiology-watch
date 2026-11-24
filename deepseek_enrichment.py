"""Enrichment of already-screened records; supports bounded and unlimited full passes."""
import datetime
import json
import os
from pathlib import Path
import re
from html.parser import HTMLParser
import time
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
FULL_VERSION = 1
USER_AGENT = 'Mozilla/5.0 (compatible; JournalWatch/1.0)'

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

class MetadataText(HTMLParser):
    def __init__(self): super().__init__(); self.parts = []
    def handle_data(self, data): self.parts.append(data)
    def text(self): return ' '.join(self.parts).strip()

def _get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)

def _abstract_crossref(doi):
    data = _get_json('https://api.crossref.org/works/' + urllib.parse.quote(doi, safe=''))
    message = data.get('message') or {}
    if (message.get('DOI') or '').strip().lower() != doi:
        return '', ''
    raw = message.get('abstract') or ''
    if not raw:
        return '', ''
    parser = MetadataText(); parser.feed(raw)
    text = parser.text()
    return (text, 'https://doi.org/' + doi) if text else ('', '')

def _abstract_openalex(doi):
    data = _get_json('https://api.openalex.org/works/doi:' + urllib.parse.quote(doi, safe=''))
    found = (data.get('doi') or '').strip().lower().replace('https://doi.org/', '')
    if found != doi:
        return '', ''
    inverted = data.get('abstract_inverted_index') or {}
    if not inverted:
        return '', ''
    positions = []
    for word, indexes in inverted.items():
        for index in indexes:
            positions.append((index, word))
    positions.sort()
    text = ' '.join(word for _, word in positions).strip()
    return (text, data.get('id') or 'https://doi.org/' + doi) if text else ('', '')

def _abstract_semantic_scholar(doi):
    url = ('https://api.semanticscholar.org/graph/v1/paper/DOI:'
           + urllib.parse.quote(doi, safe='') + '?fields=title,abstract,externalIds,url')
    data = _get_json(url)
    external = data.get('externalIds') or {}
    found = (external.get('DOI') or '').strip().lower()
    title = (data.get('title') or '').strip()
    if found != doi or (title and len(title) < 8):
        return '', ''
    text = (data.get('abstract') or '').strip()
    return (text, data.get('url') or 'https://www.semanticscholar.org/') if text else ('', '')

def _abstract_europepmc_by_pmid(pmid):
    params = urllib.parse.urlencode({'query': 'EXT_ID:' + pmid + ' AND SRC:MED', 'format': 'json', 'resultType': 'core', 'pageSize': 1})
    data = _get_json('https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + params)
    for result in data.get('resultList', {}).get('result', []):
        if str(result.get('pmid') or '') != pmid or not result.get('abstractText'):
            continue
        parser = MetadataText(); parser.feed(result['abstractText'])
        source_id, source = str(result.get('id') or ''), str(result.get('source') or '')
        if re.fullmatch(r'[A-Za-z0-9]+', source_id) and re.fullmatch(r'[A-Z]+', source):
            return parser.text(), 'https://europepmc.org/article/' + source + '/' + source_id
    return '', ''

def _abstract_publisher_page(item):
    """Read citation_abstract meta from the record's own URL; verify DOI when present."""
    url = str(item.get('url') or '')
    if not url.startswith(('http://', 'https://')):
        return '', ''
    doi = (item.get('doi') or '').strip().lower()
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=12) as response:
        if response.status >= 400:
            return '', ''
        page = response.read(3000000).decode('utf-8', 'replace')
        final_url = response.geturl()
    meta = Metadata(); meta.feed(page)
    page_doi = (meta.values.get('citation_doi') or '').strip().lower()
    if doi and page_doi and page_doi != doi:
        return '', ''
    text = (meta.values.get('citation_abstract') or '').strip()
    return (text, final_url) if text else ('', '')

def find_abstract(item):
    """Try every reliable source, in order; verify identifiers before using any text."""
    pmid = str(item.get('pmid') or '')
    doi = (item.get('doi') or '').strip().lower()
    attempts = []
    if pmid.isdigit():
        attempts.append(('PubMed', lambda: (get_abstract(pmid), 'https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/')))
        attempts.append(('Europe PMC PMID', lambda: _abstract_europepmc_by_pmid(pmid)))
    if doi:
        attempts.append(('Crossref', lambda: _abstract_crossref(doi)))
        attempts.append(('OpenAlex', lambda: _abstract_openalex(doi)))
        if os.environ.get('S2_API_KEY'):
            attempts.append(('Semantic Scholar', lambda: _abstract_semantic_scholar(doi)))
        attempts.append(('Europe PMC DOI', lambda: _europepmc_by_doi(doi)))
        if re.fullmatch(r'10[.]3389/[a-z0-9.-]+', doi):
            attempts.append(('Frontiers', lambda: _frontiers_abstract(doi)))
    attempts.append(('publisher page', lambda: _abstract_publisher_page(item)))
    for name, lookup in attempts:
        try:
            text, source = lookup()
        except Exception as exc:
            print('Abstract ' + name + ' unavailable:', type(exc).__name__, flush=True)
            continue
        if isinstance(text, str) and len(text.strip()) >= 30:
            return text.strip(), source or ''
    return '', ''

def _frontiers_abstract(doi):
    url = 'https://www.frontiersin.org/articles/' + urllib.parse.quote(doi, safe='/') + '/full'
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=12) as response:
        page = response.read(3000000).decode('utf-8', 'replace')
        final_url = response.geturl()
    meta = Metadata(); meta.feed(page)
    host = (urllib.parse.urlsplit(final_url).hostname or '').lower()
    if host not in ('frontiersin.org', 'www.frontiersin.org'):
        return '', ''
    if (meta.values.get('citation_doi') or '').strip().lower() != doi:
        return '', ''
    text = (meta.values.get('citation_abstract') or '').strip()
    return (text, final_url) if text else ('', '')

def _europepmc_by_doi(doi):
    params = urllib.parse.urlencode({'query': 'DOI:"' + doi + '"', 'format': 'json', 'resultType': 'core', 'pageSize': 10})
    data = _get_json('https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + params)
    for result in data.get('resultList', {}).get('result', []):
        if (result.get('doi') or '').strip().lower() != doi or not result.get('abstractText'):
            continue
        parser = MetadataText(); parser.feed(result['abstractText'])
        source_id, source = str(result.get('id') or ''), str(result.get('source') or '')
        if re.fullmatch(r'[A-Za-z0-9]+', source_id) and re.fullmatch(r'[A-Z]+', source):
            return parser.text(), 'https://europepmc.org/article/' + source + '/' + source_id
    return '', ''

def _positive_int(name, default):
    """Read a bounded integer setting; invalid or non-positive values use the default."""
    try:
        value = int(os.environ.get(name, ''))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default

def _unlimited_requested():
    """A negative batch or budget input means the user explicitly removed all caps."""
    for name in ('DEEPSEEK_BACKFILL_BATCH', 'DEEPSEEK_BACKFILL_BUDGET', 'DEEPSEEK_FULL'):
        raw = os.environ.get(name, '')
        if raw == '1':
            return True
        try:
            if int(raw) < 0:
                return True
        except (TypeError, ValueError):
            pass
    return False

def _full_worker(item, key):
    """Fetch abstract and call DeepSeek once; no database access in worker threads."""
    identity = identity_for(item)
    title = (item.get('title') or '').strip()
    if not title or identity == 'pmid:':
        return identity, None
    abstract, abstract_source = find_abstract(item)
    if not abstract:
        return identity, ('', '', '', abstract_source, True)
    hint = glossary_hint(title + ' ' + abstract)
    prompt = ('翻译英文论文标题为简体中文。仅依据提供的摘要用中文简述研究对象、方法和主要结果，不要推测；'
              '没有摘要时简介返回空字符串。返回 JSON 对象，字段 zh 和 summary。\n术语参考：' + hint
              + '\n标题：' + title + '\n摘要：' + abstract[:12000])
    body = json.dumps({'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': prompt}],
                       'response_format': {'type': 'json_object'}, 'thinking': {'type': 'disabled'},
                       'max_tokens': 800, 'temperature': 0.1}).encode('utf-8')
    req = urllib.request.Request('https://api.deepseek.com/chat/completions', data=body,
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                                 method='POST')
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read())
    usage = payload.get('usage', {})
    print('DeepSeek usage:', json.dumps({k: usage.get(k, 0) for k in
          ('prompt_tokens', 'completion_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')}), flush=True)
    choice = payload['choices'][0]
    result = json.loads(choice['message']['content'])
    zh, summary = result.get('zh'), result.get('summary', '')
    if not isinstance(zh, str) or not zh.strip() or not isinstance(summary, str):
        raise ValueError('Invalid model response')
    return identity, (zh.strip(), summary.strip(), title, abstract_source, False)

def enrich_full(db, candidates, key, day, now=None):
    """Unrestricted pass over every site-visible record lacking a summary.

    No per-run or lifetime call cap, no off-peak gate, no first-seen date gate.
    Progress is checkpointed so an interrupted run resumes instead of restarting.
    A wall-clock deadline only prevents losing the whole run to GitHub's job limit;
    re-dispatch the workflow to continue.
    """
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_full_attempts (identity TEXT PRIMARY KEY, day TEXT NOT NULL)')
    cached = {row[0] for row in db.execute('SELECT identity FROM deepseek_cache WHERE length(summary) > 0')}
    done = {row[0] for row in db.execute('SELECT identity FROM deepseek_full_attempts')}
    pending = [entry for entry in candidates if identity_for(entry[0]) not in cached and identity_for(entry[0]) not in done]
    workers = _positive_int('DEEPSEEK_FULL_WORKERS', 20)
    deadline_seconds = _positive_int('DEEPSEEK_RUN_SECONDS', 1800)
    deadline = time.monotonic() + deadline_seconds
    print(f'DeepSeek full pass: {len(pending)} records need a summary '
          f'({workers} workers, {deadline_seconds}s window)', flush=True)
    ok = no_abstract = errors = submitted = 0
    queue = iter(pending)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}

        def fill():
            nonlocal submitted
            while len(futures) < workers * 2:
                try:
                    item, seen, tier = next(queue)
                except StopIteration:
                    return
                futures[pool.submit(_full_worker, item, key)] = identity_for(item)
                submitted += 1

        fill()
        while futures:
            left = deadline - time.monotonic()
            if left <= 0:
                print('DeepSeek full pass: time window reached, checkpointing progress', flush=True)
                for future in futures:
                    future.cancel()
                break
            done_set, _ = wait(futures, timeout=min(left, 30), return_when=FIRST_COMPLETED)
            if not done_set:
                continue
            for future in done_set:
                identity = futures.pop(future)
                try:
                    outcome = future.result()
                except Exception as exc:
                    print('DeepSeek full pass error for', identity, type(exc).__name__, flush=True)
                    errors += 1
                    db.execute('INSERT OR REPLACE INTO deepseek_full_attempts VALUES (?,?)', (identity, day + ':error'))
                else:
                    if outcome[1] is None:
                        db.execute('INSERT OR REPLACE INTO deepseek_full_attempts VALUES (?,?)', (identity, day))
                    else:
                        zh, summary, title, source, missing = outcome[1]
                        if missing:
                            no_abstract += 1
                            db.execute('INSERT OR REPLACE INTO deepseek_full_attempts VALUES (?,?)', (identity, day + ':noabstract'))
                        else:
                            ok += 1
                            db.execute('INSERT OR REPLACE INTO deepseek_cache (identity,title,zh,summary,day,abstract_source) VALUES (?,?,?,?,?,?)',
                                       (identity, title, zh, summary, day, source))
                            db.execute('INSERT OR REPLACE INTO deepseek_full_attempts VALUES (?,?)', (identity, day))
                db.commit()
            fill()
    remaining = db.execute('SELECT COUNT(*) FROM deepseek_cache WHERE length(summary) = 0').fetchone()[0]
    attempted = db.execute('SELECT COUNT(*) FROM deepseek_full_attempts').fetchone()[0]
    print(f'DeepSeek full pass: {submitted} submitted, {ok} summaries added, {no_abstract} without abstract, '
          f'{errors} errors this run; {attempted} checked total; '
          f'{remaining} cached entries still without summary', flush=True)
    return {row[0]: (row[1], row[2], row[3]) for row in db.execute(
        'SELECT identity, zh, summary, abstract_source FROM deepseek_cache')}

def enrich(db, candidates, now=None):
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_cache (identity TEXT PRIMARY KEY, title TEXT NOT NULL, zh TEXT NOT NULL, summary TEXT NOT NULL, day TEXT NOT NULL)')
    columns = {r[1] for r in db.execute('PRAGMA table_info(deepseek_cache)')}
    if 'abstract_source' not in columns:
        db.execute("ALTER TABLE deepseek_cache ADD COLUMN abstract_source TEXT NOT NULL DEFAULT ''")
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_attempts (day TEXT NOT NULL, identity TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_trial_attempts (day TEXT NOT NULL, identity TEXT NOT NULL)')
    # Backfill covers only records already shown on the site. Progress is tracked
    # separately so a retry never starts from the beginning or re-spends on a
    # paper whose enrichment previously failed.
    db.execute('CREATE TABLE IF NOT EXISTS deepseek_backfill_attempts (identity TEXT PRIMARY KEY, day TEXT NOT NULL)')
    full = _unlimited_requested()
    backfill = os.environ.get('DEEPSEEK_BACKFILL') == '1'
    key = os.environ.get('DEEPSEEK_API_KEY', '')
    fixed_now = now
    now = now or datetime.datetime.now(ZONE)
    day = now.astimezone(ZONE).date().isoformat()
    if full:
        if not key:
            print('DeepSeek full pass: no API key; nothing to do', flush=True)
            return {row[0]: (row[1], row[2], row[3]) for row in db.execute(
                'SELECT identity, zh, summary, abstract_source FROM deepseek_cache')}
        return enrich_full(db, candidates, key, day, now)
    backfill_run_limit = _positive_int('DEEPSEEK_BACKFILL_BATCH', 300)
    backfill_budget = _positive_int('DEEPSEEK_BACKFILL_BUDGET', 1200)
    trial_path = Path(__file__).resolve().parent / 'deepseek_top100.json'
    # The completed trial remains disabled unless explicitly enabled again.
    trial = json.loads(trial_path.read_text(encoding='utf-8')) if trial_path.exists() and os.environ.get('DEEPSEEK_TRIAL_ENABLED') == '1' else []
    trial_rank = {value: index for index, value in enumerate(trial)}
    trial_used = db.execute('SELECT COUNT(*) FROM deepseek_trial_attempts').fetchone()[0]
    trial_run_used = 0
    if backfill:
        # Only the site's screened candidates are passed in; never widen the set
        # to excluded records. Older first-seen dates are eligible here.
        done = {row[0] for row in db.execute('SELECT identity FROM deepseek_backfill_attempts')}
        candidates = [entry for entry in candidates if identity_for(entry[0]) not in done]
        print(f'DeepSeek backfill: {len(candidates)} site records pending', flush=True)
    else:
        candidates = sorted(candidates, key=lambda entry: trial_rank.get(identity_for(entry[0]), len(trial_rank)))
    peak_trial = os.environ.get('DEEPSEEK_PEAK_TRIAL') == '1'
    used = db.execute('SELECT COUNT(*) FROM deepseek_attempts WHERE day=?', (day,)).fetchone()[0]
    backfill_run_used = 0
    backfill_total = db.execute('SELECT COUNT(*) FROM deepseek_backfill_attempts').fetchone()[0]
    for item, seen, tier in candidates:
        if not key:
            break
        identity = identity_for(item)
        is_trial = identity in trial_rank
        if not off_peak(fixed_now or datetime.datetime.now(ZONE)) and not (peak_trial and is_trial):
            continue
        if is_trial and (trial_used >= TRIAL_LIMIT or trial_run_used >= (100 if peak_trial else TRIAL_PER_RUN) or db.execute('SELECT COUNT(*) FROM deepseek_trial_attempts WHERE identity=?', (identity,)).fetchone()[0] >= 2):
            continue
        if backfill:
            if backfill_run_used >= backfill_run_limit or backfill_total >= backfill_budget:
                break
        elif not is_trial and (used >= DAILY_LIMIT or not seen or seen < START_DATE):
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
            if backfill:
                db.execute('INSERT OR REPLACE INTO deepseek_backfill_attempts VALUES (?,?)', (identity, day))
                backfill_run_used += 1
                backfill_total += 1
            db.commit()
            used += 1
            stage = 'api response'
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.loads(response.read())
            usage = payload.get('usage', {})
            print('DeepSeek usage:', json.dumps({k: usage.get(k, 0) for k in ('prompt_tokens', 'completion_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')}), flush=True)
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
    if backfill:
        print(f'DeepSeek backfill: {backfill_run_used} called this run, '
              f'{backfill_total}/{backfill_budget} lifetime budget used', flush=True)
    return {row[0]: (row[1], row[2], row[3]) for row in db.execute('SELECT identity, zh, summary, abstract_source FROM deepseek_cache')}



