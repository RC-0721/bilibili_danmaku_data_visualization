"""Build TSV files for semi-automatic custom word maintenance."""

import argparse
import math
from collections import Counter
from pathlib import Path

import pymysql

from app.db import danmaku_table_name, danmaku_words_table_name, get_all_video_records, get_connection, table_exists
from app.file_utils import read_word_file
from app.paths import ACCEPTED_CUSTOM_WORDS_FILE, CUSTOM_WORDS_DIR, FILTERED_WORDS_FILE, REVIEW_CANDIDATES_DIR, STOPWORDS_FILE
from app.review.word_candidate_common import (
    ACCEPT_HINT,
    TOKEN_RE,
    append_auto_custom_word,
    candidate_row,
    is_valid_term,
    normalize_text,
    read_video_custom_words,
    write_tsv,
)
from app.review.word_candidate_queries import (
    fetch_content_by_row_id,
    fetch_frequent_bigrams,
    fetch_frequent_full_danmaku,
    fetch_word_counts,
    is_video_completed,
)
from app.text.aliases import load_phrase_alias_sets


def build_custom_and_alias_candidates(cur, video, args, blocked_words, accepted_custom_words, existing_alias_phrases):
    video_id = video["id"]
    bvid = video["bvid"]
    danmaku_table = danmaku_table_name(video_id)
    words_table = danmaku_words_table_name(video_id)
    if not table_exists(cur, danmaku_table):
        return [], [], 0

    existing_custom_words = read_video_custom_words(bvid)
    custom_words_path = args.custom_words_dir / f"{bvid}.txt"
    custom_rows = []
    alias_rows = []
    seen_custom = set(existing_custom_words)
    auto_written_count = 0

    for row in fetch_frequent_full_danmaku(cur, danmaku_table, args.min_full_count, args.max_candidates):
        content = row["content"]
        count = int(row["cnt"] or 0)
        phrase = normalize_text(content)
        key = phrase.lower()
        valid_custom_term = is_valid_term(phrase, args.min_term_length, args.max_term_length, blocked_words)
        if valid_custom_term and key not in seen_custom and key in accepted_custom_words:
            if append_auto_custom_word(custom_words_path, phrase, dry_run=args.dry_run_auto_accept):
                auto_written_count += 1
            seen_custom.add(key)
        elif valid_custom_term and key not in seen_custom:
            score = count * math.log(max(len(phrase), 2))
            custom_rows.append(candidate_row("custom_words", bvid, phrase, "full_danmaku", score, count, example=content, reason="high-frequency full danmaku"))
            seen_custom.add(key)

        if len(phrase) >= args.alias_min_length and key not in existing_alias_phrases and key not in blocked_words:
            alias_rows.append(candidate_row(
                "phrase_aliases",
                bvid,
                phrase,
                "long_full_danmaku",
                count * len(phrase),
                count,
                example=content,
                reason="long frequent phrase; fill alias before accepting",
            ))

    if table_exists(cur, words_table):
        for row in fetch_frequent_bigrams(cur, words_table, args.min_bigram_count, args.max_candidates):
            phrase = normalize_text(row["phrase"])
            key = phrase.lower()
            count = int(row["cnt"] or 0)
            if key in seen_custom or not is_valid_term(phrase, args.min_term_length, args.max_term_length, blocked_words):
                continue
            if key in accepted_custom_words:
                if append_auto_custom_word(custom_words_path, phrase, dry_run=args.dry_run_auto_accept):
                    auto_written_count += 1
                seen_custom.add(key)
                continue
            example = fetch_content_by_row_id(cur, danmaku_table, row["sample_row_id"])
            custom_rows.append(candidate_row("custom_words", bvid, phrase, "adjacent_bigram", count * 1.5, count, example=example, reason="frequent adjacent tokens in current segmentation"))
            seen_custom.add(key)

    custom_rows.sort(key=lambda item: float(item["score"]), reverse=True)
    alias_rows.sort(key=lambda item: float(item["score"]), reverse=True)
    return custom_rows[:args.max_candidates], alias_rows[:args.max_candidates], auto_written_count


def build_stopword_candidates(cur, videos, args, blocked_words):
    total_counts = Counter()
    video_counts = Counter()

    for video in videos:
        words_table = danmaku_words_table_name(video["id"])
        if not table_exists(cur, words_table):
            continue
        for row in fetch_word_counts(cur, words_table, args.min_stopword_count, args.max_candidates * 5):
            word = normalize_text(row["word"])
            if word:
                total_counts[word] += int(row["cnt"] or 0)
                video_counts[word] += 1

    rows = []
    total_videos = max(len(videos), 1)
    for word, count in total_counts.items():
        key = word.lower()
        if key in blocked_words or len(word) > args.max_stopword_length or not TOKEN_RE.fullmatch(word):
            continue
        appears_in_many_videos = video_counts[word] >= args.min_stopword_video_count
        very_common = count >= args.global_stopword_count
        short_common = len(word) <= 2 and count >= args.min_stopword_count
        if not (appears_in_many_videos or very_common or short_common):
            continue
        video_ratio = video_counts[word] / total_videos
        rows.append(candidate_row("stopwords", "", word, "global_word", count * (1 + video_ratio), count, video_count=video_counts[word], reason="high frequency and low distinction across videos"))

    rows.sort(key=lambda item: float(item["score"]), reverse=True)
    return rows[:args.max_candidates]


