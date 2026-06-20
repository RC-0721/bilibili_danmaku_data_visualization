"""Core database connection, video metadata, and crawl progress helpers."""

import pymysql

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


def get_connection(database=DB_NAME):
    kwargs = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "charset": "utf8mb4",
    }
    if database:
        kwargs["database"] = database
    return pymysql.connect(**kwargs)


def create_database_if_not_exists():
    conn = get_connection(database=None)
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
        conn.commit()
        print(f"数据库 {DB_NAME} 已就绪")
    finally:
        conn.close()


def init_db():
    create_database_if_not_exists()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS precious_videos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    bvid VARCHAR(20) NOT NULL UNIQUE,
                    cid BIGINT NOT NULL DEFAULT 0,
                    title VARCHAR(500) DEFAULT '',
                    cover VARCHAR(500) DEFAULT '',
                    pubdate INT DEFAULT 0,
                    duration INT DEFAULT 0,
                    owner_name VARCHAR(200) DEFAULT '',
                    owner_mid BIGINT DEFAULT 0,
                    stat_view INT DEFAULT 0,
                    stat_danmaku INT DEFAULT 0,
                    stat_reply INT DEFAULT 0,
                    stat_favorite INT DEFAULT 0,
                    stat_coin INT DEFAULT 0,
                    stat_share INT DEFAULT 0,
                    stat_like INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()
    init_progress_table()


def save_videos(video_list):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for video in video_list:
                cur.execute("""
                    INSERT INTO precious_videos
                    (bvid, cid, title, cover, pubdate, duration, owner_name, owner_mid,
                     stat_view, stat_danmaku, stat_reply, stat_favorite, stat_coin, stat_share, stat_like)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        cid = VALUES(cid), title = VALUES(title), cover = VALUES(cover),
                        pubdate = VALUES(pubdate), duration = VALUES(duration),
                        owner_name = VALUES(owner_name), owner_mid = VALUES(owner_mid),
                        stat_view = VALUES(stat_view), stat_danmaku = VALUES(stat_danmaku),
                        stat_reply = VALUES(stat_reply), stat_favorite = VALUES(stat_favorite),
                        stat_coin = VALUES(stat_coin), stat_share = VALUES(stat_share),
                        stat_like = VALUES(stat_like)
                """, (
                    video["bvid"], video.get("cid", 0), video.get("title", ""), video.get("pic", ""),
                    video.get("pubdate", 0), video.get("duration", 0),
                    video.get("owner", {}).get("name", ""), video.get("owner", {}).get("mid", 0),
                    video.get("stat", {}).get("view", 0), video.get("stat", {}).get("danmaku", 0),
                    video.get("stat", {}).get("reply", 0), video.get("stat", {}).get("favorite", 0),
                    video.get("stat", {}).get("coin", 0), video.get("stat", {}).get("share", 0),
                    video.get("stat", {}).get("like", 0),
                ))
        conn.commit()
    finally:
        conn.close()


def get_videos():
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT bvid, cid, pubdate, duration FROM precious_videos")
            return cur.fetchall()
    finally:
        conn.close()


def get_video_id_by_bvid(bvid):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM precious_videos WHERE bvid = %s", (bvid,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def init_progress_table():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS danmaku_progress (
                    bvid VARCHAR(20) NOT NULL PRIMARY KEY,
                    last_date DATE NOT NULL,
                    date_step INT NOT NULL DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (bvid) REFERENCES precious_videos(bvid)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("SHOW COLUMNS FROM danmaku_progress LIKE 'date_step'")
            if cur.fetchone() is None:
                cur.execute("ALTER TABLE danmaku_progress ADD COLUMN date_step INT NOT NULL DEFAULT 1 AFTER last_date")
        conn.commit()
    finally:
        conn.close()


def get_progress(bvid):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT last_date FROM danmaku_progress WHERE bvid = %s", (bvid,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def get_date_step(bvid, default=1):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT date_step FROM danmaku_progress WHERE bvid = %s", (bvid,))
            row = cur.fetchone()
            if not row or row[0] is None:
                return default
            return max(int(row[0]), 1)
    finally:
        conn.close()


def update_progress(bvid, last_date, date_step=None):
    if date_step is not None:
        date_step = max(int(date_step), 1)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if date_step is None:
                cur.execute("""
                    INSERT INTO danmaku_progress (bvid, last_date)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE last_date = VALUES(last_date)
                """, (bvid, last_date))
            else:
                cur.execute("""
                    INSERT INTO danmaku_progress (bvid, last_date, date_step)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        last_date = VALUES(last_date),
                        date_step = VALUES(date_step)
                """, (bvid, last_date, date_step))
        conn.commit()
    finally:
        conn.close()


def update_date_step(bvid, date_step):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE danmaku_progress SET date_step = %s WHERE bvid = %s", (max(int(date_step), 1), bvid))
        conn.commit()
    finally:
        conn.close()


def get_all_video_records():
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT id, bvid, cid, title, pubdate, duration, stat_danmaku
                FROM precious_videos
                ORDER BY id
            """)
            return cur.fetchall()
    finally:
        conn.close()


def table_exists(cur, table_name):
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
    """, (table_name,))
    row = cur.fetchone()
    if isinstance(row, dict):
        return next(iter(row.values())) > 0
    return row[0] > 0
