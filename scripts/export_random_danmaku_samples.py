"""导出每个视频的随机弹幕文本样本。
Export random text samples from each video's danmaku history table.
"""

import _bootstrap  # noqa: F401

import argparse
import random
import re
from pathlib import Path

import pymysql

from app.config import END_DATE
from app.db import danmaku_table_name, get_all_video_records, get_connection, table_exists
from app.paths import DANMAKU_SAMPLES_DIR


DEFAULT_OUTPUT_DIR = DANMAKU_SAMPLES_DIR
DEFAULT_LIMIT = 5000
DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_BATCHES = 80
FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_filename(value):
    """生成安全文件名。
    Build a safe filename.
    """
    return FILENAME_RE.sub("_", str(value or "").strip()) or "unknown"


def get_id_bounds(cur, table_name):
    """只读取主键范围，避免全表随机排序。
    Read only primary-key bounds to avoid full-table random sorting.
    """
    cur.execute(f"""
        SELECT MIN(id) AS min_id, MAX(id) AS max_id
        FROM `{table_name}`
        WHERE content IS NOT NULL
          AND TRIM(content) <> ''
    """)
    row = cur.fetchone()
    if not row or row["min_id"] is None or row["max_id"] is None:
        return None, None
    return int(row["min_id"]), int(row["max_id"])


def fetch_range_batch(cur, table_name, start_id, batch_size):
    """从随机主键起点向后读取一小批记录。
    Read a small ordered batch after a random primary-key start.
    """
    cur.execute(f"""
        SELECT id, content
        FROM `{table_name}`
        WHERE id >= %s
          AND content IS NOT NULL
          AND TRIM(content) <> ''
        ORDER BY id
        LIMIT %s
    """, (start_id, batch_size))
    return cur.fetchall()


def sample_table(cur, table_name, limit, batch_size, max_batches):
    """基于随机主键起点近似采样，避免 ORDER BY RAND()。
    Approximate sampling via random primary-key starts, avoiding ORDER BY RAND().
    """
    min_id, max_id = get_id_bounds(cur, table_name)
    if min_id is None:
        return []

    seen_ids = set()
    samples = []
    attempts = 0
    max_attempts = max(max_batches, (limit // max(batch_size, 1)) * 2)

    while len(samples) < limit and attempts < max_attempts:
        attempts += 1
        start_id = random.randint(min_id, max_id)
        for row in fetch_range_batch(cur, table_name, start_id, batch_size):
            row_id = int(row["id"])
            content = (row["content"] or "").strip()
            if row_id in seen_ids or not content:
                continue
            seen_ids.add(row_id)
            samples.append(content)
            if len(samples) >= limit:
                break

    return samples


def write_samples(output_dir, video, samples):
    """将单个视频样本写入 txt 文件。
    Write one video's samples to a txt file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = sample_output_path(output_dir, video)
    body = "\n".join(samples)
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")
    return path


def sample_output_path(output_dir, video):
    """返回单个视频样本文件路径。
    Return the output sample file path for one video.
    """
    bvid = video["bvid"]
    title = safe_filename(video.get("title", ""))[:80]
    suffix = f"_{title}" if title else ""
    return output_dir / f"{safe_filename(bvid)}{suffix}.txt"


def is_video_completed(cur, bvid):
    """判断视频是否已经抓取到截止日期。
    Check whether a video has been crawled through END_DATE.
    """
    if not table_exists(cur, "danmaku_progress"):
        return False

    cur.execute("""
        SELECT last_date
        FROM danmaku_progress
        WHERE bvid = %s
          AND last_date >= %s
    """, (bvid, END_DATE))
    return cur.fetchone() is not None


def process_video(cur, video, output_dir, limit, batch_size, max_batches):
    """处理一个视频：采样并写入文件。
    Process one video: sample rows and write the output file.
    """
    table_name = danmaku_table_name(video["id"])
    bvid = video["bvid"]
    output_path = sample_output_path(output_dir, video)
    if output_path.exists():
        print(f"{bvid}: 已存在随机弹幕样本 {output_path}，跳过，避免重复导出")
        return 0, True

    if not table_exists(cur, table_name):
        print(f"{bvid}: 未找到弹幕表，跳过")
        return 0, False

    samples = sample_table(cur, table_name, limit, batch_size, max_batches)
    path = write_samples(output_dir, video, samples)
    print(f"{bvid}: 导出 {len(samples)} 条 -> {path}")
    return len(samples), False


def main():
    parser = argparse.ArgumentParser(description="为每个视频导出最多 N 条随机弹幕文本样本。")
    parser.add_argument("--bvid", help="只导出指定 bvid")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"每个视频最多导出条数，默认 {DEFAULT_LIMIT}")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="每次随机起点读取的小批量大小")
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES, help="每个视频最多执行的小批量查询次数")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="txt 输出目录")
    args = parser.parse_args()

    videos = get_all_video_records()
    if args.bvid:
        videos = [video for video in videos if video["bvid"] == args.bvid]

    if not videos:
        print("没有可导出的视频。")
        return

    total = 0
    processed_videos = 0
    skipped_incomplete = 0
    skipped_existing = 0
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            for video in videos:
                if not is_video_completed(cur, video["bvid"]):
                    skipped_incomplete += 1
                    print(f"{video['bvid']}: 尚未抓取到截止日期 {END_DATE}，跳过")
                    continue
                sample_count, existed = process_video(
                    cur=cur,
                    video=video,
                    output_dir=args.output_dir,
                    limit=args.limit,
                    batch_size=args.batch_size,
                    max_batches=args.max_batches,
                )
                if existed:
                    skipped_existing += 1
                    continue
                total += sample_count
                processed_videos += 1
    finally:
        conn.close()

    print(
        f"\n完成：处理 {processed_videos} 个已完成视频，"
        f"跳过 {skipped_incomplete} 个未完成视频，"
        f"跳过 {skipped_existing} 个已有样本视频，共导出 {total} 条弹幕样本。"
    )


if __name__ == "__main__":
    main()
