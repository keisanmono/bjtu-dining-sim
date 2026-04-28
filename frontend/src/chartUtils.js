export function canRenderChartElement(element) {
  return Boolean(element && element.clientWidth > 0 && element.clientHeight > 0)
}
