"""计算已获取弹幕数量与视频原始弹幕总数的覆盖率。
Compute coverage between fetched danmaku count and original video danmaku count.
"""

import _bootstrap  # noqa: F401

from app.db import get_connection


def table_exists(cur, table_name):
    """检查统计目标表是否存在。
    Check whether the target table exists.
    """
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
    """, (table_name,))
    return cur.fetchone()[0] > 0


def get_table_count(cur, table_name):
    """读取单个弹幕历史表的行数。
    Read row count from one danmaku history table.
    """
    if not table_exists(cur, table_name):
        return 0

    cur.execute(f"SELECT COUNT(*) FROM `{table_name}`")
    return int(cur.fetchone()[0] or 0)


def format_percent(fetched_count, total_count):
    if not total_count:
        return "N/A"
    return f"{fetched_count / total_count * 100:.2f}%"


def main():
    """打印每个视频及总体的弹幕覆盖率。
    Print danmaku coverage for each video and overall.
    """
    conn = get_connection()
    total_fetched = 0
    total_original = 0

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, bvid, title, stat_danmaku
                FROM precious_videos
                ORDER BY id
            """)
            videos = cur.fetchall()

            if not videos:
                print("暂无视频数据。")
                return

            print("弹幕获取覆盖率：")
            print("-" * 96)
            print(f"{'ID':>4}  {'BVID':<14}  {'已获取':>10}  {'原总数':>10}  {'覆盖率':>10}  标题")
            print("-" * 96)

            for video_id, bvid, title, stat_danmaku in videos:
                table_name = f"video_{video_id}_danmaku_history"
                fetched_count = get_table_count(cur, table_name)
                original_count = int(stat_danmaku or 0)
                percent = format_percent(fetched_count, original_count)

                total_fetched += fetched_count
                total_original += original_count

                title = title or ""
                if len(title) > 32:
                    title = title[:32] + "..."

                print(
                    f"{video_id:>4}  {bvid:<14}  {fetched_count:>10}  "
                    f"{original_count:>10}  {percent:>10}  {title}"
                )

            print("-" * 96)
            print(
                f"合计: 已获取 {total_fetched} 条 / 原总数 {total_original} 条，"
                f"覆盖率 {format_percent(total_fetched, total_original)}"
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
