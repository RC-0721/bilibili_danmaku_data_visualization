var DanmakuDataMethods = {
  async loadVideos() {
    this.loading = true;
    this.error = "";
    try {
      const payload = await this.fetchJson("/api/videos", "视频列表接口失败");
      this.videos = payload.videos || [];
      if (this.videos.length) {
        this.selectedBvid = this.videos[0].bvid;
        this.selectedSimilarityBvids = this.videos.slice(0, Math.min(3, this.videos.length)).map((video) => video.bvid);
        this.selectedParallelBvids = this.videos.slice(0, Math.min(8, this.videos.length)).map((video) => video.bvid);
      } else {
        this.renderChart();
      }
    } catch (error) {
      this.error = error.message;
      this.renderChart();
    } finally {
      this.loading = false;
    }
  },

  async loadVideoDetail() {
    if (!this.selectedBvid) return;
    this.loadingDetail = true;
    this.error = "";
    try {
      const params = new URLSearchParams({ bvid: this.selectedBvid });
      const payload = await this.fetchJson(`/api/video-detail?${params.toString()}`, "视频详情接口失败");
      this.selectedVideo = payload.video;
      this.clearLoadedRows();
      this.suppressRangeWatch = true;
      this.startDate = this.selectedVideo.publishDate || DATA_END_DATE;
      this.endDate = DATA_END_DATE;
      this.suppressRangeWatch = false;
      await this.loadActiveData();
    } catch (error) {
      this.error = error.message;
      this.selectedVideo = null;
      this.clearLoadedRows();
      this.renderChart();
    } finally {
      this.loadingDetail = false;
    }
  },

  clearLoadedRows() {
    this.trendRows = [];
    this.wordCloudRows = [];
    this.heatmapDates = [];
    this.heatmapBuckets = [];
    this.heatmapData = [];
    this.heatmapMaxCount = 0;
    this.heatmapMaxValue = 0;
    this.similarityVideos = [];
    this.similarityCells = [];
    this.similarityMatrix = [];
    this.similarityDetails = {};
    this.parallelRows = [];
    this.parallelVideos = [];
  },

  async loadActiveData() {
    if (this.analysisMode === "similarity") {
      if (!this.startDate || !this.endDate) return;
      await this.loadSimilarityMatrix();
      return;
    }
    if (this.analysisMode === "parallel") {
      await this.loadParallelStats();
      return;
    }
    if (!this.selectedVideo || !this.selectedBvid) return;
    if (!this.startDate || !this.endDate) return;
    if (this.analysisMode === "danmaku") {
      await this.loadTrend();
    } else if (this.analysisMode === "heatmap") {
      await this.loadHeatmap();
    } else {
      await this.loadWordCloud();
    }
  },

  async loadTrend() {
    this.loading = true;
    this.error = "";
    try {
      const params = new URLSearchParams({
        bvid: this.selectedBvid,
        start: this.startDate,
        end: this.endDate,
      });
      const payload = await this.fetchJson(`/api/danmaku-trend?${params.toString()}`, "趋势接口失败");
      this.trendRows = payload.rows || [];
    } catch (error) {
      this.error = error.message;
      this.trendRows = [];
    } finally {
      this.loading = false;
      this.renderChart();
    }
  },

  async loadHeatmap() {
    this.loading = true;
    this.error = "";
    try {
      const params = new URLSearchParams({
        bvid: this.selectedBvid,
        start: this.startDate,
        end: this.endDate,
        window_seconds: String(this.heatmapWindowSeconds),
        normalize: this.heatmapNormalize,
      });
      const payload = await this.fetchJson(`/api/progress-date-heatmap?${params.toString()}`, "进度热力图接口失败");
      this.heatmapDates = payload.dates || [];
      this.heatmapBuckets = payload.progressBuckets || [];
      this.heatmapData = payload.data || [];
      this.heatmapMaxCount = Number(payload.maxCount || 0);
      this.heatmapMaxValue = Number(payload.maxValue || 0);
    } catch (error) {
      this.error = error.message;
      this.heatmapDates = [];
      this.heatmapBuckets = [];
      this.heatmapData = [];
      this.heatmapMaxCount = 0;
      this.heatmapMaxValue = 0;
    } finally {
      this.loading = false;
      this.renderChart();
    }
  },

  async loadWordCloud() {
    this.loading = true;
    this.error = "";
    try {
      const params = new URLSearchParams({
        bvid: this.selectedBvid,
        start: this.startDate,
        end: this.endDate,
        limit: "160",
      });
      const payload = await this.fetchJson(`/api/word-cloud?${params.toString()}`, "词云接口失败");
      this.wordCloudRows = payload.rows || [];
    } catch (error) {
      this.error = error.message;
      this.wordCloudRows = [];
    } finally {
      this.loading = false;
      this.renderChart();
    }
  },

  async loadSimilarityMatrix() {
    if (this.selectedSimilarityBvids.length < 2) {
      this.similarityVideos = [];
      this.similarityCells = [];
      this.similarityMatrix = [];
      this.renderChart();
      return;
    }
    this.loading = true;
    this.error = "";
    try {
      const params = new URLSearchParams({
        bvids: this.selectedSimilarityBvids.join(","),
        metric: this.similarityMetric,
        feature_version: this.similarityFeatureVersion,
        limit: "10",
      });
      const payload = await this.fetchJson(`/api/video-similarity-matrix?${params.toString()}`, "相似度接口失败");
      this.similarityVideos = payload.videos || [];
      this.similarityCells = payload.cells || [];
      this.similarityMatrix = payload.matrix || [];
      this.similarityDetails = payload.details || {};
      this.similarityFeatureVersion = payload.featureVersion || this.similarityFeatureVersion;
      if (payload.message) this.error = payload.message;
    } catch (error) {
      this.error = error.message;
      this.similarityVideos = [];
      this.similarityCells = [];
      this.similarityMatrix = [];
      this.similarityDetails = {};
    } finally {
      this.loading = false;
      this.renderChart();
    }
  },

  async loadParallelStats() {
    if (this.selectedParallelBvids.length < 2) {
      this.parallelRows = [];
      this.parallelVideos = [];
      this.renderChart();
      return;
    }
    this.loading = true;
    this.error = "";
    try {
      const params = new URLSearchParams({
        bvids: this.selectedParallelBvids.join(","),
        limit: "20",
      });
      const payload = await this.fetchJson(`/api/video-parallel-stats?${params.toString()}`, "视频画像接口失败");
      this.parallelRows = payload.rows || [];
      this.parallelVideos = payload.videos || [];
      this.parallelDimensions = payload.dimensions || [];
      if (!this.selectedParallelDimensionKeys.length && this.parallelDimensions.length) {
        this.selectedParallelDimensionKeys = this.parallelDimensions
          .filter((dimension) => dimension.defaultSelected)
          .map((dimension) => dimension.key);
      }
      if (payload.message) this.error = payload.message;
    } catch (error) {
      this.error = error.message;
      this.parallelRows = [];
      this.parallelVideos = [];
    } finally {
      this.loading = false;
      this.renderChart();
    }
  },

  async fetchJson(url, label) {
    const response = await fetch(url);
    if (!response.ok) {
      let message = `${label}: ${response.status}`;
      try {
        const errorPayload = await response.json();
        if (errorPayload.error) message += ` - ${errorPayload.error}`;
      } catch (_) {
        // Ignore non-JSON error bodies.
      }
      throw new Error(message);
    }
    return response.json();
  },
};
