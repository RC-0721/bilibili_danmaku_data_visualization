"""Build precomputed video similarity matrices.

The script computes pairwise video similarity for all videos and writes the
results into video_similarity_matrix. It uses word_cloud_daily_stats for
non-neutral sentiment features, raw danmaku history tables for trend features,
and high_energy_windows when available for high-energy structure features.
"""

import _bootstrap  # noqa: F401

import argparse
import math
from collections import defaultdict
from datetime import datetime

import pymysql

from app.db import danmaku_table_name, get_all_video_records, get_connection, table_exists
WORD_CLOUD_STATS_TABLE = "word_cloud_daily_stats"
FEATURE_VERSION = "v1"
DEFAULT_DAYS = 365
DEFAULT_HIGH_ENERGY_BINS = 100
DEFAULT_WINDOW_SECONDS = 5
DEFAULT_WEIGHTS = {
    "trend": 0.40,
    "sentiment": 0.30,
    "high_energy": 0.30,
}
METRICS = {"trend", "sentiment", "high_energy", "combined"}


def ensure_similarity_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_similarity_matrix (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            feature_version VARCHAR(50) NOT NULL,
            metric VARCHAR(30) NOT NULL,
            video_id_a INT NOT NULL,
            video_id_b INT NOT NULL,
            bvid_a VARCHAR(20) NOT NULL,
            bvid_b VARCHAR(20) NOT NULL,
            similarity DOUBLE NOT NULL DEFAULT 0,
            word_similarity DOUBLE DEFAULT NULL,
            trend_similarity DOUBLE DEFAULT NULL,
            sentiment_similarity DOUBLE DEFAULT NULL,
            high_energy_similarity DOUBLE DEFAULT NULL,
            shared_terms_json JSON DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_similarity_pair (feature_version, metric, video_id_a, video_id_b),
            INDEX idx_metric_version (feature_version, metric),
            INDEX idx_video_pair (video_id_a, video_id_b)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def parse_metric_arg(value):
    if value == "all":
        return sorted(METRICS)
    metrics = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in metrics if item not in METRICS]
    if unknown:
        raise ValueError(f"unknown metric: {', '.join(unknown)}")
    return metrics


def cosine_dense(vector_a, vector_b):
    if not vector_a or not vector_b:
        return None
    dot = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(value * value for value in vector_a))
    norm_b = math.sqrt(sum(value * value for value in vector_b))
    if not norm_a or not norm_b:
        return None
    return dot / (norm_a * norm_b)


def publish_date(video):
    pubdate = int(video.get("pubdate") or 0)
    if pubdate <= 0:
        return None
    return datetime.fromtimestamp(pubdate).date()


def load_sentiment_vectors(cur, videos):
    vectors = {}
    for video in videos:
        cur.execute(f"""
            SELECT sentiment, SUM(count) AS count
            FROM `{WORD_CLOUD_STATS_TABLE}`
            WHERE video_id = %s
            GROUP BY sentiment
        """, (video["id"],))
        counts = defaultdict(int)
        for row in cur.fetchall():
            counts[row["sentiment"] or "neutral"] += int(row["count"] or 0)
        positive = counts["positive"]
        negative = counts["negative"]
        non_neutral_total = positive + negative
        if non_neutral_total <= 0:
            vectors[video["id"]] = []
        else:
            vectors[video["id"]] = [positive / non_neutral_total, negative / non_neutral_total]
    return vectors


def load_trend_vectors(cur, videos, days):
    vectors = {}
    for video in videos:
        table_name = danmaku_table_name(video["id"])
        pub_date = publish_date(video)
        if not pub_date or not table_exists(cur, table_name):
            vectors[video["id"]] = []
            continue
        vector = [0.0] * days
        cur.execute(f"""
            SELECT dm_date, COUNT(*) AS count
            FROM `{table_name}`
            WHERE dm_date IS NOT NULL
            GROUP BY dm_date
        """)
        for row in cur.fetchall():
            day_index = (row["dm_date"] - pub_date).days
            if 0 <= day_index < days:
                vector[day_index] = math.log1p(int(row["count"] or 0))
        vectors[video["id"]] = vector
    return vectors


def load_high_energy_vectors(cur, videos, bins, window_seconds):
    vectors = {}
    if not table_exists(cur, "high_energy_windows"):
        return {video["id"]: [] for video in videos}

    for video in videos:
        duration = int(video.get("duration") or 0)
        if duration <= 0:
            vectors[video["id"]] = []
            continue
        vector = [0.0] * bins
        cur.execute("""
            SELECT start_seconds, score
            FROM high_energy_windows
            WHERE video_id = %s
              AND window_seconds = %s
        """, (video["id"], window_seconds))
        for row in cur.fetchall():
            ratio = max(0.0, min(float(row["start_seconds"] or 0) / duration, 0.999999))
            index = min(int(ratio * bins), bins - 1)
            vector[index] = max(vector[index], float(row["score"] or 0))
        vectors[video["id"]] = vector
    return vectors


def combined_similarity(scores):
    available = {
        key: value
        for key, value in scores.items()
        if key in DEFAULT_WEIGHTS and value is not None
    }
    weight_sum = sum(DEFAULT_WEIGHTS[key] for key in available)
    if weight_sum <= 0:
        return None
    return sum(available[key] * DEFAULT_WEIGHTS[key] for key in available) / weight_sum


def metric_value(metric, scores):
    if metric == "combined":
        return combined_similarity(scores)
    return scores.get(metric)


