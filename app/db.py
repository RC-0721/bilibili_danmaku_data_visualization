"""Database helper aggregate.

New code may import from app.db_core or app.danmaku_tables directly. This
module keeps the stable app.db interface for existing scripts.
"""

from app.danmaku_tables import (
    danmaku_table_name,
    danmaku_words_table_name,
    ensure_danmaku_table_schema,
    ensure_danmaku_words_table,
    fetch_existing_danmaku_keys,
    iter_source_danmaku,
    iter_unsegmented_danmaku,
    make_danmaku_key,
    save_danmaku_list,
    save_danmaku_words,
    table_has_rows,
)
from app.db_core import (
    create_database_if_not_exists,
    get_all_video_records,
    get_connection,
    get_date_step,
    get_progress,
    get_video_id_by_bvid,
    get_videos,
    init_db,
    init_progress_table,
    save_videos,
    table_exists,
    update_date_step,
    update_progress,
)

__all__ = [
    "create_database_if_not_exists",
    "danmaku_table_name",
    "danmaku_words_table_name",
    "ensure_danmaku_table_schema",
    "ensure_danmaku_words_table",
    "fetch_existing_danmaku_keys",
    "get_all_video_records",
    "get_connection",
    "get_date_step",
    "get_progress",
    "get_video_id_by_bvid",
    "get_videos",
    "init_db",
    "init_progress_table",
    "iter_source_danmaku",
    "iter_unsegmented_danmaku",
    "make_danmaku_key",
    "save_danmaku_list",
    "save_danmaku_words",
    "save_videos",
    "table_exists",
    "table_has_rows",
    "update_date_step",
    "update_progress",
]
