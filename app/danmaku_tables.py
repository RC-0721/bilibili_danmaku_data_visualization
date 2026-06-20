"""Per-video danmaku and segmentation table helpers."""

import hashlib

from app.db_core import get_connection, get_video_id_by_bvid, table_exists


def danmaku_table_name(video_id):
    return f"video_{int(video_id)}_danmaku_history"


def danmaku_words_table_name(video_id):
    return f"danmaku_words_{int(video_id)}"


def make_danmaku_key(dm):
    dm_id = dm.get("id", 0)
    try:
        dm_id_int = int(dm_id)
    except (TypeError, ValueError):
        dm_id_int = 0
    if dm_id_int > 0:
        return f"id:{dm_id_int}"

    id_str = str(dm.get("idStr") or "").strip()
    if id_str:
        return f"idstr:{id_str}"

    raw_key = "|".join(
        str(dm.get(name, ""))
        for name in ("cid", "ctime", "progress", "mode", "midHash", "content")
    )
    return "hash:" + hashlib.md5(raw_key.encode("utf-8")).hexdigest()


def ensure_danmaku_table_schema(cur, table_name):
    cur.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE 'id_str'")
    if cur.fetchone() is None:
        cur.execute(f"ALTER TABLE `{table_name}` ADD COLUMN id_str VARCHAR(50) DEFAULT '' AFTER dm_id")

    cur.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE 'danmaku_key'")
    if cur.fetchone() is None:
        cur.execute(f"ALTER TABLE `{table_name}` ADD COLUMN danmaku_key VARCHAR(64) DEFAULT NULL AFTER id_str")
        cur.execute(f"""
            UPDATE `{table_name}`
            SET danmaku_key = CASE
                WHEN dm_id > 0 THEN CONCAT('id:', dm_id)
                ELSE CONCAT('hash:', MD5(CONCAT_WS('|', cid, ctime, progress, mode, mid_hash, content)))
            END
            WHERE danmaku_key IS NULL OR danmaku_key = ''
        """)

    cur.execute(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = 'idx_danmaku_key'")
    if cur.fetchone() is None:
        cur.execute(f"CREATE INDEX idx_danmaku_key ON `{table_name}` (danmaku_key)")


def fetch_existing_danmaku_keys(cur, table_name, keys, chunk_size=1000):
    existing = set()
    key_list = list(keys)
    for index in range(0, len(key_list), chunk_size):
        chunk = key_list[index:index + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        cur.execute(f"SELECT danmaku_key FROM `{table_name}` WHERE danmaku_key IN ({placeholders})", chunk)
        existing.update(row[0] for row in cur.fetchall())
    return existing


def save_danmaku_list(danmaku_list):
    if not danmaku_list:
        return 0
    bvid = danmaku_list[0]["bvid"]
    video_id = get_video_id_by_bvid(bvid)
    if video_id is None:
        print(f"  视频 {bvid} 不在 precious_videos 表中，弹幕未保存")
        return 0

    table_name = danmaku_table_name(video_id)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS `{table_name}` (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    bvid VARCHAR(20) NOT NULL,
                    cid BIGINT NOT NULL,
                    dm_date DATE NOT NULL,
                    dm_id BIGINT DEFAULT 0,
                    id_str VARCHAR(50) DEFAULT '',
                    danmaku_key VARCHAR(64) NOT NULL,
                    progress INT DEFAULT 0,
                    mode INT DEFAULT 0,
                    fontsize INT DEFAULT 0,
                    color INT DEFAULT 0,
                    mid_hash VARCHAR(50) DEFAULT '',
                    content TEXT,
                    ctime BIGINT DEFAULT 0,
                    send_time DATETIME DEFAULT NULL,
                    weight INT DEFAULT 0,
                    pool INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_danmaku_key (danmaku_key),
                    INDEX idx_dm_date (dm_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            ensure_danmaku_table_schema(cur, table_name)

            data = []
            seen_keys = set()
            for dm in danmaku_list:
                danmaku_key = make_danmaku_key(dm)
                if danmaku_key in seen_keys:
                    continue
                seen_keys.add(danmaku_key)
                data.append((
                    dm["bvid"], dm["cid"], dm["dm_date"],
                    dm.get("id", 0), dm.get("idStr", ""), danmaku_key,
                    dm.get("progress", 0), dm.get("mode", 0), dm.get("fontsize", 0),
                    dm.get("color", 0), dm.get("midHash", ""), dm.get("content", ""),
                    dm.get("ctime", 0), dm.get("send_time"), dm.get("weight", 0), dm.get("pool", 0),
                ))

            if not data:
                conn.commit()
                return 0

            existing_keys = fetch_existing_danmaku_keys(cur, table_name, seen_keys)
            data = [row for row in data if row[5] not in existing_keys]
            if not data:
                conn.commit()
                return 0

            cur.executemany(f"""
                INSERT IGNORE INTO `{table_name}`
                (bvid, cid, dm_date, dm_id, id_str, danmaku_key, progress, mode, fontsize, color,
                 mid_hash, content, ctime, send_time, weight, pool)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, data)
            inserted_count = cur.rowcount
        conn.commit()
        return inserted_count
    finally:
        conn.close()


def ensure_danmaku_words_table(cur, video_id):
    table_name = danmaku_words_table_name(video_id)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            danmaku_row_id BIGINT NOT NULL,
            dm_id BIGINT NOT NULL DEFAULT 0,
            word_index INT NOT NULL,
            word VARCHAR(100) NOT NULL,
            sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_word (danmaku_row_id, word_index, word),
            INDEX idx_dm_id (dm_id),
            INDEX idx_word (word),
            INDEX idx_sentiment (sentiment)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    return table_name


def table_has_rows(cur, table_name):
    cur.execute(f"SELECT 1 FROM `{table_name}` LIMIT 1")
    return cur.fetchone() is not None


def iter_source_danmaku(cur, video_id, batch_size=1000):
    source_table = danmaku_table_name(video_id)
    if not table_exists(cur, source_table):
        return

    last_id = 0
    while True:
        cur.execute(f"""
            SELECT id, dm_id, content
            FROM `{source_table}`
            WHERE id > %s
              AND content IS NOT NULL
              AND content <> ''
            ORDER BY id
            LIMIT %s
        """, (last_id, batch_size))
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            yield row
            last_id = row["id"] if isinstance(row, dict) else row[0]


def iter_unsegmented_danmaku(cur, video_id, batch_size=1000):
    source_table = danmaku_table_name(video_id)
    words_table = ensure_danmaku_words_table(cur, video_id)
    if not table_exists(cur, source_table):
        return

    last_id = 0
    while True:
        cur.execute(f"""
            SELECT d.id, d.dm_id, d.content
            FROM `{source_table}` AS d
            LEFT JOIN `{words_table}` AS w ON w.danmaku_row_id = d.id
            WHERE d.id > %s
              AND w.id IS NULL
              AND d.content IS NOT NULL
              AND d.content <> ''
            ORDER BY d.id
            LIMIT %s
        """, (last_id, batch_size))
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            yield row
            last_id = row["id"] if isinstance(row, dict) else row[0]


def save_danmaku_words(cur, video_id, rows, chunk_size=1000):
    if not rows:
        return 0
    chunk_size = max(int(chunk_size or 1000), 1)
    table_name = ensure_danmaku_words_table(cur, video_id)
    data = []
    inserted = 0

    def flush_data():
        nonlocal inserted
        if not data:
            return
        cur.executemany(f"""
            INSERT IGNORE INTO `{table_name}`
            (danmaku_row_id, dm_id, word_index, word, sentiment)
            VALUES (%s, %s, %s, %s, %s)
        """, data)
        inserted += cur.rowcount
        data.clear()

    for row in rows:
        for word_index, item in enumerate(row["words"]):
            data.append((
                row["danmaku_row_id"],
                row.get("dm_id") or 0,
                word_index,
                item["word"],
                item["sentiment"],
            ))
            if len(data) >= chunk_size:
                flush_data()

    flush_data()
    return inserted
