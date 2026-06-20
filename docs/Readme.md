# Bilibili Danmaku Data Visualization

本文档记录当前项目结构、运行流程、脚本入口和常用参数。根目录只保留入口和说明文件；批处理脚本统一放在 `scripts/`，业务模块统一放在 `app/`。

## 运行前准备

1. 在 `app/config.py` 中按占位提示填写本地数据库连接、B 站 Cookie、`END_DATE`。
2. 安装依赖：

```powershell
pip install -r requirements.txt
```

3. 分词功能使用 `pkuseg`。如果当前虚拟环境无法安装，请切换到本地 Python 3.8 环境后运行分词相关脚本。
4. 入站必刷接口保存文件应放在 `data/precious.txt`。

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `api_server.py` | 后端 API 和静态前端服务入口 |
| `Readme.md` | 项目运行说明 |
| `requirements.txt` | Python 依赖 |
| `app/config.py` | 数据库、Cookie、请求头、抓取截止日期配置 |
| `app/db.py` | 数据库访问聚合入口 |
| `app/api/` | 后端 API 模块 |
| `app/analysis/` | 高能窗口等分析构建逻辑 |
| `app/crawl/` | 弹幕抓取客户端、步长规则和调度逻辑 |
| `app/review/` | 半自动词典维护候选生成逻辑 |
| `app/text/` | 分词、短语别名、情绪词典逻辑 |
| `scripts/` | 可直接运行的脚本入口 |
| `frontend/` | 静态前端页面、JS 模块、CSS 模块和本地 vendor |
| `resources/text/` | `stopwords`、`filtered_words`、`phrase_aliases` 等文本资源 |
| `custom_words/` | 每个视频的 pkuseg 用户词典 |
| `review_candidates/` | 半自动词典维护候选 TSV |
| `data/` | 本地数据输入文件，例如 `precious.txt` |
| `logs/` | 运行日志 |
| `backups/` | 脚本自动生成的备份文件 |
| `words/` | 大连理工大学情感词汇本体库文件 |

## 推荐流程

```powershell
python scripts\fetch_videos.py
python scripts\fetch_danmaku.py
python scripts\clean_duplicate_danmaku.py
python scripts\clean_duplicate_danmaku.py --execute --add-unique-index
python scripts\build_video_custom_words.py
python scripts\build_danmaku_words.py --batch-size 300
python scripts\build_word_cloud_stats.py --batch-days 7
python scripts\build_high_energy_windows.py --window-seconds 5
python scripts\build_video_similarity_matrix.py --execute
python scripts\build_video_parallel_stats.py --execute
python api_server.py
```

`clean_duplicate_danmaku.py --execute` 会修改数据库，建议先运行无参数命令预览。

## 数据导入与抓取

### `scripts\fetch_videos.py`

从 `data/precious.txt` 读取 B 站入站必刷接口 JSON，写入 `precious_videos` 表。

```powershell
python scripts\fetch_videos.py
```

前置条件：
- `data/precious.txt` 为 `https://api.bilibili.com/x/web-interface/popular/precious` 返回的完整 JSON。

### `scripts\fetch_danmaku.py`

按数据库视频列表抓取历史弹幕，写入每个视频的 `video_{id}_danmaku_history` 表。

```powershell
python scripts\fetch_danmaku.py
```

主要配置：

| 配置 | 位置 | 说明 |
| --- | --- | --- |
| `END_DATE` | `app/config.py` | 抓取截止日期，包含该日 |
| `RATE_LIMIT_COOLDOWN_SECONDS` | `app/crawl/danmaku_client.py` | 触发 `-702` 后固定等待秒数 |
| `NORMAL_SLEEP_RANGE` | `app/crawl/danmaku_rules.py` | 正常请求后的随机等待区间 |
| `DAYS_PER_VIDEO_PER_RUN` | `app/crawl/danmaku_rules.py` | 每周期单个视频最多抓取次数 |
| `CYCLE_SLEEP_SECONDS` | `app/crawl/danmaku_rules.py` | 一个周期结束后的休息时间 |
| `DATE_STEP_HALVE_AT` | `app/crawl/danmaku_rules.py` | 日期步长上限 |

