export function nextViewAfterRecommendation(currentView) {
  return currentView
}

export function applyRecommendedConfig(targetConfig, recommendedConfig) {
  for (const key of Object.keys(targetConfig)) {
    if (Object.hasOwn(recommendedConfig, key)) {
      targetConfig[key] = recommendedConfig[key]
    }
  }
  return targetConfig
}
