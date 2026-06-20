"""简单查询工具：统计每个视频已入库弹幕数量。
Simple query tool for counting stored danmaku per video.
"""

import _bootstrap  # noqa: F401

import pymysql
from app.db import get_connection, get_videos

def get_danmaku_count(video_id):
    """
    查询指定视频的弹幕表数据量
    如果表不存在则返回 0

    Count rows in the per-video danmaku table.
    Return 0 if the table does not exist.
    """
    table_name = f"video_{video_id}_danmaku_history"
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 先检查表是否存在
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE() AND table_name = %s
            """, (table_name,))
            if cur.fetchone()[0] == 0:
                return 0
            # 存在则统计行数
            cur.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            return cur.fetchone()[0]
    finally:
        conn.close()

def main():
    """打印所有视频的弹幕入库数量。
    Print stored danmaku count for all videos.
    """
    videos = get_videos()   # 获取所有视频基本信息
    if not videos:
        print("暂无视频数据。")
        return

    print("视频弹幕数量统计：")
    total = 0
    for v in videos:
        bvid = v["bvid"]
        # 需要先通过 bvid 查询视频的 id
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM precious_videos WHERE bvid = %s", (bvid,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            print(f"{bvid}: 视频ID未找到")
            continue
        video_id = row[0]
        count = get_danmaku_count(video_id)
        print(f"{bvid}: {count} 条弹幕")
        total += count

    print(f"\n所有视频弹幕总数: {total} 条")

if __name__ == "__main__":
    main()
