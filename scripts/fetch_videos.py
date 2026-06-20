"""从本地 precious.txt 导入 B 站入站必刷视频列表。
Import Bilibili popular/precious videos from local precious.txt.
"""

import _bootstrap  # noqa: F401

import json
from pathlib import Path
from app.db import init_db, save_videos
from app.paths import PROJECT_ROOT

PRECIOUS_FILE = PROJECT_ROOT / "data" / "precious.txt"


def load_precious_videos(file_path: Path = PRECIOUS_FILE):
    """从本地 precious.txt 读取入站必刷页面保存的 JSON，返回视频列表。
    Read saved JSON from precious.txt and return the video list.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"找不到本地文件: {file_path}")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{file_path} 不是有效的 JSON: {e}") from e

    if data.get("code") != 0:
        raise RuntimeError(f"入站必刷数据错误: code={data.get('code')}, message={data.get('message')}")

    videos = data.get("data", {}).get("list")
    if not isinstance(videos, list):
        raise RuntimeError("入站必刷数据缺少 data.list 视频列表")

    return videos

if __name__ == "__main__":
    print("初始化数据库表...")
    init_db()
    print(f"正在从本地文件读取入站必刷视频列表: {PRECIOUS_FILE}")
    videos = load_precious_videos()
    print(f"共读取 {len(videos)} 个视频，正在存入数据库...")
    save_videos(videos)
    print("视频信息已更新。")
