var DanmakuHeatmapSimilarityChartMethods = {
  renderProgressDateHeatmap() {
    const dates = this.heatmapDates;
    const buckets = this.heatmapBuckets;
    const labels = buckets.map((bucket) => this.formatSeconds(bucket));
    const maxValue = this.heatmapNormalize === "date" ? 1 : this.heatmapMaxValue;
    const xInterval = Math.max(0, Math.ceil(labels.length / 12) - 1);
    const yInterval = Math.max(0, Math.ceil(dates.length / 14) - 1);

    this.setChartOption({
      color: ["#f4e7d3", "#d8b478", "#b8784f", "#7a3f34"],
      grid: { left: 96, right: 84, top: 42, bottom: 62 },
      tooltip: {
        position: "top",
        formatter: (params) => {
          const item = params.data || [];
          const bucket = buckets[item[0]] || 0;
          const date = dates[item[1]] || "";
          const count = Number(item[3] || 0);
          const value = Number(item[2] || 0);
          const lines = [
            `日期: ${date}`,
            `播放位置: ${this.formatSeconds(bucket)} - ${this.formatSeconds(bucket + this.heatmapWindowSeconds)}`,
            `弹幕数量: ${this.formatNumber(count)}`,
          ];
          if (this.heatmapNormalize === "date") {
            lines.push(`当日相对强度: ${(value * 100).toFixed(1)}%`);
          }
          return lines.join("<br/>");
        },
      },
      toolbox: this.chartToolbox(),
      xAxis: {
        type: "category",
        data: labels,
        splitArea: { show: false },
        axisLabel: { color: "#657086", interval: xInterval },
        axisLine: { lineStyle: { color: "#dbe2ee" } },
      },
      yAxis: {
        type: "category",
        data: dates,
        splitArea: { show: false },
        axisLabel: { color: "#657086", interval: yInterval },
        axisLine: { lineStyle: { color: "#dbe2ee" } },
      },
      visualMap: {
        min: 0,
        max: maxValue || 1,
        calculable: true,
        orient: "vertical",
        right: 12,
        top: "middle",
        dimension: 2,
        formatter: (value) => {
          if (this.heatmapNormalize === "date") return `${Math.round(value * 100)}%`;
          return this.compactNumber(value);
        },
        textStyle: { color: "#657086" },
        inRange: {
          color: ["#f3f6f8", "#b9d9de", "#6aa7b4", "#1f7a8c", "#bf5b45"],
        },
      },
      series: [
        {
          name: "弹幕密度",
          type: "heatmap",
          data: this.heatmapData,
          encode: { x: 0, y: 1, value: 2 },
          progressive: 2000,
          emphasis: {
            itemStyle: {
              borderColor: "#172033",
              borderWidth: 1,
            },
          },
        },
      ],
      graphic: this.emptyGraphic(this.heatmapData.length === 0 ? "当前时段没有进度热力图数据" : ""),
    });
  },

  renderSimilarityMatrix() {
    const videos = this.similarityVideos;
    const labels = videos.map((video) => this.compactTitle(video.title || video.bvid, 14));
    const data = this.similarityCells.map((cell) => [cell[0], cell[1], Number(cell[2] || 0)]);

    this.setChartOption({
      grid: { left: 150, right: 96, top: 56, bottom: 110 },
      tooltip: {
        position: "top",
        formatter: (params) => {
          const item = params.data || [];
          const colVideo = videos[item[0]] || {};
          const rowVideo = videos[item[1]] || {};
          const detail = this.similarityDetails[`${rowVideo.id}:${colVideo.id}`] || {};
          return [
            `${escapeHtml(rowVideo.title || rowVideo.bvid || "")}`,
            `${escapeHtml(colVideo.title || colVideo.bvid || "")}`,
            `相似度: ${Number(item[2] || 0).toFixed(3)}`,
            `趋势: ${this.formatOptionalScore(detail.trendSimilarity)}`,
            `情绪: ${this.formatOptionalScore(detail.sentimentSimilarity)}`,
            `高能: ${this.formatOptionalScore(detail.highEnergySimilarity)}`,
          ].join("<br/>");
        },
      },
      toolbox: this.chartToolbox(),
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { color: "#657086", rotate: 35, interval: 0 },
        axisLine: { lineStyle: { color: "#dbe2ee" } },
      },
      yAxis: {
        type: "category",
        data: labels,
        inverse: true,
        axisLabel: { color: "#657086", interval: 0 },
        axisLine: { lineStyle: { color: "#dbe2ee" } },
      },
      visualMap: {
        min: 0,
        max: 1,
        calculable: true,
        orient: "vertical",
        right: 16,
        top: "middle",
        formatter: (value) => value.toFixed(2),
        textStyle: { color: "#657086" },
        inRange: {
          color: ["#f3f6f8", "#b9d9de", "#6aa7b4", "#1f7a8c", "#bf5b45"],
        },
      },
      series: [
        {
          name: "视频相似度",
          type: "heatmap",
          data,
          label: {
            show: true,
            formatter: (params) => Number(params.data?.[2] || 0).toFixed(2),
            color: "#172033",
            fontSize: 11,
          },
          emphasis: {
            itemStyle: {
              borderColor: "#172033",
              borderWidth: 1,
            },
          },
        },
      ],
      graphic: this.emptyGraphic(data.length === 0 ? "请选择 2-10 个视频生成相似度矩阵" : ""),
    });
  },
};
