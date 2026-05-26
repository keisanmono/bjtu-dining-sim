// 文件说明：图表工具：封装 ECharts 渲染前的 DOM 尺寸判断。

// 讲解注释：canRenderChartElement() 封装本文件中的一个独立处理步骤。
export function canRenderChartElement(element) {
  return Boolean(element && element.clientWidth > 0 && element.clientHeight > 0)
}
