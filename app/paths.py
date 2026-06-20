"""Central project paths used by scripts and application modules."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FRONTEND_DIR = PROJECT_ROOT / "frontend"
REVIEW_CANDIDATES_DIR = PROJECT_ROOT / "review_candidates"
CUSTOM_WORDS_DIR = PROJECT_ROOT / "custom_words"
DANMAKU_SAMPLES_DIR = PROJECT_ROOT / "danmaku_samples"
TEXT_RESOURCES_DIR = PROJECT_ROOT / "resources" / "text"

STOPWORDS_FILE = TEXT_RESOURCES_DIR / "stopwords.txt"
FILTERED_WORDS_FILE = TEXT_RESOURCES_DIR / "filtered_words.txt"
PHRASE_ALIASES_FILE = TEXT_RESOURCES_DIR / "phrase_aliases.txt"
PHRASE_ALIAS_FEATURES_FILE = TEXT_RESOURCES_DIR / "phrase_alias_features.txt"
ACCEPTED_CUSTOM_WORDS_FILE = TEXT_RESOURCES_DIR / "accepted_custom_words.txt"

SENTIMENT_ONTOLOGY_FILE = PROJECT_ROOT / "words" / "words" / "words.xlsx"