说明：
- 已抓取到 `END_DATE` 的视频会跳过。
- 抓取断点和日期步长保存在 `danmaku_progress`。
- 触发 B 站限流后会固定等待 5000 秒并继续任务。

## 数据维护

### `scripts\clean_duplicate_danmaku.py`

清理所有 `video_*_danmaku_history` 表中的重复弹幕。

```powershell
python scripts\clean_duplicate_danmaku.py
python scripts\clean_duplicate_danmaku.py --execute
python scripts\clean_duplicate_danmaku.py --execute --add-unique-index
python scripts\clean_duplicate_danmaku.py --execute --reset-auto-increment
python scripts\clean_duplicate_danmaku.py --execute --resequence-ids
```

| 参数 | 说明 |
| --- | --- |
| `--execute` | 实际删除重复行；不加时只统计 |
| `--add-unique-index` | 清理后为弹幕唯一键添加唯一索引 |
| `--reset-auto-increment` | 将下一条自增 id 重置为 `MAX(id) + 1` |
| `--resequence-ids` | 重建表并将已有行 id 从 1 开始连续重排 |

`--resequence-ids` 会改变已有行 id，如果其他表依赖旧 id，应谨慎使用。

### `scripts\drop_danmaku_words_tables.py`

删除所有 `danmaku_words_*` 分词表，用于调整分词策略后重建。

```powershell
python scripts\drop_danmaku_words_tables.py
python scripts\drop_danmaku_words_tables.py --execute
```

| 参数 | 说明 |
| --- | --- |
| `--execute` | 实际删除分词表；不加时只打印表名 |

## 分词与词典

### `scripts\build_video_custom_words.py`

按视频统计高频完整弹幕，写入 `custom_words/{bvid}.txt`。

```powershell
python scripts\build_video_custom_words.py
python scripts\build_video_custom_words.py --bvid BV1BK411L7DJ
python scripts\build_video_custom_words.py --dry-run
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | 无 | 只处理指定视频 |
| `--limit` | `500` | 完整弹幕出现次数阈值 |
| `--output-dir` | `custom_words` | 视频词典输出目录 |
| `--min-length` | `2` | 最短短语长度 |
| `--max-length` | `50` | 最长短语长度；`0` 表示不限制 |
| `--dry-run` | 关闭 | 只预览，不写入 |

说明：
- 未抓取到 `END_DATE` 的视频会跳过。
- 已存在 `custom_words/{bvid}.txt` 时会跳过，避免覆盖手工维护内容。
- `resources/text/filtered_words.txt` 中的词不会进入用户词典。

### `scripts\build_danmaku_words.py`

使用 pkuseg 对已入库弹幕分词，写入 `danmaku_words_{video_id}` 表。

```powershell
python scripts\build_danmaku_words.py --batch-size 300
python scripts\build_danmaku_words.py --bvid BV1BK411L7DJ --batch-size 300
python scripts\build_danmaku_words.py --batch-size 100 --cache-size 10000
python scripts\build_danmaku_words.py --cache-size 0
```

低磁盘压力模式：

```powershell
python scripts\build_danmaku_words.py --batch-size 100 --insert-chunk-size 200 --commit-every-batches 5 --io-sleep 1 --max-danmaku-per-video 20000
```

低磁盘压力自动循环：

```powershell
python scripts\build_danmaku_words.py --batch-size 100 --insert-chunk-size 200 --commit-every-batches 5 --io-sleep 1 --max-danmaku-per-video 20000 --loop --loop-sleep 5
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | 无 | 只处理指定视频 |
| `--batch-size` | `300` | 批量读取弹幕数量 |
| `--insert-chunk-size` | `500` | 单次 `executemany` 写入词条数 |
| `--cache-size` | `100000` | 当前视频内分词缓存大小；`0` 表示关闭 |
| `--commit-every-batches` | `20` | 每多少个弹幕批次提交一次事务 |
| `--io-sleep` | `0.2` | 每次分段提交后暂停秒数 |
| `--max-danmaku-per-video` | `0` | 单视频本轮最多处理弹幕数；`0` 表示不限 |
| `--max-videos` | `0` | 本轮最多处理视频数；`0` 表示不限 |
| `--force-resumable-scan` | 关闭 | 强制使用断点扫描 |
| `--loop` | 关闭 | 一轮结束后自动继续下一轮 |
| `--loop-sleep` | `0` | 每轮结束后暂停秒数 |

