// 文件说明：推荐流程工具：封装应用推荐配置和推荐后页面停留策略。

// 生成推荐后仍停留在当前页面，由调用方决定是否切换 tab。
export function nextViewAfterRecommendation(currentView) {
  return currentView
}

// 只复制基础配置中已存在的字段，避免推荐响应中的额外字段污染页面状态。
export function applyRecommendedConfig(targetConfig, recommendedConfig) {
  for (const key of Object.keys(targetConfig)) {
    if (Object.hasOwn(recommendedConfig, key)) {
      // 只覆盖页面已经声明过的配置键，忽略后端 best/config 里的派生字段。
      targetConfig[key] = recommendedConfig[key]
    }
  }
  return targetConfig
}
