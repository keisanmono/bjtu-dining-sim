export function nextViewAfterRecommendation(currentView) {
  return currentView
}

export function applyRecommendedConfig(targetConfig, recommendedConfig) {
  Object.assign(targetConfig, recommendedConfig)
  return targetConfig
}
