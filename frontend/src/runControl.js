// 文件说明：实时运行控制工具：封装单步重置、步进延迟和请求条件判断。

export const AUTO_STEP_BUFFER_MS = 80

// 没有 run_id 或用户明确 reset 时，下一次 step 必须携带完整配置新建运行。
export function shouldResetStepRun(resetRequest, runId) {
  return resetRequest === true || !runId
}

// 自动步进延迟等于地图过渡时长加一个缓冲，避免动画被下一帧打断。
export function liveStepDelay(transitionMs, bufferMs = AUTO_STEP_BUFFER_MS) {
  const transition = Math.max(0, Math.round(Number(transitionMs) || 0))
  const buffer = Math.max(0, Math.round(Number(bufferMs) || 0))
  return transition + buffer
}

// 只有正在运行、未完成且没有请求在途时才允许发起下一次实时 step。
export function shouldRequestLiveStep({ isRunning = false, isDone = false, stepInFlight = false } = {}) {
  return Boolean(isRunning) && !isDone && !stepInFlight
}
