"""Shared API constants and helpers."""

from datetime import datetime

from app.file_utils import read_word_file
from app.paths import STOPWORDS_FILE


WORD_CLOUD_STATS_TABLE = "word_cloud_daily_stats"
SIMILARITY_MAX_VIDEOS = 10
SIMILARITY_MAX_MATRIX_VIDEOS = 91
SIMILARITY_DEFAULT_TOP_WORDS = 500
SIMILARITY_MAX_TOP_WORDS = 1000
SIMILARITY_MATRIX_TABLE = "video_similarity_matrix"
SIMILARITY_METRICS = {"trend", "sentiment", "high_energy", "combined"}
PARALLEL_STATS_TABLE = "video_parallel_stats"
PARALLEL_MAX_VIDEOS = 20

DEFAULT_WORD_CLOUD_STOPWORDS = {
    "的", "了", "呢", "吗", "啊", "吧", "呀", "哦", "嗯", "啦", "嘛", "哇", "呃", "额",
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们", "自己",
    "这", "那", "这个", "那个", "这些", "那些", "这里", "那里", "这样", "那样",
    "是", "在", "有", "和", "就", "都", "也", "很", "太", "又", "还", "被", "把", "给",
    "与", "及", "或", "而", "如果", "但是", "因为", "所以", "然后", "还是", "已经",
    "一个", "一下", "什么", "怎么", "为什么", "可以", "不能", "没有", "不是", "就是",
    "真的", "感觉", "时候", "里面", "现在", "直接", "视频", "弹幕", "b站", "up", "up主",
    "哈哈", "哈哈哈", "233", "www", "emmm",
}

PARALLEL_DIMENSIONS = [
    {"key": "viewCount", "label": "播放量", "unit": "次", "format": "number", "scale": "log", "defaultSelected": True},
    {"key": "danmakuCount", "label": "官方弹幕量", "unit": "条", "format": "number", "scale": "log", "defaultSelected": True},
    {"key": "durationMinutes", "label": "时长", "unit": "分钟", "format": "decimal", "scale": "linear", "defaultSelected": True},
    {"key": "danmakuRate", "label": "弹幕率", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": True},
    {"key": "coinRate", "label": "投币率", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": True},
    {"key": "favoriteRate", "label": "收藏率", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": True},
    {"key": "peakDensity", "label": "峰值密度", "unit": "条/秒", "format": "decimal", "scale": "linear", "defaultSelected": True},
    {"key": "positiveRatio", "label": "正向占比", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": True},
    {"key": "lexicalRichness", "label": "词汇丰富度", "unit": "", "format": "decimal", "scale": "linear", "defaultSelected": True},
    {"key": "crawledDanmakuCount", "label": "已抓弹幕量", "unit": "条", "format": "number", "scale": "log", "defaultSelected": False},
    {"key": "replyRate", "label": "评论率", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": False},
    {"key": "shareRate", "label": "分享率", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": False},
    {"key": "likeRate", "label": "点赞率", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": False},
    {"key": "highEnergyWindowCount", "label": "高能窗口数", "unit": "个", "format": "number", "scale": "linear", "defaultSelected": False},
    {"key": "avgRepeatRatio", "label": "重复倾向", "unit": "", "format": "percent", "scale": "linear", "defaultSelected": False},
]


def json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def to_date_string(timestamp):
    if not timestamp:
        return None
    return datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d")


def parse_date_param(value, name):
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}: {value}") from exc
    return value


def load_word_cloud_stopwords():
    stopwords = set(DEFAULT_WORD_CLOUD_STOPWORDS)
    stopwords.update(read_word_file(STOPWORDS_FILE))
    return stopwords


def is_meaningful_word(word, stopwords):
    word = (word or "").strip().lower()
    if len(word) <= 1:
        return False
    if word in stopwords:
        return False
    return not word.isdigit()


def parse_bvid_list(query, max_count, require_nonempty=False):
    raw_values = query.get("bvids", [])
    tokens = []
    for value in raw_values:
        tokens.extend(str(value or "").split(","))

    bvids = []
    seen = set()
    for token in tokens:
        bvid = token.strip()
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        bvids.append(bvid)

    if require_nonempty and not bvids:
        raise ValueError("missing bvids")
    if len(bvids) > max_count:
        raise ValueError(f"bvids must contain at most {max_count} videos")
    return bvids


def parse_heatmap_window_seconds(query):
    try:
        window_seconds = int(query.get("window_seconds", ["30"])[0] or 30)
    except ValueError as exc:
        raise ValueError("invalid window_seconds") from exc
    allowed = {5, 10, 30, 60}
    if window_seconds not in allowed:
        raise ValueError("window_seconds must be one of 5, 10, 30, 60")
    return window_seconds


def parse_json_list(value):
    import json

    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []
