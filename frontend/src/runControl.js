// 文件说明：实时运行控制工具：封装单步重置、步进延迟和请求条件判断。

export const AUTO_STEP_BUFFER_MS = 80

// 讲解注释：shouldResetStepRun() 封装本文件中的一个独立处理步骤。
export function shouldResetStepRun(resetRequest, runId) {
  return resetRequest === true || !runId
}

// 讲解注释：liveStepDelay() 封装本文件中的一个独立处理步骤。
export function liveStepDelay(transitionMs, bufferMs = AUTO_STEP_BUFFER_MS) {
  const transition = Math.max(0, Math.round(Number(transitionMs) || 0))
  const buffer = Math.max(0, Math.round(Number(bufferMs) || 0))
  return transition + buffer
}

// 讲解注释：shouldRequestLiveStep() 封装本文件中的一个独立处理步骤。
export function shouldRequestLiveStep({ isRunning = false, isDone = false, stepInFlight = false } = {}) {
  return Boolean(isRunning) && !isDone && !stepInFlight
}