def replace_rows(cur, rows, chunk_size=1000):
    if not rows:
        return 0
    sql = """
        INSERT INTO video_similarity_matrix
        (
            feature_version, metric, video_id_a, video_id_b, bvid_a, bvid_b,
            similarity, word_similarity, trend_similarity, sentiment_similarity,
            high_energy_similarity, shared_terms_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            similarity = VALUES(similarity),
            word_similarity = VALUES(word_similarity),
            trend_similarity = VALUES(trend_similarity),
            sentiment_similarity = VALUES(sentiment_similarity),
            high_energy_similarity = VALUES(high_energy_similarity),
            shared_terms_json = VALUES(shared_terms_json),
            created_at = CURRENT_TIMESTAMP
    """
    written = 0
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        cur.executemany(sql, chunk)
        written += cur.rowcount
    return written


def build_rows(videos, metrics, feature_version, vectors):
    rows = []
    for video_a in videos:
        for video_b in videos:
            id_a = video_a["id"]
            id_b = video_b["id"]
            if id_a == id_b:
                scores = {
                    "trend": 1.0 if vectors["trend"].get(id_a) else None,
                    "sentiment": 1.0 if vectors["sentiment"].get(id_a) else None,
                    "high_energy": 1.0 if vectors["high_energy"].get(id_a) else None,
                }
            else:
                scores = {
                    "trend": cosine_dense(vectors["trend"].get(id_a, []), vectors["trend"].get(id_b, [])),
                    "sentiment": cosine_dense(vectors["sentiment"].get(id_a, []), vectors["sentiment"].get(id_b, [])),
                    "high_energy": cosine_dense(vectors["high_energy"].get(id_a, []), vectors["high_energy"].get(id_b, [])),
                }

            for metric in metrics:
                value = metric_value(metric, scores)
                if value is None:
                    value = 0.0
                rows.append((
                    feature_version,
                    metric,
                    id_a,
                    id_b,
                    video_a["bvid"],
                    video_b["bvid"],
                    round(float(value), 6),
                    None,
                    None if scores["trend"] is None else round(float(scores["trend"]), 6),
                    None if scores["sentiment"] is None else round(float(scores["sentiment"]), 6),
                    None if scores["high_energy"] is None else round(float(scores["high_energy"]), 6),
                    None,
                ))
    return rows


def parse_args():
    parser = argparse.ArgumentParser(description="构建视频相似度矩阵预计算表")
    parser.add_argument("--metric", default="all", help="trend/sentiment/high_energy/combined/all，可用逗号分隔")
    parser.add_argument("--feature-version", default=FEATURE_VERSION, help="特征版本")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="趋势向量取发布后多少天")
    parser.add_argument("--high-energy-bins", type=int, default=DEFAULT_HIGH_ENERGY_BINS, help="高能结构归一化桶数")
    parser.add_argument("--window-seconds", type=int, default=DEFAULT_WINDOW_SECONDS, help="使用哪个高能窗口粒度")
    parser.add_argument("--limit-videos", type=int, default=0, help="仅处理前 N 个视频；0 表示全部")
    parser.add_argument("--execute", action="store_true", help="实际写入数据库；不加时只预览")
    args = parser.parse_args()
    args.metrics = parse_metric_arg(args.metric)
    args.days = max(args.days, 1)
    args.high_energy_bins = max(args.high_energy_bins, 1)
    args.limit_videos = max(args.limit_videos, 0)
    return args


def main():
    args = parse_args()
    videos = get_all_video_records()
    if args.limit_videos:
        videos = videos[:args.limit_videos]
    if not videos:
        print("没有可处理的视频。")
        return

    planned_rows = len(videos) * len(videos) * len(args.metrics)
    print(f"准备处理 {len(videos)} 个视频，metric={','.join(args.metrics)}，version={args.feature_version}")
    print(f"预计生成 {planned_rows} 行相似度记录。")
    if not args.execute:
        print("当前为预览模式，未读取大表、未写入数据库。加 --execute 后正式计算并写入。")
        return

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if not table_exists(cur, WORD_CLOUD_STATS_TABLE):
                raise RuntimeError("word_cloud_daily_stats 不存在，请先运行 build_word_cloud_stats.py")

            ensure_similarity_table(cur)
            conn.commit()

            print("读取趋势特征...")
            trend_vectors = load_trend_vectors(cur, videos, args.days)
            print("读取非中性情绪结构特征...")
            sentiment_vectors = load_sentiment_vectors(cur, videos)
            print("读取高能结构特征...")
            high_energy_vectors = load_high_energy_vectors(cur, videos, args.high_energy_bins, args.window_seconds)

            vectors = {
                "trend": trend_vectors,
                "sentiment": sentiment_vectors,
                "high_energy": high_energy_vectors,
            }
            rows = build_rows(videos, args.metrics, args.feature_version, vectors)
            print(f"实际生成 {len(rows)} 行相似度记录。")

            metrics_placeholders = ", ".join(["%s"] * len(args.metrics))
            cur.execute(f"""
                DELETE FROM video_similarity_matrix
                WHERE feature_version = %s
                  AND metric IN ({metrics_placeholders})
            """, [args.feature_version, *args.metrics])
            cur.execute("""
                DELETE FROM video_similarity_matrix
                WHERE feature_version = %s
                  AND metric = 'word'
            """, (args.feature_version,))
            written = replace_rows(cur, rows)
            conn.commit()
            print(f"完成：写入/更新 {written} 行。")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