说明：
- 默认只处理已抓取完成的视频。
- 已写入分词表的弹幕不会重复处理。
- 分词会读取 `custom_words/{bvid}.txt`、`resources/text/filtered_words.txt`、`resources/text/phrase_aliases.txt`。
- 情绪标签来自 `words/words/words.xlsx`，输出为 `positive`、`neutral`、`negative`。

### `scripts\test_segmentation_bv1bk411l7dj.py`

测试分词效果，不写入数据库。

```powershell
python scripts\test_segmentation_bv1bk411l7dj.py
python scripts\test_segmentation_bv1bk411l7dj.py --bvid BV1BK411L7DJ --limit 50
python scripts\test_segmentation_bv1bk411l7dj.py --bvid BV1BK411L7DJ --text "这是一条测试弹幕"
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | `BV1BK411L7DJ` | 测试视频 |
| `--limit` | `200` | 从数据库读取的弹幕条数 |
| `--text` | 无 | 直接测试一条文本 |
| `--dict-preview` | `10` | 打印用户词典预览数量；`0` 表示不预览 |

## 分析指标解释

本项目中的指标主要用于描述三类关系：弹幕随时间的变化、弹幕在视频播放进度上的分布、视频之间的相似性。所有指标都应作为解释性分析工具使用，不应直接视为严格因果结论。

### 弹幕数量趋势指标

| 指标 | 计算方式 | 解释 | 局限 |
| --- | --- | --- | --- |
| 每日新增 | 按 `dm_date` 统计每天新增入库弹幕数 | 衡量视频在不同日期的弹幕活跃度 | 受抓取覆盖率、弹幕池上限和接口可用性影响 |
| 累计数量 | 所选日期范围内每日新增的累加值 | 观察弹幕积累速度和长尾表现 | 如果早期日期抓取不完整，累计曲线会偏低 |
| 峰值单日 | 所选粒度下新增弹幕数最大值 | 识别传播峰值、二次传播或集中观看阶段 | 峰值可能由补抓、重复弹幕或单日异常造成 |
| 覆盖原总数 | 已入库弹幕数 / 官方弹幕总数 | 粗略评估采集覆盖程度 | 官方总数口径和历史可抓取数据不一定完全一致 |

使用建议：
- 看视频生命周期时优先使用“每日新增”和“累计数量”。
- 判断是否存在二次传播时，关注发布后一段时间以外的异常峰值。
- 覆盖率只用于评估采集质量，不建议作为视频热度指标。

### 播放进度 x 日期热力图指标

| 指标 | 计算方式 | 解释 | 局限 |
| --- | --- | --- | --- |
| 播放窗口 | 将 `progress` 按 `window_seconds` 切分 | 统计视频不同播放位置的弹幕分布 | 窗口过大会掩盖短时爆点，过小会增加噪声 |
| 峰值格弹幕 | 某日期、某播放窗口中的最大弹幕数 | 定位最强弹幕集中位置 | 大视频更容易出现高绝对值 |
| 绝对数量模式 | 颜色直接映射窗口弹幕数 | 适合比较不同日期的总体强弱 | 容易被高弹幕日期压制低弹幕日期细节 |
| 按日期归一模式 | 每天内部按最大值归一化 | 适合观察同一天内的高能位置 | 不适合比较不同日期之间的总量差异 |

使用建议：
- 判断“视频哪个片段最容易触发弹幕”时使用绝对数量模式。
- 判断“不同日期观众关注的位置是否变化”时使用按日期归一模式。

### 词云与文本指标

| 指标 | 计算方式 | 解释 | 局限 |
| --- | --- | --- | --- |
| 高频词总量 | 当前时间范围内返回词条的 `count` 合计 | 衡量词云中高频词的总体规模 | 只统计返回的 Top 词，不等于全部词数 |
| 最高频词 | 当前范围内 `count` 最大的词或 alias | 识别最核心弹幕主题、梗或角色名 | 受分词、停用词和 alias 规则影响明显 |
| 返回词条数 | 词云接口返回的词条数量 | 反映当前时段可展示的主题丰富度 | 受 `limit` 参数限制 |
| alias 对应短语 | `phrase_aliases` 将长句映射为展示词 | 降低刷屏长句对词云可读性的影响 | alias 需要人工维护，覆盖不足会影响结果 |

词云结果会受到以下文件共同影响：
- `custom_words/{bvid}.txt`
- `resources/text/filtered_words.txt`
- `resources/text/stopwords.txt`
- `resources/text/phrase_aliases.txt`

### 高能窗口指标

高能窗口由 `scripts\build_high_energy_windows.py` 生成。默认每 5 秒一个窗口。

窗口分数公式：

```text
score = 0.55 * density_norm
      + 0.20 * repeat_ratio
      + 0.15 * emotion_ratio
      + 0.10 * top_word_ratio
