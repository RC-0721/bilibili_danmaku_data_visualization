var DanmakuWatchers = {
  async selectedBvid() {
    await this.loadVideoDetail();
  },
  async startDate() {
    if (this.suppressRangeWatch) return;
    await this.loadActiveData();
  },
  async endDate() {
    if (this.suppressRangeWatch) return;
    await this.loadActiveData();
  },
  async analysisMode() {
    await this.loadActiveData();
  },
  selectedSimilarityBvids: {
    deep: true,
    async handler(value) {
      if (value.length > 10) {
        this.selectedSimilarityBvids = value.slice(0, 10);
        return;
      }
      if (this.analysisMode === "similarity") await this.loadActiveData();
    },
  },
  selectedParallelBvids: {
    deep: true,
    async handler(value) {
      if (value.length > 20) {
        this.selectedParallelBvids = value.slice(0, 20);
        return;
      }
      if (this.analysisMode === "parallel") await this.loadActiveData();
    },
  },
  async similarityMetric() {
    if (this.analysisMode === "similarity") await this.loadActiveData();
  },
  parallelValueMode() {
    this.renderChart();
  },
  selectedParallelDimensionKeys: {
    deep: true,
    handler() {
      this.renderChart();
    },
  },
  metric: "renderChart",
  bucket: "renderChart",
  async heatmapWindowSeconds() {
    if (this.analysisMode === "heatmap") await this.loadActiveData();
  },
  async heatmapNormalize() {
    if (this.analysisMode === "heatmap") await this.loadActiveData();
  },
};
