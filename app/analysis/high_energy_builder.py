"""Rule-based high-energy window builder."""

import argparse
from math import floor

import pymysql

from app.analysis.high_energy_tables import (
    ensure_high_energy_segments_table,
    ensure_high_energy_table,
    save_rows,
    save_segments,
)
from app.db import get_all_video_records, get_connection, table_exists

DEFAULT_WINDOW_SECONDS = 5
DEFAULT_PERCENTILE = 90
DEFAULT_MIN_SCORE = 0.55
DEFAULT_MIN_COUNT = 20
DEFAULT_TOP_WORDS = 5
DEFAULT_MERGE_GAP_WINDOWS = 1


def percentile(values, percent):
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, floor((percent / 100) * (len(ordered) - 1))))
    return ordered[index]


def fetch_window_counts(cur, table_name, window_ms):
    cur.execute(f"""
        SELECT
            FLOOR(progress / %s) AS window_index,
            COUNT(*) AS danmaku_count,
            COUNT(DISTINCT content) AS unique_count
        FROM `{table_name}`
        WHERE progress IS NOT NULL
          AND progress >= 0
          AND content IS NOT NULL
          AND TRIM(content) <> ''
        GROUP BY FLOOR(progress / %s)
        ORDER BY window_index
    """, (window_ms, window_ms))
    return cur.fetchall()


def fetch_window_sentiment(cur, danmaku_table, words_table, window_ms):
    cur.execute(f"""
        SELECT
            FLOOR(d.progress / %s) AS window_index,
            SUM(w.sentiment = 'positive') AS positive_count,
            SUM(w.sentiment = 'neutral') AS neutral_count,
            SUM(w.sentiment = 'negative') AS negative_count,
            COUNT(*) AS word_count
        FROM `{words_table}` AS w
        INNER JOIN `{danmaku_table}` AS d ON d.id = w.danmaku_row_id
        WHERE d.progress IS NOT NULL
          AND d.progress >= 0
        GROUP BY FLOOR(d.progress / %s)
    """, (window_ms, window_ms))
    return {
        int(row["window_index"]): {
            "positive_count": int(row["positive_count"] or 0),
            "neutral_count": int(row["neutral_count"] or 0),
            "negative_count": int(row["negative_count"] or 0),
            "word_count": int(row["word_count"] or 0),
        }
        for row in cur.fetchall()
    }


def fetch_window_top_words(cur, danmaku_table, words_table, window_ms, top_n):
    cur.execute(f"""
        SELECT
            FLOOR(d.progress / %s) AS window_index,
            w.word,
            COUNT(*) AS word_count
        FROM `{words_table}` AS w
        INNER JOIN `{danmaku_table}` AS d ON d.id = w.danmaku_row_id
        WHERE d.progress IS NOT NULL
          AND d.progress >= 0
          AND w.word IS NOT NULL
          AND w.word <> ''
        GROUP BY FLOOR(d.progress / %s), w.word
        ORDER BY window_index, word_count DESC
    """, (window_ms, window_ms))
    top_words = {}
    for row in cur.fetchall():
        window_index = int(row["window_index"])
        words = top_words.setdefault(window_index, [])
        if len(words) < top_n:
            words.append({"word": row["word"], "count": int(row["word_count"] or 0)})
    return top_words


def build_rows(count_rows, sentiment_by_window, top_words_by_window, window_seconds, min_count, min_score, percentile_value):
    if not count_rows:
        return []

    max_count = max(int(row["danmaku_count"] or 0) for row in count_rows) or 1
    scored = []
    for row in count_rows:
        window_index = int(row["window_index"])
        danmaku_count = int(row["danmaku_count"] or 0)
        unique_count = int(row["unique_count"] or 0)
        repeat_ratio = (danmaku_count - unique_count) / danmaku_count if danmaku_count else 0
        density_norm = danmaku_count / max_count
        sentiment = sentiment_by_window.get(window_index, {})
        word_count = sentiment.get("word_count", 0)
        positive_count = sentiment.get("positive_count", 0)
        negative_count = sentiment.get("negative_count", 0)
        top_words = top_words_by_window.get(window_index, [])
        top_word_count = top_words[0]["count"] if top_words else 0
        emotion_ratio = (positive_count + negative_count) / word_count if word_count else 0
        top_word_ratio = top_word_count / word_count if word_count else 0
        score = 0.55 * density_norm + 0.20 * repeat_ratio + 0.15 * emotion_ratio + 0.10 * top_word_ratio
        scored.append({
            "window_index": window_index,
            "start_seconds": window_index * window_seconds,
            "end_seconds": (window_index + 1) * window_seconds,
            "score": round(min(score, 1), 6),
            "danmaku_count": danmaku_count,
            "unique_count": unique_count,
            "repeat_ratio": round(repeat_ratio, 6),
            "density_norm": round(density_norm, 6),
            "positive_count": positive_count,
            "neutral_count": sentiment.get("neutral_count", 0),
            "negative_count": negative_count,
            "emotion_ratio": round(emotion_ratio, 6),
            "top_word": top_words[0]["word"] if top_words else "",
            "top_word_ratio": round(top_word_ratio, 6),
            "top_words": top_words,
        })

    threshold = max(min_score, percentile([row["score"] for row in scored], percentile_value))
    for row in scored:
        row["is_high"] = int(row["score"] >= threshold and row["danmaku_count"] >= min_count)
    return scored


