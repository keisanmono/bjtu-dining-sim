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
  door: Object.freeze({
    horizontal: Object.freeze({ width: 52, height: 32 }),
    vertical: Object.freeze({ width: 32, height: 52 })
  }),
  window: Object.freeze({
    horizontal: Object.freeze({ width: 44, height: 32 }),
    vertical: Object.freeze({ width: 32, height: 44 })
  }),
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
  if (kind === 'window') return wallFootprintFor('window', item)
  if (kind === 'door') return wallFootprintFor('door', item)
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
  if (kind === 'door' || kind === 'window') {
    return snapWallItemPoint(x, y, kind, item)
  }
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

function defaultDoorPosition(index, layout = null, id = `D${index + 1}`) {
  const positions = [
    { wall_side: 'left', x: LAYOUT_BOUNDS.x, y: 100 },
    { wall_side: 'right', x: LAYOUT_BOUNDS.right, y: 100 },
    { wall_side: 'top', x: 310, y: LAYOUT_BOUNDS.y },
    { wall_side: 'left', x: LAYOUT_BOUNDS.x, y: 170 }
  ]
  const position = positions[index] || positions[positions.length - 1]
  const preferred = snapAndClampPoint(position.x, position.y, 'door', position)
  return firstAvailableWallPosition(layout, 'door', id, index, preferred)
}

function defaultWindowPosition(index, layout = null, id = `W${index + 1}`) {
  // Windows are service openings on walls, so defaults occupy wall slots.
  const topSlots = [70, 130, 190, 250, 310]
  if (index < topSlots.length) {
    const preferred = snapAndClampPoint(topSlots[index], LAYOUT_BOUNDS.y, 'window', { wall_side: 'top' })
    return firstAvailableWallPosition(layout, 'window', id, index, preferred)
  }
  const rightSlots = [100, 170]
  const rightIndex = index - topSlots.length
  if (rightIndex < rightSlots.length) {
    const preferred = snapAndClampPoint(LAYOUT_BOUNDS.right, rightSlots[rightIndex], 'window', { wall_side: 'right' })
    return firstAvailableWallPosition(layout, 'window', id, index, preferred)
  }
  const leftSlots = [170, 100]
  const leftIndex = rightIndex - rightSlots.length
  if (leftIndex < leftSlots.length) {
    const preferred = snapAndClampPoint(LAYOUT_BOUNDS.x, leftSlots[leftIndex], 'window', { wall_side: 'left' })
    return firstAvailableWallPosition(layout, 'window', id, index, preferred)
  }
  const bottomIndex = leftIndex - leftSlots.length
  const preferred = snapAndClampPoint(70 + (bottomIndex % 5) * 60, LAYOUT_BOUNDS.bottom, 'window', { wall_side: 'bottom' })
  return firstAvailableWallPosition(layout, 'window', id, index, preferred)
}

function defaultTablePosition(index, capacity) {
  // Four columns fit the largest table footprint without horizontal overlap.
  const cols = 4
  const col = index % cols
  const row = Math.floor(index / cols)
  return snapAndClampPoint(70 + col * 70, 240 + row * 50, 'table', { capacity })
}

function firstAvailableWallPosition(layout, kind, id, seedIndex, preferred) {
  if (!layout) return preferred
  if (!itemOverlapsLayout(layout, kind, id, preferred.x, preferred.y, { id, ...preferred })) {
    return preferred
  }
  const candidates = wallCandidatePoints()
  const start = candidates.length ? seedIndex % candidates.length : 0
  for (let offset = 0; offset < candidates.length; offset += 1) {
    const candidate = candidates[(start + offset) % candidates.length]
    const point = snapAndClampPoint(candidate.x, candidate.y, kind, candidate)
    if (!itemOverlapsLayout(layout, kind, id, point.x, point.y, { id, ...point })) {
      return point
    }
  }
  return preferred
}

function wallCandidatePoints() {
  const points = []
  for (let x = 50; x <= 310; x += 60) {
    points.push({ wall_side: 'top', x, y: LAYOUT_BOUNDS.y })
  }
  for (let y = 50; y <= 590; y += 60) {
    points.push({ wall_side: 'right', x: LAYOUT_BOUNDS.right, y })
  }
  for (let x = 310; x >= 50; x -= 60) {
    points.push({ wall_side: 'bottom', x, y: LAYOUT_BOUNDS.bottom })
  }
  for (let y = 590; y >= 50; y -= 60) {
    points.push({ wall_side: 'left', x: LAYOUT_BOUNDS.x, y })
  }
  return points
}

