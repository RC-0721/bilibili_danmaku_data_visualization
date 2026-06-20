"""Playback-progress by date heatmap endpoint."""

import pymysql

from app.api.common import parse_date_param, parse_heatmap_window_seconds
from app.db import get_connection, table_exists


def get_progress_date_heatmap_payload(query):
    bvid = query.get("bvid", [""])[0]
    start = query.get("start", [""])[0]
    end = query.get("end", [""])[0]
    normalize = query.get("normalize", ["none"])[0] or "none"
    window_seconds = parse_heatmap_window_seconds(query)
    max_cells = 120000

    if not bvid:
        raise ValueError("missing bvid")
    if not start or not end:
        raise ValueError("missing start/end")
    start = parse_date_param(start, "start")
    end = parse_date_param(end, "end")
    if start > end:
        raise ValueError("start must be earlier than or equal to end")
    if normalize not in {"none", "date"}:
        raise ValueError("normalize must be none or date")

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id, bvid, title, duration
                FROM precious_videos
                WHERE bvid = %s
            """, (bvid,))
            video = cur.fetchone()
            if not video:
                raise ValueError(f"unknown bvid: {bvid}")

            table_name = f"video_{video['id']}_danmaku_history"
            empty_payload = {
                "bvid": bvid,
                "duration": int(video["duration"] or 0),
                "windowSeconds": window_seconds,
                "normalize": normalize,
                "dates": [],
                "progressBuckets": [],
                "data": [],
                "maxCount": 0,
                "maxValue": 0,
            }
            if not table_exists(cur, table_name):
                return empty_payload

            cur.execute(f"""
                SELECT
                    dm_date AS date,
                    FLOOR(progress / (%s * 1000)) * %s AS progress_bucket,
                    COUNT(*) AS count
                FROM `{table_name}`
                WHERE dm_date BETWEEN %s AND %s
                  AND progress >= 0
                GROUP BY dm_date, progress_bucket
                ORDER BY dm_date, progress_bucket
            """, (window_seconds, window_seconds, start, end))
            rows = cur.fetchall()
            if not rows:
                return empty_payload

            dates = sorted({row["date"].isoformat() for row in rows if row["date"] is not None})
            max_bucket = max(int(row["progress_bucket"] or 0) for row in rows)
            bucket_end = max(int(video["duration"] or 0), max_bucket)
            progress_buckets = list(range(0, bucket_end + 1, window_seconds)) or [0]

            cell_count = len(dates) * len(progress_buckets)
            if cell_count > max_cells:
                raise ValueError(
                    f"heatmap grid too large: {cell_count} cells; "
                    "increase window_seconds or narrow the date range"
                )

            date_index = {date: index for index, date in enumerate(dates)}
            bucket_index = {bucket: index for index, bucket in enumerate(progress_buckets)}
            date_max = {}
            max_count = 0
            for row in rows:
                date = row["date"].isoformat()
                count = int(row["count"] or 0)
                date_max[date] = max(date_max.get(date, 0), count)
                max_count = max(max_count, count)

            data = []
            max_value = 1 if normalize == "date" else max_count
            for row in rows:
                date = row["date"].isoformat()
                bucket = int(row["progress_bucket"] or 0)
                count = int(row["count"] or 0)
                if bucket not in bucket_index:
                    continue
                value = count / date_max[date] if normalize == "date" and date_max.get(date) else count
                data.append([bucket_index[bucket], date_index[date], value, count])

            return {
                "bvid": bvid,
                "duration": int(video["duration"] or 0),
                "windowSeconds": window_seconds,
                "normalize": normalize,
                "dates": dates,
                "progressBuckets": progress_buckets,
                "data": data,
                "maxCount": max_count,
                "maxValue": max_value,
            }
    finally:
        conn.close()
