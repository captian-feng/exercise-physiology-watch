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

from terminology import correct

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


def translations(db, records):
    db.execute("CREATE TABLE IF NOT EXISTS translations (title TEXT PRIMARY KEY, zh TEXT NOT NULL)")
    cached = {title: correct(title, zh) for title, zh in db.execute("SELECT title, zh FROM translations")}
    pending = list(dict.fromkeys(
        item["title"] for item in records
        if item["title"] not in cached
    ))
    if not pending:
        return cached, ""
    try:
        import ctranslate2
        import sentencepiece
        sp = sentencepiece.SentencePieceProcessor(model_file=str(MODEL / "sentencepiece.model"))
        engine = ctranslate2.Translator(str(MODEL / "model"), device="cpu",
                                       compute_type="int8", inter_threads=2, intra_threads=3)
        for start in range(0, len(pending), 64):
            titles = pending[start:start + 64]
            tokens = sp.encode(titles, out_type=str)
            predictions = engine.translate_batch(tokens, beam_size=3, max_batch_size=32,
                                                 max_input_length=160, max_decoding_length=160,
                                                 replace_unknowns=True)
            for title, result in zip(titles, predictions):
                chinese = sp.decode(result.hypotheses[0]).replace("▁", " ").strip()
                for before, after in SUBSTITUTIONS.items():
                    chinese = chinese.replace(before, after)
                if "cyclist" in title.lower():
                    chinese = chinese.replace("循环者", "自行车运动员")
                if "epigenetic" in title.lower():
                    chinese = chinese.replace("遗传学和遗传学", "遗传与表观遗传")
                chinese = correct(title, chinese)
                if re.search(r"[\u3400-\u9fff]", chinese):
                    cached[title] = chinese
                    db.execute("INSERT OR REPLACE INTO translations VALUES (?, ?)", (title, chinese))
        return cached, ""
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        return cached, str(error)
