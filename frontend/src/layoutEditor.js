// Pure helpers for the editable cafeteria floor plan.
//
// Coordinates live in the cafeteria world space. LAYOUT_VIEWBOX is only the
// default camera frame; the floor can be larger than it and the SVG viewport
// can pan/zoom over that world space.

export const LAYOUT_VIEWBOX = Object.freeze({ width: 360, height: 640 })
export const LAYOUT_GRID_STEP = 10
export const LAYOUT_BOUNDS = Object.freeze({ x: 24, y: 24, right: 336, bottom: 616 })
export const LAYOUT_DEFAULT_FLOOR = Object.freeze({
  x: LAYOUT_BOUNDS.x,
  y: LAYOUT_BOUNDS.y,
  width: LAYOUT_BOUNDS.right - LAYOUT_BOUNDS.x,
  height: LAYOUT_BOUNDS.bottom - LAYOUT_BOUNDS.y
})
export const LAYOUT_MAX_EDITABLE_SEATS = 2000
export const LAYOUT_MAX_FLOOR_AREA = 2200 * 2600
export const LAYOUT_SIZE_LIMITS = Object.freeze({
  width: Object.freeze({ min: 220, max: null }),
  height: Object.freeze({ min: 320, max: null }),
  maxArea: LAYOUT_MAX_FLOOR_AREA,
  step: 20
})
export const LAYOUT_VIEWPORT_MARGIN = 32
export const LAYOUT_ZOOM_LIMITS = Object.freeze({
  minWidth: 140,
  minHeight: 120,
  maxWidth: null,
  maxHeight: null
})
export const LAYOUT_MAX_DOORS = 4
export const LAYOUT_ITEM_GAP = 2

export const TABLE_CAPACITY_OPTIONS = [2, 4, 6]

const TABLE_PATTERN = [2, 4, 4, 6]
const DENSE_TABLE_THRESHOLD_SEATS = 120
const COMPACT_TABLE_COLUMN_STEP = 80
const COMPACT_TABLE_ROW_STEP = 52

