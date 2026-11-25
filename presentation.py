"""Group journal records by theme and translate titles with an offline model.

The theme list used to have eight coarse buckets and left roughly a third of the
archive in "其他或题名信息不足". It now separates the themes the lab actually
reads -- environment physiology, strength and muscle adaptation, brain and
mental health, immune and molecular adaptation, special populations, equipment
and biomechanics, public health and policy -- so fewer records fall through to
the catch-all bucket.
"""

from collections import defaultdict
import json
from pathlib import Path
import re

from terminology import PATH as GLOSSARY_PATH, correct, matched_terms

MODEL = Path(__file__).resolve().parent / "models" / "translate-en_zh-1_9"
# Chinese->Chinese fixes live in the glossary next to the terms, so there is a
# single data file to edit instead of rules scattered through this module.
CORRECTIONS = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8-sig")).get("corrections", [])
CORRECTIONS = [(re.compile(rule.get("from_re") or re.escape(rule["from"])),
                re.compile(rule["when"], re.I) if rule.get("when") else None,
                re.compile(rule["unless"], re.I) if rule.get("unless") else None,
                rule["to"]) for rule in CORRECTIONS]


def apply_corrections(title, chinese):
    """Swap the decoder's known wrong renderings for the approved Chinese."""
    for pattern, when, unless, replacement in CORRECTIONS:
        if not pattern.search(chinese):
            continue
        if when and not when.search(title):
            continue
        if unless and unless.search(title):
            continue
        chinese = pattern.sub(replacement, chinese)
    return chinese