```

| 指标 | 计算方式 | 解释 | 局限 |
| --- | --- | --- | --- |
| `density_norm` | 当前窗口弹幕数 / 当前视频最高窗口弹幕数 | 衡量窗口相对弹幕密度 | 是视频内部归一化，不适合直接跨视频比较 |
| `repeat_ratio` | `(弹幕数 - 去重内容数) / 弹幕数` | 衡量刷屏或重复表达程度 | 重复高不一定代表内容高能，也可能是固定应援 |
| `emotion_ratio` | `(正向词数 + 负向词数) / 分词总数` | 衡量情绪词集中程度 | 词典法无法稳定识别反讽和复杂语境 |
| `top_word_ratio` | 窗口最高频词次数 / 分词总数 | 衡量单一主题或梗的集中程度 | 高频词可能来自无意义刷屏 |
| `is_high` | 分数达到阈值且弹幕数达到 `min_count` | 标记高能窗口 | 阈值是经验规则，需要结合视频内容解释 |

默认判定条件：
- 分数至少达到 `--min-score`，默认 `0.55`。
- 分数至少达到当前视频窗口分数的 `--percentile` 百分位，默认 `90`。
- 窗口弹幕数至少达到 `--min-count`，默认 `20`。

### 视频相似度指标

相似度矩阵由 `scripts\build_video_similarity_matrix.py` 生成。当前前端保留趋势、情绪、高能结构和综合相似度。

| 指标 | 向量构造 | 计算方式 | 解释 |
| --- | --- | --- | --- |
| 趋势相似度 | 发布后 N 天每日弹幕数，使用 `log1p(count)` | 余弦相似度 | 判断两个视频的弹幕生命周期是否相似 |
| 情绪相似度 | `[positive / (positive + negative), negative / (positive + negative)]` | 余弦相似度 | 判断两个视频的非中性情绪结构是否相似 |
| 高能结构相似度 | 将播放进度归一化为若干桶，每桶取最高高能分数 | 余弦相似度 | 判断弹幕爆发位置在视频结构上是否相似 |
| 综合相似度 | 趋势、情绪、高能结构加权 | 加权平均 | 判断总体观众反应模式是否接近 |

综合相似度默认权重：

```text
trend: 0.40
sentiment: 0.30
high_energy: 0.30
```

如果某个分项缺失，综合相似度会跳过该项，并按剩余可用权重重新归一化。

解释建议：
- 趋势相似度高：两个视频的弹幕增长节奏相似。
- 情绪相似度高：两个视频的正负情绪比例相似。
- 高能结构相似度高：两个视频的弹幕爆发点在播放进度上相似。
- 综合相似度高：整体观众反应模式接近，但仍需要查看分项确认原因。

### 视频画像平行坐标指标

平行坐标图由 `scripts\build_video_parallel_stats.py` 生成，主要用于比较视频的基础热度、互动率、弹幕结构和文本特征。

| 指标 | 计算方式 | 解释 |
| --- | --- | --- |
| 播放量 | `precious_videos.stat_view` | 视频传播规模 |
| 官方弹幕量 | `precious_videos.stat_danmaku` | B 站官方记录的弹幕规模 |
| 已抓弹幕量 | 当前数据库中实际入库弹幕数 | 本项目可分析的数据规模 |
| 时长 | `duration / 60` | 视频长度 |
| 弹幕率 | 官方弹幕量 / 播放量 | 单位播放带来的弹幕互动强度 |
| 评论率 | 评论数 / 播放量 | 评论互动强度 |
| 收藏率 | 收藏数 / 播放量 | 内容保存意愿 |
| 投币率 | 投币数 / 播放量 | 观众认可或支持强度 |
| 分享率 | 分享数 / 播放量 | 外部传播倾向 |
| 点赞率 | 点赞数 / 播放量 | 轻量正反馈强度 |
| 峰值密度 | 高能窗口最大弹幕数 / 窗口秒数 | 视频局部爆发强度 |
| 高能窗口数 | `is_high = 1` 的窗口数量 | 高能片段分布广度 |
| 重复倾向 | 高能窗口平均 `repeat_ratio` | 刷屏或固定表达程度 |
| 正向占比 | 正向词数 / (正向词数 + 负向词数) | 非中性情绪中的正向比例 |
| 词汇丰富度 | `unique_words / sqrt(total_words)` | 弹幕表达多样性，并缓解体量差异影响 |

使用建议：
- 比较不同视频的互动结构时，优先看弹幕率、评论率、投币率、收藏率，而不是只看播放量。
- 判断弹幕是否集中爆发时，结合峰值密度和高能窗口数。
- 判断文本表达是否单一时，结合词汇丰富度和词云。

## 预聚合与分析表

### `scripts\build_word_cloud_stats.py`

构建词云每日预聚合表 `word_cloud_daily_stats`，用于加速前端词云查询。

```powershell
python scripts\build_word_cloud_stats.py --batch-days 7
python scripts\build_word_cloud_stats.py --bvid BV1Js411o76u --batch-days 7 --sleep 1
python scripts\build_word_cloud_stats.py --bvid BV1Js411o76u --rebuild --batch-days 3 --sleep 1
python scripts\build_word_cloud_stats.py --bvid BV1Js411o76u --start 2020-01-01 --end 2020-01-31
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | 无 | 只处理指定视频 |
| `--rebuild` | 关闭 | 删除目标视频旧统计并重建 |
| `--start` | 无 | 起始日期，格式 `YYYY-MM-DD` |
| `--end` | 无 | 截止日期，格式 `YYYY-MM-DD` |
| `--batch-days` | 脚本常量 | 每批处理天数 |
| `--min-count` | `1` | 每天单词计数低于该值不保存 |
| `--insert-chunk-size` | 脚本常量 | 单次批量写入行数 |
| `--limit-videos` | `0` | 本轮最多处理视频数；`0` 表示不限 |
| `--sleep` | `0.5` | 每个日期批次提交后暂停秒数 |
| `--include-incomplete` | 关闭 | 包含尚未抓取完成的视频 |

