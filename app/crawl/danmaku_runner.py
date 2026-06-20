"""Main historical danmaku crawling loop."""

import random
import time
from datetime import datetime, timedelta

import requests

from app.crawl.danmaku_client import fetch_protobuf_danmaku, parse_danmaku, timestamp_to_datetime
from app.crawl.danmaku_rules import (
    CYCLE_SLEEP_SECONDS,
    DAYS_PER_VIDEO_PER_RUN,
    INITIAL_DATE_STEP_DAYS,
    NORMAL_SLEEP_RANGE,
    adjust_date_step,
    get_danmaku_thresholds,
    get_video_duration,
    get_video_start_date,
    normalize_progress_date,
)
from app.config import END_DATE
from app.db import (
    get_date_step,
    get_progress,
    get_videos,
    init_progress_table,
    save_danmaku_list,
    update_date_step,
    update_progress,
)


def fetch_one_video_day(video: dict, idx: int, total: int, end_date, date_steps: dict) -> bool:
    bvid = video["bvid"]
    cid = video["cid"]
    start_date = get_video_start_date(video)
    duration = get_video_duration(video)
    pool_size, _, _ = get_danmaku_thresholds(duration)
    current_step = date_steps.get(bvid, INITIAL_DATE_STEP_DAYS)
    last_progress = normalize_progress_date(get_progress(bvid))

    if last_progress:
        if last_progress >= end_date:
            print(f"[{idx}/{total}] {bvid}: 已全部抓取完毕，跳过")
            return False
        fetch_date = min(max(last_progress + timedelta(days=current_step), start_date), end_date)
    else:
        fetch_date = start_date

    rolled_back = False
    while True:
        if fetch_date > end_date:
            print(f"[{idx}/{total}] {bvid}: 已全部抓取完毕，跳过")
            return False

        date_str = fetch_date.strftime("%Y-%m-%d")
        print(f"[{idx}/{total}] {bvid}: 抓取 {date_str} (日期步长 {current_step} 天, 弹幕池 {pool_size})")

        try:
            raw = fetch_protobuf_danmaku(cid, date_str)
            danmaku_list = parse_danmaku(raw)
            returned_count = len(danmaku_list)
            for dm in danmaku_list:
                dm["bvid"] = bvid
                dm["cid"] = cid
                dm["dm_date"] = date_str
                dm["send_time"] = timestamp_to_datetime(dm.get("ctime", 0))
            new_count = save_danmaku_list(danmaku_list) if danmaku_list else 0

            if new_count >= pool_size:
                next_date = handle_full_pool(bvid, start_date, fetch_date, last_progress, current_step, date_steps)
                if next_date is None:
                    update_progress(bvid, date_str, INITIAL_DATE_STEP_DAYS)
                    return True
                current_step = date_steps[bvid]
                fetch_date = next_date
                rolled_back = True
                continue

            if rolled_back:
                next_step = INITIAL_DATE_STEP_DAYS
                date_steps[bvid] = next_step
                if current_step != next_step:
                    print(f"  回滚后返回 {returned_count} 条，新增 {new_count} 条，新增数未达弹幕池上限，日期步长重置为 1 天")
            else:
                next_step = adjust_date_step(bvid, new_count, date_steps, duration)

            update_progress(bvid, date_str, next_step)
            message = f"返回 {returned_count} 条，新增 {new_count} 条" if danmaku_list else "无弹幕"
            print(f"  {date_str}:  {message}，进度已更新")
            return True

        except requests.HTTPError as exc:
            if exc.response.status_code in (404, 400):
                next_step = INITIAL_DATE_STEP_DAYS if rolled_back else adjust_date_step(bvid, 0, date_steps, duration)
                date_steps[bvid] = next_step
                update_progress(bvid, date_str, next_step)
                print(f"  {date_str}:  无数据或请求无效，进度已更新")
                return True
            print(f"  {date_str}:  请求失败 ({exc})")
        except Exception as exc:
            print(f"  {date_str}:  错误: {exc}")

        return True


