"""Shared helpers for word-review candidate generation."""

import csv
import re

from app.file_utils import read_word_file
from app.paths import CUSTOM_WORDS_DIR

TOKEN_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9_]+$")
REPEATED_RE = re.compile(r"^(.)\1{2,}$")

ACCEPT_HINT = "accept"
REVIEW_COLUMNS = [
    "status",
    "target",
    "bvid",
    "term",
    "alias",
    "candidate_type",
    "score",
    "count",
    "video_count",
    "example",
    "reason",
]


def read_video_custom_words(bvid):
    return read_word_file(CUSTOM_WORDS_DIR / f"{bvid}.txt")


def normalize_text(value):
    return re.sub(r"\s+", "", (value or "").strip())


def is_valid_term(term, min_length, max_length, blocked_words):
    term = normalize_text(term)
    if not term or len(term) < min_length:
        return False
    if max_length and len(term) > max_length:
        return False
    if term.lower() in blocked_words:
        return False
    if not TOKEN_RE.fullmatch(term):
        return False
    return not REPEATED_RE.fullmatch(term)


def candidate_row(target, bvid, term, candidate_type, score, count, video_count=1, example="", reason="", alias=""):
    return {
        "status": "",
        "target": target,
        "bvid": bvid or "",
        "term": term,
        "alias": alias,
        "candidate_type": candidate_type,
        "score": f"{score:.6f}",
        "count": str(int(count or 0)),
        "video_count": str(int(video_count or 0)),
        "example": example or "",
        "reason": reason,
    }


def append_auto_custom_word(path, phrase, dry_run=False):
    existing = read_word_file(path)
    key = phrase.lower()
    if key in existing:
        return False
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    body = "\n".join(lines)
    if body and not body.endswith("\n"):
        body += "\n"
    body += phrase
    if body and not body.endswith("\n"):
        body += "\n"
    path.write_text(body, encoding="utf-8")
    return True


def write_tsv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