### `scripts\build_high_energy_windows.py`

生成规则高能时刻窗口评分，写入 `high_energy_windows` 和 `high_energy_segments`。

```powershell
python scripts\build_high_energy_windows.py --window-seconds 5
python scripts\build_high_energy_windows.py --bvid BV1BK411L7DJ --window-seconds 5
python scripts\build_high_energy_windows.py --window-seconds 10 --percentile 90 --min-score 0.55 --min-count 20
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | 无 | 只处理指定视频 |
| `--window-seconds` | `5` | 播放时间窗口秒数 |
| `--percentile` | `90` | 高能阈值百分位 |
| `--min-score` | `0.55` | 最低高能分数 |
| `--min-count` | `20` | 高能窗口最低弹幕数 |
| `--top-words` | `5` | 每个窗口保留的高频词数量 |
| `--merge-gap-windows` | `1` | 合并片段时允许间隔的非高能窗口数 |

### `scripts\build_video_similarity_matrix.py`

预计算视频相似度矩阵，写入 `video_similarity_matrix`。当前项目视频数量约 91 个。

```powershell
python scripts\build_video_similarity_matrix.py
python scripts\build_video_similarity_matrix.py --execute
python scripts\build_video_similarity_matrix.py --metric combined --execute
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--metric` | `all` | `trend`、`sentiment`、`high_energy`、`combined` 或 `all` |
| `--feature-version` | `v1` | 特征版本 |
| `--days` | 脚本常量 | 趋势向量取发布后多少天 |
| `--high-energy-bins` | 脚本常量 | 高能结构归一化桶数 |
| `--window-seconds` | 脚本常量 | 使用哪个高能窗口粒度 |
| `--limit-videos` | `0` | 仅处理前 N 个视频；`0` 表示全部 |
| `--execute` | 关闭 | 实际写库；不加时只预览 |

说明：
- 趋势相似度使用发布后每日弹幕数的 `log1p` 向量。
- 情绪相似度移除中性词。
- 词汇相似度已不作为前端指标。

### `scripts\build_video_parallel_stats.py`

构建视频画像平行坐标图使用的 `video_parallel_stats`。

```powershell
python scripts\build_video_parallel_stats.py
python scripts\build_video_parallel_stats.py --execute
python scripts\build_video_parallel_stats.py --bvid BV1BK411L7DJ --execute
python scripts\build_video_parallel_stats.py --window-seconds 10 --execute
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | 空 | 只处理指定视频；为空时处理全部 |
| `--window-seconds` | 脚本常量 | 峰值密度使用的高能窗口秒数 |
| `--execute` | 关闭 | 实际写库；不加时只预览 |

