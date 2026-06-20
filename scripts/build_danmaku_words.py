"""为已入库弹幕构建分词表。
Build per-video word tables from stored danmaku rows.
"""

import _bootstrap  # noqa: F401

import argparse
import gc
import time
from collections import OrderedDict

from app.config import END_DATE
from app.db import (
    get_connection,
    get_all_video_records,
    ensure_danmaku_words_table,
    iter_source_danmaku,
    iter_unsegmented_danmaku,
    save_danmaku_words,
    table_exists,
    table_has_rows,
)
from app.text.segmentation import clear_segmenter_cache, segment_text


DEFAULT_SEGMENT_CACHE_SIZE = 100000


def row_value(row, key, index):
    """兼容 DictCursor 和普通 Cursor 的取值方式。
    Read a value from either DictCursor or tuple cursor rows.
    """
    if isinstance(row, dict):
        return row[key]
    return row[index]


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


def segment_text_with_cache(content, bvid, cache, cache_limit, stats):
    """对相同弹幕内容复用分词结果，减少重复调用 pkuseg。"""
    text = str(content)
    if cache is None:
        stats["misses"] += 1
        return segment_text(text, bvid=bvid)

    try:
        words = cache[text]
        cache.move_to_end(text)
        stats["hits"] += 1
        return words
    except KeyError:
        words = segment_text(text, bvid=bvid)
        stats["misses"] += 1
        cache[text] = words
        if len(cache) > cache_limit:
            cache.popitem(last=False)
        return words


def select_danmaku_iterator(cur, video_id, batch_size, force_resumable):
    """Choose the cheapest safe source iterator for this video."""
    words_table = ensure_danmaku_words_table(cur, video_id)
    if force_resumable or table_has_rows(cur, words_table):
        return iter_unsegmented_danmaku(cur, video_id, batch_size=batch_size), "resumable-left-join"
    return iter_source_danmaku(cur, video_id, batch_size=batch_size), "fresh-primary-key"


def process_video(conn, cur, video, args):
    """处理单个视频的未分词弹幕。
    Process unsegmented danmaku rows for one video.
    """
    video_id = video["id"]
    bvid = video["bvid"]
    buffer = []
    processed_danmaku = 0
    inserted_words = 0
    flushed_batches = 0
    committed_batches = 0
    segment_cache = OrderedDict() if args.cache_size > 0 else None
    cache_stats = {"hits": 0, "misses": 0}
    row_iter, iter_mode = select_danmaku_iterator(
        cur,
        video_id,
        batch_size=args.batch_size,
        force_resumable=args.force_resumable_scan,
    )

    for row in row_iter:
        danmaku_row_id = row_value(row, "id", 0)
        dm_id = row_value(row, "dm_id", 1)
        content = row_value(row, "content", 2)
        words = segment_text_with_cache(content, bvid, segment_cache, args.cache_size, cache_stats)
        processed_danmaku += 1

        if words:
            buffer.append({
                "danmaku_row_id": danmaku_row_id,
                "dm_id": dm_id,
                "words": words,
            })

        if len(buffer) >= args.batch_size:
            inserted_words += save_danmaku_words(cur, video_id, buffer, chunk_size=args.insert_chunk_size)
            buffer.clear()
            flushed_batches += 1
            if args.commit_every_batches and flushed_batches % args.commit_every_batches == 0:
                conn.commit()
                committed_batches += 1
                if args.io_sleep > 0:
                    time.sleep(args.io_sleep)
            if args.max_danmaku_per_video and processed_danmaku >= args.max_danmaku_per_video:
                print(f"{bvid}: 达到单视频处理上限 {args.max_danmaku_per_video}，本轮停止")
                break
        elif args.max_danmaku_per_video and processed_danmaku >= args.max_danmaku_per_video:
            print(f"{bvid}: 达到单视频处理上限 {args.max_danmaku_per_video}，本轮停止")
            break

    if buffer:
        inserted_words += save_danmaku_words(cur, video_id, buffer, chunk_size=args.insert_chunk_size)
        flushed_batches += 1

    conn.commit()
    committed_batches += 1

    cache_entries = len(segment_cache) if segment_cache is not None else 0
    print(
        f"{bvid}: 处理弹幕 {processed_danmaku} 条，写入词条 {inserted_words} 条，"
        f"缓存命中 {cache_stats['hits']} 条，缓存未命中 {cache_stats['misses']} 条，"
        f"缓存保留 {cache_entries} 条，读取模式 {iter_mode}，"
        f"写入批次 {flushed_batches}，提交 {committed_batches} 次"
    )
    return processed_danmaku, inserted_words


