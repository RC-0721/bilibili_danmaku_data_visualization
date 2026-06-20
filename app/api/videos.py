"""Video metadata endpoints."""

from urllib.parse import quote

import pymysql

from app.api.common import to_date_string
from app.db import get_connection


def get_videos_payload():
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id, bvid, title
                FROM precious_videos
                ORDER BY id
            """)
            videos = [
                {"id": row["id"], "bvid": row["bvid"], "title": row["title"]}
                for row in cur.fetchall()
            ]
            return {"videos": videos}
    finally:
        conn.close()


def get_video_detail_payload(query):
    bvid = query.get("bvid", [""])[0]
    if not bvid:
        raise ValueError("missing bvid")

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT
                    v.id,
                    v.bvid,
                    v.cid,
                    v.title,
                    v.cover,
                    v.pubdate,
                    v.duration,
                    v.stat_danmaku,
                    p.last_date,
                    p.date_step
                FROM precious_videos AS v
                LEFT JOIN danmaku_progress AS p ON p.bvid = v.bvid
                WHERE v.bvid = %s
            """, (bvid,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"unknown bvid: {bvid}")
            return {
                "video": {
                    "id": row["id"],
                    "bvid": row["bvid"],
                    "cid": row["cid"],
                    "title": row["title"],
                    "cover": row["cover"],
                    "coverUrl": f"/api/cover?url={quote(row['cover'] or '', safe='')}",
                    "publishDate": to_date_string(row["pubdate"]),
                    "duration": row["duration"],
                    "total": row["stat_danmaku"],
                    "lastDate": row["last_date"],
                    "dateStep": row["date_step"] or 1,
                }
            }
    finally:
        conn.close()
