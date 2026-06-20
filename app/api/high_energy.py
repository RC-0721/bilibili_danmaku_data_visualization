"""High-energy window endpoint."""

import pymysql

from app.api.common import parse_json_list
from app.db import get_connection, table_exists


def get_high_energy_payload(query):
    bvid = query.get("bvid", [""])[0]
    window_seconds = query.get("window_seconds", [""])[0]
    only_high = query.get("only_high", ["0"])[0].lower() in {"1", "true", "yes"}
    limit = int(query.get("limit", ["1000"])[0] or 1000)
    limit = max(1, min(limit, 5000))
    if not bvid:
        raise ValueError("missing bvid")

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

            if not table_exists(cur, "high_energy_windows"):
                return {
                    "bvid": bvid,
                    "windowSeconds": int(window_seconds or 0),
                    "availableWindowSeconds": [],
                    "rows": [],
                    "segments": [],
                    "summary": {},
                }

            cur.execute("""
                SELECT window_seconds
                FROM high_energy_windows
                WHERE video_id = %s
                GROUP BY window_seconds
                ORDER BY window_seconds
            """, (video["id"],))
            available_window_seconds = [int(row["window_seconds"]) for row in cur.fetchall()]

            if window_seconds:
                selected_window_seconds = int(window_seconds)
            else:
                cur.execute("""
                    SELECT window_seconds
                    FROM high_energy_windows
                    WHERE video_id = %s
                    GROUP BY window_seconds
                    ORDER BY MAX(created_at) DESC, window_seconds DESC
                    LIMIT 1
                """, (video["id"],))
                window_row = cur.fetchone()
                if not window_row:
                    return {
                        "bvid": bvid,
                        "windowSeconds": 0,
                        "availableWindowSeconds": available_window_seconds,
                        "rows": [],
                        "segments": [],
                        "summary": {},
                    }
                selected_window_seconds = int(window_row["window_seconds"])

            where_sql = "video_id = %s AND window_seconds = %s"
            params = [video["id"], selected_window_seconds]
            if only_high:
                where_sql += " AND is_high = 1"

            cur.execute(f"""
                SELECT
                    start_seconds,
                    end_seconds,
                    score,
                    is_high,
                    danmaku_count,
                    repeat_ratio,
                    density_norm,
                    positive_count,
                    neutral_count,
                    negative_count,
                    emotion_ratio,
                    top_word,
                    top_word_ratio,
                    top_words
                FROM high_energy_windows
                WHERE {where_sql}
                ORDER BY start_seconds
                LIMIT %s
            """, (*params, limit))

            rows = []
            for row in cur.fetchall():
                rows.append({
                    "startSeconds": int(row["start_seconds"]),
                    "endSeconds": int(row["end_seconds"]),
                    "score": float(row["score"] or 0),
                    "isHigh": bool(row["is_high"]),
                    "danmakuCount": int(row["danmaku_count"] or 0),
                    "repeatRatio": float(row["repeat_ratio"] or 0),
                    "densityNorm": float(row["density_norm"] or 0),
                    "positiveCount": int(row["positive_count"] or 0),
                    "neutralCount": int(row["neutral_count"] or 0),
                    "negativeCount": int(row["negative_count"] or 0),
                    "emotionRatio": float(row["emotion_ratio"] or 0),
                    "topWord": row["top_word"] or "",
                    "topWordRatio": float(row["top_word_ratio"] or 0),
                    "topWords": parse_json_list(row["top_words"]),
                })

            segments = []
            if table_exists(cur, "high_energy_segments"):
                cur.execute("""
                    SELECT
                        segment_index,
                        start_seconds,
                        end_seconds,
                        window_count,
                        peak_score,
                        avg_score,
                        danmaku_count,
                        positive_count,
                        neutral_count,
                        negative_count,
                        top_word,
                        top_words
                    FROM high_energy_segments
                    WHERE video_id = %s
                      AND window_seconds = %s
                    ORDER BY start_seconds
                """, (video["id"], selected_window_seconds))
                for row in cur.fetchall():
                    segments.append({
                        "segmentIndex": int(row["segment_index"]),
                        "startSeconds": int(row["start_seconds"]),
                        "endSeconds": int(row["end_seconds"]),
                        "windowCount": int(row["window_count"] or 0),
                        "peakScore": float(row["peak_score"] or 0),
                        "avgScore": float(row["avg_score"] or 0),
                        "danmakuCount": int(row["danmaku_count"] or 0),
                        "positiveCount": int(row["positive_count"] or 0),
                        "neutralCount": int(row["neutral_count"] or 0),
                        "negativeCount": int(row["negative_count"] or 0),
                        "topWord": row["top_word"] or "",
                        "topWords": parse_json_list(row["top_words"]),
                    })

            summary = {
                "windowCount": len(rows),
                "highWindowCount": sum(1 for row in rows if row["isHigh"]),
                "segmentCount": len(segments),
                "peakScore": max((row["score"] for row in rows), default=0),
                "peakDanmakuCount": max((row["danmakuCount"] for row in rows), default=0),
            }
            return {
                "bvid": bvid,
                "windowSeconds": selected_window_seconds,
                "availableWindowSeconds": available_window_seconds,
                "rows": rows,
                "segments": segments,
                "summary": summary,
            }
    finally:
        conn.close()
