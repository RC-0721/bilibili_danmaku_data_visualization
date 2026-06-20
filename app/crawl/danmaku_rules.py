"""Date-step and danmaku-pool rules for historical crawling."""

from datetime import date, datetime, timedelta

NORMAL_SLEEP_RANGE = (15, 45)
DAYS_PER_VIDEO_PER_RUN = 100
CYCLE_SLEEP_SECONDS = 30 * 60
INITIAL_DATE_STEP_DAYS = 1
DATE_STEP_HALVE_AT = 60
DANMAKU_POOL_RULES = (
    (30, 100),
    (60, 300),
    (180, 500),
    (600, 1000),
    (900, 1500),
    (2400, 3000),
    (3600, 6000),
)
DEFAULT_DANMAKU_POOL_SIZE = 8000
LOW_POOL_RATIO = 0.10
HIGH_POOL_RATIO = 0.60


def daterange(start_date: date, end_date: date):
    for n in range((end_date - start_date).days + 1):
        yield start_date + timedelta(n)


def get_video_start_date(video: dict) -> date:
    pubdate_ts = video["pubdate"]
    if pubdate_ts and pubdate_ts > 0:
        return datetime.fromtimestamp(pubdate_ts).date()
    return date(2009, 6, 24)


def get_video_duration(video: dict) -> int:
    try:
        return max(int(video.get("duration") or 0), 0)
    except (TypeError, ValueError):
        return 0


def get_danmaku_pool_size(duration: int) -> int:
    for max_duration, pool_size in DANMAKU_POOL_RULES:
        if duration <= max_duration:
            return pool_size
    return DEFAULT_DANMAKU_POOL_SIZE


def get_danmaku_thresholds(duration: int) -> tuple[int, int, int]:
    pool_size = get_danmaku_pool_size(duration)
    low_threshold = int(pool_size * LOW_POOL_RATIO)
    high_threshold = int(pool_size * HIGH_POOL_RATIO)
    return pool_size, low_threshold, high_threshold


def normalize_progress_date(value):
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


def get_next_fetch_date(bvid: str, start_date: date, end_date: date, date_step_days: int, get_progress):
    last_progress = get_progress(bvid)
    if last_progress:
        last_progress = normalize_progress_date(last_progress)
        if last_progress >= end_date:
            return end_date + timedelta(days=1)
        next_date = max(last_progress + timedelta(days=date_step_days), start_date)
        return min(next_date, end_date)
    return start_date


def adjust_date_step(bvid: str, new_count: int, date_steps: dict, duration: int) -> int:
    current_step = date_steps.get(bvid, INITIAL_DATE_STEP_DAYS)
    pool_size, low_threshold, high_threshold = get_danmaku_thresholds(duration)

    if new_count <= low_threshold:
        next_step = min(current_step + 1, DATE_STEP_HALVE_AT)
    elif current_step != INITIAL_DATE_STEP_DAYS and new_count >= high_threshold:
        next_step = max(current_step // 2, INITIAL_DATE_STEP_DAYS)
    else:
        next_step = current_step

    date_steps[bvid] = next_step
    if next_step != current_step:
        print(
            f"  新增 {new_count} 条，弹幕池 {pool_size} "
            f"(低阈值 {low_threshold}, 高阈值 {high_threshold})，"
            f"日期步长 {current_step} -> {next_step} 天"
        )
    return next_step