TOPIC_PATTERNS = {
    # Core physiology: oxygen transport, muscle metabolism, thresholds, strength.
    "氧运输与心肺整合": (
        r"cardiac|cardiovascular|heart rate|stroke volume|cardiac output|"
        r"blood (?:pressure|flow|volume|vessel)|vascular|endothelial|arterial|"
        r"respirat\w*|pulmonary|ventilat\w*|gas exchange|circulat\w*|"
        r"inspiratory|expiratory|respiratory muscle|"
        r"oxygen (?:uptake|consumption|delivery|extraction|saturation)|"
        r"ha?emodynamic\w*|oxygenation|hematolog\w*|blood volume|"
        r"autonomic|sympathetic|parasympathetic|baroreflex|"
        r"vo[₂2]\s?max|maximum oxygen uptake|peak oxygen uptake|"
        r"arterial stiffness|flow-mediated dilation|"
        r"haemoglobin|hemoglobin|"
        r"myocard\w*|coronary|cardiomyopath\w*|"
        r"v̇o2|vo2"
    ),
    "骨骼肌代谢与线粒体功能": (
        r"skeletal muscle|muscle (?:metabolism|metabolic|energy|oxidative|"
        r"glycogen|mitochondri|fiber type|fibre type|protein synthesis|"
        r"excitation[- ]contraction|calcium handling)|"
        r"mitochondri\w*|mitophagy|mitochondrial biogenesis|"
        r"pgc-?1|ampk|sirtuin|"
        r"oxidative phosphorylation|electron transport|"
        r"fat oxidation|carbohydrate oxidation|protein oxidation|"
        r"substrate (?:oxidation|utilization|availability)|"
        r"metabolic (?:flexibility|inflexion|profile|adaptation|"
        r"reprogramming|load|rate|syndrome)|"
        r"glycolysis|glycogenolysis|glycogen resynthesis|"
        r"myofibrillar|actomyosin|sarcoplasmic reticulum|"
        r"muscle fibre|muscle fiber|myosin|"
        r"creatine kinase|phosphocreatine|atp resynthesis|"
        r"muscle (?:oxygen|work output)|"
        r"satellite cell|myoblast|myogenesis|"
        r"insulin resistance|glucose uptake|lactate metabolism|"
        r"thermogen\w*|brown adipose|beiging"
    ),
    "强度阈值、临界功率与耐力表现": (
        r"critical (?:power|speed|velocity)|critical swimming speed|"
        r"oxygen uptake kinetics|vo[₂2]\s?kinetics|"
        r"ventilatory threshold|lactate threshold|maximal lactate steady state|"
        r"anaerobic threshold|time to exhaustion|\btte\b|time trial|"
        r"endurance performance|endurance capacity|"
        r"pacing|pacing strategy|durability|fatigue resistance|"
        r"respiratory exchange threshold|"
        r"intensity domain|training zone|zone 2|zone 3|"
        r"maximal aerobic speed|anaerobic power|"
        r"threshold (?:speed|power|pace|workload)|"
        r"excess post-exercise oxygen consumption|epoc|"
        r"oxygen (?:uptake|consumption)[^.]{0,40}(?:1|2|3|4|5|6)[ -]?km|"
        r"(?:1|2|3|4|5|6|10|12|21)[ -]?km\b|"
        r"running speed|swimming speed|cycling power output|"
        r"respiratory compensation point|"
        r"aerobic (?:power|performance|capacity)"
    ),
    "力量、爆发力与神经肌肉": (
        r"strength|hypertroph\w*|resistance train\w*|powerlift\w*|weightlift\w*|"
        r"muscle (?:mass|size|thickness|cross-sectional area|damage|"
        r"activation|architecture|fatigue)|sarcopenia|atroph\w*|"
        r"plyometric|sprint train\w*|velocity-?based|one-?repetition maximum|\b1rm\b|"
        r"maximal (?:strength|power|force)|force[- ]velocity|rate of force development|"
        r"electromyogra\w*|\bemg\b|\bsemg\b|motor unit|neuromuscul\w*|myoelectric|"
        r"knee extensor|plantar flexor|eccentric|concentric|"
        r"sarcomer\w*|contractile|stretch[- ]shorten|"
        r"kicking|throwing|sprinting|sprint speed|"
        r"jump(?:ing)? performance|explosive|"
        r"muscle soreness|delayed onset|\bdoms\b|"
        r"squat|deadlift|bench press|clean and jerk|snatch|"
        r"countermovement jump|isokinetic|"
        r"handgrip strength|grip strength|"
        r"flywheel|"
        r"mechanical load\w*"
    ),
    "免疫、炎症与分子适应": (
        r"immun\w*|inflamm\w*|cytokine\w*|microbiome|gut (?:microbiota|bacteria)|"
        r"exosome\w*|extracellular vesicle\w*|mirna\w*|microrna\w*|lncrna\w*|"
        r"transcriptom\w*|proteom\w*|metabolom\w*|epigen\w*|gene expression|"
        r"signal(?:l)?ing|molecular|cellular|"
        r"oxidative stress|antioxidant|aging|ageing|longevity|hallmark\w*|"
        r"mimetic|senescence|telomere\w*|autophagy|mitophagy|heat shock|"
        r"myokine|myokines|adipokine|"
        r"nrf2|nf-?kb"
    ),
    # Training and performance: what was done, what happened afterwards.
    "训练干预与周期化": (
        r"training (?:intervention|program\w*|plan|cycle|block|periodi|"
        r"volume|intensity|frequency|method\w*|status|week|session|practice)|"
        r"periodi[sz]ation|taperi\w*|microcycle|macrocycle|mesocycle|deload\w*|"
        r"concurrent train\w*|high[- ]intensity interval|interval train\w*|"
        r"endurance train\w*|"
        r"plyometric train\w*|strength and conditioning|"
        r"training effect|training adaptation\w*|adaptation to training|"
        r"adaptations? (?:to|from) (?:endurance|resistance|strength|sprint|"
        r"high[- ]intensity|exercise|training)|"
        r"exercise (?:intervention|prescription|program\w*)|"
        r"dose[- ]response|dosage|"
        r"preconditioning|warm-?up|"
        r"session rpe|training load|training impulse|"
        r"train(?:ing|ed)? (?:for|over) \d+ (?:week|month|year)|"
        r"after \d+ (?:week|month|year)s? of (?:resistance|endurance|high[- ]intensity|sprint|"
        r"strength|plyometric|balance|flexibility|stretching)"
    ),
    "疲劳、恢复与竞技表现": (
        r"fatigue|fatigability|recovery|overreach\w*|overtrain\w*|detrain\w*|"
        r"readiness|recovery time|sleep|nap\w*|rest(?:it|orative)|"
        r"supercompensation|acute:chronic|training monotony|"
        r"muscle damage|strength loss|"
        r"between[- ]session|post[- ]competition|in[- ]season|off[- ]season|"
        r"preseason|pre-?season"
    ),
    "测试、评估与运动表现": (
        r"assess\w*|evaluat\w*|test(?:ing)?\b|test protocol|battery|"
        r"questionnaire|scal(?:e|ing)|survey|"
        r"predictors?|prediction|predicting|predictive|"
        r"benchmark\w*|"
        r"fitness test|performance test|field test|"
        r"reference values|normative values|"
        r"response to training|"
        r"detect\w*|identif\w*|"
        r"pre-?season fitness|preseason fitness|"
        r"perceptual acuity|psychophysic\w*|"
        r"characteristics of (?:elite|trained|world[- ]class)"
    ),
    "生物力学、技术与装备": (
        r"biomechanic\w*|kinematic\w*|kinetic\w*|joint moment|torque|ground reaction|"
        r"force plate|gait\b|walking|running (?:kinematic|biomechanic|mechanics)|"
        r"balance\b|postur\w*|stabil\w*|motor control|motor learning|coordination|"
        r"movement (?:pattern|analysis|quality|variability)|motion (?:capture|analysis)|"
        r"proprioception|proprioceptive|landing|jump(?:ing)?|sprint mechanic\w*|"
        r"muscle[ -]tendon|fascicle|pennation|stiffness|"
        r"footwear|shoe\w*|spike\w*|apparel|garment\w*|compression|equipment|"
        r"exoskeleton|technique|treadmill|ergometer|change[- ]of[- ]direction|agility|"
        r"joint stiffness|tendon stiffness|"
        r"energy storage|stretching|flexibility|range of motion"
    ),
    "竞技与比赛分析": (
        r"match(?:es)?\b|matchday|fixture|"
        r"competition|competitive|tournament|championship|league|season\b|"
        r"round[- ]of|play-?off|"
        r"team sport|team performance|team selection|squad|line-?up|"
        r"tactic\w*|formation|playing position|"
        r"expected goals|\bxg\b|possession|shots? on target|"
        r"match load|match performance|match outcome|match play|"
        r"transfer fee|transfer market|scouting|draft\b|talent identification|"
        r"home advantage|away team|"
        r"world cup|olympic|premier league|\bnba\b|\bnfl\b|champions league|"
        r"athletic performance|sport performance|"
        r"performance analysis|performance profile|"
        r"(?:football|soccer|basketball|rugby|cricket|handball|volleyball|"
        r"baseball|hockey|badminton|table tennis|cycling|swimming|rowing|sailing|"
        r"skiing|snowboard|gymnastics)\s+"
        r"(?:match|league|player|players|team|teams|season|competition|"
        r"performance|tournament|championship|club|training|players)"
    ),
    # Methods: how the data was measured, modelled and reported.
    "可穿戴与运动监测": (
        r"wearab\w*|acceleromet\w*|gyroscop\w*|actigraph|smartwatch|smart ring|"
        r"inertial measurement|global positioning|\bgps\b|"
        r"photoplethysmograph\w*|device[- ]measured|"
        r"heart rate variability|\bhrv\b|"
        r"step count|daily steps|movement behaviou?r|"
        r"mobile (?:app|health)|digital (?:health|biomarker)|"
        r"activity tracker|fitness tracker|sensor array|"
        r"remote monitoring|continuous monitoring|"
        r"telemonitoring|mhealth|e-?health|"
        r"monitoring\b|monitor\w*"
    ),
    "数据建模与算法": (
        r"machine learning|deep learning|artificial intelligence|neural network|"
        r"algorithm\w*|random forest|support vector|"
        r"model[- ]based|mathematical model|computational model|"
        r"simulation|simulated|finite element|"
        r"data[- ]driven|data mining|feature (?:engineering|selection)|"
        r"prediction model|predictive model|"
        r"computer vision|pose estimation|"
        r"deep[- ]learning|convolution|transformer|"
        r"clustering|regression model|classification model|"
        r"statistical model|mixed[- ]model|"
        r"artificial neural|gradient boost"
    ),
    "测量方法与效度": (
        r"methodolog\w*|measurement (?:validity|reliability|precision|error)|"
        r"reliab\w*|valid\w*|reproducib\w*|"
        r"agreement between|concordance|bland[- ]altman|"
        r"intraclass|coefficient of variation|"
        r"minimal detectable change|standard error of measurement|"
        r"measurement properties|psychometric\w*|clinimetric\w*|"
        r"criterion[- ]?valid|construct valid|content valid|"
        r"data collection|protocol development|"
        r"reporting quality|open science|data availability|"
        r"systematic review protocol|"
        r"reference (?:values|standards)|calibration|"
        r"accuracy and precision|precision and accuracy|"
        r"instrumentation|sensor validation|"
        r"inter[- ]rater|intra[- ]rater|test[- ]retest|"
        r"smallest worthwhile"
    ),
    # People and environment.
    "环境生理与特殊场景": (
        r"heat (?:acclim\w*|stress|strain|exposure|tolerance|adaptation)|"
        r"thermoregulat\w*|core temperature|body temperature|skin temperature|"
        r"hyperthermi\w*|hypothermi\w*|cold (?:exposure|water|air|stress|acclim\w*)|"
        r"altitude|hypoxi\w*|hypobaric|hyperbaric|decompress\w*|"
        r"spaceflight|space flight|microgravity|bed rest|confinement|"
        r"isolated confined|extreme environment|arctic|polar|desert|"
        r"dehydrat\w*|hydration|fluid (?:balance|intake|loss|replacement)|"
        r"sweat\w*|thermal strain|"
        r"environmental (?:stress|challenge)|"
        r"military|armed forces|special forces|"
        r"circadian|timezone|shift work|night shift|"
        r"heat loss|temperature and heat|"
        r"indoor cycling system|video-based"
    ),
    "特殊人群与生命周期": (
        r"pregnan\w*|postpartum|placenta\w*|maternal|pediatric|paediatric|"
        r"pre-?school|children|adolescen\w*|youth|juvenile|older (?:adults?|people|women|men)|"
        r"middle-?aged|menopaus\w*|postmenopaus\w*|masters? athletes?|aged\b|"
        r"menstru\w*|disabilit\w*|para-?athlet\w*|wheelchair|amputee|spinal cord|"
        r"intellectual disability|transgender|sex difference\w*|"
        r"female athlete|male athlete|puberty|"
        r"infant|toddler|neonat\w*|preterm|"
        r"elite (?:athlete|player)s?|world[- ]class|"
        r"geriatr\w*|frailty"
    ),
    "肌肉骨骼、损伤与康复": (
        r"injur\w*|concussion\w*|rehabilitat\w*|return to (?:sport|play)|"
        r"tendinopath\w*|tendon\w*|ligament\w*|anterior cruciate|\bacl\b|"
        r"bone (?:mineral|density|health|mass|turnover)|osteopor\w*|osteoblast|osteoclast|"
        r"fracture\w*|cartilage|meniscus|joint\b|sprain|overuse|physical therapy|"
        r"musculoskeletal|low back pain|neck pain|shoulder pain|"
        r"patellofemoral|tendinopathy|"
        r"fracture risk|bone turnover|osteogenesis"
    ),
    "营养、补剂与能量可用性": (
        r"nutrition|supplement\w*|caffeine|creatine\b|beta-?alanine|nitrate|"
        r"carbohydrat\w*|protein (?:intake|supplement|dose|feeding|availability)|"
        r"amino acid\w*|diet\w*|"
        r"energy (?:intake|expenditure|availability|deficit|balance)|"
        r"low energy availability|\bred-?s\b|"
        r"ketone\w*|fasting|"
        r"body composition|body fat|adipos\w*|weight (?:loss|gain|management)|"
        r"nutrient\w*|feeding|food|caloric|"
        r"energy intake|protein timing|nutrient timing|"
        r"hydration strategy|fluid intake|"
        r"vitamins?\b|minerals?\b|iron\b|magnesium|zinc|"
        r"polyphenol\w*|anthocyanin|curcumin|green tea|"
        r"ergogenic|placebo|"
        r"hepatic steatosis|liver fat|"
        r"bone biomarker|biomarker concentrations|"
        r"l-?alanine|l-?glutamine|l-?arginine|glycine|"
        r"appetite|hypothalam\w*"
    ),
    "脑认知、心理健康与行为": (
        r"cognit\w*|brain|neuroscien\w*|mental health|mood|anxiety|depress\w*|"
        r"psycholog\w*|psychiatr\w*|executive function|memory|attention|"
        r"well-?being|quality of life|self-?efficacy|motivation|"
        r"behaviou?r change|self[- ]regulation|burnout|resilience|"
        r"cognitive (?:function|performance|decline|impairment)|neurodegenerat\w*|"
        r"dopamine|prefrontal|hippocamp\w*|default mode|"
        r"emotion|affect\b|mindfulness|meditation|"
        r"testosterone|hormone|hormonal|cortisol|"
        r"sympatholysis|"
        r"binge drinking|alcohol"
    ),
    "体力活动、公共卫生与人群干预": (
        r"physical activit\w*|sedentar\w*|sitting|inactiv\w*|"
        r"exercise (?:intervention|prescription|program\w*|referral)|"
        r"health (?:outcome\w*|benefit|promotion|inequalit\w*)|"
        r"mortality|morbidit\w*|risk factor|incidence|prevalence|"
        r"cohort|longitudinal|cross-sectional|population|epidemiolog\w*|"
        r"steps? count|daily steps|movement behaviou?r\w*|24-?hour movement|"
        r"smoking|alcohol|screen time|"
        r"public health|policy|polic\w*|governance|equity|inequalit\w*|"
        r"racism|ethnic\w*|gender|socioeconomic|social\w*|"
        r"sustainab\w*|climate|environmental impact|carbon|travel distance|"
        r"physical (?:education|literacy)|school|curricul\w*|coach(?:ing|es)?|"
        r"guideline\w*|consensus|position stand|surveillance|"
        r"promotion|adherence|compliance|doping|"
        r"replicab\w*|research (?:method|practice|quality)|meta-research|reporting|"
        r"transparen\w*|peer review|"
        r"community[- ]based|"
        r"workplace|occupational|sedentary behaviour|sedentary behavior"
    ),
}
PATTERNS = {topic: re.compile(pattern, re.IGNORECASE) for topic, pattern in TOPIC_PATTERNS.items()}
# Tie-break order for titles that match several topics equally. Earlier wins.
TIE_BREAK = {
    topic: index
    for index, topic in enumerate((
        "数据建模与算法",
        "测试、评估与运动表现",
        "测量方法与效度",
        "训练干预与周期化",
        "疲劳、恢复与竞技表现",
        "竞技与比赛分析",
        "可穿戴与运动监测",
        "环境生理与特殊场景",
        "骨骼肌代谢与线粒体功能",
        "强度阈值、临界功率与耐力表现",
        "免疫、炎症与分子适应",
        "脑认知、心理健康与行为",
        "肌肉骨骼、损伤与康复",
        "营养、补剂与能量可用性",
        "生物力学、技术与装备",
        "特殊人群与生命周期",
        "氧运输与心肺整合",
        "力量、爆发力与神经肌肉",
        "体力活动、公共卫生与人群干预",
    ))
}
# Journal-level topic tags collected from the cross-journal PubMed searches.
# Each tag points at the topic that best describes the articles it retrieves.
CROSS_JOURNAL_TOPICS = {
    "临界功率与速度": "强度阈值、临界功率与耐力表现",
    "氧摄取动力学": "强度阈值、临界功率与耐力表现",
    "训练负荷": "训练干预与周期化",
    "可穿戴运动监测": "可穿戴与运动监测",
}
OTHER = "其他或题名信息不足"
PUBLICATION_NOTICE = "编辑信息、勘误与撤稿"
NOTICE_PATTERN = re.compile(
    r"^(?:correction(?: to)?|erratum|corrigendum|retraction|acknowledg\w*|"
    r"editorial board|masthead|table of contents|response to|reply to|comment on|"
    r"commentary on|letter)\b",
    re.IGNORECASE,
)
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
]
# Term replacement inserts Chinese where English stood, so the stray space is
# only created by correct(); join the characters once that has run.
CJK_SPACE = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")


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
    # Ties are common because one title can carry several exercise-science
    # signals. The order below decides them: study-design topics (population,
    # methods, modelling, training design) win over the broad physiology
    # buckets, so "older adults after resistance training" lands on the
    # population topic rather than on strength.
    strongest = max(votes, key=lambda topic: (votes[topic], -TIE_BREAK.get(topic, len(TIE_BREAK))))
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
    """Apply the post-processing chain, iterating until the text stops changing.

    One pass is not always enough: term replacement can expose a rendering a
    later rule fixes (running -> 运行 -> 跑性能 -> 跑步表现), so the chain is
    repeated to a fixed point. Each pass is cheap and the loop is capped.
    """
    for _ in range(4):
        updated = _polish_once(title, chinese)
        if updated == chinese:
            break
        chinese = updated
    return chinese


def _polish_once(title, chinese):
    # 1. the decoder's known wrong renderings, from the glossary
    chinese = apply_corrections(title, chinese)
    # 2. function words and half-translated fragments it leaves behind
    #    ("Blood Flow Restriction versus ...", "Network Meta-analysis").
    #    Bounded by ASCII letters so Chinese text is never touched.
    for pattern, replacement in LEFTOVERS:
        chinese = pattern.sub(replacement, chinese)
    # 3. glossary terms: swap leftover English for the approved Chinese and
    #    replace the variants the model produced for that same term
    chinese = correct(title, chinese)
    # 4. term replacement can put a wrong rendering back (running -> 运行, and its
    #    variant then makes 运行性能 -> 跑性能), so correct again afterwards
    chinese = apply_corrections(title, chinese)
    # 5. joining characters can expose a doubled word the space was hiding
    for _ in range(2):
        chinese = CJK_SPACE.sub("", collapse_repeats(chinese))
    return chinese


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
    # Cached titles go through the whole post-processing chain, not just the
    # term correction: leftover English, stray spaces and doubled words were
    # added later and only reached newly decoded titles otherwise.
    cached = {title: polish(title, zh)
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
