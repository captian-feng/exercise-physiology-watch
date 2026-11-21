"""Group journal records by theme and translate titles with an offline model.

The theme list used to have eight coarse buckets and left roughly a third of the
archive in "其他或题名信息不足". It now separates the themes the lab actually
reads -- environment physiology, strength and muscle adaptation, brain and
mental health, immune and molecular adaptation, special populations, equipment
and biomechanics, public health and policy -- so fewer records fall through to
the catch-all bucket.
"""

from collections import defaultdict
from pathlib import Path
import re

from terminology import correct, matched_terms

MODEL = Path(__file__).resolve().parent / "models" / "translate-en_zh-1_9"
TOPIC_PATTERNS = {
    "临界功率、耐力与氧摄取动力学": (
        r"critical (?:power|speed)|oxygen uptake kinetics|vo[₂2]\s?kinetics|"
        r"ventilatory threshold|lactate threshold|maximal lactate steady state|"
        r"anaerobic threshold|time to exhaustion|aerobic capacity|endurance performance|"
        r"pacing|pacing strategy|fatigue resistance|durability"
    ),
    "环境生理：热、冷、高原与缺氧": (
        r"heat (?:acclim\w*|stress|strain|exposure|tolerance)|thermoregulat\w*|"
        r"core temperature|body temperature|skin temperature|hyperthermi\w*|"
        r"hypothermi\w*|cold (?:exposure|water|stress|acclim\w*)|"
        r"altitude|hypoxi\w*|hypobaric|hyperbaric|dehydrat\w*|hydration|"
        r"fluid (?:balance|intake|loss|replacement)|sweat\w*|environmental"
    ),
    "运动与脑认知、心理健康": (
        r"cognit\w*|brain|neuro(?:science|nal|n)?\b|mental health|mood|anxiety|depress\w*|"
        r"psychological|psycholog\w*|executive function|memory|attention|"
        r"well-?being|quality of life|self-?efficacy|motivation|behaviou?r change|"
        r"self[- ]regulation|burnout|resilience|"
        r"cognitive (?:function|performance|decline|impairment)|neurodegenerat\w*"
    ),
    "免疫、炎症与分子适应": (
        r"immun\w*|inflamm\w*|cytokine\w*|microbiome|gut (?:microbiota|bacteria)|"
        r"exosome\w*|extracellular vesicle\w*|mirna\w*|microrna\w*|lncrna\w*|"
        r"transcriptom\w*|proteom\w*|metabolom\w*|epigen\w*|gene expression|"
        r"signal(?:l)?ing|molecular|cellular|mitochondrial (?:biogenesis|function|quality)|"
        r"oxidative stress|antioxidant|aging|ageing|longevity|hallmark\w*|"
        r"mimetic|senescence|telomere\w*|autophagy|mitophagy|heat shock"
    ),
    "特殊人群与生命周期": (
        r"pregnan\w*|postpartum|placenta\w*|maternal|pediatric|paediatric|"
        r"pre-?school|children|adolescen\w*|youth|juvenile|older (?:adults?|people|women|men)|"
        r"middle-?aged|menopaus\w*|postmenopaus\w*|masters? athletes?|aged\b|"
        r"menstru\w*|disabilit\w*|para-?athlet\w*|wheelchair|amputee|spinal cord|"
        r"impairment|intellectual disability|transgender|sex difference\w*|"
        r"female athlete|male athlete|puberty|master\w* athlete"
    ),
    "骨骼、结缔组织与损伤康复": (
        r"injur\w*|concussion\w*|rehabilitat\w*|return to (?:sport|play)|"
        r"tendinopath\w*|tendon\w*|ligament\w*|anterior cruciate|\bacl\b|"
        r"bone (?:mineral|density|health|mass|turnover)|osteo\w*|fracture\w*|"
        r"cartilage|meniscus|joint|sprain|overuse|physical therapy|"
        r"impairment|classification"
    ),
    "力量与肌肉适应": (
        r"strength|hypertroph\w*|resistance train\w*|powerlift\w*|weightlift\w*|"
        r"muscle (?:mass|size|thickness|cross-sectional area|protein synthesis|damage|"
        r"activation|architect\w*|fatigue|glycogen|oxidative)|sarcopenia|atroph\w*|"
        r"plyometric|sprint train\w*|velocity-?based|one-?repetition maximum|\b1rm\b|"
        r"maximal (?:strength|power)|force[- ]velocity|rate of force development|"
        r"electromyogra\w*|\bemg\b|motor unit|neuromuscul\w*|myoelectric|"
        r"knee extensor|plantar flexor|eccentric|mechanical load\w*|sarcomer\w*|"
        r"contractile|stretch[- ]shorten|kicking|throwing|sprinting|sprint speed"
    ),
    "可穿戴设备、运动监测与数据建模": (
        r"wearab\w*|acceleromet\w*|gyroscop\w*|actigraph\w*|smartwatch|smart ring|"
        r"inertial measurement|global positioning|\bgps\b|\bsensors?\b|"
        r"machine learning|deep learning|artificial intelligence|neural network|"
        r"data[ -]driven|load monitoring|readiness score|heart rate variabilit|\bhrv\b|"
        r"step count|mobile (?:app|health)|digital (?:health|biomarker)|"
        r"photoplethysmograph\w*|device[- ]measured"
    ),
    "生物力学、装备与运动控制": (
        r"biomechanic\w*|kinematic\w*|kinetic\w*|joint moment|torque|ground reaction|"
        r"force plate|gait\b|walking|running (?:kinematic|biomechanic|mechanics)|"
        r"balance|postur\w*|stabil\w*|motor control|motor learning|coordination|"
        r"movement (?:pattern|analysis|quality|variability)|motion (?:capture|analysis)|"
        r"proprioception|proprioceptive|landing|jump(?:ing)?|sprint mechanic\w*|"
        r"muscle[ -]tendon|fascicle|pennation|stiffness|"
        r"footwear|shoe\w*|spike\w*|apparel|garment\w*|compression|equipment|"
        r"exoskeleton|technique|treadmill|ergometer|change[- ]of[- ]direction|agility"
    ),
    "心肺与整合生理": (
        r"cardiac|cardiovascular|heart rate|stroke volume|cardiac output|"
        r"blood (?:pressure|flow|volume|vessel)|vascular|endothelial|arterial|"
        r"respirat\w*|pulmonary|ventilat\w*|gas exchange|circulat\w*|"
        r"inspiratory|expiratory|respiratory muscle|"
        r"oxygen (?:uptake|consumption|delivery|extraction|saturation)|"
        r"ha?emodynamic\w*|oxygenation|hematolog\w*|blood volume|"
        r"autonomic|sympathetic|parasympathetic|baroreflex"
    ),
    "营养、能量代谢与补剂": (
        r"nutrition|supplement\w*|caffeine|creatine|beta-?alanine|nitrate|"
        r"carbohydrat\w*|protein (?:intake|supplement|synthesis|dose)|amino acid\w*|"
        r"diet\w*|energy (?:intake|expenditure|availability|deficit|balance)|"
        r"glycogen|ketone\w*|fat oxidation|substrate (?:oxidation|utilization)|"
        r"metabol\w*|body composition|body fat|adipos\w*|weight (?:loss|gain|management)|"
        r"fasting|low energy availability|\bred-?s\b|hydration strategy|"
        r"thermogenesis|metabolic rate|nutrient\w*|feeding|food|caloric|"
        r"hepatic steatosis|liver fat|dosing"
    ),
    "训练负荷、恢复与竞技表现": (
        r"training load|training impulse|session[ -]rpe|periodi[sz]ation|taperi\w*|"
        r"overreach\w*|overtrain\w*|recovery|readiness|detrain\w*|"
        r"workload|training (?:volume|intensity|frequency|program\w*|intervention|"
        r"method\w*|status|cycle|session|practice|week)|"
        r"perceived exertion|\brpe\b|training monotony|acute:chronic|"
        r"competition|tournament|match\w*|game\w*|locomotor|external load|"
        r"internal load|technical (?:action|performance|demand)|team sport|"
        r"small-sided|microdos\w*|sport[- ]specific|weekly (?:load|volume)|"
        r"sport performance|athletic performance|performance (?:analysis|profile)|"
        r"high[- ]intensity interval|interval train\w*|concurrent train\w*|"
        r"plyometric train\w*|strength and conditioning|sleep|"
        r"playing position|talent (?:identification|development)|draft|"
        r"physical (?:predictors|fitness|testing)|selection"
    ),
    "运动与公共卫生、政策与教育": (
        r"public health|policy|polic\w*|governance|equity|inequalit\w*|"
        r"racism|ethnic\w*|gender|socioeconomic|social\w*|"
        r"sustainab\w*|climate|environmental impact|carbon|travel distance|"
        r"physical (?:education|literacy)|school|curricul\w*|coach(?:ing|es)?|"
        r"guideline\w*|consensus|position stand|surveillance|"
        r"promotion|adherence|compliance|doping|"
        r"replicab\w*|research (?:method|practice|quality)|meta-research|reporting|"
        r"transparen\w*|peer review"
    ),
    "体力活动、健康与人群干预": (
        r"physical activit\w*|sedentar\w*|sitting|inactiv\w*|"
        r"exercise (?:intervention|prescription|program\w*|referral)|"
        r"health (?:outcome\w*|benefit\w*|promotion)|"
        r"mortality|morbidity|risk|incidence|prevalence|"
        r"cohort|longitudinal|cross-sectional|population|epidemiolog\w*|"
        r"steps? count|daily steps|movement behaviou?r\w*|24-?hour movement|"
        r"smoking|alcohol|screen time|sedentary time"
    ),
}
PATTERNS = {topic: re.compile(pattern, re.IGNORECASE) for topic, pattern in TOPIC_PATTERNS.items()}
CROSS_JOURNAL_TOPICS = {
    "临界功率与速度": "临界功率、耐力与氧摄取动力学",
    "氧摄取动力学": "临界功率、耐力与氧摄取动力学",
    "训练负荷": "训练负荷、恢复与竞技表现",
    "可穿戴运动监测": "可穿戴设备、运动监测与数据建模",
}
OTHER = "其他或题名信息不足"
PUBLICATION_NOTICE = "编辑信息、勘误与撤稿"
NOTICE_PATTERN = re.compile(
    r"^(?:correction(?: to)?|erratum|corrigendum|retraction|acknowledg\w*|"
    r"editorial board|masthead|table of contents|response to|reply to|comment on|"
    r"commentary on|letter)\b",
    re.IGNORECASE,
)
SUBSTITUTIONS = {
    "关键功率": "临界功率", "关键力量": "临界功率", "临界电力": "临界功率",
    "关键速度": "临界速度", "氧吸收动力学": "氧摄取动力学",
    "随机控制试验": "随机对照试验", "随机受控试验": "随机对照试验",
    "吸氧动力学": "氧摄取动力学", "间隔训练": "间歇训练",
    "定居行为": "久坐行为", "沉积行为": "久坐行为",
    "系统审查": "系统综述", "系统评价和荟萃分析": "系统综述与荟萃分析",
}
# Residual English the decoder leaves in an otherwise Chinese sentence. The
# boundaries are ASCII so Chinese characters next to the fragment are kept.
LEFTOVERS = [
    (re.compile(r"(?<![A-Za-z])(?:versus|vs\.?)(?![A-Za-z])", re.IGNORECASE), "对比"),
    (re.compile(r"(?<![A-Za-z])and(?![A-Za-z])", re.IGNORECASE), "与"),
    (re.compile(r"(?<![A-Za-z])or(?![A-Za-z])"), "或"),
    (re.compile(r"(?<![A-Za-z])the(?![A-Za-z])", re.IGNORECASE), ""),
    (re.compile(r"(?<![A-Za-z])for(?![A-Za-z])", re.IGNORECASE), ""),
    (re.compile(r"(?<![A-Za-z])meta[-\s]+", re.IGNORECASE), "荟萃"),
    (re.compile(r"(?<![A-Za-z])max(?![A-Za-z])", re.IGNORECASE), "最大"),
    (re.compile(r"(?<![A-Za-z])beyond(?![A-Za-z])", re.IGNORECASE), "超越"),
    (re.compile(r"(?<![A-Za-z])analysis(?![A-Za-z])", re.IGNORECASE), "分析"),
    (re.compile(r"(?<![A-Za-z])min(?![A-Za-z])", re.IGNORECASE), "分钟"),
    (re.compile(r"\s{2,}"), " "),
    (re.compile(r"\s+([,，。;；:：])"), r"\1"),
    # Term replacement inserts Chinese where English stood, and the decoder also
    # drops spaces mid-sentence; Chinese does not use a space between characters.
    (re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])"), ""),
]


