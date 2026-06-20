"""Video similarity endpoints."""

import json
import math

import pymysql

from app.api.common import (
    SIMILARITY_DEFAULT_TOP_WORDS,
    SIMILARITY_MATRIX_TABLE,
    SIMILARITY_MAX_MATRIX_VIDEOS,
    SIMILARITY_MAX_TOP_WORDS,
    SIMILARITY_MAX_VIDEOS,
    SIMILARITY_METRICS,
    WORD_CLOUD_STATS_TABLE,
    is_meaningful_word,
    load_word_cloud_stopwords,
    parse_bvid_list,
    parse_date_param,
)
from app.db import get_connection, table_exists


def cosine_similarity(vector_a, vector_b):
    if not vector_a or not vector_b:
        return 0.0
    if len(vector_a) > len(vector_b):
        vector_a, vector_b = vector_b, vector_a
    dot = sum(value * vector_b.get(word, 0.0) for word, value in vector_a.items())
    norm_a = math.sqrt(sum(value * value for value in vector_a.values()))
    norm_b = math.sqrt(sum(value * value for value in vector_b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def load_similarity_vector(cur, video_id, start, end, top_words, stopwords):
    fetch_limit = min(top_words * 3, SIMILARITY_MAX_TOP_WORDS * 3)
    cur.execute(f"""
        SELECT word, SUM(count) AS value
        FROM `{WORD_CLOUD_STATS_TABLE}`
        WHERE video_id = %s
          AND stat_date BETWEEN %s AND %s
        GROUP BY word
        ORDER BY value DESC
        LIMIT %s
    """, (video_id, start, end, fetch_limit))

    vector = {}
    for row in cur.fetchall():
        word = (row["word"] or "").strip()
        if not is_meaningful_word(word, stopwords):
            continue
        vector[word] = math.log1p(float(row["value"] or 0))
        if len(vector) >= top_words:
            break
    return vector


def get_video_similarity_payload(query):
    bvids = parse_bvid_list(query, SIMILARITY_MAX_VIDEOS, require_nonempty=True)
    start = query.get("start", [""])[0] or "1900-01-01"
    end = query.get("end", [""])[0] or "2999-12-31"
    top_words = int(query.get("top_words", [str(SIMILARITY_DEFAULT_TOP_WORDS)])[0] or SIMILARITY_DEFAULT_TOP_WORDS)
    top_words = max(50, min(top_words, SIMILARITY_MAX_TOP_WORDS))
    start = parse_date_param(start, "start")
    end = parse_date_param(end, "end")
    if start > end:
        raise ValueError("start must be earlier than or equal to end")

    stopwords = load_word_cloud_stopwords()
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if not table_exists(cur, WORD_CLOUD_STATS_TABLE):
                return {
                    "videos": [],
                    "matrix": [],
                    "cells": [],
                    "topWords": top_words,
                    "source": "missing_stats",
                    "message": "word_cloud_daily_stats 不存在，请先运行 build_word_cloud_stats.py",
                }

            placeholders = ", ".join(["%s"] * len(bvids))
            cur.execute(f"""
                SELECT id, bvid, title
                FROM precious_videos
                WHERE bvid IN ({placeholders})
            """, bvids)
            by_bvid = {row["bvid"]: row for row in cur.fetchall()}
            videos = [by_bvid[bvid] for bvid in bvids if bvid in by_bvid]
            if not videos:
                raise ValueError("no known videos selected")

            vectors = {}
            vector_sizes = {}
            for video in videos:
                vector = load_similarity_vector(cur, video["id"], start, end, top_words, stopwords)
                vectors[video["bvid"]] = vector
                vector_sizes[video["bvid"]] = len(vector)

            matrix = []
            cells = []
            for row_index, row_video in enumerate(videos):
                matrix_row = []
                for col_index, col_video in enumerate(videos):
                    if row_index == col_index:
                        score = 1.0 if vectors[row_video["bvid"]] else 0.0
                    else:
                        score = cosine_similarity(vectors[row_video["bvid"]], vectors[col_video["bvid"]])
                    score = round(score, 4)
                    matrix_row.append(score)
                    cells.append([col_index, row_index, score])
                matrix.append(matrix_row)

            return {
                "videos": [
                    {
                        "id": video["id"],
                        "bvid": video["bvid"],
                        "title": video["title"],
                        "vectorSize": vector_sizes[video["bvid"]],
                    }
                    for video in videos
                ],
                "matrix": matrix,
                "cells": cells,
                "topWords": top_words,
                "source": WORD_CLOUD_STATS_TABLE,
            }
    finally:
        conn.close()


def get_video_similarity_matrix_payload(query):
    metric = query.get("metric", ["combined"])[0] or "combined"
    feature_version = query.get("feature_version", ["v1"])[0] or "v1"
    bvids = parse_bvid_list(query, SIMILARITY_MAX_MATRIX_VIDEOS)
    limit = int(query.get("limit", [str(SIMILARITY_MAX_MATRIX_VIDEOS)])[0] or SIMILARITY_MAX_MATRIX_VIDEOS)
    limit = max(2, min(limit, SIMILARITY_MAX_MATRIX_VIDEOS))

    if metric not in SIMILARITY_METRICS:
        raise ValueError("metric must be one of trend, sentiment, high_energy, combined")

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if not table_exists(cur, SIMILARITY_MATRIX_TABLE):
                return {
                    "metric": metric,
                    "featureVersion": feature_version,
                    "videos": [],
                    "cells": [],
                    "matrix": [],
                    "details": {},
                    "source": "missing_matrix",
                    "message": "video_similarity_matrix 不存在，请先运行 build_video_similarity_matrix.py --execute",
                }

            if bvids:
                placeholders = ", ".join(["%s"] * len(bvids))
                cur.execute(f"""
                    SELECT id, bvid, title
                    FROM precious_videos
                    WHERE bvid IN ({placeholders})
                """, bvids)
                by_bvid = {row["bvid"]: row for row in cur.fetchall()}
                videos = [by_bvid[bvid] for bvid in bvids if bvid in by_bvid][:limit]
            else:
                cur.execute("""
                    SELECT id, bvid, title
                    FROM precious_videos
                    ORDER BY id
                    LIMIT %s
                """, (limit,))
                videos = cur.fetchall()

            if not videos:
                raise ValueError("no known videos selected")

            video_ids = [video["id"] for video in videos]
            placeholders = ", ".join(["%s"] * len(video_ids))
            cur.execute(f"""
                SELECT
                    video_id_a,
                    video_id_b,
                    similarity,
                    trend_similarity,
                    sentiment_similarity,
                    high_energy_similarity
                FROM `{SIMILARITY_MATRIX_TABLE}`
                WHERE feature_version = %s
                  AND metric = %s
                  AND video_id_a IN ({placeholders})
                  AND video_id_b IN ({placeholders})
            """, [feature_version, metric, *video_ids, *video_ids])
            by_pair = {
                (row["video_id_a"], row["video_id_b"]): row
                for row in cur.fetchall()
            }

            id_to_index = {video["id"]: index for index, video in enumerate(videos)}
            matrix = []
            cells = []
            details = {}
            for row_video in videos:
                matrix_row = []
                for col_video in videos:
                    row = by_pair.get((row_video["id"], col_video["id"]))
                    score = float(row["similarity"] or 0) if row else (1.0 if row_video["id"] == col_video["id"] else 0.0)
                    score = round(score, 4)
                    row_index = id_to_index[row_video["id"]]
                    col_index = id_to_index[col_video["id"]]
                    matrix_row.append(score)
                    cells.append([col_index, row_index, score])
                    if row:
                        details[f"{row_video['id']}:{col_video['id']}"] = {
                            "trendSimilarity": row["trend_similarity"],
                            "sentimentSimilarity": row["sentiment_similarity"],
                            "highEnergySimilarity": row["high_energy_similarity"],
                        }
                matrix.append(matrix_row)

            return {
                "metric": metric,
                "featureVersion": feature_version,
                "videos": videos,
                "cells": cells,
                "matrix": matrix,
                "details": details,
                "source": SIMILARITY_MATRIX_TABLE,
            }
    finally:
        conn.close()
