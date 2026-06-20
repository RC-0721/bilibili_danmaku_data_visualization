# Bilibili Danmaku Data Visualization

一个面向 B 站视频弹幕数据的采集、分析与可视化项目。项目围绕入站必刷视频构建数据集，支持历史弹幕抓取、弹幕去重、中文分词、词云统计、高能片段识别、播放进度与日期二维热力图、视频相似度矩阵、平行坐标图以及 Tableau 辅助制图数据导出。

## 功能概览

- 视频元数据导入：从 B 站入站必刷接口 JSON 中导入视频信息。
- 历史弹幕抓取：支持断点续抓、限流冷却、按视频进度记录抓取状态。
- 数据清理：提供重复弹幕清理、自增 id 重排、分词表删除等维护脚本。
- 文本处理：使用 `pkuseg` 分词，支持停用词、过滤词、自定义词典和短语 alias。
- 预聚合统计：构建词云统计表、高能窗口表、相似度矩阵和平行坐标统计表。
- Web 可视化：基于 Vue 与 ECharts 展示趋势图、词云、热力图、相似度矩阵、平行坐标图和悬浮视频播放器。
- Tableau 数据准备：导出综合画像散点气泡图、互动指标对比图和雷达图所需 CSV。

## 技术栈

- 后端：Python、pymysql、requests、protobuf
- 文本处理：pkuseg、大连理工大学情感词汇本体库
- 数据库：MySQL
- 前端：Vue、Apache ECharts、echarts-wordcloud
- 外部制图：Tableau Public 或 Tableau Desktop

## 项目结构

```text
.
├── api_server.py              # 后端 API 与静态前端入口
├── requirements.txt           # Python 依赖
├── app/                       # 核心业务模块
│   ├── api/                   # API 路由与查询逻辑
│   ├── analysis/              # 高能窗口等分析逻辑
│   ├── crawl/                 # 弹幕抓取客户端与调度逻辑
│   ├── review/                # 半自动词典维护逻辑
│   └── text/                  # 分词、alias、情绪词典逻辑
├── scripts/                   # 可直接运行的数据处理脚本
├── frontend/                  # 静态前端页面和图表模块
├── resources/text/            # 停用词、过滤词、alias 等文本资源
├── custom_words/              # 每个视频的自定义词典
├── review_candidates/         # 人工审核候选词表
├── data/                      # 本地输入数据
├── tableau_exports/           # Tableau CSV 导出目录
└── docs/                      # 详细运行说明
```

## 快速开始

1. 安装依赖：

```powershell
pip install -r requirements.txt
```

2. 配置本地参数：

打开 `app/config.py`，按提示填写本地 MySQL 连接信息、B 站 Cookie 和弹幕抓取截止日期。仓库中的配置文件只保留占位提示，不包含可直接使用的账号凭据。

3. 准备视频接口数据：

将 `https://api.bilibili.com/x/web-interface/popular/precious` 返回的完整 JSON 保存为 `data/precious.txt`。

4. 初始化数据流程：

```powershell
python scripts\fetch_videos.py
python scripts\fetch_danmaku.py
python scripts\clean_duplicate_danmaku.py
python scripts\build_video_custom_words.py
python scripts\build_danmaku_words.py --batch-size 300
python scripts\build_word_cloud_stats.py --batch-days 7
python scripts\build_high_energy_windows.py --window-seconds 5
python scripts\build_video_similarity_matrix.py --execute
python scripts\build_video_parallel_stats.py --execute
```

5. 启动 Web 服务：

```powershell
python api_server.py
```

默认访问地址：

```text
http://127.0.0.1:8000
```

## 常用脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/fetch_videos.py` | 从 `data/precious.txt` 导入视频信息 |
| `scripts/fetch_danmaku.py` | 抓取历史弹幕 |
| `scripts/clean_duplicate_danmaku.py` | 清理重复弹幕 |
| `scripts/build_video_custom_words.py` | 为已完成抓取的视频生成自定义词典 |
| `scripts/build_danmaku_words.py` | 构建分词表 |
| `scripts/build_word_cloud_stats.py` | 构建词云预聚合表 |
| `scripts/build_high_energy_windows.py` | 构建高能片段统计表 |
| `scripts/build_video_similarity_matrix.py` | 构建视频相似度矩阵 |
| `scripts/build_video_parallel_stats.py` | 构建平行坐标图统计表 |

完整参数说明见 [docs/Readme.md](docs/Readme.md)。

## 文档

- [项目运行说明](docs/Readme.md)
