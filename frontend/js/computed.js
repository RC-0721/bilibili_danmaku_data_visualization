var DanmakuComputed = {
  minDate() {
    if (this.analysisMode === "similarity" || this.analysisMode === "parallel") return DATA_MIN_DATE;
    return this.selectedVideo?.publishDate || DATA_END_DATE;
  },

  activeViewLabel() {
    if (this.analysisMode === "danmaku") return this.metricLabel;
    if (this.analysisMode === "heatmap") return "进度日期热力图";
    if (this.analysisMode === "similarity") return "视频相似度矩阵";
    if (this.analysisMode === "parallel") return "视频画像平行坐标";
    return "词云图";
  },

  workspaceTitle() {
    if (this.analysisMode === "similarity") return "视频相似度矩阵";
    if (this.analysisMode === "parallel") return "视频画像";
    return this.selectedVideo?.title || "请选择视频";
  },

  playerTitle() {
    return this.selectedVideo?.title || "B站播放器";
  },

  playerSrc() {
    if (!this.selectedVideo?.bvid || !this.selectedVideo?.cid) return "";
    const params = new URLSearchParams({
      bvid: this.selectedVideo.bvid,
      cid: String(this.selectedVideo.cid),
      page: "1",
      autoplay: "0",
      danmaku: "1",
    });
    return `https://player.bilibili.com/player.html?${params.toString()}`;
  },

  metricLabel() {
    return this.metric === "daily" ? "每日新增" : "累计数量";
  },

  bucketLabel() {
    return { day: "按日", week: "按周", month: "按月" }[this.bucket];
  },

  headerSubtitle() {
    if (this.analysisMode === "similarity") {
      return `已选择 ${this.selectedSimilarityBvids.length}/10 个视频 · ${this.similarityMetricLabel} · ${this.similarityFeatureVersion}`;
    }
    if (this.analysisMode === "parallel") {
      return `已选择 ${this.selectedParallelBvids.length}/20 个视频 · ${this.parallelSelectedDimensions.length} 个维度 · ${this.parallelValueMode === "log" ? "对数缩放" : "原始值"}`;
    }
    if (this.analysisMode === "heatmap") {
      const mode = this.heatmapNormalize === "date" ? "按日期归一化" : "绝对数量";
      return `${this.startDate} 至 ${this.endDate} · ${this.activeViewLabel} · ${this.heatmapWindowSeconds} 秒窗口 · ${mode}`;
    }
    const parts = [`${this.startDate} 至 ${this.endDate}`, this.activeViewLabel];
    if (this.analysisMode === "danmaku") parts.push(this.bucketLabel);
    return parts.join(" · ");
  },

  chartRows() {
    if (!this.startDate || !this.endDate) return [];
    const byDate = new Map(this.trendRows.map((row) => [row.date, Number(row.count || 0)]));
    const dailyRows = eachDate(this.startDate, this.endDate).map((date) => ({
      date,
      count: byDate.get(date) || 0,
    }));

    const aggregated = aggregateRows(dailyRows, this.bucket, ["count"]);
    let running = 0;
    return aggregated.map((row) => {
      running += row.count;
      return { ...row, daily: row.count, cumulative: running };
    });
  },

  danmakuSummary() {
    const totalAdded = this.chartRows.reduce((sum, row) => sum + row.daily, 0);
    const peakDaily = this.chartRows.reduce((max, row) => Math.max(max, row.daily), 0);
    const videoTotal = this.selectedVideo?.total || 0;
    return {
      totalAdded,
      peakDaily,
      coverage: videoTotal ? `${((totalAdded / videoTotal) * 100).toFixed(2)}%` : "N/A",
    };
  },

  wordSummary() {
    const totalTopWords = this.wordCloudRows.reduce((sum, row) => sum + Number(row.value || 0), 0);
    const topWord = this.wordCloudRows[0];
    return {
      totalTopWords,
      topWord: topWord ? `${topWord.name} (${this.formatNumber(topWord.value)})` : "N/A",
      uniqueWords: this.wordCloudRows.length,
    };
  },

  heatmapSummary() {
    return {
      dates: this.heatmapDates.length,
      buckets: this.heatmapBuckets.length,
      peakCount: this.heatmapMaxCount,
    };
  },

  similaritySummary() {
    const scores = [];
    for (let rowIndex = 0; rowIndex < this.similarityMatrix.length; rowIndex += 1) {
      for (let colIndex = rowIndex + 1; colIndex < this.similarityMatrix[rowIndex].length; colIndex += 1) {
        scores.push(Number(this.similarityMatrix[rowIndex][colIndex] || 0));
      }
    }
    const avgScore = scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : 0;
    const maxScore = scores.length ? Math.max(...scores) : 0;
    return { videoCount: this.similarityVideos.length, avgScore, maxScore };
  },

  similarityMetricLabel() {
    return {
      combined: "综合相似度",
      trend: "趋势相似度",
      sentiment: "情绪相似度",
      high_energy: "高能结构相似度",
    }[this.similarityMetric] || "综合相似度";
  },

  parallelSelectedDimensions() {
    const selected = new Set(this.selectedParallelDimensionKeys);
    return this.parallelDimensions.filter((dimension) => selected.has(dimension.key));
  },

  parallelSummary() {
    const rows = this.parallelRows;
    const avgPositive = rows.length ? rows.reduce((sum, row) => sum + Number(row.positiveRatio || 0), 0) / rows.length : 0;
    const maxPeakDensity = rows.length ? Math.max(...rows.map((row) => Number(row.peakDensity || 0))) : 0;
    return {
      videoCount: rows.length,
      dimensionCount: this.parallelSelectedDimensions.length,
      avgPositive,
      maxPeakDensity,
    };
  },

  kpiLabels() {
    if (this.analysisMode === "danmaku") return { first: "区间新增", second: "峰值单日", third: "覆盖原总数" };
    if (this.analysisMode === "heatmap") return { first: "覆盖日期数", second: "进度窗口数", third: "峰值格弹幕" };
    if (this.analysisMode === "similarity") return { first: "参与视频", second: "平均相似度", third: "最高相似度" };
    if (this.analysisMode === "parallel") return { first: "参与视频", second: "画像维度", third: "平均正向" };
    return { first: "高频词总量", second: "最高频词", third: "返回词条数" };
  },

  kpiValues() {
    if (this.analysisMode === "danmaku") {
      return {
        first: this.formatNumber(this.danmakuSummary.totalAdded),
        second: this.formatNumber(this.danmakuSummary.peakDaily),
        third: this.danmakuSummary.coverage,
      };
    }
    if (this.analysisMode === "heatmap") {
      return {
        first: this.formatNumber(this.heatmapSummary.dates),
        second: this.formatNumber(this.heatmapSummary.buckets),
        third: this.formatNumber(this.heatmapSummary.peakCount),
      };
    }
    if (this.analysisMode === "similarity") {
      return {
        first: this.formatNumber(this.similaritySummary.videoCount),
        second: this.similaritySummary.avgScore.toFixed(3),
        third: this.similaritySummary.maxScore.toFixed(3),
      };
    }
    if (this.analysisMode === "parallel") {
      return {
        first: this.formatNumber(this.parallelSummary.videoCount),
        second: this.formatNumber(this.parallelSummary.dimensionCount),
        third: this.formatPercent(this.parallelSummary.avgPositive),
      };
    }
    return {
      first: this.formatNumber(this.wordSummary.totalTopWords),
      second: this.wordSummary.topWord,
      third: this.formatNumber(this.wordSummary.uniqueWords),
    };
  },

  kpiFourthLabel() {
    if (this.analysisMode === "similarity") return "特征版本";
    if (this.analysisMode === "parallel") return "峰值密度";
    return "视频弹幕总数";
  },

  kpiFourthValue() {
    if (this.analysisMode === "similarity") return this.similarityFeatureVersion;
    if (this.analysisMode === "parallel") return `${this.parallelSummary.maxPeakDensity.toFixed(2)} 条/秒`;
    return this.formatNumber(this.selectedVideo?.total || 0);
  },

  indicatorNotes() {
    if (this.analysisMode === "danmaku") {
      return [
        { title: "区间新增", body: "当前日期范围内抓取到并成功入库的弹幕数量，用于观察视频弹幕生命周期。" },
        { title: "峰值单日", body: "所选时间粒度下的最高新增弹幕量，可辅助识别传播峰值或二次传播。" },
        { title: "覆盖原总数", body: "区间入库弹幕数与官方弹幕总数的比值，只能反映采集覆盖程度，不能等同于完整弹幕留存率。" },
      ];
    }
    if (this.analysisMode === "heatmap") {
      return [
        { title: "进度窗口", body: "把视频播放进度切成固定秒数窗口，统计每个日期内各窗口的弹幕密度。" },
        { title: "绝对数量", body: "颜色直接表示窗口弹幕数，适合比较整体弹幕规模。" },
        { title: "按日期归一", body: "每天单独归一化颜色，适合观察同一天内部哪些播放位置更突出。" },
      ];
    }
    if (this.analysisMode === "words") {
      return [
        { title: "高频词总量", body: "当前时间范围内返回词条的累计出现次数，用于判断弹幕主题集中程度。" },
        { title: "最高频词", body: "词云中出现次数最高的词或 alias，悬停可查看被 alias 替代的原始短语。" },
        { title: "过滤影响", body: "词云结果受 custom_words、filtered_words、stopwords 和 phrase_aliases 共同影响。" },
      ];
    }
    if (this.analysisMode === "similarity") {
      return [
        { title: "趋势相似度", body: "比较发布后每日弹幕数量向量，使用 log1p 降低极端大视频的影响。" },
        { title: "情绪相似度", body: "只比较正向和负向比例，已移除中性词，适合看情绪结构是否接近。" },
        { title: "高能结构相似度", body: "比较高能窗口在播放进度上的分布，适合判断观众集中反应的位置是否相似。" },
        { title: "综合相似度", body: "按趋势 0.40、情绪 0.30、高能 0.30 加权；缺失指标会自动跳过并重新归一化权重。" },
      ];
    }
    return [
      { title: "互动率", body: "弹幕率、评论率、投币率等均以播放量为分母，用于削弱播放量级差异。" },
      { title: "峰值密度", body: "高能窗口中最高的弹幕密度，单位为条/秒，用于衡量视频局部爆发强度。" },
      { title: "正向占比", body: "正向词数除以正向词数与负向词数之和，不包含中性词。" },
      { title: "词汇丰富度", body: "unique_words / sqrt(total_words)，用于衡量表达多样性，同时缓解大体量视频的规模优势。" },
    ];
  },
};
