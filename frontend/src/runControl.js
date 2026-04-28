export function shouldResetStepRun(resetRequest, runId) {
  return resetRequest === true || !runId
}
