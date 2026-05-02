// Pure helpers for the editable cafeteria floor plan.
//
// Coordinates use the SVG viewBox 0 0 360 640. Each draggable item stores
// its center coordinates. Items are kept inside `LAYOUT_BOUNDS` (the inner
// floor area) and snapped to a fixed grid step so dragging produces clean,
// reproducible positions that the backend simulation can interpret.

export const LAYOUT_VIEWBOX = Object.freeze({ width: 360, height: 640 })
export const LAYOUT_GRID_STEP = 10
export const LAYOUT_BOUNDS = Object.freeze({ x: 24, y: 24, right: 336, bottom: 616 })
export const LAYOUT_MAX_EDITABLE_SEATS = 180
export const LAYOUT_MAX_DOORS = 4
export const LAYOUT_ITEM_GAP = 4

export const TABLE_CAPACITY_OPTIONS = [2, 4, 6]

const TABLE_PATTERN = [2, 4, 4, 6]
const DENSE_TABLE_THRESHOLD_SEATS = 120

const FOOTPRINTS = Object.freeze({
  door: Object.freeze({ width: 28, height: 52 }),
  window: Object.freeze({ width: 40, height: 28 }),
  table: Object.freeze({
    2: Object.freeze({ width: 52, height: 26 }),
    4: Object.freeze({ width: 60, height: 48 }),
    6: Object.freeze({ width: 70, height: 48 })
  })
})

export function tableTypeForCapacity(capacity) {
  const value = Math.max(1, Number(capacity) || 1)
  if (value <= 1) return 'single_seat'
  if (value <= 2) return 'two_seat'
  if (value <= 4) return 'four_seat'
  return 'six_seat'
}

export function buildTableCapacities(numSeats) {
  let remaining = clampInteger(numSeats, 1, LAYOUT_MAX_EDITABLE_SEATS)
  const capacities = []
  let index = 0
  if (remaining > DENSE_TABLE_THRESHOLD_SEATS) {
    while (remaining > 0) {
      const capacity = Math.min(6, remaining)
      capacities.push(capacity)
      remaining -= capacity
    }
    return capacities
  }
  while (remaining > 0) {
    const capacity = Math.min(TABLE_PATTERN[index % TABLE_PATTERN.length], remaining)
    capacities.push(capacity)
    remaining -= capacity
    index += 1
  }
  return capacities
}

export function getItemFootprint(kind, item) {
  if (kind === 'window') return FOOTPRINTS.window
  if (kind === 'door') return FOOTPRINTS.door
  if (kind === 'table') {
    const capacity = Math.max(1, Number(item?.capacity) || 1)
    if (capacity <= 2) return FOOTPRINTS.table[2]
    if (capacity <= 4) return FOOTPRINTS.table[4]
    return FOOTPRINTS.table[6]
  }
  return { width: 20, height: 20 }
}

export function snapToGrid(value, step = LAYOUT_GRID_STEP) {
  const safeStep = Math.max(1, Number(step) || LAYOUT_GRID_STEP)
  return Math.round(Number(value) / safeStep) * safeStep
}

export function clampToBounds(x, y, footprint, bounds = LAYOUT_BOUNDS) {
  const halfW = (footprint?.width || 20) / 2
  const halfH = (footprint?.height || 20) / 2
  return {
    x: Math.max(bounds.x + halfW, Math.min(bounds.right - halfW, x)),
    y: Math.max(bounds.y + halfH, Math.min(bounds.bottom - halfH, y))
  }
}

function snapInsideRange(value, lower, upper, step = LAYOUT_GRID_STEP) {
  const snapped = snapToGrid(value, step)
  if (snapped < lower) {
    return Math.ceil(lower / step) * step
  }
  if (snapped > upper) {
    return Math.floor(upper / step) * step
  }
  return snapped
}

