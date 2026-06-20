"""Database table helpers for high-energy window analysis."""

import json


def ensure_high_energy_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS high_energy_windows (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            video_id INT NOT NULL,
            bvid VARCHAR(20) NOT NULL,
            window_seconds INT NOT NULL,
            window_index INT NOT NULL,
            start_seconds INT NOT NULL,
            end_seconds INT NOT NULL,
            score DOUBLE NOT NULL,
            is_high TINYINT NOT NULL DEFAULT 0,
            danmaku_count INT NOT NULL DEFAULT 0,
            unique_count INT NOT NULL DEFAULT 0,
            repeat_ratio DOUBLE NOT NULL DEFAULT 0,
            density_norm DOUBLE NOT NULL DEFAULT 0,
            positive_count INT NOT NULL DEFAULT 0,
            neutral_count INT NOT NULL DEFAULT 0,
            negative_count INT NOT NULL DEFAULT 0,
            emotion_ratio DOUBLE NOT NULL DEFAULT 0,
            top_word VARCHAR(100) DEFAULT '',
            top_word_ratio DOUBLE NOT NULL DEFAULT 0,
            top_words TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_video_window (video_id, window_seconds, window_index),
            INDEX idx_video_score (video_id, score),
            INDEX idx_video_time (video_id, start_seconds)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def ensure_high_energy_segments_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS high_energy_segments (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            video_id INT NOT NULL,
            bvid VARCHAR(20) NOT NULL,
            window_seconds INT NOT NULL,
            segment_index INT NOT NULL,
            start_seconds INT NOT NULL,
            end_seconds INT NOT NULL,
            window_count INT NOT NULL DEFAULT 0,
            peak_score DOUBLE NOT NULL DEFAULT 0,
            avg_score DOUBLE NOT NULL DEFAULT 0,
            danmaku_count INT NOT NULL DEFAULT 0,
            positive_count INT NOT NULL DEFAULT 0,
            neutral_count INT NOT NULL DEFAULT 0,
            negative_count INT NOT NULL DEFAULT 0,
            top_word VARCHAR(100) DEFAULT '',
            top_words TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_video_segment (video_id, window_seconds, segment_index),
            INDEX idx_video_time (video_id, start_seconds),
            INDEX idx_video_peak (video_id, peak_score)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def save_rows(cur, video, window_seconds, rows):
    cur.execute(
        "DELETE FROM high_energy_windows WHERE video_id = %s AND window_seconds = %s",
        (video["id"], window_seconds),
    )
    if not rows:
        return 0

    data = [
        (
            video["id"],
            video["bvid"],
            window_seconds,
            row["window_index"],
            row["start_seconds"],
            row["end_seconds"],
            row["score"],
            row["is_high"],
            row["danmaku_count"],
            row["unique_count"],
            row["repeat_ratio"],
            row["density_norm"],
            row["positive_count"],
            row["neutral_count"],
            row["negative_count"],
            row["emotion_ratio"],
            row["top_word"],
            row["top_word_ratio"],
            json.dumps(row["top_words"], ensure_ascii=False),
        )
        for row in rows
    ]

    cur.executemany("""
        INSERT INTO high_energy_windows (
            video_id, bvid, window_seconds, window_index,
            start_seconds, end_seconds, score, is_high,
            danmaku_count, unique_count, repeat_ratio, density_norm,
            positive_count, neutral_count, negative_count, emotion_ratio,
            top_word, top_word_ratio, top_words
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
        )
    """, data)
    return cur.rowcount


def save_segments(cur, video, window_seconds, segments):
    cur.execute(
        "DELETE FROM high_energy_segments WHERE video_id = %s AND window_seconds = %s",
        (video["id"], window_seconds),
    )
    if not segments:
        return 0

    data = [
        (
            video["id"],
            video["bvid"],
            window_seconds,
            segment["segment_index"],
            segment["start_seconds"],
            segment["end_seconds"],
            segment["window_count"],
            segment["peak_score"],
            segment["avg_score"],
            segment["danmaku_count"],
            segment["positive_count"],
            segment["neutral_count"],
            segment["negative_count"],
            segment["top_word"],
            json.dumps(segment["top_words"], ensure_ascii=False),
        )
        for segment in segments
    ]

    cur.executemany("""
        INSERT INTO high_energy_segments (
            video_id, bvid, window_seconds, segment_index,
            start_seconds, end_seconds, window_count,
            peak_score, avg_score, danmaku_count,
            positive_count, neutral_count, negative_count,
            top_word, top_words
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s
        )
    """, data)
    return cur.rowcount
