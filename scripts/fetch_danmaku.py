"""CLI wrapper for the Bilibili historical danmaku crawler."""

import _bootstrap  # noqa: F401

from app.crawl.danmaku_runner import main


if __name__ == "__main__":
    main()
