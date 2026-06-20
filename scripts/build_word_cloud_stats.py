"""Build daily word-cloud statistics for fast frontend range queries.

The script pre-aggregates danmaku word counts by video, date, word, and
sentiment. The API can then aggregate this much smaller table instead of
joining raw danmaku rows with per-video word tables on every request.
"""

import _bootstrap  # noqa: F401

import argparse
import time
from datetime import datetime, timedelta

import pymysql

from app.config import END_DATE
from app.db import (
    danmaku_table_name,
    danmaku_words_table_name,
    get_all_video_records,
    get_connection,
    table_exists,
)
from app.file_utils import read_word_file
from app.paths import FILTERED_WORDS_FILE


DEFAULT_BATCH_DAYS = 7
DEFAULT_INSERT_CHUNK_SIZE = 1000


def parse_date(value, name):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"invalid {name}: {value}") from exc


def ensure_stats_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS word_cloud_daily_stats (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            video_id INT NOT NULL,
            bvid VARCHAR(20) NOT NULL,
            stat_date DATE NOT NULL,
            word VARCHAR(100) NOT NULL,
            sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral',
            count INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_word_day (video_id, stat_date, word, sentiment),
            INDEX idx_query_range (video_id, stat_date),
            INDEX idx_query_sentiment (video_id, sentiment, stat_date),
            INDEX idx_word_lookup (video_id, word)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS word_cloud_stats_progress (
            video_id INT PRIMARY KEY,
            bvid VARCHAR(20) NOT NULL,
            last_stat_date DATE DEFAULT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def get_source_date_bounds(cur, danmaku_table):
    cur.execute(f"""
        SELECT MIN(dm_date) AS min_date, MAX(dm_date) AS max_date
        FROM `{danmaku_table}`
        WHERE dm_date IS NOT NULL
    """)
    row = cur.fetchone()
    if not row:
        return None, None
    return row["min_date"], row["max_date"]


def get_progress_date(cur, video_id):
    cur.execute("""
        SELECT last_stat_date
        FROM word_cloud_stats_progress
        WHERE video_id = %s
    """, (video_id,))
    row = cur.fetchone()
    return row["last_stat_date"] if row else None


def is_video_completed(cur, bvid):
    """只默认统计已抓取到截止日期的视频，避免基于半成品数据生成前端缓存。
    Only build default stats for videos crawled through END_DATE.
    """
    cur.execute("""
        SELECT last_date
        FROM danmaku_progress
        WHERE bvid = %s
          AND last_date >= %s
    """, (bvid, END_DATE))
    return cur.fetchone() is not None


def update_progress(cur, video, last_stat_date):
    cur.execute("""
        INSERT INTO word_cloud_stats_progress (video_id, bvid, last_stat_date)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            bvid = VALUES(bvid),
            last_stat_date = VALUES(last_stat_date)
    """, (video["id"], video["bvid"], last_stat_date))


def reset_video_stats(cur, video_id):
    cur.execute("DELETE FROM word_cloud_daily_stats WHERE video_id = %s", (video_id,))
    cur.execute("DELETE FROM word_cloud_stats_progress WHERE video_id = %s", (video_id,))


def is_valid_stat_word(word, filtered_words):
    word = (word or "").strip()
    if len(word) <= 1:
        return False
    if word.lower() in filtered_words:
        return False
    if word.isdigit():
        return False
    return True


def fetch_daily_word_counts(cur, danmaku_table, words_table, start_date, end_date):
    cur.execute(f"""
        SELECT
            d.dm_date AS stat_date,
            w.word,
            w.sentiment,
            COUNT(*) AS count
        FROM `{danmaku_table}` AS d
        STRAIGHT_JOIN `{words_table}` AS w
          ON w.danmaku_row_id = d.id
        WHERE d.dm_date BETWEEN %s AND %s
          AND w.word IS NOT NULL
          AND w.word <> ''
        GROUP BY d.dm_date, w.word, w.sentiment
    """, (start_date, end_date))
    return cur.fetchall()


def replace_stats_batch(cur, video, rows, start_date, end_date, filtered_words, min_count, insert_chunk_size):
    cur.execute("""
        DELETE FROM word_cloud_daily_stats
        WHERE video_id = %s
          AND stat_date BETWEEN %s AND %s
    """, (video["id"], start_date, end_date))

    data = []
    inserted = 0
    insert_sql = """
        INSERT INTO word_cloud_daily_stats
        (video_id, bvid, stat_date, word, sentiment, count)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            count = VALUES(count),
            updated_at = CURRENT_TIMESTAMP
    """

    def flush():
        nonlocal inserted
        if not data:
            return
        cur.executemany(insert_sql, data)
        inserted += cur.rowcount
        data.clear()

    for row in rows:
        word = (row["word"] or "").strip()
        count = int(row["count"] or 0)
        if count < min_count:
            continue
        if not is_valid_stat_word(word, filtered_words):
            continue
        data.append((
            video["id"],
            video["bvid"],
            row["stat_date"],
            word,
            row["sentiment"] or "neutral",
            count,
        ))
        if len(data) >= insert_chunk_size:
            flush()

    flush()
    return inserted


def date_batches(start_date, end_date, batch_days):
    current = start_date
    while current <= end_date:
        batch_end = min(end_date, current + timedelta(days=batch_days - 1))
        yield current, batch_end
        current = batch_end + timedelta(days=1)


def process_video(cur, conn, video, args, filtered_words):
    danmaku_table = danmaku_table_name(video["id"])
    words_table = danmaku_words_table_name(video["id"])
    if not table_exists(cur, danmaku_table):
        print(f"{video['bvid']}: 未找到弹幕表，跳过")
        return 0
    if not table_exists(cur, words_table):
        print(f"{video['bvid']}: 未找到分词表，跳过")
        return 0

    if args.rebuild:
        reset_video_stats(cur, video["id"])
        conn.commit()

    source_start, source_end = get_source_date_bounds(cur, danmaku_table)
    if not source_start or not source_end:
        print(f"{video['bvid']}: 弹幕表没有可统计日期，跳过")
        return 0

    start_date = parse_date(args.start, "start") or source_start
    end_date = parse_date(args.end, "end") or source_end
    start_date = max(start_date, source_start)
    end_date = min(end_date, source_end)

    if not args.rebuild and not args.start:
        progress_date = get_progress_date(cur, video["id"])
        if progress_date:
            start_date = max(start_date, progress_date + timedelta(days=1))

    if start_date > end_date:
        print(f"{video['bvid']}: 统计已是最新，无需处理")
        return 0

    total_inserted = 0
    for batch_start, batch_end in date_batches(start_date, end_date, args.batch_days):
        rows = fetch_daily_word_counts(cur, danmaku_table, words_table, batch_start, batch_end)
        inserted = replace_stats_batch(
            cur,
            video,
            rows,
            batch_start,
            batch_end,
            filtered_words,
            args.min_count,
            args.insert_chunk_size,
        )
        update_progress(cur, video, batch_end)
        conn.commit()
        total_inserted += inserted
        print(
            f"{video['bvid']}: {batch_start} 至 {batch_end} "
            f"聚合 {len(rows)} 行，写入/更新 {inserted} 行"
        )
        if args.sleep > 0:
            time.sleep(args.sleep)

    return total_inserted


def parse_args():
    parser = argparse.ArgumentParser(description="构建词云每日预聚合统计表")
    parser.add_argument("--bvid", help="只处理指定 bvid")
    parser.add_argument("--rebuild", action="store_true", help="删除目标视频旧统计并重建")
    parser.add_argument("--start", help="只统计该日期之后，格式 YYYY-MM-DD")
    parser.add_argument("--end", help="只统计该日期之前，格式 YYYY-MM-DD")
    parser.add_argument("--batch-days", type=int, default=DEFAULT_BATCH_DAYS, help="每批处理的天数")
    parser.add_argument("--min-count", type=int, default=1, help="每天单词低于该次数不保存")
    parser.add_argument("--insert-chunk-size", type=int, default=DEFAULT_INSERT_CHUNK_SIZE, help="单次批量写入行数")
    parser.add_argument("--limit-videos", type=int, default=0, help="本轮最多处理多少个视频；0 表示不限")
    parser.add_argument("--sleep", type=float, default=0.5, help="每个日期批次提交后的暂停秒数")
    parser.add_argument("--include-incomplete", action="store_true", help="包含尚未抓取到截止日期的视频")
    args = parser.parse_args()
    args.batch_days = max(args.batch_days, 1)
    args.min_count = max(args.min_count, 1)
    args.insert_chunk_size = max(args.insert_chunk_size, 1)
    args.limit_videos = max(args.limit_videos, 0)
    args.sleep = max(args.sleep, 0)
    return args


def main():
    args = parse_args()
    videos = get_all_video_records()
    if args.bvid:
        videos = [video for video in videos if video["bvid"] == args.bvid]
    if args.limit_videos:
        videos = videos[:args.limit_videos]
    if not videos:
        print("没有可处理的视频。")
        return

    filtered_words = read_word_file(FILTERED_WORDS_FILE)
    total_inserted = 0
    processed = 0
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            ensure_stats_tables(cur)
            conn.commit()
            for video in videos:
                if not args.include_incomplete and not is_video_completed(cur, video["bvid"]):
                    print(f"{video['bvid']}: 尚未抓取到截止日期 {END_DATE}，跳过")
                    continue
                inserted = process_video(cur, conn, video, args, filtered_words)
                total_inserted += inserted
                processed += 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"\n完成：处理 {processed} 个视频，写入/更新统计行 {total_inserted}。")


if __name__ == "__main__":
    main()
