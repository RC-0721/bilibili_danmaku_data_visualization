var DanmakuParallelChartMethods = {
  renderParallelCoordinates() {
    const dimensions = this.parallelSelectedDimensions;
    const rows = this.parallelRows;
    if (!dimensions.length || rows.length < 2) {
      this.setChartOption({
        graphic: this.emptyGraphic(!dimensions.length ? "请选择至少 1 个画像维度" : "请选择 2-20 个视频生成画像"),
      });
      return;
    }

    const axis = dimensions.map((dimension, index) => ({
      dim: index,
      name: dimension.label,
      nameLocation: "end",
      nameGap: 18,
      axisLabel: {
        color: "#657086",
        formatter: (value) => this.formatParallelAxisValue(value, dimension),
      },
      nameTextStyle: {
        color: "#354057",
        fontWeight: 650,
      },
    }));

    const data = rows.map((row, index) => ({
      name: row.title || row.bvid,
      value: dimensions.map((dimension) => this.parallelChartValue(row, dimension)),
      raw: row,
      lineStyle: {
        color: this.parallelLineColor(row, index),
        width: 2,
        opacity: 0.72,
      },
    }));

    this.setChartOption({
      parallelAxis: axis,
      parallel: {
        left: 56,
        right: 72,
        top: 54,
        bottom: 42,
        parallelAxisDefault: {
          type: "value",
          axisLine: { lineStyle: { color: "#dbe2ee" } },
          splitLine: { show: false },
        },
      },
      tooltip: {
        trigger: "item",
        formatter: (params) => {
          const row = params.data?.raw || {};
          const lines = [
            escapeHtml(row.title || row.bvid || ""),
            `BV号: ${escapeHtml(row.bvid || "")}`,
          ];
          for (const dimension of dimensions) {
            lines.push(`${dimension.label}: ${this.formatParallelRawValue(row[dimension.key], dimension)}`);
          }
          return lines.join("<br/>");
        },
      },
      toolbox: this.chartToolbox(),
      series: [
        {
          name: "视频画像",
          type: "parallel",
          smooth: true,
          inactiveOpacity: 0.08,
          activeOpacity: 1,
          emphasis: {
            lineStyle: {
              width: 4,
              opacity: 1,
            },
          },
          data,
        },
      ],
      graphic: this.emptyGraphic(data.length === 0 ? "请选择 2-20 个视频生成画像" : ""),
    });
  },
};
