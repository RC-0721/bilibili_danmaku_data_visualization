"""Apply accepted review candidates to word-maintenance files.

Rows are accepted only when the TSV column status is set to one of:
accept, accepted, yes, y, 1, true, 通过, 接受.
"""

import _bootstrap  # noqa: F401

import argparse
import csv
from pathlib import Path

from app.file_utils import append_unique_lines, normalize_line
from app.paths import (
    ACCEPTED_CUSTOM_WORDS_FILE,
    CUSTOM_WORDS_DIR,
    FILTERED_WORDS_FILE,
    PHRASE_ALIASES_FILE,
    REVIEW_CANDIDATES_DIR,
    STOPWORDS_FILE,
)

ACCEPT_VALUES = {"accept", "accepted", "yes", "y", "1", "true", "通过", "接受"}


def read_review_rows(input_dir):
    rows = []
    for path in sorted(input_dir.glob("*_candidates.tsv")):
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter="\t")
            for row in reader:
                row["_source_file"] = path.name
                rows.append(row)
    return rows


def auto_accept_phrase_alias_rows(input_dir, dry_run=False):
    """Fill status=accept when a phrase alias row has alias but empty status."""
    updated = 0
    for path in sorted(input_dir.glob("phrase_aliases_candidates.tsv")):
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter="\t")
            rows = list(reader)
            fieldnames = reader.fieldnames or []

        if not rows or "status" not in fieldnames or "alias" not in fieldnames:
            continue

        changed = False
        for row in rows:
            if normalize_line(row.get("alias")) and not normalize_line(row.get("status")):
                row["status"] = "accept"
                updated += 1
                changed = True

        if changed and not dry_run:
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)

    return updated


def is_accepted(row):
    return normalize_line(row.get("status")).lower() in ACCEPT_VALUES


def phrase_alias_line(row):
    phrase = normalize_line(row.get("term"))
    alias = normalize_line(row.get("alias"))
    if not phrase or not alias:
        return ""
    return f"{phrase} => {alias}"


def group_accepted_rows(rows):
    grouped = {
        "custom_words": {},
        "stopwords": [],
        "phrase_aliases": [],
        "skipped_alias_without_value": 0,
        "unknown_target": 0,
    }
    for row in rows:
        if not is_accepted(row):
            continue
        target = normalize_line(row.get("target"))
        term = normalize_line(row.get("term"))
        bvid = normalize_line(row.get("bvid"))
        if target == "custom_words":
            if not bvid or not term:
                continue
            grouped["custom_words"].setdefault(bvid, []).append(term)
        elif target == "stopwords":
            if term:
                grouped["stopwords"].append(term)
        elif target == "phrase_aliases":
            line = phrase_alias_line(row)
            if line:
                grouped["phrase_aliases"].append(line)
            else:
                grouped["skipped_alias_without_value"] += 1
        else:
            grouped["unknown_target"] += 1
    return grouped


def main():
    parser = argparse.ArgumentParser(description="应用已审核通过的词典维护候选")
    parser.add_argument("--input-dir", type=Path, default=REVIEW_CANDIDATES_DIR, help="审核 TSV 所在目录")
    parser.add_argument("--custom-words-dir", type=Path, default=CUSTOM_WORDS_DIR, help="custom_words 输出目录")
    parser.add_argument("--stopwords-file", type=Path, default=STOPWORDS_FILE, help="stopwords.txt 路径")
    parser.add_argument("--filtered-words-file", type=Path, default=FILTERED_WORDS_FILE, help="filtered_words.txt 路径")
    parser.add_argument("--phrase-aliases-file", type=Path, default=PHRASE_ALIASES_FILE, help="phrase_aliases.txt 路径")
    parser.add_argument(
        "--accepted-custom-words-file",
        type=Path,
        default=ACCEPTED_CUSTOM_WORDS_FILE,
        help="全局已审核 custom_words 短语文件",
    )
    parser.add_argument(
        "--stopword-target",
        choices=("stopwords", "filtered", "both"),
        default="both",
        help="接受的 stopwords 候选写入哪个文件；both 会同时影响词云和后续分词",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印将写入的数量，不修改文件")
    parser.add_argument("--no-backup", action="store_true", help="写入前不备份目标文件")
    args = parser.parse_args()

    auto_accepted_aliases = auto_accept_phrase_alias_rows(args.input_dir, dry_run=args.dry_run)
    rows = read_review_rows(args.input_dir)
    grouped = group_accepted_rows(rows)
    backup = not args.no_backup

    custom_count = 0
    accepted_global_terms = []
    for bvid, terms in sorted(grouped["custom_words"].items()):
        path = args.custom_words_dir / f"{bvid}.txt"
        custom_count += append_unique_lines(path, terms, dry_run=args.dry_run, backup=backup)
        accepted_global_terms.extend(terms)

    accepted_global_count = append_unique_lines(
        args.accepted_custom_words_file,
        accepted_global_terms,
        dry_run=args.dry_run,
        backup=backup,
    )

    stopwords_count = 0
    filtered_count = 0
    if args.stopword_target in ("stopwords", "both"):
        stopwords_count = append_unique_lines(
            args.stopwords_file,
            grouped["stopwords"],
            dry_run=args.dry_run,
            backup=backup,
        )
    if args.stopword_target in ("filtered", "both"):
        filtered_count = append_unique_lines(
            args.filtered_words_file,
            grouped["stopwords"],
            dry_run=args.dry_run,
            backup=backup,
        )

    alias_count = append_unique_lines(
        args.phrase_aliases_file,
        grouped["phrase_aliases"],
        dry_run=args.dry_run,
        backup=backup,
    )

    action = "预览" if args.dry_run else "写入"
    print(f"{action} 自动补全 phrase_aliases accept 状态: {auto_accepted_aliases}")
    print(f"{action} custom_words 新词条: {custom_count}")
    print(f"{action} accepted_custom_words.txt 新词条: {accepted_global_count}")
    print(f"{action} stopwords.txt 新词条: {stopwords_count}")
    print(f"{action} filtered_words.txt 新词条: {filtered_count}")
    print(f"{action} phrase_aliases.txt 新规则: {alias_count}")
    if grouped["skipped_alias_without_value"]:
        print(f"跳过 alias 为空的 phrase_aliases 候选: {grouped['skipped_alias_without_value']}")
    if grouped["unknown_target"]:
        print(f"跳过未知 target 行: {grouped['unknown_target']}")


if __name__ == "__main__":
    main()