export function snapAndClampPoint(x, y, kind, item) {
  const footprint = getItemFootprint(kind, item)
  const halfW = footprint.width / 2
  const halfH = footprint.height / 2
  return {
    x: snapInsideRange(x, LAYOUT_BOUNDS.x + halfW, LAYOUT_BOUNDS.right - halfW),
    y: snapInsideRange(y, LAYOUT_BOUNDS.y + halfH, LAYOUT_BOUNDS.bottom - halfH)
  }
}

export function totalLayoutSeats(layout) {
  return (layout?.tables || []).reduce((sum, table) => sum + (Number(table.capacity) || 0), 0)
}

function clampInteger(value, lower, upper) {
  return Math.min(upper, Math.max(lower, Math.round(Number(value) || lower)))
}

function defaultDoorPosition(index) {
  const positions = [
    { x: 40, y: 120 },
    { x: 320, y: 40 },
    { x: 40, y: 40 },
    { x: 320, y: 180 }
  ]
  const position = positions[index] || positions[positions.length - 1]
  return snapAndClampPoint(position.x, position.y, 'door', null)
}

function defaultWindowPosition(index) {
  // Lay windows out as a counter row (or two) along the upper portion.
  const cols = 4
  const col = index % cols
  const row = Math.floor(index / cols)
  return snapAndClampPoint(80 + col * 60, 80 + row * 50, 'window', null)
}

function defaultTablePosition(index, capacity) {
  // Four columns fit the largest table footprint without horizontal overlap.
  const cols = 4
  const col = index % cols
  const row = Math.floor(index / cols)
  return snapAndClampPoint(70 + col * 70, 240 + row * 50, 'table', { capacity })
}

export function createDefaultLayout(config) {
  const numWindows = clampInteger(config?.num_windows, 1, 30)
  const numSeats = clampInteger(config?.num_seats, 1, LAYOUT_MAX_EDITABLE_SEATS)
  const doors = [{
    id: 'D1',
    arrival_share: 1,
    ...defaultDoorPosition(0)
  }]
  const windows = Array.from({ length: numWindows }, (_unused, index) => ({
    id: `W${index + 1}`,
    service_rate_factor: 1,
    ...defaultWindowPosition(index)
  }))
  const tables = buildTableCapacities(numSeats).map((capacity, index) => ({
    id: `T${index + 1}`,
    capacity,
    table_type: tableTypeForCapacity(capacity),
    ...defaultTablePosition(index, capacity)
  }))
  return { doors, windows, tables }
}

export function adjustLayoutWindowCount(layout, desiredCount) {
  const target = clampInteger(desiredCount, 1, 30)
  const current = layout?.windows || []
  if (current.length === target) {
    return layout
  }
  if (current.length > target) {
    return { ...layout, windows: current.slice(0, target) }
  }
  const additional = []
  for (let index = current.length; index < target; index += 1) {
    additional.push({
      id: nextWindowId(current.concat(additional)),
      service_rate_factor: 1,
      ...defaultWindowPosition(index)
    })
  }
  return { ...layout, windows: [...current, ...additional] }
}

export function adjustLayoutDoorCount(layout, desiredCount) {
  const target = clampInteger(desiredCount, 1, LAYOUT_MAX_DOORS)
  const current = layout?.doors || []
  if (current.length === target) {
    return layout
  }
  if (current.length > target) {
    return { ...layout, doors: current.slice(0, target) }
  }
  const additional = []
  for (let index = current.length; index < target; index += 1) {
    additional.push({
      id: nextDoorId(current.concat(additional)),
      arrival_share: 1,
      ...defaultDoorPosition(index)
    })
  }
  return { ...layout, doors: [...current, ...additional] }
}

export function rebuildLayoutTablesForSeats(layout, numSeats) {
  const capacities = buildTableCapacities(numSeats)
  const tables = capacities.map((capacity, index) => ({
    id: `T${index + 1}`,
    capacity,
    table_type: tableTypeForCapacity(capacity),
    ...defaultTablePosition(index, capacity)
  }))
  return { ...layout, tables }
}

