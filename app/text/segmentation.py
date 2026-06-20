"""弹幕文本分词与简易情绪标注。
Danmaku tokenization and lightweight sentiment labeling.
"""

import re
import zipfile
import xml.etree.ElementTree as ET

try:
    import pkuseg
except ImportError as exc:
    raise ImportError("缺少 pkuseg，请先运行: pip install pkuseg") from exc

from app.file_utils import read_word_file
from app.paths import CUSTOM_WORDS_DIR, FILTERED_WORDS_FILE, SENTIMENT_ONTOLOGY_FILE
from app.text.aliases import load_phrase_alias_maps


TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]+")
XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
POLARITY_TO_SCORE = {
    "0": (0, 0),
    "1": (1, 0),
    "2": (0, 1),
    "3": (1, 1),
}
_FILTERED_WORDS = None
_PHRASE_TO_ALIAS = None
_ALIAS_TO_PHRASES = None
_SENTIMENT_LEXICON = None
_SEGMENTERS = {}


def load_filtered_words():
    """读取全局过滤词典。
    Load the global filtered-word dictionary.
    """
    return read_word_file(FILTERED_WORDS_FILE)


def get_filtered_words():
    global _FILTERED_WORDS
    if _FILTERED_WORDS is None:
        _FILTERED_WORDS = load_filtered_words()
    return _FILTERED_WORDS


def is_filtered_word(word):
    return (word or "").strip().lower() in get_filtered_words()


def load_phrase_aliases():
    """读取长短语到展示词的别名词典。
    Load phrase-to-display-word alias rules.
    """
    return load_phrase_alias_maps()


def get_phrase_aliases():
    """返回缓存后的短语别名映射。
    Return cached phrase alias mappings.
    """
    global _PHRASE_TO_ALIAS, _ALIAS_TO_PHRASES
    if _PHRASE_TO_ALIAS is None or _ALIAS_TO_PHRASES is None:
        _PHRASE_TO_ALIAS, _ALIAS_TO_PHRASES = load_phrase_aliases()
    return _PHRASE_TO_ALIAS, _ALIAS_TO_PHRASES


def get_alias_for_phrase(text):
    """如果整条弹幕命中别名词典，返回展示词。
    Return the display word if the full danmaku line matches an alias rule.
    """
    phrase_to_alias, _ = get_phrase_aliases()
    return phrase_to_alias.get((text or "").strip().lower())


def get_alias_phrases():
    """返回展示词到原短语列表的映射，供词云 tooltip 使用。
    Return display-word to original-phrase mapping for word-cloud tooltips.
    """
    _, alias_to_phrases = get_phrase_aliases()
    return alias_to_phrases


def xlsx_column_index(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def load_xlsx_shared_strings(zip_file):
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    shared = []
    for item in root.findall("m:si", XLSX_NS):
        shared.append("".join(node.text or "" for node in item.findall(".//m:t", XLSX_NS)))
    return shared


def xlsx_cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", XLSX_NS))

    value_node = cell.find("m:v", XLSX_NS)
    if value_node is None:
        return ""
    if cell_type == "s":
        return shared_strings[int(value_node.text)]
    return value_node.text or ""


def iter_ontology_rows(file_path):
    if not file_path.exists():
        return

    with zipfile.ZipFile(file_path) as zip_file:
        shared_strings = load_xlsx_shared_strings(zip_file)
        sheet_root = ET.fromstring(zip_file.read("xl/worksheets/sheet1.xml"))
        for row in sheet_root.findall(".//m:sheetData/m:row", XLSX_NS):
            values = []
            for cell in row.findall("m:c", XLSX_NS):
                index = xlsx_column_index(cell.attrib["r"])
                while len(values) <= index:
                    values.append("")
                values[index] = xlsx_cell_value(cell, shared_strings)
            yield values


def parse_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def apply_polarity_score(scores, strength, polarity):
    positive_weight, negative_weight = POLARITY_TO_SCORE.get(str(polarity).strip(), (0, 0))
    strength_value = parse_int(strength, default=1)
    if positive_weight:
        scores["positive"] = max(scores["positive"], strength_value * positive_weight)
    if negative_weight:
        scores["negative"] = max(scores["negative"], strength_value * negative_weight)


def score_to_sentiment(scores):
    if scores["positive"] > scores["negative"]:
        return "positive"
    if scores["negative"] > scores["positive"]:
        return "negative"
    return "neutral"


def load_sentiment_ontology():
    """Load Dalian University of Technology Chinese sentiment ontology from xlsx."""
    lexicon_scores = {}
    for index, row in enumerate(iter_ontology_rows(SENTIMENT_ONTOLOGY_FILE) or []):
        if index == 0 or not row:
            continue

        word = (row[0] if len(row) > 0 else "").strip().lower()
        if not word:
            continue

        scores = lexicon_scores.setdefault(word, {"positive": 0, "negative": 0})
        if len(row) > 6:
            apply_polarity_score(scores, row[5], row[6])
        if len(row) > 9:
            apply_polarity_score(scores, row[8], row[9])

    return {
        word: score_to_sentiment(scores)
        for word, scores in lexicon_scores.items()
    }


def get_sentiment_lexicon():
    global _SENTIMENT_LEXICON
    if _SENTIMENT_LEXICON is None:
        _SENTIMENT_LEXICON = load_sentiment_ontology()
    return _SENTIMENT_LEXICON


def classify_sentiment(word):
    """Return positive/negative/neutral using the DUTIR sentiment ontology."""
    key = (word or "").strip().lower()
    if not key:
        return "neutral"
    return get_sentiment_lexicon().get(key, "neutral")


def get_segmenter(bvid=None):
    """按视频返回 pkuseg 分词器，存在用户词典时加载 custom_words/{bvid}.txt。
    Return a pkuseg segmenter for a video, loading custom_words/{bvid}.txt when present.
    """
    key = bvid or "__default__"
    if key not in _SEGMENTERS:
        user_dict = None
        if bvid:
            custom_words_file = CUSTOM_WORDS_DIR / f"{bvid}.txt"
            if custom_words_file.exists():
                user_dict = str(custom_words_file)
        _SEGMENTERS[key] = pkuseg.pkuseg(user_dict=user_dict)
    return _SEGMENTERS[key]


def clear_segmenter_cache(bvid=None):
    """Release cached pkuseg segmenters.
    If bvid is provided, only release that video's segmenter.
    """
    if bvid is None:
        _SEGMENTERS.clear()
        return
    _SEGMENTERS.pop(bvid, None)


def segment_text(text, bvid=None):
    """使用 pkuseg 分词，并过滤无效或手动屏蔽的词。
    Segment text with pkuseg and remove invalid or manually filtered tokens.
    """
    if not text:
        return []

    alias = get_alias_for_phrase(str(text))
    if alias and TOKEN_RE.fullmatch(alias) and not is_filtered_word(alias):
        return [{
            "word": alias,
            "sentiment": classify_sentiment(alias),
        }]

    words = []
    for token in get_segmenter(bvid).cut(str(text)):
        token = token.strip()
        if not token or not TOKEN_RE.fullmatch(token):
            continue
        if is_filtered_word(token):
            continue
        words.append({
            "word": token,
            "sentiment": classify_sentiment(token),
        })
    return words