def topic_for(item):
    title = item["title"].strip()
    if NOTICE_PATTERN.match(title):
        return PUBLICATION_NOTICE
    known = set(item.get("topics", ()))
    votes = {
        topic: sum(1 for _ in pattern.finditer(title))
        + 3 * sum(CROSS_JOURNAL_TOPICS.get(tag) == topic for tag in known)
        for topic, pattern in PATTERNS.items()
    }
    strongest = max(votes, key=votes.get)
    return strongest if votes[strongest] else OTHER


def grouped(items, journal_order=()):
    by_journal = defaultdict(lambda: defaultdict(list))
    for item in items:
        name = item.get("journal") or item.get("venue") or "期刊待核实"
        by_journal[name][topic_for(item)].append(item)
    positions = {name: index for index, name in enumerate(journal_order)}
    topic_order = (*PATTERNS, PUBLICATION_NOTICE, OTHER)
    return [
        (name, [(topic, by_journal[name][topic]) for topic in topic_order if topic in by_journal[name]])
        for name in sorted(by_journal, key=lambda name: (positions.get(name, len(positions)), name.casefold()))
    ]


def degenerate(text):
    """Detect a decoding loop such as '与男性的活体活体活体活体...'.

    A neural decoder occasionally locks onto one token and repeats it (classic
    repetition collapse), which fills the rest of the sentence with one n-gram.
    Such output is dominated by a short repeated fragment and easy to detect.
    """
    size = len(text)
    if size < 12:
        return False
    for width in (2, 3, 4):
        counts = {}
        for index in range(size - width + 1):
            gram = text[index:index + width]
            counts[gram] = counts.get(gram, 0) + 1
        gram, count = max(counts.items(), key=lambda pair: pair[1])
        if count >= 4 and count * width / size > 0.35:
            return True
    return False


