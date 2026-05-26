// 文件说明：推荐候选工具：把页面输入范围转换成后端可枚举的候选列表。

import { LAYOUT_MAX_EDITABLE_SEATS } from './layoutEditor.js'

// 将候选范围下界向下对齐到步长，且至少保留一个步长。
export function roundDownToStep(value, step) {
  return Math.max(step, Math.floor(value / step) * step)
}

// 将候选范围上界向上对齐到步长，避免漏掉边界方案。
export function roundUpToStep(value, step) {
  return Math.max(step, Math.ceil(value / step) * step)
}

// 根据当前基础配置生成推荐候选范围的默认值。
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
    staggerStep: 5,
    peakCountMin: 1,
    peakCountMax: 3
  }
}

// 按最小值、最大值和步长生成去重后的整数候选列表。
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

// 将页面候选设置转换成后端推荐接口需要的四组候选数组。
export function buildCandidatesFromSettings(settings) {
  return {
    windows: buildIntegerRange(settings.windowMin, settings.windowMax, 1, 1, 30),
    seats: buildEvenSeatRange(settings.seatMin, settings.seatMax, settings.seatStep, 2, LAYOUT_MAX_EDITABLE_SEATS),
    staggers: buildIntegerRange(settings.staggerMin, settings.staggerMax, settings.staggerStep, 0, 120),
    peakCounts: buildIntegerRange(settings.peakCountMin, settings.peakCountMax, 1, 1, 6)
  }
}

// 生成偶数座位候选，保证前端餐桌拆分能保持偶数座位。
function buildEvenSeatRange(minValue, maxValue, stepValue, lower, upper) {
  const step = Math.max(2, roundEven(Number(stepValue) || 2))
  const first = clamp(roundEven(Number(minValue) || lower), lower, upper)
  const last = clamp(roundEven(Number(maxValue) || lower), lower, upper)
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

// 将候选值限制在给定闭区间内。
function clamp(value, lower, upper) {
  return Math.min(upper, Math.max(lower, value))
}

// 将座位数向下规整为偶数。
function roundEven(value) {
  return Math.floor(value / 2) * 2
}