def handle_full_pool(bvid, start_date, fetch_date, last_progress, current_step, date_steps):
    print(f"  新增数达到弹幕池上限，暂不推进进度")
    if current_step != INITIAL_DATE_STEP_DAYS:
        next_step = max(current_step // 2, INITIAL_DATE_STEP_DAYS)
        rollback_date = max(start_date, fetch_date - timedelta(days=next_step))
        print(f"  满池回滚: 日期 {fetch_date} -> {rollback_date}, 步长 {current_step} -> {next_step}")
        date_steps[bvid] = next_step
        update_date_step(bvid, next_step)
        return rollback_date

    rollback_date = fetch_date - timedelta(days=1)
    if rollback_date < start_date:
        print("  已到视频发布日期，无法继续回滚；按步长 1 推进当前满池日期")
        date_steps[bvid] = INITIAL_DATE_STEP_DAYS
        return None
    if last_progress and rollback_date <= last_progress:
        print("  回滚日期已不晚于数据库断点，无法继续拆分；按步长 1 推进当前满池日期")
        date_steps[bvid] = INITIAL_DATE_STEP_DAYS
        return None

    print(f"  步长已为 1 且新增数仍满池，日期回滚一天: {fetch_date} -> {rollback_date}")
    date_steps[bvid] = INITIAL_DATE_STEP_DAYS
    update_date_step(bvid, INITIAL_DATE_STEP_DAYS)
    return rollback_date


def main():
    end_date = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    print(f"弹幕抓取截止日期: {end_date}")
    init_progress_table()
    all_videos = get_videos()
    if not all_videos:
        print("数据库中没有视频，请先运行 fetch_videos.py")
        return

    videos, completed_count = select_pending_videos(all_videos, end_date)
    if not videos:
        print("所有视频都已抓取到截止日期，本次没有需要抓取的任务。")
        return

    print(f"共 {len(all_videos)} 个视频，其中 {completed_count} 个已到截止日期，剩余 {len(videos)} 个进入抓取任务。")
    date_steps = {video["bvid"]: get_date_step(video["bvid"], INITIAL_DATE_STEP_DAYS) for video in videos}
    print(f"已从 danmaku_progress 读取 {len(date_steps)} 个视频的日期步长")
    run_cycles(videos, end_date, date_steps)


def select_pending_videos(all_videos, end_date):
    videos = []
    completed_count = 0
    for video in all_videos:
        last_progress = normalize_progress_date(get_progress(video["bvid"]))
        if last_progress and last_progress >= end_date:
            completed_count += 1
            continue
        videos.append(video)
    return videos, completed_count


def run_cycles(videos, end_date, date_steps):
    cycle_no = 1
    while True:
        cycle_processed = run_one_cycle(videos, end_date, date_steps, cycle_no)
        if cycle_processed == 0:
            print("\n全部视频都已抓取到截止日期。")
            print("全部弹幕抓取完成。")
            return
        print(f"\n第 {cycle_no} 个周期顺利完成，共处理 {cycle_processed} 个日期；休息 {CYCLE_SLEEP_SECONDS // 60} 分钟后继续。")
        time.sleep(CYCLE_SLEEP_SECONDS)
        cycle_no += 1


def run_one_cycle(videos, end_date, date_steps, cycle_no):
    cycle_processed = 0
    fetch_counts = {video["bvid"]: 0 for video in videos}
    finished_bvids = set()
    indexed_videos = list(enumerate(videos, 1))
    print(f"\n===== 开始第 {cycle_no} 个周期：随机选择视频抓取，每个视频最多 {DAYS_PER_VIDEO_PER_RUN} 次 =====")

    while True:
        candidates = [
            (idx, video)
            for idx, video in indexed_videos
            if video["bvid"] not in finished_bvids and fetch_counts[video["bvid"]] < DAYS_PER_VIDEO_PER_RUN
        ]
        if not candidates:
            return cycle_processed

        idx, video = random.choice(candidates)
        bvid = video["bvid"]
        print(f"  本周期 {bvid} 已抓取 {fetch_counts[bvid]}/{DAYS_PER_VIDEO_PER_RUN} 次")
        processed = fetch_one_video_day(video, idx, len(videos), end_date, date_steps)
        if not processed:
            finished_bvids.add(bvid)
            continue
        fetch_counts[bvid] += 1
        cycle_processed += 1
        time.sleep(random.uniform(*NORMAL_SLEEP_RANGE))