## 半自动词典维护

### `scripts\generate_word_review_candidates.py`

生成 `custom_words`、`stopwords`、`phrase_aliases` 审核候选。

```powershell
python scripts\generate_word_review_candidates.py
python scripts\generate_word_review_candidates.py --bvid BV1BK411L7DJ
python scripts\generate_word_review_candidates.py --bvid BV1BK411L7DJ --min-full-count 50 --min-bigram-count 50 --max-candidates 300
```

输出文件：

| 文件 | 说明 |
| --- | --- |
| `review_candidates/custom_words_candidates.tsv` | 视频专属词典候选 |
| `review_candidates/stopwords_candidates.tsv` | 停用词/过滤词候选 |
| `review_candidates/phrase_aliases_candidates.tsv` | 长短语别名候选 |

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | 无 | 只为指定视频生成候选 |
| `--output-dir` | `review_candidates` | 候选 TSV 输出目录 |
| `--custom-words-dir` | `custom_words` | 视频专属词典目录 |
| `--accepted-custom-words-file` | `resources/text/accepted_custom_words.txt` | 全局已审核短语文件 |
| `--include-incomplete` | 关闭 | 包含尚未抓取完成的视频 |
| `--dry-run-auto-accept` | 关闭 | 预览自动命中全局短语的写入数量 |
| `--max-candidates` | `200` | 每类候选最多输出条数 |
| `--min-full-count` | `500` | 完整弹幕候选最低出现次数 |
| `--min-bigram-count` | `2000` | 相邻词组合候选最低出现次数 |
| `--min-stopword-count` | `1000` | 单视频词频进入停用词候选统计的阈值 |
| `--global-stopword-count` | `50000` | 全局词频阈值 |
| `--min-stopword-video-count` | `20` | 至少出现在多少个视频中 |
| `--min-term-length` | `2` | custom_words 候选最短长度 |
| `--max-term-length` | `6` | custom_words 候选最长长度；`0` 表示不限制 |
| `--alias-min-length` | `7` | phrase_aliases 候选最短长度 |
| `--max-stopword-length` | `4` | stopwords 候选最长长度 |

