"""删除所有 danmaku_words_* 分词表的维护脚本。
Maintenance script for dropping all danmaku_words_* word tables.
"""

import _bootstrap  # noqa: F401

import argparse

import pymysql

from app.db import get_connection


TABLE_PATTERN = "danmaku_words\\_%"


def list_word_tables(cur):
    """列出当前数据库中的所有分词表。
    List all word-segmentation tables in the current database.
    """
    cur.execute(
        """
        SELECT table_name AS name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name LIKE %s
        ORDER BY table_name
        """,
        (TABLE_PATTERN,),
    )
    rows = cur.fetchall()
    tables = []
    for row in rows:
        if isinstance(row, dict):
            tables.append(row.get("name") or row.get("table_name") or row.get("TABLE_NAME"))
        else:
            tables.append(row[0])
    return [table for table in tables if table]


def drop_tables(cur, tables):
    """删除传入的表名列表。
    Drop the provided list of tables.
    """
    for table in tables:
        cur.execute(f"DROP TABLE IF EXISTS `{table}`")


def main():
    """命令行入口，默认只预览，--execute 才真正删除。
    CLI entry; dry-run by default and drops only with --execute.
    """
    parser = argparse.ArgumentParser(description="Delete all danmaku_words_* segmentation tables.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually drop the tables. Without this flag, only prints the matched tables.",
    )
    args = parser.parse_args()

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            tables = list_word_tables(cur)
            if not tables:
                print("No danmaku_words_* tables found.")
                return

            print(f"Found {len(tables)} danmaku_words_* tables:")
            for table in tables:
                print(f"  - {table}")

            if not args.execute:
                print("\nDry run only. Re-run with --execute to drop these tables.")
                return

            drop_tables(cur, tables)
        conn.commit()
        print(f"\nDropped {len(tables)} danmaku_words_* tables.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
