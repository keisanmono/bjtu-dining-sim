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
    staggerMin: 0,
    staggerMax: 10,
    staggerStep: 5
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
    staggers: buildIntegerRange(settings.staggerMin, settings.staggerMax, settings.staggerStep, 0, 120)
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

export function buildConfigCandidateGroups(windowCandidates, seatCandidates, staggerCandidates) {
  return [
    {
      key: 'windows',
      label: '窗口',
      field: 'num_windows',
      values: windowCandidates.map((value) => ({ value, label: `${value} 个` }))
    },
    {
      key: 'seats',
      label: '座位',
      field: 'num_seats',
      values: seatCandidates.map((value) => ({ value, label: `${value} 个` }))
    },
    {
      key: 'stagger',
      label: '错峰',
      field: 'stagger_minutes',
      values: staggerCandidates.map((value) => ({ value, label: formatStaggerCandidate(value) }))
    }
  ]
}

function clamp(value, lower, upper) {
  return Math.min(upper, Math.max(lower, value))
}
