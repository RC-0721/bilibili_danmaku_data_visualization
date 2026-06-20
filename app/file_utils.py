"""Small file helpers shared by maintenance scripts."""

import shutil
from datetime import datetime
from pathlib import Path


def normalize_line(value):
    return (value or "").strip().lstrip("\ufeff")


def read_existing_lines(path):
    path = Path(path)
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def read_word_file(path, lowercase=True):
    words = set()
    for line in read_existing_lines(path):
        line = normalize_line(line)
        if not line or line.startswith("#"):
            continue
        words.add(line.lower() if lowercase else line)
    return words


def make_backup(path):
    path = Path(path)
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak_{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def append_unique_lines(path, values, dry_run=False, backup=True):
    path = Path(path)
    values = [normalize_line(value) for value in values if normalize_line(value)]
    if not values:
        return 0

    existing_lines = read_existing_lines(path)
    existing_keys = {
        line.strip().lower()
        for line in existing_lines
        if line.strip() and not line.strip().startswith("#")
    }
    new_lines = []
    for value in values:
        key = value.lower()
        if key in existing_keys:
            continue
        existing_keys.add(key)
        new_lines.append(value)

    if dry_run or not new_lines:
        return len(new_lines)

    path.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        make_backup(path)

    body = "\n".join(existing_lines)
    if body and not body.endswith("\n"):
        body += "\n"
    body += "\n".join(new_lines)
    if body and not body.endswith("\n"):
        body += "\n"
    path.write_text(body, encoding="utf-8")
    return len(new_lines)
