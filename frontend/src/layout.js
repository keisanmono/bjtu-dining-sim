import {
  buildTableCapacities,
  createDefaultLayout,
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

export function buildLayoutFromConfig(config) {
  return createDefaultLayout(config)
}

export function buildSimulationConfigPayload(config, layout = null) {
  const effectiveLayout = isUsableLayout(layout)
    ? normalizeLayout(layout)
    : buildLayoutFromConfig(config)
  return {
    ...config,
    layout: effectiveLayout,
    party_size_distribution: partyDistributionForLayout(effectiveLayout)
  }
}

function isUsableLayout(layout) {
  return Boolean(
    layout &&
    Array.isArray(layout.doors) && layout.doors.length &&
    Array.isArray(layout.windows) && layout.windows.length &&
    Array.isArray(layout.tables) && layout.tables.length
  )
}

function normalizeLayout(layout) {
  const doors = layout.doors.map((door) => ({
    id: door.id,
    x: round1(door.x),
    y: round1(door.y),
    arrival_share: Number(door.arrival_share ?? 1)
  }))
  const windows = layout.windows.map((window) => ({
    id: window.id,
    x: round1(window.x),
    y: round1(window.y),
    service_rate_factor: Number(window.service_rate_factor ?? 1)
  }))
  const tables = layout.tables.map((table, index) => {
    const capacity = Math.max(1, Math.round(Number(table.capacity) || 1))
    return {
      id: table.id || `T${index + 1}`,
      x: round1(table.x),
      y: round1(table.y),
      capacity,
      table_type: table.table_type || tableTypeForCapacity(capacity)
    }
  })
  return { doors, windows, tables }
}

function partyDistributionForLayout(layout) {
  const maxCapacity = Math.max(1, ...layout.tables.map((table) => table.capacity))
  return Object.fromEntries(
    Object.entries(defaultPartySizeDistribution)
      .filter(([size]) => Number(size) <= maxCapacity)
      .map(([size, weight]) => [Number(size), weight])
  )
}

function round1(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return 0
  return Math.round(number * 10) / 10
}

export function totalSeatsFromLayout(layout) {
  return totalLayoutSeats(layout)
}
