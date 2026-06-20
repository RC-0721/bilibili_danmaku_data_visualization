"""Video parallel-coordinate profile endpoint."""

import pymysql

from app.api.common import PARALLEL_DIMENSIONS, PARALLEL_MAX_VIDEOS, PARALLEL_STATS_TABLE, parse_bvid_list
from app.db import get_connection, table_exists


def get_video_parallel_stats_payload(query):
    bvids = parse_bvid_list(query, PARALLEL_MAX_VIDEOS)
    limit = int(query.get("limit", [str(PARALLEL_MAX_VIDEOS)])[0] or PARALLEL_MAX_VIDEOS)
    limit = max(1, min(limit, PARALLEL_MAX_VIDEOS))

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if not table_exists(cur, PARALLEL_STATS_TABLE):
                return {
                    "dimensions": PARALLEL_DIMENSIONS,
                    "videos": [],
                    "rows": [],
                    "source": "missing_parallel_stats",
                    "message": "video_parallel_stats 不存在，请先运行 build_video_parallel_stats.py --execute",
                }

            if bvids:
                placeholders = ", ".join(["%s"] * len(bvids))
                cur.execute(f"""
                    SELECT *
                    FROM `{PARALLEL_STATS_TABLE}`
                    WHERE bvid IN ({placeholders})
                """, bvids)
                by_bvid = {row["bvid"]: row for row in cur.fetchall()}
                raw_rows = [by_bvid[bvid] for bvid in bvids if bvid in by_bvid][:limit]
            else:
                cur.execute(f"""
                    SELECT *
                    FROM `{PARALLEL_STATS_TABLE}`
                    ORDER BY stat_view DESC
                    LIMIT %s
                """, (limit,))
                raw_rows = cur.fetchall()

            rows = []
            videos = []
            for row in raw_rows:
                item = {
                    "videoId": int(row["video_id"]),
                    "bvid": row["bvid"],
                    "title": row["title"] or row["bvid"],
                    "durationSeconds": int(row["duration_seconds"] or 0),
                    "durationMinutes": round(float(row["duration_seconds"] or 0) / 60, 3),
                    "viewCount": int(row["stat_view"] or 0),
                    "danmakuCount": int(row["stat_danmaku"] or 0),
                    "replyCount": int(row["stat_reply"] or 0),
                    "favoriteCount": int(row["stat_favorite"] or 0),
                    "coinCount": int(row["stat_coin"] or 0),
                    "shareCount": int(row["stat_share"] or 0),
                    "likeCount": int(row["stat_like"] or 0),
                    "crawledDanmakuCount": int(row["crawled_danmaku_count"] or 0),
                    "danmakuRate": float(row["danmaku_rate"] or 0),
                    "replyRate": float(row["reply_rate"] or 0),
                    "favoriteRate": float(row["favorite_rate"] or 0),
                    "coinRate": float(row["coin_rate"] or 0),
                    "shareRate": float(row["share_rate"] or 0),
                    "likeRate": float(row["like_rate"] or 0),
                    "peakDensity": float(row["peak_density"] or 0),
                    "highEnergyWindowCount": int(row["high_energy_window_count"] or 0),
                    "avgRepeatRatio": float(row["avg_repeat_ratio"] or 0),
                    "positiveCount": int(row["positive_count"] or 0),
                    "neutralCount": int(row["neutral_count"] or 0),
                    "negativeCount": int(row["negative_count"] or 0),
                    "positiveRatio": float(row["positive_ratio"] or 0),
                    "totalWords": int(row["total_words"] or 0),
                    "uniqueWords": int(row["unique_words"] or 0),
                    "lexicalRichness": float(row["lexical_richness"] or 0),
                    "windowSeconds": int(row["window_seconds"] or 0),
                }
                rows.append(item)
                videos.append({
                    "id": item["videoId"],
                    "bvid": item["bvid"],
                    "title": item["title"],
                })

            return {
                "dimensions": PARALLEL_DIMENSIONS,
                "videos": videos,
                "rows": rows,
                "source": PARALLEL_STATS_TABLE,
                "maxVideos": PARALLEL_MAX_VIDEOS,
            }
    finally:
        conn.close()
