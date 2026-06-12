// 文件说明：图表工具：封装 ECharts 渲染前的 DOM 尺寸判断。

// ECharts 只有在容器已挂载且有尺寸时才初始化或重绘。
export function canRenderChartElement(element) {
  return Boolean(element && element.clientWidth > 0 && element.clientHeight > 0)
}
