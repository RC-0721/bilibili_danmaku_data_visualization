var DanmakuTrendWordChartMethods = {
  renderDanmakuChart() {
    const rows = this.chartRows;
    const values = rows.map((row) => row[this.metric]);
    const dates = rows.map((row) => row.date);

    this.setChartOption({
      color: ["#1f7a8c"],
      grid: { left: 60, right: 28, top: 42, bottom: 42 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value) => this.formatNumber(value),
      },
      toolbox: this.chartToolbox(),
      xAxis: this.categoryAxis(dates),
      yAxis: this.valueAxis(),
      series: [
        {
          name: this.metricLabel,
          type: "line",
          data: values,
          smooth: true,
          showSymbol: false,
          showAllSymbol: false,
          lineStyle: { width: 3 },
          areaStyle: { color: "rgba(31, 122, 140, 0.12)" },
          emphasis: { focus: "series" },
        },
      ],
      graphic: this.emptyGraphic(rows.length === 0 ? "当前时段没有弹幕数据" : ""),
    });
  },

  renderWordCloud() {
    const data = this.wordCloudRows.map((row, index) => ({
      name: row.name,
      value: row.value,
      phrases: row.phrases || [],
      textStyle: { color: WORD_COLORS[index % WORD_COLORS.length] },
    }));

    this.setChartOption({
      tooltip: {
        formatter: (params) => {
          const phrases = params.data?.phrases || [];
          const phraseHtml = phrases.length
            ? `<br/>对应短语:<br/>${phrases.map((phrase) => escapeHtml(phrase)).join("<br/>")}`
            : "";
          return `${escapeHtml(params.name)}<br/>${this.formatNumber(params.value)} 次${phraseHtml}`;
        },
      },
      series: [
        {
          type: "wordCloud",
          shape: "circle",
          keepAspect: false,
          left: "center",
          top: "center",
          width: "94%",
          height: "90%",
          sizeRange: [12, 58],
          rotationRange: [-25, 25],
          rotationStep: 5,
          gridSize: 8,
          drawOutOfBound: false,
          data,
        },
      ],
      graphic: this.emptyGraphic(data.length === 0 ? "当前时段没有分词数据" : ""),
    });
  },
};
