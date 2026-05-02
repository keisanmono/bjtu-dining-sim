import { LAYOUT_MAX_EDITABLE_SEATS } from './layoutEditor.js'

export function roundDownToStep(value, step) {
  return Math.max(step, Math.floor(value / step) * step)
}

export function roundUpToStep(value, step) {
  return Math.max(step, Math.ceil(value / step) * step)
}

export function createDefaultCandidateSettings(config) {
  const seatStep = 20
  const baselineSeats = Math.min(LAYOUT_MAX_EDITABLE_SEATS, Number(config.num_seats || seatStep))
  return {
    windowMin: Math.max(1, Number(config.num_windows || 1) - 1),
    windowMax: Math.min(30, Number(config.num_windows || 1) + 2),
    seatMin: Math.min(LAYOUT_MAX_EDITABLE_SEATS, roundDownToStep(baselineSeats * 0.75, seatStep)),
    seatMax: Math.min(LAYOUT_MAX_EDITABLE_SEATS, roundUpToStep(baselineSeats * 1.25, seatStep)),
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
    seats: buildIntegerRange(settings.seatMin, settings.seatMax, settings.seatStep, 1, LAYOUT_MAX_EDITABLE_SEATS),
    staggers: buildIntegerRange(settings.staggerMin, settings.staggerMax, settings.staggerStep, 0, 120)
  }
}

function clamp(value, lower, upper) {
  return Math.min(upper, Math.max(lower, value))
}