export function setItemPosition(layout, kind, id, x, y) {
  const collection = collectionKeyForKind(kind)
  if (!collection) return layout
  const items = layout[collection].map((item) => {
    if (item.id !== id) return item
    const point = snapAndClampPoint(x, y, kind, item)
    if (itemOverlapsLayout(layout, kind, id, point.x, point.y, item)) {
      return item
    }
    return { ...item, x: point.x, y: point.y }
  })
  return { ...layout, [collection]: items }
}

export function setTableCapacity(layout, id, capacity) {
  const sanitized = sanitizeCapacity(capacity)
  const tables = (layout?.tables || []).map((table) => {
    if (table.id !== id) return table
    const point = snapAndClampPoint(table.x, table.y, 'table', { ...table, capacity: sanitized })
    if (itemOverlapsLayout(layout, 'table', id, point.x, point.y, { ...table, capacity: sanitized })) {
      return table
    }
    return {
      ...table,
      capacity: sanitized,
      table_type: tableTypeForCapacity(sanitized),
      x: point.x,
      y: point.y
    }
  })
  return { ...layout, tables }
}

export function itemOverlapsLayout(layout, kind, id, x, y, itemOverride = null) {
  const movingItem = itemOverride || findItem(layout, kind, id)
  if (!movingItem) return false
  const movingBox = itemBounds(kind, { ...movingItem, x, y })
  return allLayoutItems(layout).some((candidate) => {
    if (candidate.kind === kind && candidate.item.id === id) return false
    return boxesOverlap(movingBox, itemBounds(candidate.kind, candidate.item))
  })
}

export function itemBounds(kind, item) {
  const footprint = getItemFootprint(kind, item)
  const gap = LAYOUT_ITEM_GAP / 2
  return {
    left: item.x - footprint.width / 2 - gap,
    right: item.x + footprint.width / 2 + gap,
    top: item.y - footprint.height / 2 - gap,
    bottom: item.y + footprint.height / 2 + gap
  }
}

export function findItem(layout, kind, id) {
  const collection = collectionKeyForKind(kind)
  if (!collection) return null
  return (layout?.[collection] || []).find((item) => item.id === id) || null
}

export function reorderTableIds(layout) {
  const tables = (layout?.tables || []).map((table, index) => ({
    ...table,
    id: `T${index + 1}`
  }))
  return { ...layout, tables }
}

function sanitizeCapacity(capacity) {
  const value = clampInteger(capacity, 1, 12)
  if (TABLE_CAPACITY_OPTIONS.includes(value)) return value
  if (value <= 2) return 2
  if (value <= 4) return 4
  return 6
}

function collectionKeyForKind(kind) {
  if (kind === 'door') return 'doors'
  if (kind === 'window') return 'windows'
  if (kind === 'table') return 'tables'
  return null
}

function allLayoutItems(layout) {
  return [
    ...(layout?.doors || []).map((item) => ({ kind: 'door', item })),
    ...(layout?.windows || []).map((item) => ({ kind: 'window', item })),
    ...(layout?.tables || []).map((item) => ({ kind: 'table', item }))
  ]
}

function boxesOverlap(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}

function nextDoorId(existing) {
  const usedIndices = new Set(
    existing
      .map((item) => Number(String(item.id || '').replace(/^D/, '')))
      .filter((value) => Number.isFinite(value))
  )
  let candidate = 1
  while (usedIndices.has(candidate)) candidate += 1
  return `D${candidate}`
}

function nextWindowId(existing) {
  const usedIndices = new Set(
    existing
      .map((item) => Number(String(item.id || '').replace(/^W/, '')))
      .filter((value) => Number.isFinite(value))
  )
  let candidate = 1
  while (usedIndices.has(candidate)) candidate += 1
  return `W${candidate}`
}