def parse_args():
    parser = argparse.ArgumentParser(description="生成 custom_words / stopwords / phrase_aliases 审核候选")
    parser.add_argument("--bvid", help="只为指定视频生成候选")
    parser.add_argument("--output-dir", type=Path, default=REVIEW_CANDIDATES_DIR, help="候选 TSV 输出目录")
    parser.add_argument("--custom-words-dir", type=Path, default=CUSTOM_WORDS_DIR, help="custom_words 输出目录")
    parser.add_argument("--accepted-custom-words-file", type=Path, default=ACCEPTED_CUSTOM_WORDS_FILE, help="全局已审核 custom_words 短语文件")
    parser.add_argument("--include-incomplete", action="store_true", help="包含尚未抓取到截止日期的视频")
    parser.add_argument("--dry-run-auto-accept", action="store_true", help="预览自动命中全局短语的写入数量，不修改 custom_words")
    parser.add_argument("--max-candidates", type=int, default=200, help="每类候选最多输出条数")
    parser.add_argument("--min-full-count", type=int, default=500, help="完整弹幕候选最低出现次数")
    parser.add_argument("--min-bigram-count", type=int, default=2000, help="相邻分词组合候选最低出现次数")
    parser.add_argument("--min-stopword-count", type=int, default=1000, help="单视频词频达到该值才进入停用词候选统计")
    parser.add_argument("--global-stopword-count", type=int, default=50000, help="全局词频达到该值可成为停用词候选")
    parser.add_argument("--min-stopword-video-count", type=int, default=20, help="出现在至少多少个视频中可成为停用词候选")
    parser.add_argument("--min-term-length", type=int, default=2, help="custom_words 候选最短长度")
    parser.add_argument("--max-term-length", type=int, default=6, help="custom_words 候选最长长度；0 表示不限制")
    parser.add_argument("--alias-min-length", type=int, default=7, help="phrase_aliases 候选最短长度")
    parser.add_argument("--max-stopword-length", type=int, default=4, help="stopwords 候选最长长度")
    return parser.parse_args()


def select_videos(cur, videos, args):
    selected_videos = []
    skipped_incomplete = 0
    for video in videos:
        if not args.include_incomplete and not is_video_completed(cur, video["bvid"]):
            skipped_incomplete += 1
            continue
        selected_videos.append(video)
    return selected_videos, skipped_incomplete


def main():
    args = parse_args()
    videos = get_all_video_records()
    if args.bvid:
        videos = [video for video in videos if video["bvid"] == args.bvid]
    if not videos:
        print("没有可处理的视频。")
        return

    stopwords = read_word_file(STOPWORDS_FILE)
    filtered_words = read_word_file(FILTERED_WORDS_FILE)
    accepted_custom_words = read_word_file(args.accepted_custom_words_file)
    alias_phrases, alias_words = load_phrase_alias_sets()
    blocked_words = set(stopwords) | set(filtered_words) | set(alias_words)

    custom_rows = []
    alias_rows = []
    auto_written_total = 0
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            selected_videos, skipped_incomplete = select_videos(cur, videos, args)
            for video in selected_videos:
                video_custom, video_alias, auto_written_count = build_custom_and_alias_candidates(cur, video, args, blocked_words, accepted_custom_words, alias_phrases)
                custom_rows.extend(video_custom)
                alias_rows.extend(video_alias)
                auto_written_total += auto_written_count
            stopword_rows = build_stopword_candidates(cur, selected_videos, args, blocked_words)
    finally:
        conn.close()

    write_tsv(args.output_dir / "custom_words_candidates.tsv", custom_rows)
    write_tsv(args.output_dir / "stopwords_candidates.tsv", stopword_rows)
    write_tsv(args.output_dir / "phrase_aliases_candidates.tsv", alias_rows)
    print(f"输出 custom_words 候选: {len(custom_rows)}")
    print(f"输出 stopwords 候选: {len(stopword_rows)}")
    print(f"输出 phrase_aliases 候选: {len(alias_rows)}")
    print(f"自动命中全局已审核短语并写入 custom_words: {auto_written_total}")
    print(f"跳过未完成视频: {skipped_incomplete}")
    print(f"候选目录: {args.output_dir}")
    print(f"审核时将 status 填为 {ACCEPT_HINT} 后，再运行 apply_word_review_candidates.py")
