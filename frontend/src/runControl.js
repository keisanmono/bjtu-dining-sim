export const AUTO_STEP_BUFFER_MS = 80

export function shouldResetStepRun(resetRequest, runId) {
  return resetRequest === true || !runId
}

export function liveStepDelay(transitionMs, bufferMs = AUTO_STEP_BUFFER_MS) {
  const transition = Math.max(0, Math.round(Number(transitionMs) || 0))
  const buffer = Math.max(0, Math.round(Number(bufferMs) || 0))
  return transition + buffer
}

export function shouldRequestLiveStep({ isRunning = false, isDone = false, stepInFlight = false } = {}) {
  return Boolean(isRunning) && !isDone && !stepInFlight
}
