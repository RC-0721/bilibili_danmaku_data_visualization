"""CLI wrapper for semi-automatic word-review candidate generation."""

import _bootstrap  # noqa: F401

from app.review.word_candidate_builder import main


if __name__ == "__main__":
    main()
