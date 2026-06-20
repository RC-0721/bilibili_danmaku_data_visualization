"""Word-cloud and danmaku trend endpoints."""

import pymysql

from app.api.common import (
    WORD_CLOUD_STATS_TABLE,
    is_meaningful_word,
    load_word_cloud_stopwords,
)
from app.db import get_connection, table_exists

try:
    from app.text.segmentation import get_alias_phrases
except ImportError:
    def get_alias_phrases():
        return {}


def format_word_cloud_rows(raw_rows, stopwords, alias_phrases, limit):
    rows = []
    for row in raw_rows:
        word = (row["name"] or "").strip()
        if not is_meaningful_word(word, stopwords):
            continue
        item = {"name": word, "value": int(row["value"] or 0)}
        if word in alias_phrases:
            item["phrases"] = alias_phrases[word]
        rows.append(item)
        if len(rows) >= limit:
            break
    return rows


def query_word_cloud_stats_rows(cur, video_id, start, end, fetch_limit):
    if not table_exists(cur, WORD_CLOUD_STATS_TABLE):
        return None

    cur.execute(f"""
        SELECT 1
        FROM `{WORD_CLOUD_STATS_TABLE}`
        WHERE video_id = %s
          AND stat_date BETWEEN %s AND %s
        LIMIT 1
    """, (video_id, start, end))
    if not cur.fetchone():
        return None

    cur.execute(f"""
        SELECT word AS name, SUM(count) AS value
        FROM `{WORD_CLOUD_STATS_TABLE}`
        WHERE video_id = %s
          AND stat_date BETWEEN %s AND %s
        GROUP BY word
        ORDER BY value DESC
        LIMIT %s
    """, (video_id, start, end, fetch_limit))
    return cur.fetchall()


def query_word_cloud_raw_rows(cur, video_id, start, end, fetch_limit):
    danmaku_table = f"video_{video_id}_danmaku_history"
    words_table = f"danmaku_words_{video_id}"
    if not table_exists(cur, danmaku_table) or not table_exists(cur, words_table):
        return []

    date_expr = "COALESCE(DATE(d.send_time), DATE(FROM_UNIXTIME(d.ctime)))"
    cur.execute(f"""
        SELECT w.word AS name, COUNT(*) AS value
        FROM `{words_table}` AS w
        INNER JOIN `{danmaku_table}` AS d ON d.id = w.danmaku_row_id
        WHERE {date_expr} BETWEEN %s AND %s
        GROUP BY w.word
        ORDER BY value DESC
        LIMIT %s
    """, (start, end, fetch_limit))
    return cur.fetchall()


def get_trend_payload(query):
    bvid = query.get("bvid", [""])[0]
    start = query.get("start", [""])[0]
    end = query.get("end", [""])[0]
    if not bvid:
        raise ValueError("missing bvid")
    if not start or not end:
        raise ValueError("missing start/end")

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id, bvid, title, stat_danmaku
                FROM precious_videos
                WHERE bvid = %s
            """, (bvid,))
            video = cur.fetchone()
            if not video:
                raise ValueError(f"unknown bvid: {bvid}")

            table_name = f"video_{video['id']}_danmaku_history"
            if not table_exists(cur, table_name):
                return {"bvid": bvid, "rows": []}

            date_expr = "COALESCE(DATE(send_time), DATE(FROM_UNIXTIME(ctime)))"
            cur.execute(f"""
                SELECT {date_expr} AS date, COUNT(*) AS count
                FROM `{table_name}`
                WHERE {date_expr} BETWEEN %s AND %s
                GROUP BY {date_expr}
                ORDER BY {date_expr}
            """, (start, end))
            rows = [
                {"date": row["date"], "count": int(row["count"] or 0)}
                for row in cur.fetchall()
                if row["date"] is not None
            ]
            return {"bvid": bvid, "rows": rows}
    finally:
        conn.close()


def get_word_cloud_payload(query):
    bvid = query.get("bvid", [""])[0]
    start = query.get("start", [""])[0]
    end = query.get("end", [""])[0]
    limit = int(query.get("limit", ["120"])[0] or 120)
    limit = max(20, min(limit, 300))
    if not bvid:
        raise ValueError("missing bvid")
    if not start or not end:
        raise ValueError("missing start/end")

    stopwords = load_word_cloud_stopwords()
    alias_phrases = get_alias_phrases()
    fetch_limit = min(limit * 5, 1500)

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id, bvid, title
                FROM precious_videos
                WHERE bvid = %s
            """, (bvid,))
            video = cur.fetchone()
            if not video:
                raise ValueError(f"unknown bvid: {bvid}")

            source = "stats"
            raw_rows = query_word_cloud_stats_rows(cur, video["id"], start, end, fetch_limit)
            if raw_rows is None:
                source = "raw"
                raw_rows = query_word_cloud_raw_rows(cur, video["id"], start, end, fetch_limit)

            rows = format_word_cloud_rows(raw_rows, stopwords, alias_phrases, limit)
            return {
                "bvid": bvid,
                "rows": rows,
                "stopwordCount": len(stopwords),
                "source": source,
            }
    finally:
        conn.close()