# Legitimate Chinese reduplication; collapsing these would damage correct text.
REDUPLICATION = {
    "常常", "渐渐", "刚刚", "慢慢", "人人", "个个", "处处", "时时", "天天", "年年",
    "纷纷", "屡屡", "恰恰", "偏偏", "往往", "稍稍", "微微", "略略", "统统", "本本",
    "条条", "件件", "种种", "层层", "步步", "声声", "字字", "句句", "家家", "户户",
    "村村", "默默", "悄悄", "偷偷", "牢牢", "紧紧", "死死", "好好", "多多", "大大",
    "小小", "高高", "快快", "轻轻", "重重", "深深", "远远", "久久", "长长", "短短",
    "满满", "空空", "看看", "想想", "试试", "说说", "走走", "坐坐", "谈谈",
}
REPEATED_UNIT = re.compile(r"([\u4e00-\u9fff]{2,3})\1")
LEFT_OVER_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
# Titles often separate a descriptive clause from the finding with a colon or a
# dash; decoding the pieces separately stops the model from drifting.
SEGMENT_SPLIT = re.compile(r"(?<=[:;])\s+|\s+[–—]\s+")


def collapse_repeats(text):
    """Undo the decoder's local word doubling ('运动运动特征', '断层断层断层').

    Phrases like '常常' or '看看' are real Chinese and are left alone; anything
    else repeated back to back is a decoding artifact.
    """
    def replace(match):
        return match.group(0) if match.group(1) in REDUPLICATION else match.group(1)

    previous = None
    while previous != text:
        previous = text
        text = REPEATED_UNIT.sub(replace, text)
    return text