export function createDefaultLayout(config) {
  const numWindows = clampInteger(config?.num_windows, 1, 30)
  const numSeats = clampInteger(config?.num_seats, 1, LAYOUT_MAX_EDITABLE_SEATS)
  const tables = buildTableCapacities(numSeats).map((capacity, index) => ({
    id: `T${index + 1}`,
    capacity,
    table_type: tableTypeForCapacity(capacity),
    ...defaultTablePosition(index, capacity)
  }))
  const doors = []
  let draft = { doors, windows: [], tables }
  doors.push({
    id: 'D1',
    arrival_share: 1,
    ...defaultDoorPosition(0, draft, 'D1')
  })
  draft = { ...draft, doors }
  const windows = []
  for (let index = 0; index < numWindows; index += 1) {
    const id = `W${index + 1}`
    windows.push({
      id,
      service_rate_factor: 1,
      ...defaultWindowPosition(index, { ...draft, windows }, id)
    })
  }
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
    const id = nextWindowId(current.concat(additional))
    additional.push({
      id,
      service_rate_factor: 1,
      ...defaultWindowPosition(index, { ...layout, windows: [...current, ...additional] }, id)
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
    const id = nextDoorId(current.concat(additional))
    additional.push({
      id,
      arrival_share: 1,
      ...defaultDoorPosition(index, { ...layout, doors: [...current, ...additional] }, id)
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

export function setItemPosition(layout, kind, id, x, y, options = {}) {
  const collection = collectionKeyForKind(kind)
  if (!collection) return layout
  const allowOverlap = Boolean(options.allowOverlap)
  const items = layout[collection].map((item) => {
    if (item.id !== id) return item
    const point = snapAndClampPoint(x, y, kind, item)
    const movedItem = { ...item, x: point.x, y: point.y, ...wallSidePatch(kind, point) }
    if (!allowOverlap && itemOverlapsLayout(layout, kind, id, point.x, point.y, movedItem)) {
      return item
    }
    return movedItem
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

function snapWallItemPoint(x, y, kind, item) {
  const wallSide = nearestWallSide(x, y)
  const footprint = getItemFootprint(kind, { ...item, wall_side: wallSide })
  const halfW = footprint.width / 2
  const halfH = footprint.height / 2
  if (wallSide === 'top') {
    return {
      x: snapInsideRange(x, LAYOUT_BOUNDS.x + halfW, LAYOUT_BOUNDS.right - halfW),
      y: LAYOUT_BOUNDS.y + halfH,
      wall_side: wallSide
    }
  }
  if (wallSide === 'right') {
    return {
      x: LAYOUT_BOUNDS.right - halfW,
      y: snapInsideRange(y, LAYOUT_BOUNDS.y + halfH, LAYOUT_BOUNDS.bottom - halfH),
      wall_side: wallSide
    }
  }
  if (wallSide === 'bottom') {
    return {
      x: snapInsideRange(x, LAYOUT_BOUNDS.x + halfW, LAYOUT_BOUNDS.right - halfW),
      y: LAYOUT_BOUNDS.bottom - halfH,
      wall_side: wallSide
    }
  }
  return {
    x: LAYOUT_BOUNDS.x + halfW,
    y: snapInsideRange(y, LAYOUT_BOUNDS.y + halfH, LAYOUT_BOUNDS.bottom - halfH),
    wall_side: wallSide
  }
}

function nearestWallSide(x, y) {
  const distances = [
    { wall_side: 'top', value: Math.abs(y - LAYOUT_BOUNDS.y) },
    { wall_side: 'right', value: Math.abs(x - LAYOUT_BOUNDS.right) },
    { wall_side: 'bottom', value: Math.abs(y - LAYOUT_BOUNDS.bottom) },
    { wall_side: 'left', value: Math.abs(x - LAYOUT_BOUNDS.x) }
  ]
  return distances.reduce((nearest, candidate) => (
    candidate.value < nearest.value ? candidate : nearest
  )).wall_side
}

function wallFootprintFor(kind, item) {
  const side = normalizeWallSide(item?.wall_side, kind === 'door' ? 'left' : 'top')
  return side === 'top' || side === 'bottom'
    ? FOOTPRINTS[kind].horizontal
    : FOOTPRINTS[kind].vertical
}

function normalizeWallSide(side, fallback) {
  return ['top', 'right', 'bottom', 'left'].includes(side) ? side : fallback
}

function wallSidePatch(kind, point) {
  if (kind !== 'door' && kind !== 'window') return {}
  return { wall_side: point.wall_side }
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
