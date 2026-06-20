"""项目配置：数据库、请求头、Cookie 和抓取截止日期。
Project configuration: database, request headers, cookie, and crawl end date.
"""

# 数据库连接配置。
# Database connection settings.
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "请填写本地 MySQL 用户名"
DB_PASSWORD = "请填写本地 MySQL 密码"
DB_NAME = "请填写本地数据库名"

# B 站请求 Cookie，用于弹幕接口鉴权。
# Bilibili request cookie used for danmaku API authorization.
COOKIE = (
    "请填写从浏览器复制的 B 站 Cookie；"
    "至少应包含 SESSDATA、bili_jct、DedeUserID 等必要字段"
)

# 通用 HTTP 请求头。
# Shared HTTP request headers.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Cookie": COOKIE,
    "Referer": "https://www.bilibili.com/",
}

# 弹幕抓取截止日期（包含该日）
# Danmaku crawl end date, inclusive.
END_DATE = "2026-05-10"
