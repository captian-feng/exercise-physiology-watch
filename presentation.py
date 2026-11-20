"""Group journal records by theme and translate titles with an offline model."""

from collections import defaultdict
from pathlib import Path
import re

MODEL = Path(__file__).resolve().parent / "models" / "translate-en_zh-1_9"
TOPIC_PATTERNS = {
    "临界功率、耐力与氧摄取动力学": r"critical (?:power|speed|swimming speed)|oxygen uptake kinetics|vo[₂2] kinetics|\bw[′']|v[̇]?o[₂2] ?max|aerobic capacity|endurance performance|ventilatory threshold",
    "训练负荷、恢复与运动表现": r"training load|training impulse|session[- ]rpe|overreach|recovery|sport performance|athletic performance|strength train|resistance train|interval train|power output|sprint|conditioning|periodization|periodisation|competition",
    "可穿戴设备、运动监测与数据建模": r"wearab|acceleromet|gyroscop|actigraph|smartwatch|inertial measurement|machine learning|deep learning|artificial intelligence|sensor|monitoring|algorithm|validity|reliability",
    "损伤、康复与运动医学": r"injur|concuss|tendinopath|rehabilitat|fracture|arthro|rupture|return to (?:sport|play)|ligament|osteoarthrit|pain|clinical|surgery|surgical",
    "生物力学与运动控制": r"biomech|kinemat|kinetic[s]?\b|joint moment|gait|balance|postur|motor control|motion analys|jump|force plate|movement pattern|electromyogra",
    "营养、能量代谢与补剂": r"nutrition|supplement|caffeine|creatine|carbohydrat|protein intake|diet|glycogen|ketone|metabol|energy expenditure|energy availability|body composition",
    "肌肉、心肺与整合生理": r"physiolog|cardiovascular|cardiac|respirat|pulmonary|vascular|skeletal muscle|neuromuscul|mitochond|hypoxi|heat stress|fatigue|autonomic|blood pressure|heart rate",
    "体力活动、健康与人群干预": r"physical activit|sedentary|public health|epidemiolog|mortality|obesity|diabetes|health promotion|exercise intervention|exercise prescription|physical fitness|older adult|adolescent|school|sleep|mental health|cognition",
}
PATTERNS = {topic: re.compile(pattern, re.IGNORECASE) for topic, pattern in TOPIC_PATTERNS.items()}
CROSS_JOURNAL_TOPICS = {
    "临界功率与速度": "临界功率、耐力与氧摄取动力学",
    "氧摄取动力学": "临界功率、耐力与氧摄取动力学",
    "训练负荷": "训练负荷、恢复与运动表现",
    "可穿戴运动监测": "可穿戴设备、运动监测与数据建模",
}
OTHER = "其他或题名信息不足"
PUBLICATION_NOTICE = "编辑信息、勘误与撤稿"
NOTICE_PATTERN = re.compile(r"^(?:correction(?: to)?|erratum|corrigendum|retraction|editorial board|masthead|table of contents)\b", re.IGNORECASE)
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
    cached = dict(db.execute("SELECT title, zh FROM translations"))
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
                if re.search(r"[\u3400-\u9fff]", chinese):
                    cached[title] = chinese
                    db.execute("INSERT OR REPLACE INTO translations VALUES (?, ?)", (title, chinese))
        return cached, ""
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        return cached, str(error)

