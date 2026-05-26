// 文件说明：推荐候选工具：把页面输入范围转换成后端可枚举的候选列表。

import { LAYOUT_MAX_EDITABLE_SEATS } from './layoutEditor.js'

// 讲解注释：roundDownToStep() 对数值做取整或精度处理。
export function roundDownToStep(value, step) {
  return Math.max(step, Math.floor(value / step) * step)
}

// 讲解注释：roundUpToStep() 对数值做取整或精度处理。
export function roundUpToStep(value, step) {
  return Math.max(step, Math.ceil(value / step) * step)
}

// 讲解注释：createDefaultCandidateSettings() 创建默认对象或运行时辅助对象。
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

// 讲解注释：buildIntegerRange() 组装展示、请求或内部计算所需的数据结构。
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

// 讲解注释：buildCandidatesFromSettings() 组装展示、请求或内部计算所需的数据结构。
export function buildCandidatesFromSettings(settings) {
  return {
    windows: buildIntegerRange(settings.windowMin, settings.windowMax, 1, 1, 30),
    seats: buildEvenSeatRange(settings.seatMin, settings.seatMax, settings.seatStep, 2, LAYOUT_MAX_EDITABLE_SEATS),
    staggers: buildIntegerRange(settings.staggerMin, settings.staggerMax, settings.staggerStep, 0, 120),
    peakCounts: buildIntegerRange(settings.peakCountMin, settings.peakCountMax, 1, 1, 6)
  }
}

// 讲解注释：buildEvenSeatRange() 处理座位、等座或入座相关状态。
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

// 讲解注释：clamp() 把数值限制在允许范围内。
function clamp(value, lower, upper) {
  return Math.min(upper, Math.max(lower, value))
}

// 讲解注释：roundEven() 对数值做取整或精度处理。
function roundEven(value) {
  return Math.floor(value / 2) * 2
}
