"""清理弹幕历史表中的重复记录并维护自增 ID。
Clean duplicate rows in danmaku history tables and maintain auto-increment IDs.
"""

import _bootstrap  # noqa: F401

import argparse
import time

from app.db import get_connection, ensure_danmaku_table_schema


def get_danmaku_tables(cur):
    """查找所有 video_*_danmaku_history 表。
    Find all video_*_danmaku_history tables.
    """
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name LIKE 'video\\_%\\_danmaku\\_history'
        ORDER BY table_name
    """)
    return [row[0] for row in cur.fetchall()]


def get_duplicate_stats(cur, table_name):
    """统计指定表的重复组和重复行数量。
    Count duplicate groups and duplicate rows in a table.
    """
    cur.execute(f"""
        SELECT
            COUNT(*) AS duplicate_groups,
            COALESCE(SUM(group_count - 1), 0) AS duplicate_rows
        FROM (
            SELECT danmaku_key, COUNT(*) AS group_count
            FROM `{table_name}`
            WHERE danmaku_key IS NOT NULL AND danmaku_key <> ''
            GROUP BY danmaku_key
            HAVING COUNT(*) > 1
        ) AS grouped
    """)
    row = cur.fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def delete_duplicates(cur, table_name):
    """按 danmaku_key 删除重复行，只保留最小 id。
    Delete duplicate rows by danmaku_key, keeping the smallest id.
    """
    cur.execute(f"""
        DELETE target
        FROM `{table_name}` AS target
        JOIN (
            SELECT danmaku_key, MIN(id) AS keep_id
            FROM `{table_name}`
            WHERE danmaku_key IS NOT NULL AND danmaku_key <> ''
            GROUP BY danmaku_key
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
        ON target.danmaku_key = duplicate_groups.danmaku_key
       AND target.id <> duplicate_groups.keep_id
    """)
    return cur.rowcount


def add_unique_index(cur, table_name):
    cur.execute(f"SHOW INDEX FROM `{table_name}` WHERE Key_name = 'unique_danmaku_key'")
    if cur.fetchone() is not None:
        return False

    cur.execute(f"CREATE UNIQUE INDEX unique_danmaku_key ON `{table_name}` (danmaku_key)")
    return True


def reset_auto_increment(cur, table_name):
    cur.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM `{table_name}`")
    next_id = int(cur.fetchone()[0] or 1)
    cur.execute(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = {next_id}")
    return next_id


def resequence_ids(cur, table_name):
    """重建表以连续化已有行的自增 id。
    Rebuild the table to resequence existing auto-increment IDs.
    """
    suffix = int(time.time() * 1000)
    tmp_table = f"{table_name}_resequence_{suffix}"
    old_table = f"{table_name}_old_{suffix}"

    cur.execute(f"CREATE TABLE `{tmp_table}` LIKE `{table_name}`")
    cur.execute(f"ALTER TABLE `{tmp_table}` AUTO_INCREMENT = 1")
    cur.execute(f"""
        INSERT INTO `{tmp_table}` (
            bvid, cid, dm_date, dm_id, id_str, danmaku_key,
            progress, mode, fontsize, color, mid_hash, content,
            ctime, send_time, weight, pool, created_at
        )
        SELECT
            bvid, cid, dm_date, dm_id, id_str, danmaku_key,
            progress, mode, fontsize, color, mid_hash, content,
            ctime, send_time, weight, pool, created_at
        FROM `{table_name}`
        ORDER BY id
    """)
    cur.execute(f"RENAME TABLE `{table_name}` TO `{old_table}`, `{tmp_table}` TO `{table_name}`")
    cur.execute(f"DROP TABLE `{old_table}`")
    cur.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM `{table_name}`")
    return int(cur.fetchone()[0] or 1)


def main():
    parser = argparse.ArgumentParser(description="清理各视频弹幕历史表中的重复弹幕")
    parser.add_argument("--execute", action="store_true", help="实际删除重复行；默认只统计")
    parser.add_argument(
        "--add-unique-index",
        action="store_true",
        help="删除重复行后为 danmaku_key 添加唯一索引",
    )
    parser.add_argument(
        "--reset-auto-increment",
        action="store_true",
        help="清理后将每张表的下一个自增 id 重置为 MAX(id) + 1",
    )
    parser.add_argument(
        "--resequence-ids",
        action="store_true",
        help="清理后重建每张表，将已有行 id 从 1 开始连续重排",
    )
    args = parser.parse_args()

    if args.resequence_ids and not args.execute:
        parser.error("--resequence-ids 必须和 --execute 一起使用")

    conn = get_connection()
    total_duplicate_groups = 0
    total_duplicate_rows = 0
    total_deleted_rows = 0
    total_unique_indexes = 0
    total_reset_tables = 0

    try:
        with conn.cursor() as cur:
            tables = get_danmaku_tables(cur)
            if not tables:
                print("未找到 video_*_danmaku_history 表。")
                return

            print(f"找到 {len(tables)} 张弹幕表。")
            if not args.execute:
                print("当前为预览模式，不会删除数据。确认无误后使用 --execute 执行清理。")

            for table_name in tables:
                ensure_danmaku_table_schema(cur, table_name)
                duplicate_groups, duplicate_rows = get_duplicate_stats(cur, table_name)
                total_duplicate_groups += duplicate_groups
                total_duplicate_rows += duplicate_rows

                if duplicate_rows == 0:
                    print(f"{table_name}: 无重复")
                else:
                    print(f"{table_name}: 重复组 {duplicate_groups} 个，待删除 {duplicate_rows} 行")

                if not args.execute:
                    continue

                if duplicate_rows > 0:
                    deleted_rows = delete_duplicates(cur, table_name)
                    total_deleted_rows += deleted_rows
                    print(f"{table_name}: 已删除 {deleted_rows} 行")

                if args.resequence_ids:
                    next_id = resequence_ids(cur, table_name)
                    total_reset_tables += 1
                    print(f"{table_name}: 已重排已有行 id，下一自增 id = {next_id}")
                elif args.reset_auto_increment:
                    next_id = reset_auto_increment(cur, table_name)
                    total_reset_tables += 1
                    print(f"{table_name}: 自增 id 已重置，下一自增 id = {next_id}")

                if args.add_unique_index:
                    added = add_unique_index(cur, table_name)
                    if added:
                        total_unique_indexes += 1
                        print(f"{table_name}: 已添加 unique_danmaku_key 唯一索引")

            if args.execute:
                conn.commit()
            else:
                conn.rollback()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("\n汇总：")
    print(f"重复组: {total_duplicate_groups}")
    print(f"重复行: {total_duplicate_rows}")
    if args.execute:
        print(f"已删除: {total_deleted_rows}")
        if args.reset_auto_increment or args.resequence_ids:
            print(f"重置 id 表数: {total_reset_tables}")
        if args.add_unique_index:
            print(f"新增唯一索引: {total_unique_indexes}")


if __name__ == "__main__":
    main()
