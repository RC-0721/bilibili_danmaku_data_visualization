"""Build and apply a rule-based phrase-alias feature model.

The model reads phrase_aliases.txt, extracts reusable fragments for each alias,
stores them in phrase_alias_features.txt, and can use those features to fill the
alias column in review_candidates/phrase_aliases_candidates.tsv.
"""

import _bootstrap  # noqa: F401

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from app.file_utils import make_backup, normalize_line
from app.paths import PHRASE_ALIASES_FILE, PHRASE_ALIAS_FEATURES_FILE, REVIEW_CANDIDATES_DIR
from app.text.aliases import iter_phrase_alias_rules

CANDIDATES_FILE = REVIEW_CANDIDATES_DIR / "phrase_aliases_candidates.tsv"
WORD_CHAR_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_]")


def is_separator(char):
    return WORD_CHAR_RE.fullmatch(char) is None


def strip_separators(value):
    return "".join(char for char in normalize_line(value) if not is_separator(char))


def split_on_separators(value):
    parts = []
    buffer = []
    for char in normalize_line(value):
        if is_separator(char):
            if buffer:
                parts.append("".join(buffer))
                buffer = []
            continue
        buffer.append(char)
    if buffer:
        parts.append("".join(buffer))
    return parts


def derive_repetition_features(text, min_feature_length):
    """Extract repeated prefix and remainder fragments from an unseparated line."""
    features = set()
    text = strip_separators(text)
    if len(text) < min_feature_length * 2:
        return features

    for size in range(min_feature_length, len(text) // 2 + 1):
        prefix = text[:size]
        offset = 0
        repeat_count = 0
        while text.startswith(prefix, offset):
            repeat_count += 1
            offset += size
        if repeat_count < 2:
            continue

        features.add(prefix)
        remainder = text[offset:]
        if len(remainder) >= min_feature_length:
            features.add(remainder)
            if remainder.startswith(prefix) and len(remainder) > len(prefix):
                features.add(remainder)
            features.update(derive_repetition_features(remainder, min_feature_length))
        elif remainder:
            features.add(prefix + remainder)
        break

    return features


def max_cover_length(text, features):
    """Return the maximum non-overlapping character coverage by feature strings."""
    text = strip_separators(text)
    if not text or not features:
        return 0

    feature_list = sorted({strip_separators(item) for item in features if strip_separators(item)}, key=len, reverse=True)
    dp = [0] * (len(text) + 1)
    for index in range(len(text)):
        if dp[index] > dp[index + 1]:
            dp[index + 1] = dp[index]
        for feature in feature_list:
            end = index + len(feature)
            if end <= len(text) and text.startswith(feature, index):
                value = dp[index] + len(feature)
                if value > dp[end]:
                    dp[end] = value
    return dp[len(text)]


def is_fully_covered(text, features):
    text = strip_separators(text)
    return bool(text) and max_cover_length(text, features) == len(text)


def extract_features_from_phrase(phrase, min_feature_length):
    """Extract sorted, de-duplicated feature fragments from one alias phrase."""
    initial_parts = split_on_separators(phrase)
    if not initial_parts:
        initial_parts = [strip_separators(phrase)]

    features = set()
    for part in initial_parts:
        part = strip_separators(part)
        if len(part) < min_feature_length:
            continue
        features.add(part)
        features.update(derive_repetition_features(part, min_feature_length))

    full_text = strip_separators(phrase)
    if len(initial_parts) == 1 and len(full_text) >= min_feature_length:
        features.add(full_text)
        features.update(derive_repetition_features(full_text, min_feature_length))

    pruned = []
    for feature in sorted(features, key=lambda value: (len(value), value)):
        other_features = [item for item in features if item != feature and len(item) < len(feature)]
        if other_features and is_fully_covered(feature, other_features):
            continue
        pruned.append(feature)
    return pruned


def load_existing_features(path):
    features = defaultdict(set)
    if not path.exists():
        return features

    current_alias = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = normalize_line(line)
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_alias = normalize_line(line[1:-1])
            continue
        if "\t" in line:
            alias, feature = line.split("\t", 1)
        elif current_alias:
            alias, feature = current_alias, line
        else:
            continue
        alias = normalize_line(alias)
        feature = strip_separators(feature)
        if alias and feature:
            features[alias].add(feature)
    return features


def build_features(alias_rows, min_feature_length):
    features = defaultdict(set)
    for phrase, alias in alias_rows:
        for feature in extract_features_from_phrase(phrase, min_feature_length):
            features[alias].add(feature)
    return features


def write_features(path, features, dry_run=False, backup=True):
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        make_backup(path)

    lines = [
        "# phrase alias feature dictionary",
        "# format: alias<TAB>feature",
        "# You may also add grouped entries as [alias] followed by one feature per line.",
        "",
    ]
    for alias in sorted(features):
        for feature in sorted(features[alias], key=lambda value: (len(value), value)):
            lines.append(f"{alias}\t{feature}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def match_alias(text, features_by_alias, threshold):
    normalized_text = strip_separators(text)
    if not normalized_text:
        return None

    best = None
    for alias, features in features_by_alias.items():
        coverage = max_cover_length(normalized_text, features)
        if coverage <= 0:
            continue
        ratio = coverage / len(normalized_text)
        if ratio < threshold:
            continue
        matched_features = [
            feature
            for feature in features
            if feature and feature in normalized_text
        ]
        candidate = {
            "alias": alias,
            "ratio": ratio,
            "coverage": coverage,
            "matched_features": matched_features,
        }
        if best is None:
            best = candidate
            continue
        best_key = (best["ratio"], best["coverage"], len(best["matched_features"]), len(best["alias"]))
        candidate_key = (
            candidate["ratio"],
            candidate["coverage"],
            len(candidate["matched_features"]),
            len(candidate["alias"]),
        )
        if candidate_key > best_key:
            best = candidate
    return best


def read_candidates(path):
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    return fieldnames, rows


def write_candidates(path, fieldnames, rows, dry_run=False, backup=True):
    if dry_run:
        return
    if backup:
        make_backup(path)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def annotate_candidates(path, features_by_alias, threshold, overwrite=False, dry_run=False, backup=True):
    fieldnames, rows = read_candidates(path)
    if "alias" not in fieldnames or "term" not in fieldnames:
        raise ValueError("candidate TSV must contain term and alias columns")

    updated = 0
    skipped_existing = 0
    examples = []
    for row in rows:
        if normalize_line(row.get("target")) and normalize_line(row.get("target")) != "phrase_aliases":
            continue
        if normalize_line(row.get("alias")) and not overwrite:
            skipped_existing += 1
            continue

        match = match_alias(row.get("term"), features_by_alias, threshold)
        if not match:
            continue
        row["alias"] = match["alias"]
        updated += 1
        if len(examples) < 10:
            examples.append((row.get("term", ""), match["alias"], match["ratio"]))

    write_candidates(path, fieldnames, rows, dry_run=dry_run, backup=backup)
    return {
        "updated": updated,
        "skipped_existing": skipped_existing,
        "total_rows": len(rows),
        "examples": examples,
    }


def self_test():
    features = extract_features_from_phrase("蓝蓝路⭐蓝蓝路⭐蓝蓝路路", min_feature_length=2)
    assert features == ["蓝蓝路", "蓝蓝路路"], features

    features = extract_features_from_phrase("蓝蓝路蓝蓝路蓝蓝路路", min_feature_length=2)
    assert features == ["蓝蓝路", "蓝蓝路路"], features

    match = match_alias(
        "蓝蓝路蓝蓝路蓝蓝路路蓝",
        {"蓝蓝路": set(features)},
        threshold=0.8,
    )
    assert match and match["alias"] == "蓝蓝路" and match["ratio"] > 0.8, match
    print("self-test passed")


def main():
    parser = argparse.ArgumentParser(description="Build phrase-alias features and annotate alias review candidates.")
    parser.add_argument("--phrase-aliases-file", type=Path, default=PHRASE_ALIASES_FILE, help="phrase_aliases.txt path")
    parser.add_argument("--features-file", type=Path, default=PHRASE_ALIAS_FEATURES_FILE, help="alias feature txt path")
    parser.add_argument("--candidates-file", type=Path, default=CANDIDATES_FILE, help="phrase_aliases_candidates.tsv path")
    parser.add_argument("--threshold", type=float, default=0.8, help="minimum feature coverage ratio")
    parser.add_argument("--min-feature-length", type=int, default=2, help="minimum feature length")
    parser.add_argument("--overwrite-alias", action="store_true", help="overwrite existing alias values in candidates")
    parser.add_argument("--no-merge-existing", action="store_true", help="do not merge manually maintained feature file entries")
    parser.add_argument("--features-only", action="store_true", help="only write phrase_alias_features.txt")
    parser.add_argument("--annotate-only", action="store_true", help="only read existing features and annotate candidates")
    parser.add_argument("--dry-run", action="store_true", help="preview changes without writing files")
    parser.add_argument("--no-backup", action="store_true", help="do not create .bak timestamp backups before writing")
    parser.add_argument("--self-test", action="store_true", help="run built-in examples and exit")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    backup = not args.no_backup
    features = defaultdict(set)

    if not args.annotate_only:
        alias_rows = list(iter_phrase_alias_rules(args.phrase_aliases_file))
        features = build_features(alias_rows, args.min_feature_length)
        if not args.no_merge_existing:
            for alias, values in load_existing_features(args.features_file).items():
                features[alias].update(values)
        write_features(args.features_file, features, dry_run=args.dry_run, backup=backup)
    else:
        features = load_existing_features(args.features_file)

    feature_count = sum(len(values) for values in features.values())
    action = "preview" if args.dry_run else "write"
    print(f"{action} feature aliases: {len(features)}")
    print(f"{action} feature rows: {feature_count}")
    print(f"features file: {args.features_file}")

    if args.features_only:
        return

    result = annotate_candidates(
        args.candidates_file,
        features,
        threshold=args.threshold,
        overwrite=args.overwrite_alias,
        dry_run=args.dry_run,
        backup=backup,
    )
    print(f"{action} candidate aliases: {result['updated']}")
    print(f"skipped existing aliases: {result['skipped_existing']}")
    print(f"candidate rows: {result['total_rows']}")
    for term, alias, ratio in result["examples"]:
        print(f"  {alias}\t{ratio:.3f}\t{term}")


if __name__ == "__main__":
    main()