def polish(title, chinese):
    for before, after in SUBSTITUTIONS.items():
        chinese = chinese.replace(before, after)
    if "cyclist" in title.lower():
        chinese = chinese.replace("循环者", "自行车运动员")
    if "epigenetic" in title.lower():
        chinese = chinese.replace("遗传学和遗传学", "遗传与表观遗传")
    # Function words and half-translated fragments the decoder leaves behind
    # ("Blood Flow Restriction versus ...", "Network Meta-analysis"). Bounded by
    # ASCII letters so Chinese text is never touched.
    for pattern, replacement in LEFTOVERS:
        chinese = pattern.sub(replacement, chinese)
    return collapse_repeats(correct(title, chinese))


def truncated(title, chinese):
    """True when the translation covers only a fragment of the title.

    Chinese is denser than English, but a ratio this low means the decoder
    stopped early -- e.g. a long title rendered as just "血管衰老?".
    """
    if len(title) < 40:
        return False
    return len(chinese) < len(title) * 0.20


def quality_score(title, chinese):
    """Rank candidate translations without a reference.

    Glossary coverage is the strongest signal available offline: if the title
    names a term the glossary knows, a good translation uses its approved
    Chinese. Leftovers, loops, doubled words and truncation subtract.
    """
    terms = matched_terms(title)
    score = 2 * sum(1 for term in terms if term["zh"] in chinese)
    score -= 3 * len(LEFT_OVER_WORD.findall(chinese))
    score -= 6 if degenerate(chinese) else 0
    score -= 3 if REPEATED_UNIT.search(chinese) else 0
    score -= 3 if truncated(title, chinese) else 0
    return score


