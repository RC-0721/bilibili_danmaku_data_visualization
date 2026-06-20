"""测试指定视频的分词效果，不写入数据库。
Test segmentation for one video without writing to the database.
"""

import _bootstrap  # noqa: F401

import argparse

import pymysql

from app.db import danmaku_table_name, get_connection, table_exists
from app.paths import CUSTOM_WORDS_DIR
from app.text.segmentation import segment_text


DEFAULT_BVID = "BV1BK411L7DJ"


def get_video(cur, bvid):
    """读取视频内部 id 和标题。
    Read internal video id and title.
    """
    cur.execute("""
        SELECT id, bvid, title
        FROM precious_videos
        WHERE bvid = %s
    """, (bvid,))
    return cur.fetchone()


def fetch_sample_contents(cur, video_id, limit):
    """读取少量弹幕文本用于分词测试。
    Read a small number of danmaku texts for segmentation testing.
    """
    table_name = danmaku_table_name(video_id)
    if not table_exists(cur, table_name):
        return []

    cur.execute(f"""
        SELECT content
        FROM `{table_name}`
        WHERE content IS NOT NULL
          AND TRIM(content) <> ''
        ORDER BY id
        LIMIT %s
    """, (limit,))
    return [row["content"] for row in cur.fetchall()]


def print_segmented(content, words):
    """打印单条弹幕及其分词结果。
    Print one danmaku text and its segmented words.
    """
    rendered = " / ".join(f"{item['word']}[{item['sentiment']}]" for item in words)
    print(f"原文: {content}")
    print(f"分词: {rendered or '(无有效词)'}")
    print("-" * 80)


def inspect_custom_words(bvid, preview_limit):
    """检查并打印当前视频的 custom_words 词典状态。
    Inspect and print custom_words dictionary status for the current video.
    """
    path = CUSTOM_WORDS_DIR / f"{bvid}.txt"
    if not path.exists():
        print(f"用户词典: 未找到 {path}")
        return

    words = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    print(f"用户词典: {path}")
    print(f"用户词典词条数: {len(words)}")
    if words and preview_limit > 0:
        print("用户词典预览:")
        for word in words[:preview_limit]:
            print(f"  - {word}")


def main():
    parser = argparse.ArgumentParser(description="测试 BV1BK411L7DJ 的 pkuseg 分词效果")
    parser.add_argument("--bvid", default=DEFAULT_BVID, help=f"测试视频 bvid，默认 {DEFAULT_BVID}")
    parser.add_argument("--limit", type=int, default=200, help="测试弹幕条数")
    parser.add_argument("--text", help="直接测试一条文本，不读取数据库")
    parser.add_argument("--dict-preview", type=int, default=10, help="用户词典预览词条数，设为 0 不预览")
    args = parser.parse_args()

    inspect_custom_words(args.bvid, args.dict_preview)
    print("-" * 80)

    if args.text:
        print_segmented(args.text, segment_text(args.text, bvid=args.bvid))
        return

    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            video = get_video(cur, args.bvid)
            if not video:
                print(f"未找到视频: {args.bvid}")
                return

            print(f"测试视频: {video['bvid']} - {video['title']}")
            print(f"测试条数: {args.limit}")
            print("-" * 80)

            contents = fetch_sample_contents(cur, video["id"], args.limit)
            if not contents:
                print("未读取到可测试的弹幕。")
                return

            for content in contents:
                words = segment_text(content, bvid=args.bvid)
                print_segmented(content, words)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
