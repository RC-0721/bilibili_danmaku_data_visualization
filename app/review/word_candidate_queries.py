"""Database queries used by word-review candidate generation."""

from app.config import END_DATE
from app.db import table_exists


def is_video_completed(cur, bvid):
    if not table_exists(cur, "danmaku_progress"):
        return False
    cur.execute("""
        SELECT last_date
        FROM danmaku_progress
        WHERE bvid = %s
          AND last_date >= %s
    """, (bvid, END_DATE))
    return cur.fetchone() is not None


def fetch_frequent_full_danmaku(cur, table_name, min_count, limit):
    cur.execute(f"""
        SELECT content, COUNT(*) AS cnt
        FROM `{table_name}`
        WHERE content IS NOT NULL
          AND TRIM(content) <> ''
        GROUP BY content
        HAVING COUNT(*) >= %s
        ORDER BY cnt DESC, content ASC
        LIMIT %s
    """, (min_count, limit))
    return cur.fetchall()


def fetch_frequent_bigrams(cur, words_table, min_count, limit):
    cur.execute(f"""
        SELECT
            CONCAT(w1.word, w2.word) AS phrase,
            COUNT(*) AS cnt,
            MIN(w1.danmaku_row_id) AS sample_row_id
        FROM `{words_table}` AS w1
        INNER JOIN `{words_table}` AS w2
          ON w2.danmaku_row_id = w1.danmaku_row_id
         AND w2.word_index = w1.word_index + 1
        WHERE w1.word IS NOT NULL
          AND w1.word <> ''
          AND w2.word IS NOT NULL
          AND w2.word <> ''
        GROUP BY phrase
        HAVING COUNT(*) >= %s
        ORDER BY cnt DESC, phrase ASC
        LIMIT %s
    """, (min_count, limit))
    return cur.fetchall()


def fetch_content_by_row_id(cur, table_name, row_id):
    if not row_id:
        return ""
    cur.execute(f"SELECT content FROM `{table_name}` WHERE id = %s", (row_id,))
    row = cur.fetchone()
    if not row:
        return ""
    return row["content"] if isinstance(row, dict) else row[0]


def fetch_word_counts(cur, words_table, min_count, limit):
    cur.execute(f"""
        SELECT word, COUNT(*) AS cnt
        FROM `{words_table}`
        WHERE word IS NOT NULL
          AND word <> ''
        GROUP BY word
        HAVING COUNT(*) >= %s
        ORDER BY cnt DESC, word ASC
        LIMIT %s
    """, (min_count, limit))
    return cur.fetchall()
