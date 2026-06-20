"""Build video-level statistics for the parallel-coordinate view.

The script pre-aggregates metadata, interaction counts, high-energy density,
sentiment structure, and lexical richness into video_parallel_stats. The
frontend can then render the parallel-coordinate chart without scanning raw
danmaku or word tables on every request.
"""

import _bootstrap  # noqa: F401

import argparse
import math

import pymysql

from app.db import danmaku_table_name, get_connection, table_exists


PARALLEL_STATS_TABLE = "video_parallel_stats"
DEFAULT_WINDOW_SECONDS = 5


def ratio(numerator, denominator):
    denominator = float(denominator or 0)
    if denominator <= 0:
        return 0.0
    return float(numerator or 0) / denominator


def ensure_parallel_stats_table(cur):
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS `{PARALLEL_STATS_TABLE}` (
            video_id INT NOT NULL PRIMARY KEY,
            bvid VARCHAR(20) NOT NULL,
            title VARCHAR(500) DEFAULT '',
            duration_seconds INT NOT NULL DEFAULT 0,
            stat_view BIGINT NOT NULL DEFAULT 0,
            stat_danmaku BIGINT NOT NULL DEFAULT 0,
            stat_reply BIGINT NOT NULL DEFAULT 0,
            stat_favorite BIGINT NOT NULL DEFAULT 0,
            stat_coin BIGINT NOT NULL DEFAULT 0,
            stat_share BIGINT NOT NULL DEFAULT 0,
            stat_like BIGINT NOT NULL DEFAULT 0,
            crawled_danmaku_count BIGINT NOT NULL DEFAULT 0,
            danmaku_rate DOUBLE NOT NULL DEFAULT 0,
            reply_rate DOUBLE NOT NULL DEFAULT 0,
            favorite_rate DOUBLE NOT NULL DEFAULT 0,
            coin_rate DOUBLE NOT NULL DEFAULT 0,
            share_rate DOUBLE NOT NULL DEFAULT 0,
            like_rate DOUBLE NOT NULL DEFAULT 0,
            peak_density DOUBLE NOT NULL DEFAULT 0,
            high_energy_window_count INT NOT NULL DEFAULT 0,
            avg_repeat_ratio DOUBLE NOT NULL DEFAULT 0,
            positive_count BIGINT NOT NULL DEFAULT 0,
            neutral_count BIGINT NOT NULL DEFAULT 0,
            negative_count BIGINT NOT NULL DEFAULT 0,
            positive_ratio DOUBLE NOT NULL DEFAULT 0,
            total_words BIGINT NOT NULL DEFAULT 0,
            unique_words BIGINT NOT NULL DEFAULT 0,
            lexical_richness DOUBLE NOT NULL DEFAULT 0,
            window_seconds INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_bvid (bvid),
            INDEX idx_view (stat_view),
            INDEX idx_peak_density (peak_density),
            INDEX idx_positive_ratio (positive_ratio)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def fetch_videos(cur, bvid=None):
    where_sql = ""
    params = []
    if bvid:
        where_sql = "WHERE bvid = %s"
        params.append(bvid)
    cur.execute(f"""
        SELECT
            id,
            bvid,
            title,
            duration,
            stat_view,
            stat_danmaku,
            stat_reply,
            stat_favorite,
            stat_coin,
            stat_share,
            stat_like
        FROM precious_videos
        {where_sql}
        ORDER BY id
    """, params)
    return cur.fetchall()


def load_crawled_counts(cur, videos):
    counts = {}
    for video in videos:
        table_name = danmaku_table_name(video["id"])
        if not table_exists(cur, table_name):
            counts[video["id"]] = 0
            continue
        cur.execute(f"SELECT COUNT(*) AS count FROM `{table_name}`")
        row = cur.fetchone()
        counts[video["id"]] = int(row["count"] or 0)
    return counts


def load_high_energy_stats(cur, window_seconds):
    if not table_exists(cur, "high_energy_windows"):
        return {}
    cur.execute("""
        SELECT
            video_id,
            MAX(danmaku_count / window_seconds) AS peak_density,
            SUM(is_high = 1) AS high_energy_window_count,
            AVG(repeat_ratio) AS avg_repeat_ratio
        FROM high_energy_windows
        WHERE window_seconds = %s
        GROUP BY video_id
    """, (window_seconds,))
    return {
        row["video_id"]: {
            "peak_density": float(row["peak_density"] or 0),
            "high_energy_window_count": int(row["high_energy_window_count"] or 0),
            "avg_repeat_ratio": float(row["avg_repeat_ratio"] or 0),
        }
        for row in cur.fetchall()
    }


def load_word_stats(cur):
    if not table_exists(cur, "word_cloud_daily_stats"):
        return {}
    cur.execute("""
        SELECT
            video_id,
            SUM(count) AS total_words,
            COUNT(DISTINCT word) AS unique_words,
            SUM(CASE WHEN sentiment = 'positive' THEN count ELSE 0 END) AS positive_count,
            SUM(CASE WHEN sentiment = 'neutral' THEN count ELSE 0 END) AS neutral_count,
            SUM(CASE WHEN sentiment = 'negative' THEN count ELSE 0 END) AS negative_count
        FROM word_cloud_daily_stats
        GROUP BY video_id
    """)
    stats = {}
    for row in cur.fetchall():
        positive = int(row["positive_count"] or 0)
        negative = int(row["negative_count"] or 0)
        total_words = int(row["total_words"] or 0)
        unique_words = int(row["unique_words"] or 0)
        stats[row["video_id"]] = {
            "total_words": total_words,
            "unique_words": unique_words,
            "positive_count": positive,
            "neutral_count": int(row["neutral_count"] or 0),
            "negative_count": negative,
            "positive_ratio": ratio(positive, positive + negative),
            "lexical_richness": unique_words / math.sqrt(total_words) if total_words > 0 else 0.0,
        }
    return stats


def build_rows(videos, crawled_counts, high_energy_stats, word_stats, window_seconds):
    rows = []
    for video in videos:
        video_id = video["id"]
        view_count = int(video["stat_view"] or 0)
        official_danmaku = int(video["stat_danmaku"] or 0)
        high_energy = high_energy_stats.get(video_id, {})
        words = word_stats.get(video_id, {})
        rows.append((
            video_id,
            video["bvid"],
            video["title"] or "",
            int(video["duration"] or 0),
            view_count,
            official_danmaku,
            int(video["stat_reply"] or 0),
            int(video["stat_favorite"] or 0),
            int(video["stat_coin"] or 0),
            int(video["stat_share"] or 0),
            int(video["stat_like"] or 0),
            int(crawled_counts.get(video_id, 0)),
            ratio(official_danmaku, view_count),
            ratio(video["stat_reply"], view_count),
            ratio(video["stat_favorite"], view_count),
            ratio(video["stat_coin"], view_count),
            ratio(video["stat_share"], view_count),
            ratio(video["stat_like"], view_count),
            float(high_energy.get("peak_density", 0)),
            int(high_energy.get("high_energy_window_count", 0)),
            float(high_energy.get("avg_repeat_ratio", 0)),
            int(words.get("positive_count", 0)),
            int(words.get("neutral_count", 0)),
            int(words.get("negative_count", 0)),
            float(words.get("positive_ratio", 0)),
            int(words.get("total_words", 0)),
            int(words.get("unique_words", 0)),
            float(words.get("lexical_richness", 0)),
            window_seconds,
        ))
    return rows


def replace_rows(cur, rows):
    if not rows:
        return 0
    sql = f"""
        INSERT INTO `{PARALLEL_STATS_TABLE}`
        (
            video_id, bvid, title, duration_seconds,
            stat_view, stat_danmaku, stat_reply, stat_favorite, stat_coin, stat_share, stat_like,
            crawled_danmaku_count,
            danmaku_rate, reply_rate, favorite_rate, coin_rate, share_rate, like_rate,
            peak_density, high_energy_window_count, avg_repeat_ratio,
            positive_count, neutral_count, negative_count, positive_ratio,
            total_words, unique_words, lexical_richness,
            window_seconds
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s
        )
        ON DUPLICATE KEY UPDATE
            bvid = VALUES(bvid),
            title = VALUES(title),
            duration_seconds = VALUES(duration_seconds),
            stat_view = VALUES(stat_view),
            stat_danmaku = VALUES(stat_danmaku),
            stat_reply = VALUES(stat_reply),
            stat_favorite = VALUES(stat_favorite),
            stat_coin = VALUES(stat_coin),
            stat_share = VALUES(stat_share),
            stat_like = VALUES(stat_like),
            crawled_danmaku_count = VALUES(crawled_danmaku_count),
            danmaku_rate = VALUES(danmaku_rate),
            reply_rate = VALUES(reply_rate),
            favorite_rate = VALUES(favorite_rate),
            coin_rate = VALUES(coin_rate),
            share_rate = VALUES(share_rate),
            like_rate = VALUES(like_rate),
            peak_density = VALUES(peak_density),
            high_energy_window_count = VALUES(high_energy_window_count),
            avg_repeat_ratio = VALUES(avg_repeat_ratio),
            positive_count = VALUES(positive_count),
            neutral_count = VALUES(neutral_count),
            negative_count = VALUES(negative_count),
            positive_ratio = VALUES(positive_ratio),
            total_words = VALUES(total_words),
            unique_words = VALUES(unique_words),
            lexical_richness = VALUES(lexical_richness),
            window_seconds = VALUES(window_seconds),
            updated_at = CURRENT_TIMESTAMP
    """
    cur.executemany(sql, rows)
    return cur.rowcount


def parse_args():
    parser = argparse.ArgumentParser(description="构建视频平行坐标图预聚合统计表")
    parser.add_argument("--bvid", default="", help="仅处理指定视频；默认处理全部视频")
    parser.add_argument("--window-seconds", type=int, default=DEFAULT_WINDOW_SECONDS, help="峰值密度使用的高能窗口秒数")
    parser.add_argument("--execute", action="store_true", help="实际写入数据库；不加时只预览")
    args = parser.parse_args()
    args.window_seconds = max(int(args.window_seconds or DEFAULT_WINDOW_SECONDS), 1)
    return args


def main():
    args = parse_args()
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            videos = fetch_videos(cur, args.bvid.strip() or None)
            if not videos:
                print("没有可处理的视频。")
                return

            print(f"准备处理 {len(videos)} 个视频，峰值密度窗口={args.window_seconds}s。")
            if not args.execute:
                print("当前为预览模式，未读取统计大表、未写入数据库。加 --execute 后正式计算并写入。")
                return

            ensure_parallel_stats_table(cur)
            conn.commit()

            print("读取已抓取弹幕数量...")
            crawled_counts = load_crawled_counts(cur, videos)
            print("读取高能窗口统计...")
            high_energy_stats = load_high_energy_stats(cur, args.window_seconds)
            print("读取词汇与情绪统计...")
            word_stats = load_word_stats(cur)

            rows = build_rows(videos, crawled_counts, high_energy_stats, word_stats, args.window_seconds)
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