def assemble(parts, pieces):
    """Join translated segments back with Chinese punctuation."""
    text = ""
    for index, piece in enumerate(pieces):
        text += piece
        if index < len(pieces) - 1:
            text += "：" if parts[index].rstrip().endswith((":", "：")) else "；"
    return text


def translate_batch(engine, sp, titles):
    """Pick the best of several decoding attempts per title.

    Beam search returns near-duplicate hypotheses, so a random-sampling pass is
    decoded as well: it explores renderings beam search never reaches, and on the
    measured corpus the union beats beam-only by a wide margin. One segmented
    attempt is added for titles with a colon or dash, where a single pass drifts
    or stops early. All candidates are ranked by quality_score.
    """
    common = dict(max_input_length=160, max_decoding_length=96,
                  no_repeat_ngram_size=4, repetition_penalty=1.15)
    tokens = sp.encode(titles, out_type=str)
    whole = engine.translate_batch(
        tokens, beam_size=4, num_hypotheses=3, max_batch_size=32,
        replace_unknowns=True, **common)
    sampled = engine.translate_batch(
        tokens, beam_size=1, num_hypotheses=3, max_batch_size=32,
        replace_unknowns=True, sampling_topk=10, sampling_temperature=1.0,
        **common)

    segments = {}          # title index -> list of segments
    flat = []              # all segments across titles, for one batched decode
    for index, title in enumerate(titles):
        parts = [part.strip() for part in SEGMENT_SPLIT.split(title) if part and part.strip()]
        if 1 < len(parts) <= 4:
            segments[index] = parts
            flat.extend(parts)
    translated_segments = {}
    if flat:
        piece_tokens = sp.encode(flat, out_type=str)
        pieces = engine.translate_batch(
            piece_tokens, beam_size=4, max_batch_size=32,
            replace_unknowns=True, **common)
        pieces = [sp.decode(result.hypotheses[0]).replace("▁", " ").strip()
                  for result in pieces]
        cursor = 0
        for index, parts in segments.items():
            translated_segments[index] = assemble(parts, pieces[cursor:cursor + len(parts)])
            cursor += len(parts)

    best = []
    for index, title in enumerate(titles):
        candidates = [sp.decode(hypothesis).replace("▁", " ").strip()
                      for hypothesis in whole[index].hypotheses]
        candidates += [sp.decode(hypothesis).replace("▁", " ").strip()
                       for hypothesis in sampled[index].hypotheses]
        if index in translated_segments:
            candidates.append(translated_segments[index])
        polished = [polish(title, candidate) for candidate in candidates]
        ranked = max(range(len(candidates)), key=lambda i: quality_score(title, polished[i]))
        best.append(candidates[ranked])
    return best