### `scripts\apply_word_review_candidates.py`

应用审核通过的候选。`phrase_aliases_candidates.tsv` 中已填写 `alias` 但 `status` 为空的行，会自动补为 `accept`。

```powershell
python scripts\apply_word_review_candidates.py --dry-run
python scripts\apply_word_review_candidates.py
python scripts\apply_word_review_candidates.py --stopword-target stopwords
python scripts\apply_word_review_candidates.py --stopword-target filtered
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--input-dir` | `review_candidates` | 审核 TSV 所在目录 |
| `--custom-words-dir` | `custom_words` | 视频专属词典目录 |
| `--stopwords-file` | `resources/text/stopwords.txt` | 停用词文件 |
| `--filtered-words-file` | `resources/text/filtered_words.txt` | 分词过滤词文件 |
| `--phrase-aliases-file` | `resources/text/phrase_aliases.txt` | 短语别名文件 |
| `--accepted-custom-words-file` | `resources/text/accepted_custom_words.txt` | 全局已审核短语文件 |
| `--stopword-target` | `both` | `stopwords`、`filtered` 或 `both` |
| `--dry-run` | 关闭 | 只预览，不写入 |
| `--no-backup` | 关闭 | 写入前不备份目标文件 |

推荐循环：

```powershell
python scripts\generate_word_review_candidates.py
python scripts\apply_word_review_candidates.py --dry-run
python scripts\apply_word_review_candidates.py
python scripts\drop_danmaku_words_tables.py --execute
python scripts\build_danmaku_words.py --batch-size 300
python scripts\build_word_cloud_stats.py --rebuild --batch-days 7
```

### `scripts\build_phrase_alias_feature_model.py`

根据 `resources/text/phrase_aliases.txt` 生成 alias 特征词，并自动标注 `review_candidates/phrase_aliases_candidates.tsv`。

```powershell
python scripts\build_phrase_alias_feature_model.py --dry-run
python scripts\build_phrase_alias_feature_model.py
python scripts\build_phrase_alias_feature_model.py --features-only
python scripts\build_phrase_alias_feature_model.py --annotate-only
python scripts\build_phrase_alias_feature_model.py --self-test
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--phrase-aliases-file` | `resources/text/phrase_aliases.txt` | 已审核短语别名文件 |
| `--features-file` | `resources/text/phrase_alias_features.txt` | alias 特征词文件 |
| `--candidates-file` | `review_candidates/phrase_aliases_candidates.tsv` | 待标注 TSV |
| `--threshold` | `0.8` | 特征词覆盖候选弹幕的最低比例 |
| `--min-feature-length` | `2` | 最短特征词长度 |
| `--overwrite-alias` | 关闭 | 覆盖候选中已有 alias |
| `--no-merge-existing` | 关闭 | 不合并已有特征词文件 |
| `--features-only` | 关闭 | 只生成特征词文件 |
| `--annotate-only` | 关闭 | 只读取已有特征词并标注候选 |
| `--dry-run` | 关闭 | 只预览，不写入 |
| `--no-backup` | 关闭 | 写入前不备份 |
| `--self-test` | 关闭 | 运行内置示例测试 |

## 样本导出与统计

### `scripts\export_random_danmaku_samples.py`

为每个已抓取完成的视频导出最多 N 条随机弹幕样本，默认输出到 `danmaku_samples/`。

```powershell
python scripts\export_random_danmaku_samples.py
python scripts\export_random_danmaku_samples.py --bvid BV1BK411L7DJ
python scripts\export_random_danmaku_samples.py --limit 3000 --batch-size 50 --max-batches 60
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--bvid` | 无 | 只导出指定视频 |
| `--limit` | `5000` | 每个视频最多导出条数 |
| `--batch-size` | 脚本常量 | 每次随机主键起点读取的小批量大小 |
| `--max-batches` | 脚本常量 | 每个视频最多执行的小批量查询次数 |
| `--output-dir` | `danmaku_samples` | txt 输出目录 |

