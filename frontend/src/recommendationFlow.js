// 文件说明：推荐流程工具：封装应用推荐配置和推荐后页面停留策略。

// 讲解注释：nextViewAfterRecommendation() 处理优化推荐相关流程。
export function nextViewAfterRecommendation(currentView) {
  return currentView
}

// 讲解注释：applyRecommendedConfig() 处理优化推荐相关流程。
export function applyRecommendedConfig(targetConfig, recommendedConfig) {
  for (const key of Object.keys(targetConfig)) {
    if (Object.hasOwn(recommendedConfig, key)) {
      targetConfig[key] = recommendedConfig[key]
    }
  }
  return targetConfig
}
