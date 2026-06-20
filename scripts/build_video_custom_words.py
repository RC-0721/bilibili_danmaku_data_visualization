"""根据高频完整弹幕生成每个视频的 pkuseg 用户词典。
Generate per-video pkuseg user dictionaries from frequent full danmaku lines.
"""

import _bootstrap  # noqa: F401

import argparse
import re
from pathlib import Path

import pymysql

from app.config import END_DATE
from app.text.segmentation import get_filtered_words
from app.db import (
    danmaku_table_name,
    get_all_video_records,
    get_connection,
    table_exists,
)
from app.paths import CUSTOM_WORDS_DIR


DEFAULT_OUTPUT_DIR = CUSTOM_WORDS_DIR
DEFAULT_LIMIT = 200000
WHITESPACE_RE = re.compile(r"\s+")


def clean_phrase(value):
    """规范化候选短语中的空白。
    Normalize whitespace in a candidate phrase.
    """
    phrase = (value or "").strip()
    phrase = WHITESPACE_RE.sub(" ", phrase)
    return phrase


def is_valid_phrase(phrase, min_length, max_length, filtered_words):
    if not phrase:
        return False
    if phrase.lower() in filtered_words:
        return False
    if len(phrase) < min_length:
        return False
    if max_length and len(phrase) > max_length:
        return False
    # pkuseg userdict is stored as one word or phrase per line.
    if WHITESPACE_RE.search(phrase):
        return False
    return True


def get_frequent_danmaku(cur, video_id, limit, min_length, max_length, filtered_words):
    """统计单个视频中超过阈值的完整弹幕。
    Count full danmaku lines whose frequency is above the threshold.
    """
    table_name = danmaku_table_name(video_id)
    if not table_exists(cur, table_name):
        return [], {"missing_table": True, "skipped": 0}

    cur.execute(f"""
        SELECT content, COUNT(*) AS count
        FROM `{table_name}`
        WHERE content IS NOT NULL
          AND TRIM(content) <> ''
        GROUP BY content
        HAVING COUNT(*) > %s
        ORDER BY count DESC, content ASC
    """, (limit,))

    phrases = []
    skipped = 0
    seen = set()
    for row in cur.fetchall():
        content = row["content"] if isinstance(row, dict) else row[0]
        count = row["count"] if isinstance(row, dict) else row[1]
        phrase = clean_phrase(content)
        if phrase in seen:
            continue
        seen.add(phrase)
        if not is_valid_phrase(phrase, min_length, max_length, filtered_words):
            skipped += 1
            continue
        phrases.append({"phrase": phrase, "count": int(count or 0)})

    return phrases, {"missing_table": False, "skipped": skipped}


def write_userdict(path, phrases):
    """写入 pkuseg 用户词典格式：每行一个词或短语。
    Write pkuseg userdict lines: one word or phrase per line.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [item["phrase"] for item in phrases]
    body = "\n".join(lines)
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")


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


def process_video(cur, video, output_dir, limit, min_length, max_length, dry_run):
    video_id = video["id"]
    bvid = video["bvid"]
    output_path = output_dir / f"{bvid}.txt"
    if output_path.exists():
        print(f"{bvid}: 已存在用户词典 {output_path}，跳过，避免覆盖")
        return 0, True

    filtered_words = get_filtered_words()
    phrases, stats = get_frequent_danmaku(
        cur,
        video_id,
        limit,
        min_length,
        max_length,
        filtered_words,
    )

    if not dry_run:
        write_userdict(output_path, phrases)

    if stats["missing_table"]:
        print(f"{bvid}: 未找到弹幕表，跳过")
    else:
        action = "预览" if dry_run else "写入"
        print(
            f"{bvid}: {action} {len(phrases)} 条 -> {output_path} "
            f"(过滤 {stats['skipped']} 条，过滤词典 {len(filtered_words)} 条)"
        )
    return len(phrases), False


def main():
    parser = argparse.ArgumentParser(
        description="统计每个视频的高频完整弹幕，并写入对应的 pkuseg 视频词典。"
    )
    parser.add_argument("--bvid", help="只处理指定 bvid")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"弹幕出现次数阈值，默认 {DEFAULT_LIMIT}",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="词典输出目录")
    parser.add_argument("--min-length", type=int, default=2, help="最短短语长度，默认 2")
    parser.add_argument("--max-length", type=int, default=50, help="最长短语长度，默认 50；设为 0 不限制")
    parser.add_argument("--dry-run", action="store_true", help="只统计和打印，不写入文件")
    args = parser.parse_args()

    videos = get_all_video_records()
    if args.bvid:
        videos = [video for video in videos if video["bvid"] == args.bvid]

    if not videos:
        print("没有可处理的视频。")
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
                phrase_count, existed = process_video(
                    cur=cur,
                    video=video,
                    output_dir=args.output_dir,
                    limit=args.limit,
                    min_length=args.min_length,
                    max_length=args.max_length,
                    dry_run=args.dry_run,
                )
                if existed:
                    skipped_existing += 1
                    continue
                total += phrase_count
                processed_videos += 1
    finally:
        conn.close()

    print(
        f"\n完成：处理 {processed_videos} 个已完成视频，"
        f"跳过 {skipped_incomplete} 个未完成视频，"
        f"跳过 {skipped_existing} 个已有词典视频，输出候选短语 {total} 条。"
    )


if __name__ == "__main__":
    main()