说明：
- 未抓取到 `END_DATE` 的视频会跳过。
- 已导出过样本文件的视频会跳过。
- 脚本使用随机主键起点近似采样，避免 `ORDER BY RAND()`。

### `scripts\danmaku_coverage.py`

计算每个视频已抓取弹幕数与原视频弹幕总数的百分比。

```powershell
python scripts\danmaku_coverage.py
```

### `scripts\query.py`

打印每个视频当前已入库弹幕数量和原视频弹幕总数。

```powershell
python scripts\query.py
```

## 前后端服务

### `api_server.py`

启动后端 API 与静态前端服务。

```powershell
python api_server.py
```

指定端口：

```powershell
$env:PORT = "8090"
python api_server.py
```

访问地址：

```text
http://127.0.0.1:8080/
```

主要接口：

| 接口 | 说明 |
| --- | --- |
| `/api/videos` | 轻量视频列表 |
| `/api/video-detail?bvid=...` | 单个视频详情 |
| `/api/danmaku-trend?bvid=...&start=YYYY-MM-DD&end=YYYY-MM-DD` | 弹幕数量趋势 |
| `/api/progress-date-heatmap?bvid=...&start=YYYY-MM-DD&end=YYYY-MM-DD&window_seconds=30&normalize=none` | 播放进度 x 日期二维热力图 |
| `/api/word-cloud?bvid=...&start=YYYY-MM-DD&end=YYYY-MM-DD&limit=160` | 词云数据，优先读取预聚合表 |
| `/api/video-similarity-matrix?bvids=BV1...,BV2...&metric=combined&feature_version=v1` | 视频相似度矩阵 |
| `/api/video-parallel-stats?bvids=BV1...,BV2...` | 视频画像平行坐标图 |
| `/api/high-energy?bvid=...` | 高能时刻窗口评分 |
| `/api/cover?url=...` | 代理视频封面 |

前端拆分：

| 路径 | 说明 |
| --- | --- |
| `frontend/index.html` | 页面结构 |
| `frontend/app.js` | Vue 应用装配入口 |
| `frontend/js/` | 状态、计算属性、请求、图表渲染、UI 工具 |
| `frontend/styles.css` | CSS 聚合入口 |
| `frontend/css/` | 页面基础、控制区、工作区、播放器、响应式样式 |

## 常见维护命令

查看任意脚本参数：

```powershell
python scripts\脚本名.py --help
```

检查 Python 语法：

```powershell
.\.venv\Scripts\python.exe -m compileall -q api_server.py app scripts
```

检查前端 JS 语法：

```powershell
node --check frontend\app.js
Get-ChildItem frontend\js\*.js | ForEach-Object { node --check $_.FullName }
```

检查是否仍存在超过 300 行的源码文件：

```powershell
Get-ChildItem -Recurse -Force -File |
  Where-Object { $_.FullName -notmatch '\\.venv\\|__pycache__|frontend\\vendor\\|\\.git\\|\\.idea\\|backups\\|resources\\|review_candidates\\|words\\|logs\\' } |
  ForEach-Object {
    $lineCount = (Get-Content -LiteralPath $_.FullName -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
    [PSCustomObject]@{ Lines = $lineCount; Path = $_.FullName.Substring((Get-Location).Path.Length + 1) }
  } |
  Sort-Object Lines -Descending |
  Select-Object -First 20
```

## 注意事项

- `app/config.py` 只保留占位提示；发布或共享项目前不要写入真实数据库密码和 Cookie。
- `scripts/` 中的部分脚本会直接修改数据库或文本资源，涉及删除、重建、应用审核结果时建议先使用预览参数。
- 词典、停用词、过滤词和 alias 修改后，需要重新生成分词表，并重建依赖分词结果的统计表。