def translations(db, records):
    db.execute("CREATE TABLE IF NOT EXISTS translations (title TEXT PRIMARY KEY, zh TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS retranslated (title TEXT PRIMARY KEY)")
    cached = {title: collapse_repeats(correct(title, zh))
              for title, zh in db.execute("SELECT title, zh FROM translations")}
    # A cached title that ended in a decoding loop or stopped half-way is
    # dropped here so the next run translates it again instead of serving
    # broken text forever.
    for title in [title for title, zh in cached.items()
                  if degenerate(zh) or truncated(title, zh)]:
        del cached[title]
    # The decoder improved, but the archive keeps whatever it cached earlier.
    # Re-decode the weakest entries a slice at a time, remembering which titles
    # were already retried so a run cannot loop on titles that stay bad.
    tried = {row[0] for row in db.execute("SELECT title FROM retranslated")}
    weak = []
    for title, zh in cached.items():
        if title in tried:
            continue
        if quality_score(title, zh) < 0:
            weak.append(title)
            if len(weak) >= 1500:
                break
    retried = set(weak)
    previous = {title: cached[title] for title in weak}
    for title in weak:
        del cached[title]
    pending = list(dict.fromkeys(
        item["title"] for item in records
        if item["title"] not in cached
    ))
    if not pending:
        return cached, ""
    rejected = 0
    try:
        import ctranslate2
        import sentencepiece
        sp = sentencepiece.SentencePieceProcessor(model_file=str(MODEL / "sentencepiece.model"))
        engine = ctranslate2.Translator(str(MODEL / "model"), device="cpu",
                                       compute_type="int8", inter_threads=2, intra_threads=3)
        for start in range(0, len(pending), 64):
            titles = pending[start:start + 64]
            candidates = translate_batch(engine, sp, titles)
            for title, chinese in zip(titles, candidates):
                if degenerate(chinese) or truncated(title, chinese):
                    # Retry once on its own with a different decoding profile, so
                    # a loop or an early stop gets a second, independent chance.
                    token = sp.encode([title], out_type=str)[0]
                    retry = engine.translate_batch(
                        [token], beam_size=6, max_batch_size=1,
                        max_decoding_length=max(48, len(token) * 4),
                        replace_unknowns=False, no_repeat_ngram_size=3,
                        repetition_penalty=1.3)
                    chinese = sp.decode(retry[0].hypotheses[0]).replace("▁", " ").strip()
                chinese = polish(title, chinese)
                if (degenerate(chinese) or truncated(title, chinese)
                        or not re.search(r"[\u3400-\u9fff]", chinese)):
                    # Never cache a broken title; the English original is shown.
                    rejected += 1
                    if title in previous:
                        cached[title] = previous[title]
                    continue
                # Re-decoding is not uniformly better, so a retried title keeps
                # its old translation unless the new one scores higher.
                if title in previous and (quality_score(title, previous[title])
                                          >= quality_score(title, chinese)):
                    chinese = previous[title]
                cached[title] = chinese
                db.execute("INSERT OR REPLACE INTO translations VALUES (?, ?)", (title, chinese))
        for title in retried:
            db.execute("INSERT OR IGNORE INTO retranslated VALUES (?)", (title,))
        if rejected:
            print(f"Translation guard rejected {rejected} titles", flush=True)
        if retried:
            print(f"Re-decoded {len(retried)} weakly cached titles", flush=True)
        return cached, ""
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        return cached, str(error)
