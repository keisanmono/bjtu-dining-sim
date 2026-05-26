// 文件说明：布局请求转换工具：把前端布局和基础参数整理成后端 SimulationConfig。

import {
  buildTableCapacities,
  createDefaultLayout,
  normalizeTableRotation,
  tableTypeForCapacity,
  totalLayoutSeats
} from './layoutEditor.js'

export const defaultPartySizeDistribution = {
  1: 0.55,
  2: 0.30,
  3: 0.08,
  4: 0.04,
  5: 0.02,
  6: 0.01
}

export { buildTableCapacities, tableTypeForCapacity }

// 根据当前参数生成一份可直接提交给后端的默认布局。
export function buildLayoutFromConfig(config) {
  return createDefaultLayout(config)
}

// buildSimulationConfigPayload() 把页面配置和布局整理为后端仿真接口请求体。
export function buildSimulationConfigPayload(config, layout = null) {
  const effectiveLayout = isUsableLayout(layout)
    ? normalizeLayout(layout)
    : buildLayoutFromConfig(config)
  return {
    ...config,
    num_seats: totalLayoutSeats(effectiveLayout),
    num_windows: effectiveLayout.windows.length,
    layout: effectiveLayout,
    party_size_distribution: partyDistributionForLayout(effectiveLayout)
  }
}

// 判断布局是否包含仿真必需的入口、窗口和餐桌。
function isUsableLayout(layout) {
  return Boolean(
    layout &&
    Array.isArray(layout.doors) && layout.doors.length &&
    Array.isArray(layout.windows) && layout.windows.length &&
    Array.isArray(layout.tables) && layout.tables.length
  )
}

// 清洗布局坐标、容量和旋转角，输出后端 schema 可接收的字段。
function normalizeLayout(layout) {
  const doors = layout.doors.map((door) => ({
    id: door.id,
    x: round1(door.x),
    y: round1(door.y),
    ...(door.wall_side ? { wall_side: door.wall_side } : {}),
    arrival_share: Number(door.arrival_share ?? 1)
  }))
  const windows = layout.windows.map((window) => ({
    id: window.id,
    x: round1(window.x),
    y: round1(window.y),
    ...(window.wall_side ? { wall_side: window.wall_side } : {}),
    service_rate_factor: Number(window.service_rate_factor ?? 1)
  }))
  const tables = layout.tables.map((table, index) => {
    const capacity = Math.max(1, Math.round(Number(table.capacity) || 1))
    return {
      id: table.id || `T${index + 1}`,
      x: round1(table.x),
      y: round1(table.y),
      capacity,
      table_type: table.table_type || tableTypeForCapacity(capacity),
      rotation: normalizeTableRotation(table.rotation)
    }
  })
  return { doors, windows, tables }
}

// 根据最大餐桌容量裁剪结伴人数分布，避免出现坐不下的小组。
function partyDistributionForLayout(layout) {
  const maxCapacity = Math.max(1, ...layout.tables.map((table) => table.capacity))
  return Object.fromEntries(
    Object.entries(defaultPartySizeDistribution)
      .filter(([size]) => Number(size) <= maxCapacity)
      .map(([size, weight]) => [Number(size), weight])
  )
}

// 将布局坐标保留一位小数，减少请求体中的浮点噪声。
function round1(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return 0
  return Math.round(number * 10) / 10
}

// 对外暴露布局总座位数，内部复用布局编辑器的统计函数。
export function totalSeatsFromLayout(layout) {
  return totalLayoutSeats(layout)
}