const FOOTPRINTS = Object.freeze({
  door: Object.freeze({
    horizontal: Object.freeze({ width: 52, height: 32 }),
    vertical: Object.freeze({ width: 32, height: 52 })
  }),
  window: Object.freeze({
    horizontal: Object.freeze({ width: 36, height: 32 }),
    vertical: Object.freeze({ width: 32, height: 36 })
  }),
  table: Object.freeze({
    2: Object.freeze({ width: 52, height: 26 }),
    4: Object.freeze({ width: 64, height: 50 }),
    6: Object.freeze({ width: 76, height: 50 })
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
  let remaining = normalizeSeatCount(numSeats, LAYOUT_MAX_EDITABLE_SEATS)
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

export function normalizeSeatCount(value, upper = LAYOUT_MAX_EDITABLE_SEATS) {
  const boundedUpper = Math.max(2, toEven(Math.min(LAYOUT_MAX_EDITABLE_SEATS, Number(upper) || LAYOUT_MAX_EDITABLE_SEATS)))
  const bounded = Math.min(boundedUpper, Math.max(2, Math.floor(Number(value) || 2)))
  return Math.max(2, toEven(bounded))
}

export function floorBoundsForLayout(layout) {
  const floor = sanitizeFloorSize(layout?.floor || layout)
  return {
    x: floor.x,
    y: floor.y,
    right: floor.x + floor.width,
    bottom: floor.y + floor.height
  }
}

export function fitViewBoxForLayout(layout, margin = LAYOUT_VIEWPORT_MARGIN) {
  const bounds = floorBoundsForLayout(layout)
  const floorWidth = bounds.right - bounds.x
  const floorHeight = bounds.bottom - bounds.y
  const width = Math.max(LAYOUT_VIEWBOX.width, floorWidth + margin * 2)
  const height = Math.max(LAYOUT_VIEWBOX.height, floorHeight + margin * 2)
  const centerX = bounds.x + floorWidth / 2
  const centerY = bounds.y + floorHeight / 2
  return {
    x: centerX - width / 2,
    y: centerY - height / 2,
    width,
    height
  }
}

export function maxFloorDimensionForArea(axis, floor = {}) {
  const safeFloor = sanitizeFloorSize(floor)
  if (axis === 'height') {
    return snapFloorExtentDown(LAYOUT_SIZE_LIMITS.maxArea / safeFloor.width, LAYOUT_SIZE_LIMITS.height.min)
  }
  return snapFloorExtentDown(LAYOUT_SIZE_LIMITS.maxArea / safeFloor.height, LAYOUT_SIZE_LIMITS.width.min)
}

export function zoomViewBox(viewBox, factor, focusPoint) {
  const current = sanitizeViewBox(viewBox)
  const safeFactor = Math.max(0.2, Math.min(5, Number(factor) || 1))
  const width = clampOptionalUpper(current.width * safeFactor, LAYOUT_ZOOM_LIMITS.minWidth, LAYOUT_ZOOM_LIMITS.maxWidth)
  const height = clampOptionalUpper(current.height * safeFactor, LAYOUT_ZOOM_LIMITS.minHeight, LAYOUT_ZOOM_LIMITS.maxHeight)
  const focus = focusPoint || {
    x: current.x + current.width / 2,
    y: current.y + current.height / 2
  }
  const ratioX = (focus.x - current.x) / current.width
  const ratioY = (focus.y - current.y) / current.height
  return {
    x: focus.x - ratioX * width,
    y: focus.y - ratioY * height,
    width,
    height
  }
}

export function clientPointToViewBoxPoint(clientX, clientY, rect, viewBox) {
  const current = sanitizeViewBox(viewBox)
  const safeRect = sanitizeClientRect(rect)
  if (!safeRect.width || !safeRect.height) {
    return { x: current.x, y: current.y }
  }
  const scale = viewBoxScaleForClientRect(safeRect, current)
  const renderedWidth = current.width * scale
  const renderedHeight = current.height * scale
  const offsetX = (safeRect.width - renderedWidth) / 2
  const offsetY = (safeRect.height - renderedHeight) / 2
  return {
    x: current.x + (Number(clientX) - safeRect.left - offsetX) / scale,
    y: current.y + (Number(clientY) - safeRect.top - offsetY) / scale
  }
}

export function clientDeltaToViewBoxDelta(deltaX, deltaY, rect, viewBox) {
  const current = sanitizeViewBox(viewBox)
  const safeRect = sanitizeClientRect(rect)
  if (!safeRect.width || !safeRect.height) {
    return { x: 0, y: 0 }
  }
  const scale = viewBoxScaleForClientRect(safeRect, current)
  return {
    x: Number(deltaX) / scale,
    y: Number(deltaY) / scale
  }
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

export function tableTopForCapacity(capacity) {
  const value = Math.max(1, Number(capacity) || 1)
  if (value <= 2) return { width: 28, height: 18 }
  if (value <= 4) return { width: 40, height: 26 }
  return { width: 52, height: 26 }
}

export function tableChairRectsForCapacity(capacity) {
  const value = Math.max(1, Number(capacity) || 1)
  const top = tableTopForCapacity(value)
  const halfW = top.width / 2
  const halfH = top.height / 2
  const chairSize = 10
  const gap = 2

  if (value <= 2) {
    return [
      { key: 'L', x: -halfW - gap - chairSize, y: -chairSize / 2, width: chairSize, height: chairSize },
      { key: 'R', x: halfW + gap, y: -chairSize / 2, width: chairSize, height: chairSize }
    ]
  }
  if (value <= 4) {
    return [
      { key: 'T', x: -chairSize / 2, y: -halfH - gap - chairSize, width: chairSize, height: chairSize },
      { key: 'B', x: -chairSize / 2, y: halfH + gap, width: chairSize, height: chairSize },
      { key: 'L', x: -halfW - gap - chairSize, y: -chairSize / 2, width: chairSize, height: chairSize },
      { key: 'R', x: halfW + gap, y: -chairSize / 2, width: chairSize, height: chairSize }
    ]
  }
  return [
    { key: 'T1', x: -halfW / 2 - chairSize / 2, y: -halfH - gap - chairSize, width: chairSize, height: chairSize },
    { key: 'T2', x: halfW / 2 - chairSize / 2, y: -halfH - gap - chairSize, width: chairSize, height: chairSize },
    { key: 'B1', x: -halfW / 2 - chairSize / 2, y: halfH + gap, width: chairSize, height: chairSize },
    { key: 'B2', x: halfW / 2 - chairSize / 2, y: halfH + gap, width: chairSize, height: chairSize },
    { key: 'L', x: -halfW - gap - chairSize, y: -chairSize / 2, width: chairSize, height: chairSize },
    { key: 'R', x: halfW + gap, y: -chairSize / 2, width: chairSize, height: chairSize }
  ]
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

export function snapAndClampPoint(x, y, kind, item, bounds = LAYOUT_BOUNDS) {
  if (kind === 'door' || kind === 'window') {
    return snapWallItemPoint(x, y, kind, item, bounds)
  }
  const footprint = getItemFootprint(kind, item)
  const halfW = footprint.width / 2
  const halfH = footprint.height / 2
  return {
    x: snapInsideRange(x, bounds.x + halfW, bounds.right - halfW),
    y: snapInsideRange(y, bounds.y + halfH, bounds.bottom - halfH)
  }
}

export function totalLayoutSeats(layout) {
  return (layout?.tables || []).reduce((sum, table) => sum + (Number(table.capacity) || 0), 0)
}

function clampInteger(value, lower, upper) {
  return Math.min(upper, Math.max(lower, Math.round(Number(value) || lower)))
}

function defaultDoorPosition(index, layout = null, id = `D${index + 1}`) {
  const bounds = floorBoundsForLayout(layout)
  const positions = [
    { wall_side: 'left', x: bounds.x, y: bounds.y + 76 },
    { wall_side: 'right', x: bounds.right, y: bounds.y + 76 },
    { wall_side: 'top', x: bounds.right - 26, y: bounds.y },
    { wall_side: 'left', x: bounds.x, y: bounds.y + 146 }
  ]
  const position = positions[index] || positions[positions.length - 1]
  const preferred = snapAndClampPoint(position.x, position.y, 'door', position, bounds)
  return firstAvailableWallPosition(layout, 'door', id, index, preferred)
}

function defaultWindowPosition(index, layout = null, id = `W${index + 1}`) {
  const bounds = floorBoundsForLayout(layout)
  // Windows are service openings on walls, so defaults occupy wall slots.
  const topSlots = [bounds.x + 46, bounds.x + 106, bounds.x + 166, bounds.x + 226, bounds.right - 26]
  if (index < topSlots.length) {
    const preferred = snapAndClampPoint(topSlots[index], bounds.y, 'window', { wall_side: 'top' }, bounds)
    return firstAvailableWallPosition(layout, 'window', id, index, preferred)
  }
  const rightSlots = [bounds.y + 76, bounds.y + 146]
  const rightIndex = index - topSlots.length
  if (rightIndex < rightSlots.length) {
    const preferred = snapAndClampPoint(bounds.right, rightSlots[rightIndex], 'window', { wall_side: 'right' }, bounds)
    return firstAvailableWallPosition(layout, 'window', id, index, preferred)
  }
  const leftSlots = [bounds.y + 146, bounds.y + 76]
  const leftIndex = rightIndex - rightSlots.length
  if (leftIndex < leftSlots.length) {
    const preferred = snapAndClampPoint(bounds.x, leftSlots[leftIndex], 'window', { wall_side: 'left' }, bounds)
    return firstAvailableWallPosition(layout, 'window', id, index, preferred)
  }
  const bottomIndex = leftIndex - leftSlots.length
  const preferred = snapAndClampPoint(bounds.x + 46 + (bottomIndex % 5) * 60, bounds.bottom, 'window', { wall_side: 'bottom' }, bounds)
  return firstAvailableWallPosition(layout, 'window', id, index, preferred)
}

function defaultTablePosition(index, capacity, layout = null) {
  const bounds = floorBoundsForLayout(layout)
  // Keep tables away from wall-mounted doors/windows so default generation
  // starts from a collision-free editable layout.
  const cols = 3
  const col = index % cols
  const row = Math.floor(index / cols)
  return snapAndClampPoint(bounds.x + 76 + col * 80, bounds.y + 76 + row * 50, 'table', { capacity }, bounds)
}

function firstAvailableWallPosition(layout, kind, id, seedIndex, preferred) {
  return findAvailableWallPosition(layout, kind, id, seedIndex, preferred) || preferred
}

function findAvailableWallPosition(layout, kind, id, seedIndex, preferred) {
  if (!layout) return preferred
  if (!itemOverlapsLayout(layout, kind, id, preferred.x, preferred.y, { id, ...preferred })) {
    return preferred
  }
  const candidates = wallCandidatePoints(layout)
  const start = candidates.length ? seedIndex % candidates.length : 0
  for (let offset = 0; offset < candidates.length; offset += 1) {
    const candidate = candidates[(start + offset) % candidates.length]
    const point = snapAndClampPoint(candidate.x, candidate.y, kind, candidate, floorBoundsForLayout(layout))
    if (!itemOverlapsLayout(layout, kind, id, point.x, point.y, { id, ...point })) {
      return point
    }
  }
  return null
}

function firstAvailableTablePosition(layout, id, seedIndex, capacity) {
  return findAvailableTablePosition(layout, id, seedIndex, capacity) || defaultTablePosition(seedIndex, capacity, layout)
}

function findAvailableTablePosition(layout, id, seedIndex, capacity) {
  const preferred = defaultTablePosition(seedIndex, capacity, layout)
  if (!layout || !itemOverlapsLayout(layout, 'table', id, preferred.x, preferred.y, { id, capacity, ...preferred })) {
    return preferred
  }
  const candidates = tableCandidatePoints(layout, capacity)
  const start = candidates.length ? seedIndex % candidates.length : 0
  for (let offset = 0; offset < candidates.length; offset += 1) {
    const point = candidates[(start + offset) % candidates.length]
    if (!itemOverlapsLayout(layout, 'table', id, point.x, point.y, { id, capacity, ...point })) {
      return point
    }
  }
  return null
}

function wallCandidatePoints(layout) {
  const bounds = floorBoundsForLayout(layout)
  const points = []
  for (let x = bounds.x + 26; x <= bounds.right - 26; x += 40) {
    points.push({ wall_side: 'top', x, y: bounds.y })
  }
  for (let y = bounds.y + 46; y <= bounds.bottom - 46; y += 40) {
    points.push({ wall_side: 'right', x: bounds.right, y })
  }
  for (let x = bounds.right - 26; x >= bounds.x + 26; x -= 40) {
    points.push({ wall_side: 'bottom', x, y: bounds.bottom })
  }
  for (let y = bounds.bottom - 46; y >= bounds.y + 46; y -= 40) {
    points.push({ wall_side: 'left', x: bounds.x, y })
  }
  return points
}

function tableCandidatePoints(layout, capacity) {
  const bounds = floorBoundsForLayout(layout)
  const fp = getItemFootprint('table', { capacity })
  const startX = snapInsideRange(bounds.x + 76, bounds.x + fp.width / 2, bounds.right - fp.width / 2)
  const startY = snapInsideRange(bounds.y + 76, bounds.y + fp.height / 2, bounds.bottom - fp.height / 2)
  const endX = bounds.right - fp.width / 2
  const endY = bounds.bottom - fp.height / 2
  const points = []
  for (let y = startY; y <= endY; y += 50) {
    for (let x = startX; x <= endX; x += 80) {
      points.push({ x, y })
    }
  }
  return points
}

function arrangeTablesCompact(baseLayout, tables) {
  const arranged = []
  for (const table of tables) {
    const candidateLayout = { ...baseLayout, tables: arranged }
    const placed = firstAvailableTableCandidate(candidateLayout, table, compactTableCandidatePoints(candidateLayout, table))
    if (!placed) return null
    arranged.push(placed)
  }
  return arranged
}

function arrangeTablesSpread(baseLayout, tables) {
  const arranged = []
  const bounds = floorBoundsForLayout(baseLayout)
  const floorWidth = bounds.right - bounds.x
  const floorHeight = bounds.bottom - bounds.y
  const count = tables.length
  const cols = Math.max(1, Math.ceil(Math.sqrt(count * (floorWidth / Math.max(1, floorHeight)))))
  const rows = Math.max(1, Math.ceil(count / cols))
  const cellW = floorWidth / cols
  const cellH = floorHeight / rows
  for (const [index, table] of tables.entries()) {
    const col = index % cols
    const row = Math.floor(index / cols)
    const ideal = {
      x: bounds.x + cellW * (col + 0.5),
      y: bounds.y + cellH * (row + 0.5)
    }
    const candidateLayout = { ...baseLayout, tables: arranged }
    const placed = firstAvailableTableCandidate(candidateLayout, table, spreadTableCandidatePoints(candidateLayout, table, ideal, cellW, cellH))
    if (!placed) return null
    arranged.push(placed)
  }
  return arranged
}

function firstAvailableTableCandidate(layout, table, candidates) {
  const bounds = floorBoundsForLayout(layout)
  for (const candidate of candidates) {
    const point = snapAndClampPoint(candidate.x, candidate.y, 'table', table, bounds)
    const moved = {
      ...table,
      x: point.x,
      y: point.y
    }
    if (!itemOverlapsLayout(layout, 'table', moved.id, moved.x, moved.y, moved)) {
      return moved
    }
  }
  return null
}

function compactTableCandidatePoints(layout, table) {
  const bounds = floorBoundsForLayout(layout)
  const fp = getItemFootprint('table', table)
  const startX = snapInsideRange(bounds.x + 76, bounds.x + fp.width / 2, bounds.right - fp.width / 2)
  const startY = snapInsideRange(bounds.y + 36, bounds.y + fp.height / 2, bounds.bottom - fp.height / 2)
  const endX = bounds.right - fp.width / 2
  const endY = bounds.bottom - fp.height / 2
  const points = []
  for (let y = startY; y <= endY; y += COMPACT_TABLE_ROW_STEP) {
    for (let x = startX; x <= endX; x += COMPACT_TABLE_COLUMN_STEP) {
      points.push({ x, y })
    }
  }
  return points
}

function spreadTableCandidatePoints(layout, table, ideal, cellW, cellH) {
  const bounds = floorBoundsForLayout(layout)
  const fp = getItemFootprint('table', table)
  const maxRadius = Math.max(cellW, cellH, 120)
  const points = []
  for (let radius = 0; radius <= maxRadius; radius += LAYOUT_GRID_STEP) {
    if (radius === 0) {
      points.push(ideal)
      continue
    }
    points.push(
      { x: ideal.x - radius, y: ideal.y },
      { x: ideal.x + radius, y: ideal.y },
      { x: ideal.x, y: ideal.y - radius },
      { x: ideal.x, y: ideal.y + radius },
      { x: ideal.x - radius, y: ideal.y - radius },
      { x: ideal.x + radius, y: ideal.y - radius },
      { x: ideal.x - radius, y: ideal.y + radius },
      { x: ideal.x + radius, y: ideal.y + radius }
    )
  }
  return points.filter((point) => (
    point.x >= bounds.x + fp.width / 2 &&
    point.x <= bounds.right - fp.width / 2 &&
    point.y >= bounds.y + fp.height / 2 &&
    point.y <= bounds.bottom - fp.height / 2
  ))
}

function placeTablesForSeats(layout, numSeats) {
  const capacities = buildTableCapacities(numSeats)
  if (numSeats > DENSE_TABLE_THRESHOLD_SEATS) {
    return placeTablesGreedy(layout, capacities)
  }
  const tables = []
  for (const [index, capacity] of capacities.entries()) {
    const id = `T${index + 1}`
    const point = findAvailableTablePosition({ ...layout, tables }, id, index, capacity)
    if (!point) return null
    tables.push({
      id,
      capacity,
      table_type: tableTypeForCapacity(capacity),
      ...point
    })
  }
  return tables.length === capacities.length ? tables : placeTablesGreedy(layout, capacities)
}

function placeTablesGreedy(layout, capacities) {
  const tables = []
  const candidateCache = new Map()
  const nextCandidateIndex = new Map()
  for (const [index, capacity] of capacities.entries()) {
    const id = `T${index + 1}`
    const candidates = candidateCache.get(capacity) || tableCandidatePoints(layout, capacity)
    candidateCache.set(capacity, candidates)
    const startIndex = nextCandidateIndex.get(capacity) || 0
    const placed = findGreedyTableCandidate(layout, tables, id, capacity, startIndex, candidates)
    if (!placed) return null
    nextCandidateIndex.set(capacity, placed.candidateIndex + 1)
    delete placed.candidateIndex
    tables.push(placed)
  }
  return tables
}

function placeSameCapacityTablesGreedy(layout, capacity, maxTables) {
  const tables = []
  const candidates = tableCandidatePoints(layout, capacity)
  let startIndex = 0
  while (tables.length < maxTables) {
    const id = `L${tables.length + 1}`
    const placed = findGreedyTableCandidate(layout, tables, id, capacity, startIndex, candidates)
    if (!placed) break
    startIndex = placed.candidateIndex + 1
    delete placed.candidateIndex
    tables.push(placed)
  }
  return tables
}

function findGreedyTableCandidate(layout, tables, id, capacity, startIndex = 0, candidates = null) {
  const points = candidates || tableCandidatePoints(layout, capacity)
  for (let candidateIndex = startIndex; candidateIndex < points.length; candidateIndex += 1) {
    const point = points[candidateIndex]
    const table = {
      id,
      capacity,
      table_type: tableTypeForCapacity(capacity),
      ...point,
      candidateIndex
    }
    if (!itemOverlapsLayout({ ...layout, tables }, 'table', id, point.x, point.y, table)) {
      return table
    }
  }
  return null
}

function calculateCandidateSlotSeatLimit(baseLayout) {
  const sixTables = placeSameCapacityTablesGreedy(
    baseLayout,
    6,
    Math.ceil(LAYOUT_MAX_EDITABLE_SEATS / 6)
  )
  for (let seats = LAYOUT_MAX_EDITABLE_SEATS; seats > DENSE_TABLE_THRESHOLD_SEATS; seats -= 2) {
    const sixCount = Math.floor(seats / 6)
    const remainder = seats - sixCount * 6
    if (sixCount > sixTables.length) continue
    if (remainder === 0) return seats
    const placedSixTables = sixTables.slice(0, sixCount)
    const remainderTable = findGreedyTableCandidate(
      baseLayout,
      placedSixTables,
      `L${sixCount + 1}`,
      remainder,
      0
    )
    if (remainderTable) return seats
  }
  for (let seats = Math.min(DENSE_TABLE_THRESHOLD_SEATS, LAYOUT_MAX_EDITABLE_SEATS); seats >= 2; seats -= 2) {
    if (placeTablesForSeats(baseLayout, seats)) return seats
  }
  return 2
}

export function createDefaultLayout(config) {
  const numWindows = clampInteger(config?.num_windows, 1, 30)
  const floor = floorSizeFromConfig(config)
  const doors = []
  let draft = { floor, doors, windows: [], tables: [] }
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
  draft = { ...draft, windows }
  const numSeats = normalizeSeatCount(config?.num_seats, calculateLayoutSeatLimit(draft))
  const tables = placeTablesForSeats(draft, numSeats) || []
  return { floor, doors, windows, tables }
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
    const draft = { ...layout, windows: [...current, ...additional] }
    const point = findAvailableWallPosition(draft, 'window', id, index, defaultWindowPosition(index, draft, id))
    if (!point) break
    additional.push({
      id,
      service_rate_factor: 1,
      ...point
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
    const draft = { ...layout, doors: [...current, ...additional] }
    const point = findAvailableWallPosition(draft, 'door', id, index, defaultDoorPosition(index, draft, id))
    if (!point) break
    additional.push({
      id,
      arrival_share: 1,
      ...point
    })
  }
  return { ...layout, doors: [...current, ...additional] }
}

export function arrangeLayoutTables(layout, mode = 'spread') {
  const tables = (layout?.tables || []).map((table, index) => ({
    ...table,
    id: table.id || `T${index + 1}`,
    table_type: table.table_type || tableTypeForCapacity(table.capacity)
  }))
  if (!tables.length) return layout
  const baseLayout = {
    ...layout,
    floor: sanitizeFloorSize(layout?.floor),
    tables: []
  }
  const strategy = mode === 'compact' ? 'compact' : 'spread'
  const arranged = strategy === 'compact'
    ? arrangeTablesCompact(baseLayout, tables)
    : arrangeTablesSpread(baseLayout, tables) || arrangeTablesCompact(baseLayout, tables)
  if (!arranged || arranged.length !== tables.length) {
    return layout
  }
  return { ...layout, floor: baseLayout.floor, tables: arranged }
}

export function rebuildLayoutTablesForSeats(layout, numSeats) {
  const baseLayout = { ...layout, floor: sanitizeFloorSize(layout?.floor), tables: [] }
  const target = normalizeSeatCount(numSeats, calculateLayoutSeatLimit(baseLayout))
  let tables = []
  for (let seats = target; seats >= 2; seats -= 2) {
    const placed = placeTablesForSeats(baseLayout, seats)
    if (placed) {
      tables = placed
      break
    }
  }
  return { ...layout, tables }
}

export function calculateLayoutSeatLimit(layout) {
  const baseLayout = {
    floor: sanitizeFloorSize(layout?.floor),
    doors: layout?.doors || [],
    windows: layout?.windows || [],
    tables: []
  }
  return Math.max(2, normalizeSeatCount(calculateCandidateSlotSeatLimit(baseLayout), LAYOUT_MAX_EDITABLE_SEATS))
}

export function resizeLayoutFloor(layout, floorSize, options = {}) {
  const blockTableConflicts = Boolean(options.blockTableConflicts)
  const currentFloor = sanitizeFloorSize(layout?.floor)
  const floor = sanitizeFloorSize(floorSize, currentFloor)
  const isShrink = floor.width < currentFloor.width || floor.height < currentFloor.height
  const doors = []
  let draft = { floor, doors, windows: [], tables: [] }
  ;(layout?.doors || []).forEach((door, index) => {
    const id = door.id || `D${index + 1}`
    const preferred = snapAndClampPoint(door.x, door.y, 'door', door, floorBoundsForLayout(draft))
    const point = findAvailableWallPosition({ ...draft, doors }, 'door', id, index, preferred)
    if (!point) return
    doors.push({
      ...door,
      id,
      ...point
    })
  })
  draft = { ...draft, doors }
  const windows = []
  ;(layout?.windows || []).forEach((window, index) => {
    const id = window.id || `W${index + 1}`
    const preferred = snapAndClampPoint(window.x, window.y, 'window', window, floorBoundsForLayout(draft))
    const point = findAvailableWallPosition({ ...draft, windows }, 'window', id, index, preferred)
    if (!point) return
    windows.push({
      ...window,
      id,
      ...point
    })
  })
  draft = { ...draft, windows }
  if (blockTableConflicts && isShrink && floorResizeConflictsWithTables(
    { ...draft, tables: layout?.tables || [] },
    changedFloorSides(currentFloor, floor),
    layout
  )) {
    return layout
  }
  const tables = (layout?.tables || []).map((table, index) => {
    const id = table.id || `T${index + 1}`
    const point = snapAndClampPoint(table.x, table.y, 'table', table, floorBoundsForLayout(draft))
    return {
      ...table,
      id,
      ...point
    }
  })
  return { ...draft, tables }
}

export function resizeLayoutFloorFromHandle(layout, handle, pointerX, pointerY) {
  const bounds = floorBoundsForLayout(layout)
  const floor = sanitizeFloorSize(layout?.floor)
  const handleName = String(handle || 'corner')
  let width = floor.width
  let height = floor.height
  if (handleName === 'right' || handleName === 'corner' || handleName === 'bottom-right') {
    width = snapFloorExtent(pointerX - bounds.x, LAYOUT_SIZE_LIMITS.width.min, LAYOUT_SIZE_LIMITS.width.max)
  }
  if (handleName === 'bottom' || handleName === 'corner' || handleName === 'bottom-right') {
    height = snapFloorExtent(pointerY - bounds.y, LAYOUT_SIZE_LIMITS.height.min, LAYOUT_SIZE_LIMITS.height.max)
  }
  return resizeLayoutFloor(
    layout,
    {
      x: bounds.x,
      y: bounds.y,
      width,
      height
    },
    { blockTableConflicts: true }
  )
}

export function setItemPosition(layout, kind, id, x, y, options = {}) {
  const collection = collectionKeyForKind(kind)
  if (!collection) return layout
  const allowOverlap = Boolean(options.allowOverlap)
  const bounds = floorBoundsForLayout(layout)
  const items = layout[collection].map((item) => {
    if (item.id !== id) return item
    const point = snapAndClampPoint(x, y, kind, item, bounds)
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
  const bounds = floorBoundsForLayout(layout)
  const tables = (layout?.tables || []).map((table) => {
    if (table.id !== id) return table
    const point = snapAndClampPoint(table.x, table.y, 'table', { ...table, capacity: sanitized }, bounds)
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
  const movingBoxes = getItemCollisionBoxes(kind, { ...movingItem, x, y })
  return allLayoutItems(layout).some((candidate) => {
    if (candidate.kind === kind && candidate.item.id === id) return false
    return boxesOverlapAny(movingBoxes, getItemCollisionBoxes(candidate.kind, candidate.item))
  })
}

function floorResizeConflictsWithTables(layout, changedSides = ['left', 'right', 'top', 'bottom'], previousLayout = null) {
  const tables = layout?.tables || []
  if (!tables.length) return false
  const bounds = floorBoundsForLayout(layout)
  if (tables.some((table) => tableTouchesFloorWall(table, bounds, changedSides))) {
    return true
  }
  return [
    ...(layout?.doors || []).map((item) => ({ kind: 'door', item })),
    ...(layout?.windows || []).map((item) => ({ kind: 'window', item }))
  ].some(({ kind, item }) => openingChanged(previousLayout, kind, item) && itemOverlapsTables(layout, kind, item))
}

function tableTouchesFloorWall(table, bounds, changedSides) {
  const clearance = LAYOUT_ITEM_GAP
  return getItemCollisionBoxes('table', table).some((box) => (
    (changedSides.includes('left') && box.left < bounds.x + clearance) ||
    (changedSides.includes('right') && box.right > bounds.right - clearance) ||
    (changedSides.includes('top') && box.top < bounds.y + clearance) ||
    (changedSides.includes('bottom') && box.bottom > bounds.bottom - clearance)
  ))
}

function changedFloorSides(previousFloor, nextFloor) {
  const sides = []
  if (nextFloor.x > previousFloor.x) sides.push('left')
  if (nextFloor.y > previousFloor.y) sides.push('top')
  if (nextFloor.x + nextFloor.width < previousFloor.x + previousFloor.width) sides.push('right')
  if (nextFloor.y + nextFloor.height < previousFloor.y + previousFloor.height) sides.push('bottom')
  return sides
}

function openingChanged(previousLayout, kind, item) {
  if (!previousLayout) return true
  const previous = findItem(previousLayout, kind, item.id)
  if (!previous) return true
  return previous.x !== item.x || previous.y !== item.y || previous.wall_side !== item.wall_side
}

function itemOverlapsTables(layout, kind, item) {
  const movingBoxes = getItemCollisionBoxes(kind, item)
  return (layout?.tables || []).some((table) => (
    boxesOverlapAny(movingBoxes, getItemCollisionBoxes('table', table))
  ))
}

export function getItemCollisionBoxes(kind, item) {
  if (kind === 'table') {
    return tableShapeRects(item).map((rect) => localRectToBox(item, rect))
  }
  return [itemBounds(kind, item)]
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

function floorSizeFromConfig(config) {
  return sanitizeFloorSize(config?.floor || {
    width: config?.floor_width,
    height: config?.floor_height
  })
}

function sanitizeFloorSize(floor = {}, referenceFloor = null) {
  const width = sanitizeFloorDimension(
    floor.width,
    LAYOUT_SIZE_LIMITS.width.min,
    LAYOUT_SIZE_LIMITS.width.max,
    LAYOUT_SIZE_LIMITS.step,
    LAYOUT_DEFAULT_FLOOR.width
  )
  const height = sanitizeFloorDimension(
    floor.height,
    LAYOUT_SIZE_LIMITS.height.min,
    LAYOUT_SIZE_LIMITS.height.max,
    LAYOUT_SIZE_LIMITS.step,
    LAYOUT_DEFAULT_FLOOR.height
  )
  return constrainFloorArea({
    x: snapOptional(floor.x, (LAYOUT_VIEWBOX.width - width) / 2),
    y: snapOptional(floor.y, (LAYOUT_VIEWBOX.height - height) / 2),
    width,
    height
  }, referenceFloor)
}

function sanitizeViewBox(viewBox = {}) {
  const width = clampOptionalUpper(
    Number(viewBox.width) || LAYOUT_VIEWBOX.width,
    LAYOUT_ZOOM_LIMITS.minWidth,
    LAYOUT_ZOOM_LIMITS.maxWidth
  )
  const height = clampOptionalUpper(
    Number(viewBox.height) || LAYOUT_VIEWBOX.height,
    LAYOUT_ZOOM_LIMITS.minHeight,
    LAYOUT_ZOOM_LIMITS.maxHeight
  )
  return {
    x: Number.isFinite(Number(viewBox.x)) ? Number(viewBox.x) : 0,
    y: Number.isFinite(Number(viewBox.y)) ? Number(viewBox.y) : 0,
    width,
    height
  }
}

function sanitizeClientRect(rect = {}) {
  return {
    left: Number(rect.left) || 0,
    top: Number(rect.top) || 0,
    width: Math.max(0, Number(rect.width) || 0),
    height: Math.max(0, Number(rect.height) || 0)
  }
}

function viewBoxScaleForClientRect(rect, viewBox) {
  return Math.min(rect.width / viewBox.width, rect.height / viewBox.height) || 1
}

function clampToStep(value, lower, upper, step, fallback = upper) {
  const raw = Number.isFinite(Number(value)) ? Number(value) : fallback
  const bounded = clampOptionalUpper(raw, lower, upper)
  return clampOptionalUpper(Math.round(bounded / step) * step, lower, upper)
}

function clampOptionalUpper(value, lower, upper) {
  const boundedLower = Math.max(lower, Number(value) || lower)
  const numericUpper = upper === null || upper === undefined ? Number.NaN : Number(upper)
  return Number.isFinite(numericUpper)
    ? Math.min(numericUpper, boundedLower)
    : boundedLower
}

function constrainFloorArea(floor, referenceFloor = null) {
  const maxArea = LAYOUT_SIZE_LIMITS.maxArea
  if (!Number.isFinite(maxArea) || floor.width * floor.height <= maxArea) {
    return floor
  }
  const reference = referenceFloor && Number.isFinite(referenceFloor.width) && Number.isFinite(referenceFloor.height)
    ? referenceFloor
    : null
  const widthChanged = reference ? floor.width !== reference.width : true
  const heightChanged = reference ? floor.height !== reference.height : true
  let width = floor.width
  let height = floor.height

  if (widthChanged && !heightChanged) {
    width = snapFloorExtentDown(maxArea / height, LAYOUT_SIZE_LIMITS.width.min)
  } else if (heightChanged && !widthChanged) {
    height = snapFloorExtentDown(maxArea / width, LAYOUT_SIZE_LIMITS.height.min)
  } else {
    const scale = Math.sqrt(maxArea / (width * height))
    width = snapFloorExtentDown(width * scale, LAYOUT_SIZE_LIMITS.width.min)
    height = snapFloorExtentDown(height * scale, LAYOUT_SIZE_LIMITS.height.min)
  }

  const adjusted = shrinkFloorAreaToLimit(width, height, widthChanged && !heightChanged ? 'width' : heightChanged && !widthChanged ? 'height' : null)
  return {
    ...floor,
    width: adjusted.width,
    height: adjusted.height
  }
}

function shrinkFloorAreaToLimit(width, height, preferredAxis = null) {
  let nextWidth = width
  let nextHeight = height
  while (nextWidth * nextHeight > LAYOUT_SIZE_LIMITS.maxArea) {
    if (preferredAxis === 'width' && nextWidth > LAYOUT_SIZE_LIMITS.width.min) {
      nextWidth -= LAYOUT_SIZE_LIMITS.step
    } else if (preferredAxis === 'height' && nextHeight > LAYOUT_SIZE_LIMITS.height.min) {
      nextHeight -= LAYOUT_SIZE_LIMITS.step
    } else if (nextWidth / LAYOUT_SIZE_LIMITS.width.min >= nextHeight / LAYOUT_SIZE_LIMITS.height.min && nextWidth > LAYOUT_SIZE_LIMITS.width.min) {
      nextWidth -= LAYOUT_SIZE_LIMITS.step
    } else if (nextHeight > LAYOUT_SIZE_LIMITS.height.min) {
      nextHeight -= LAYOUT_SIZE_LIMITS.step
    } else {
      break
    }
  }
  return { width: nextWidth, height: nextHeight }
}

function snapFloorExtentDown(value, lower) {
  return Math.max(lower, Math.floor(Number(value) / LAYOUT_SIZE_LIMITS.step) * LAYOUT_SIZE_LIMITS.step)
}

function sanitizeFloorDimension(value, lower, upper, step, fallback) {
  const raw = Number(value)
  if (!Number.isFinite(raw)) return fallback
  if (raw === fallback) return fallback
  return clampToStep(raw, lower, upper, step, fallback)
}

function snapFloorExtent(value, lower, upper) {
  return clampToStep(value, lower, upper, LAYOUT_SIZE_LIMITS.step)
}

function snapOptional(value, fallback) {
  const raw = Number(value)
  if (!Number.isFinite(raw)) return fallback
  return raw
}

function toEven(value) {
  return Math.floor(value / 2) * 2
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

function boxesOverlapAny(leftBoxes, rightBoxes) {
  return leftBoxes.some((left) => rightBoxes.some((right) => boxesOverlap(left, right)))
}

function tableShapeRects(table) {
  const top = tableTopForCapacity(table?.capacity)
  return [
    {
      key: 'top',
      x: -top.width / 2,
      y: -top.height / 2,
      width: top.width,
      height: top.height
    },
    ...tableChairRectsForCapacity(table?.capacity)
  ]
}

function localRectToBox(item, rect) {
  return {
    left: item.x + rect.x,
    right: item.x + rect.x + rect.width,
    top: item.y + rect.y,
    bottom: item.y + rect.y + rect.height
  }
}

function snapWallItemPoint(x, y, kind, item, bounds = LAYOUT_BOUNDS) {
  const wallSide = nearestWallSide(x, y, bounds)
  const footprint = getItemFootprint(kind, { ...item, wall_side: wallSide })
  const halfW = footprint.width / 2
  const halfH = footprint.height / 2
  if (wallSide === 'top') {
    return {
      x: snapInsideRange(x, bounds.x + halfW, bounds.right - halfW),
      y: snapToGrid(bounds.y + halfH),
      wall_side: wallSide
    }
  }
  if (wallSide === 'right') {
    return {
      x: snapToGrid(bounds.right - halfW),
      y: snapInsideRange(y, bounds.y + halfH, bounds.bottom - halfH),
      wall_side: wallSide
    }
  }
  if (wallSide === 'bottom') {
    return {
      x: snapInsideRange(x, bounds.x + halfW, bounds.right - halfW),
      y: snapToGrid(bounds.bottom - halfH),
      wall_side: wallSide
    }
  }
  return {
    x: snapToGrid(bounds.x + halfW),
    y: snapInsideRange(y, bounds.y + halfH, bounds.bottom - halfH),
    wall_side: wallSide
  }
}

function nearestWallSide(x, y, bounds = LAYOUT_BOUNDS) {
  const distances = [
    { wall_side: 'top', value: Math.abs(y - bounds.y) },
    { wall_side: 'right', value: Math.abs(x - bounds.right) },
    { wall_side: 'bottom', value: Math.abs(y - bounds.bottom) },
    { wall_side: 'left', value: Math.abs(x - bounds.x) }
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
