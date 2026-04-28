export function formatStaggerCandidate(minutes) {
  return minutes === 0 ? '不启用' : `${minutes} 分钟`
}

export function roundDownToStep(value, step) {
  return Math.max(step, Math.floor(value / step) * step)
}

export function roundUpToStep(value, step) {
  return Math.max(step, Math.ceil(value / step) * step)
}

export function createDefaultCandidateSettings(config) {
  const seatStep = 20
  return {
    windowMin: Math.max(1, Number(config.num_windows || 1) - 1),
    windowMax: Math.min(30, Number(config.num_windows || 1) + 2),
    seatMin: roundDownToStep(Number(config.num_seats || seatStep) * 0.75, seatStep),
    seatMax: roundUpToStep(Number(config.num_seats || seatStep) * 1.25, seatStep),
    seatStep,
    staggers: [0, 5, 10]
  }
}

export function buildIntegerRange(minValue, maxValue, stepValue = 1, lower = 1, upper = 2000) {
  const step = Math.max(1, Math.round(Number(stepValue) || 1))
  const first = clamp(Math.round(Number(minValue) || lower), lower, upper)
  const last = clamp(Math.round(Number(maxValue) || lower), lower, upper)
  const start = Math.min(first, last)
  const end = Math.max(first, last)
  const values = []

  for (let value = start; value <= end; value += step) {
    values.push(value)
  }
  if (values.at(-1) !== end) {
    values.push(end)
  }
  return [...new Set(values)]
}

export function buildCandidatesFromSettings(settings) {
  return {
    windows: buildIntegerRange(settings.windowMin, settings.windowMax, 1, 1, 30),
    seats: buildIntegerRange(settings.seatMin, settings.seatMax, settings.seatStep, 1, 2000),
    staggers: [...new Set((settings.staggers || []).map(Number))]
      .filter((value) => value >= 0 && value <= 120)
      .sort((a, b) => a - b)
  }
}

export function buildCandidateGroups(windowCandidates, seatCandidates, staggerCandidates) {
  return [
    {
      key: 'windows',
      label: '窗口',
      values: windowCandidates.map((value) => `${value} 个`)
    },
    {
      key: 'seats',
      label: '座位',
      values: seatCandidates.map((value) => `${value} 个`)
    },
    {
      key: 'stagger',
      label: '错峰',
      values: staggerCandidates.map(formatStaggerCandidate)
    }
  ]
}

function clamp(value, lower, upper) {
  return Math.min(upper, Math.max(lower, value))
}
