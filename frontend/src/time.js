// 文件说明：仿真时钟工具，负责真实钟点和内部相对分钟之间的转换。

const MINUTES_PER_DAY = 24 * 60

export function formatClockMinute(value) {
  const minute = normalizeClockMinute(value)
  const hours = Math.floor(minute / 60)
  const minutes = minute % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

export function parseClockTime(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(0, Math.round(value))
  }
  const text = String(value ?? '').trim()
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(text)
  if (!match) return 0
  const hours = Math.min(23, Math.max(0, Number(match[1]) || 0))
  const minutes = Math.min(59, Math.max(0, Number(match[2]) || 0))
  return hours * 60 + minutes
}

export function clockMinuteFromRecord(record, simulationStartMinute = 0) {
  if (Number.isFinite(Number(record?.clock_minute))) {
    return Math.round(Number(record.clock_minute))
  }
  if (Number.isFinite(Number(record?.snapshot?.clock_minute))) {
    return Math.round(Number(record.snapshot.clock_minute))
  }
  return Math.max(0, Math.round(Number(simulationStartMinute) || 0)) + Math.max(0, Math.round(Number(record?.t) || 0))
}

function normalizeClockMinute(value) {
  const number = Math.round(Number(value) || 0)
  return ((number % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY
}