def combine_top_words(rows, top_n):
    counts = {}
    for row in rows:
        for item in row.get("top_words") or []:
            word = item.get("word")
            if word:
                counts[word] = counts.get(word, 0) + int(item.get("count") or 0)
    return [{"word": word, "count": count} for word, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:top_n]]


def segment_from_rows(segment_index, rows, top_n):
    top_words = combine_top_words(rows, top_n)
    score_sum = sum(float(row["score"] or 0) for row in rows)
    return {
        "segment_index": segment_index,
        "start_seconds": min(row["start_seconds"] for row in rows),
        "end_seconds": max(row["end_seconds"] for row in rows),
        "window_count": len(rows),
        "peak_score": round(max(float(row["score"] or 0) for row in rows), 6),
        "avg_score": round(score_sum / len(rows), 6),
        "danmaku_count": sum(int(row["danmaku_count"] or 0) for row in rows),
        "positive_count": sum(int(row["positive_count"] or 0) for row in rows),
        "neutral_count": sum(int(row["neutral_count"] or 0) for row in rows),
        "negative_count": sum(int(row["negative_count"] or 0) for row in rows),
        "top_word": top_words[0]["word"] if top_words else "",
        "top_words": top_words,
    }


def build_segments(rows, merge_gap_windows, top_n):
    segments = []
    current_rows = []
    last_window_index = None
    for row in [item for item in rows if item.get("is_high")]:
        window_index = int(row["window_index"])
        if current_rows and window_index - last_window_index - 1 > merge_gap_windows:
            segments.append(segment_from_rows(len(segments) + 1, current_rows, top_n))
            current_rows = []
        current_rows.append(row)
        last_window_index = window_index
    if current_rows:
        segments.append(segment_from_rows(len(segments) + 1, current_rows, top_n))
    return segments


def process_video(cur, video, args):
    danmaku_table = f"video_{video['id']}_danmaku_history"
    words_table = f"danmaku_words_{video['id']}"
    if not table_exists(cur, danmaku_table):
        print(f"{video['bvid']}: 未找到弹幕表，跳过")
        return 0

    window_ms = args.window_seconds * 1000
    count_rows = fetch_window_counts(cur, danmaku_table, window_ms)
    sentiment_by_window = {}
    top_words_by_window = {}
    if table_exists(cur, words_table):
        sentiment_by_window = fetch_window_sentiment(cur, danmaku_table, words_table, window_ms)
        top_words_by_window = fetch_window_top_words(cur, danmaku_table, words_table, window_ms, args.top_words)
    else:
        print(f"{video['bvid']}: 未找到分词表，仅使用弹幕密度与重复率评分")

    rows = build_rows(count_rows, sentiment_by_window, top_words_by_window, args.window_seconds, args.min_count, args.min_score, args.percentile)
    segments = build_segments(rows, args.merge_gap_windows, args.top_words)
    inserted = save_rows(cur, video, args.window_seconds, rows)
    inserted_segments = save_segments(cur, video, args.window_seconds, segments)
    high_count = sum(row["is_high"] for row in rows)
    print(f"{video['bvid']}: 写入 {inserted} 个窗口，其中高能窗口 {high_count} 个；合并高能片段 {inserted_segments} 个")
    return inserted


def parse_args():
    parser = argparse.ArgumentParser(description="生成规则高能时刻窗口评分")
    parser.add_argument("--bvid", help="只处理指定 bvid")
    parser.add_argument("--window-seconds", type=int, default=DEFAULT_WINDOW_SECONDS, help="时间窗口秒数")
    parser.add_argument("--percentile", type=int, default=DEFAULT_PERCENTILE, help="高能阈值百分位")
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE, help="最低高能分数")
    parser.add_argument("--min-count", type=int, default=DEFAULT_MIN_COUNT, help="窗口最低弹幕数")
    parser.add_argument("--top-words", type=int, default=DEFAULT_TOP_WORDS, help="每个窗口保留的高频词数量")
    parser.add_argument("--merge-gap-windows", type=int, default=DEFAULT_MERGE_GAP_WINDOWS, help="合并高能片段时允许间隔的非高能窗口数")
    return parser.parse_args()


def main():
    args = parse_args()
    videos = get_all_video_records()
    if args.bvid:
        videos = [video for video in videos if video["bvid"] == args.bvid]
    if not videos:
        print("没有可处理的视频。")
        return

    total = 0
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            ensure_high_energy_table(cur)
            ensure_high_energy_segments_table(cur)
            for video in videos:
                total += process_video(cur, video, args)
                conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"\n完成：处理 {len(videos)} 个视频，写入 {total} 个窗口评分。")