def release_video_memory(bvid):
    """Release memory held by one video's tokenizer and temporary objects."""
    clear_segmenter_cache(bvid)
    gc.collect()


def parse_args():
    parser = argparse.ArgumentParser(description="对已入库弹幕进行 pkuseg 分词并写入 danmaku_words_{video_id}")
    parser.add_argument("--bvid", help="只处理指定 bvid")
    parser.add_argument("--batch-size", type=int, default=300, help="批量读取和写入大小")
    parser.add_argument("--insert-chunk-size", type=int, default=500, help="单次 executemany 写入的词条数量")
    parser.add_argument(
        "--cache-size",
        type=int,
        default=DEFAULT_SEGMENT_CACHE_SIZE,
        help="每个视频内缓存的不同弹幕文本数量；设为 0 可关闭缓存",
    )
    parser.add_argument(
        "--commit-every-batches",
        type=int,
        default=20,
        help="每写入多少个弹幕批次提交一次事务；设为 0 表示每个视频结束后提交",
    )
    parser.add_argument(
        "--io-sleep",
        type=float,
        default=0.2,
        help="每次分段提交后暂停秒数，用于降低磁盘持续占用",
    )
    parser.add_argument(
        "--max-danmaku-per-video",
        type=int,
        default=0,
        help="每个视频本轮最多处理多少条弹幕；0 表示不限",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=0,
        help="本轮最多处理多少个视频；0 表示不限",
    )
    parser.add_argument(
        "--force-resumable-scan",
        action="store_true",
        help="强制使用 LEFT JOIN 断点扫描；默认仅在分词表已有数据时使用",
    )
    parser.add_argument("--loop", action="store_true", help="一轮结束后自动继续下一轮")
    parser.add_argument("--loop-sleep", type=float, default=0, help="每轮结束后的暂停秒数")
    args = parser.parse_args()
    args.batch_size = max(args.batch_size, 1)
    args.insert_chunk_size = max(args.insert_chunk_size, 1)
    args.cache_size = max(args.cache_size, 0)
    args.commit_every_batches = max(args.commit_every_batches, 0)
    args.io_sleep = max(args.io_sleep, 0)
    args.max_danmaku_per_video = max(args.max_danmaku_per_video, 0)
    args.max_videos = max(args.max_videos, 0)
    args.loop_sleep = max(args.loop_sleep, 0)
    return args


def run_once(args, round_index=1):
    """Run one complete pass over the selected videos."""
    videos = get_all_video_records()
    if args.bvid:
        videos = [video for video in videos if video["bvid"] == args.bvid]

    if not videos:
        print("没有可处理的视频。")
        return

    total_danmaku = 0
    total_words = 0
    processed_videos = 0
    skipped_incomplete = 0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for video in videos:
                if not is_video_completed(cur, video["bvid"]):
                    skipped_incomplete += 1
                    print(f"{video['bvid']}: 尚未抓取到截止日期 {END_DATE}，跳过")
                    continue
                if args.max_videos and processed_videos >= args.max_videos:
                    print(f"达到本轮视频处理上限 {args.max_videos}，停止")
                    break
                processed_danmaku = 0
                inserted_words = 0
                try:
                    processed_danmaku, inserted_words = process_video(
                        conn,
                        cur,
                        video,
                        args,
                    )
                    total_danmaku += processed_danmaku
                    total_words += inserted_words
                    processed_videos += 1
                finally:
                    release_video_memory(video["bvid"])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        f"\n完成：处理 {processed_videos} 个已完成视频，"
        f"跳过 {skipped_incomplete} 个未完成视频，"
        f"处理弹幕 {total_danmaku} 条，写入词条 {total_words} 条"
    )
    return {
        "round_index": round_index,
        "processed_videos": processed_videos,
        "skipped_incomplete": skipped_incomplete,
        "total_danmaku": total_danmaku,
        "total_words": total_words,
    }


def main():
    """命令行入口：批量或按 bvid 构建分词表。
    CLI entry: build word tables in bulk or for one bvid.
    """
    args = parse_args()
    round_index = 1
    while True:
        if args.loop:
            print(f"\n========== 分词构建第 {round_index} 轮 ==========")
        stats = run_once(args, round_index=round_index)
        if not args.loop:
            break
        if stats["total_danmaku"] <= 0:
            print("本轮没有处理到新的弹幕，自动循环结束。")
            break
        round_index += 1
        if args.loop_sleep > 0:
            print(f"等待 {args.loop_sleep} 秒后继续下一轮...")
            time.sleep(args.loop_sleep)


if __name__ == "__main__":
    main()
