"""Phrase alias parsing helpers shared by text and review scripts."""

from app.file_utils import normalize_line
from app.paths import PHRASE_ALIASES_FILE


def parse_phrase_alias_line(line):
    line = normalize_line(line)
    if not line or line.startswith("#"):
        return None
    if "=>" in line:
        phrase, alias = line.split("=>", 1)
    elif "\t" in line:
        phrase, alias = line.split("\t", 1)
    else:
        return None
    phrase = normalize_line(phrase)
    alias = normalize_line(alias)
    if not phrase or not alias:
        return None
    return phrase, alias


def iter_phrase_alias_rules(path=PHRASE_ALIASES_FILE):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_phrase_alias_line(line)
        if parsed:
            yield parsed


def load_phrase_alias_maps(path=PHRASE_ALIASES_FILE):
    phrase_to_alias = {}
    alias_to_phrases = {}
    for phrase, alias in iter_phrase_alias_rules(path):
        phrase_to_alias[phrase.lower()] = alias
        alias_to_phrases.setdefault(alias, []).append(phrase)
    return phrase_to_alias, alias_to_phrases


def load_phrase_alias_sets(path=PHRASE_ALIASES_FILE):
    phrases = set()
    aliases = set()
    for phrase, alias in iter_phrase_alias_rules(path):
        phrases.add(phrase.lower())
        aliases.add(alias.lower())
    return phrases, aliases
