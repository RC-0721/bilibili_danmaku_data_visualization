var DanmakuUiMethods = {
  resetRange() {
    if (this.analysisMode === "parallel") {
      this.selectedParallelBvids = this.videos.slice(0, Math.min(8, this.videos.length)).map((video) => video.bvid);
      return;
    }
    if (this.analysisMode === "similarity") {
      this.startDate = DATA_MIN_DATE;
      this.endDate = DATA_END_DATE;
      return;
    }
    if (!this.selectedVideo) return;
    this.startDate = this.selectedVideo.publishDate || DATA_END_DATE;
    this.endDate = DATA_END_DATE;
  },

  openPlayer() {
    if (!this.selectedVideo) return;
    this.playerOpen = true;
    this.playerMinimized = false;
  },

  resizeChart() {
    this.chart?.resize();
  },

  parallelChartValue(row, dimension) {
    const rawValue = Number(row?.[dimension.key] || 0);
    if (this.parallelValueMode === "log" && dimension.scale === "log") {
      return Math.log10(rawValue + 1);
    }
    return rawValue;
  },

  parallelLineColor(row, index) {
    const positiveRatio = Number(row.positiveRatio || 0);
    if (positiveRatio >= 0.7) return "#2f7d55";
    if (positiveRatio <= 0.35) return "#bf5b45";
    return PARALLEL_COLORS[index % PARALLEL_COLORS.length];
  },

  formatParallelAxisValue(value, dimension) {
    if (this.parallelValueMode === "log" && dimension.scale === "log") {
      return this.compactNumber(Math.pow(10, Number(value || 0)) - 1);
    }
    return this.formatParallelRawValue(value, dimension, true);
  },

  formatParallelRawValue(value, dimension, compact = false) {
    const numeric = Number(value || 0);
    if (dimension.format === "percent") return this.formatPercent(numeric);
    if (dimension.format === "decimal") {
      const formatted = numeric >= 10 ? numeric.toFixed(1) : numeric.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
      return dimension.unit ? `${formatted} ${dimension.unit}` : formatted;
    }
    const formatted = compact ? this.compactNumber(numeric) : this.formatNumber(numeric);
    return dimension.unit ? `${formatted} ${dimension.unit}` : formatted;
  },

  formatNumber(value) {
    return Number(value || 0).toLocaleString("zh-CN");
  },

  formatPercent(value) {
    return `${(Number(value || 0) * 100).toFixed(1)}%`;
  },

  formatOptionalScore(value) {
    if (value === null || value === undefined) return "N/A";
    return Number(value || 0).toFixed(3);
  },

  formatSeconds(value) {
    const totalSeconds = Math.max(0, Math.floor(Number(value || 0)));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = String(totalSeconds % 60).padStart(2, "0");
    return `${minutes}:${seconds}`;
  },

  compactNumber(value) {
    if (value >= 10000) return `${(value / 10000).toFixed(1)}万`;
    return String(Math.round(value));
  },

  compactTitle(value, maxLength) {
    const text = String(value || "");
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength - 1)}…`;
  },
};
