var DanmakuChartMethods = {
  renderChart() {
    nextTick(() => {
      if (!this.chart) return;
      if (this.analysisMode === "similarity") {
        this.renderSimilarityMatrix();
      } else if (this.analysisMode === "parallel") {
        this.renderParallelCoordinates();
      } else if (this.analysisMode === "heatmap") {
        this.renderProgressDateHeatmap();
      } else if (this.analysisMode === "words") {
        this.renderWordCloud();
      } else {
        this.renderDanmakuChart();
      }
    });
  },

  setChartOption(option) {
    this.chart.clear();
    this.chart.setOption(option, { notMerge: true });
  },

  chartToolbox() {
    return {
      right: 8,
      feature: {
        saveAsImage: {},
      },
    };
  },

  categoryAxis(dates) {
    return {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLabel: { color: "#657086" },
      axisLine: { lineStyle: { color: "#dbe2ee" } },
    };
  },

  valueAxis() {
    return {
      type: "value",
      axisLabel: { color: "#657086", formatter: (value) => this.compactNumber(value) },
      splitLine: { lineStyle: { color: "#edf1f6" } },
    };
  },

  emptyGraphic(text) {
    if (!text) return [];
    return [
      {
        type: "text",
        left: "center",
        top: "middle",
        style: {
          text,
          fill: "#657086",
          fontSize: 15,
        },
      },
    ];
  },
};
