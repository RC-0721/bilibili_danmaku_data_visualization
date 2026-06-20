const { createApp, nextTick } = Vue;

createApp({
  data: createDanmakuAppState,
  computed: DanmakuComputed,
  watch: DanmakuWatchers,

  async mounted() {
    this.chart = echarts.init(this.$refs.chartEl);
    window.addEventListener("resize", this.resizeChart);
    await this.loadVideos();
  },

  beforeUnmount() {
    window.removeEventListener("resize", this.resizeChart);
    this.chart?.dispose();
  },

  methods: {
    ...DanmakuDataMethods,
    ...DanmakuChartMethods,
    ...DanmakuTrendWordChartMethods,
    ...DanmakuHeatmapSimilarityChartMethods,
    ...DanmakuParallelChartMethods,
    ...DanmakuUiMethods,
  },
}).mount("#app");
