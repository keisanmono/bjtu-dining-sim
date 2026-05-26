// 文件说明：布局纯函数工具：计算默认布局、拖拽吸附、碰撞检测和座位排布。

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
export const TABLE_ROTATION_OPTIONS = [0, 90]

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

// 将容量映射为后端指标和前端图例共用的桌型标识。
export function tableTypeForCapacity(capacity) {
  const value = Math.max(1, Number(capacity) || 1)
  if (value <= 1) return 'single_seat'
  if (value <= 2) return 'two_seat'
  if (value <= 4) return 'four_seat'
  return 'six_seat'
}

// 将目标座位数拆成一组餐桌容量，大布局优先使用六人桌提高密度。
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

// 将座位输入限制为正偶数，并不超过布局编辑器允许的上限。
export function normalizeSeatCount(value, upper = LAYOUT_MAX_EDITABLE_SEATS) {
  const boundedUpper = Math.max(2, toEven(Math.min(LAYOUT_MAX_EDITABLE_SEATS, Number(upper) || LAYOUT_MAX_EDITABLE_SEATS)))
  const bounded = Math.min(boundedUpper, Math.max(2, Math.floor(Number(value) || 2)))
  return Math.max(2, toEven(bounded))
}

// 把 floor 的位置和尺寸转换为 left/right/top/bottom 边界。
export function floorBoundsForLayout(layout) {
  const floor = sanitizeFloorSize(layout?.floor || layout)
  return {
    x: floor.x,
    y: floor.y,
    right: floor.x + floor.width,
    bottom: floor.y + floor.height
  }
}

// 计算能完整包住食堂地面并留出边距的 SVG viewBox。
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

// 在最大面积约束下，给宽度或高度输入框计算动态上限。
export function maxFloorDimensionForArea(axis, floor = {}) {
  const safeFloor = sanitizeFloorSize(floor)
  if (axis === 'height') {
    return snapFloorExtentDown(LAYOUT_SIZE_LIMITS.maxArea / safeFloor.width, LAYOUT_SIZE_LIMITS.height.min)
  }
  return snapFloorExtentDown(LAYOUT_SIZE_LIMITS.maxArea / safeFloor.height, LAYOUT_SIZE_LIMITS.width.min)
}

// zoomViewBox() 处理 SVG 视野缩放。
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

// 将浏览器 client 坐标换算为当前 SVG viewBox 的世界坐标。
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

// 将浏览器像素位移换算成 viewBox 世界坐标中的位移。
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

// 根据图元类型、容量和旋转角返回碰撞检测用 footprint。
export function getItemFootprint(kind, item) {
  if (kind === 'window') return wallFootprintFor('window', item)
  if (kind === 'door') return wallFootprintFor('door', item)
  if (kind === 'table') {
    const capacity = Math.max(1, Number(item?.capacity) || 1)
    if (capacity <= 2) return rotatedFootprint(FOOTPRINTS.table[2], item)
    if (capacity <= 4) return rotatedFootprint(FOOTPRINTS.table[4], item)
    return rotatedFootprint(FOOTPRINTS.table[6], item)
  }
  return { width: 20, height: 20 }
}

// 将任意餐桌旋转角规整为编辑器支持的 0 或 90 度。
export function normalizeTableRotation(rotation) {
  const normalized = ((Math.round(Number(rotation) || 0) % 180) + 180) % 180
  return normalized >= 45 && normalized < 135 ? 90 : 0
}

// 根据餐桌容量返回桌面可视矩形尺寸。
export function tableTopForCapacity(capacity) {
  const value = Math.max(1, Number(capacity) || 1)
  if (value <= 2) return { width: 28, height: 18 }
  if (value <= 4) return { width: 40, height: 26 }
  return { width: 52, height: 26 }
}

// 根据容量生成椅子在餐桌局部坐标中的矩形列表。
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

// 将坐标或尺寸吸附到编辑器网格。
export function snapToGrid(value, step = LAYOUT_GRID_STEP) {
  const safeStep = Math.max(1, Number(step) || LAYOUT_GRID_STEP)
  return Math.round(Number(value) / safeStep) * safeStep
}

// 根据 footprint 把图元中心点限制在给定边界内部。
export function clampToBounds(x, y, footprint, bounds = LAYOUT_BOUNDS) {
  const halfW = (footprint?.width || 20) / 2
  const halfH = (footprint?.height || 20) / 2
  return {
    x: Math.max(bounds.x + halfW, Math.min(bounds.right - halfW, x)),
    y: Math.max(bounds.y + halfH, Math.min(bounds.bottom - halfH, y))
  }
}

// 先吸附网格，再把值夹到上下界内。
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

// 将图元移动目标点吸附到网格，并按图元类型限制在地面或墙面上。
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

// 汇总当前所有餐桌容量，作为布局的实际座位数。
export function totalLayoutSeats(layout) {
  return (layout?.tables || []).reduce((sum, table) => sum + (Number(table.capacity) || 0), 0)
}

// 将输入规整为整数并限制在闭区间内。
function clampInteger(value, lower, upper) {
  return Math.min(upper, Math.max(lower, Math.round(Number(value) || lower)))
}

// 按入口序号给出默认墙面位置，并避开现有门窗。
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

// 按窗口序号优先沿上墙、右墙、左墙、下墙分配默认位置。
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

// 按三列网格给默认餐桌位置，并保持离墙面门窗有距离。
function defaultTablePosition(index, capacity, layout = null) {
  const bounds = floorBoundsForLayout(layout)
  // Keep tables away from wall-mounted doors/windows so default generation
  // starts from a collision-free editable layout.
  const cols = 3
  const col = index % cols
  const row = Math.floor(index / cols)
  return snapAndClampPoint(bounds.x + 76 + col * 80, bounds.y + 76 + row * 50, 'table', { capacity }, bounds)
}

// 查找第一个可用墙面点；找不到时保留首选位置作为兜底。
function firstAvailableWallPosition(layout, kind, id, seedIndex, preferred) {
  return findAvailableWallPosition(layout, kind, id, seedIndex, preferred) || preferred
}

// 在墙面候选点中寻找不会和现有门窗餐桌碰撞的位置。
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

// 为新增餐桌寻找无碰撞位置，失败时回退到默认网格位置。
function firstAvailableTablePosition(layout, id, seedIndex, capacity) {
  return findAvailableTablePosition(layout, id, seedIndex, capacity) || defaultTablePosition(seedIndex, capacity, layout)
}

// 在餐桌候选网格中寻找第一个不碰撞的摆放点。
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

// 沿四面墙生成门窗可尝试的候选吸附点。
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

// 在食堂地面内部生成餐桌网格候选点。
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

// 从左上向右下紧凑排布已有餐桌。
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

// 将餐桌按地面比例分散到网格单元中，再就近寻找无碰撞点。
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

// 在给定候选点列表中返回第一张可无碰撞放置的餐桌。
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

// 为紧凑排布生成较密的餐桌候选点。
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

// 以理想位置为中心向外扩展，生成分散排布的候选点。
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

// 根据目标座位数生成餐桌列表，小布局逐张放置，大布局使用贪心排布。
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
      rotation: 0,
      ...point
    })
  }
  return tables.length === capacities.length ? tables : placeTablesGreedy(layout, capacities)
}

// 对大量餐桌按容量缓存候选点，顺序寻找可放置位置。
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

// 尽量放置同容量餐桌，用于估算当前地面能容纳的最大座位数。
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

// 从指定候选下标开始寻找下一张不碰撞餐桌。
function findGreedyTableCandidate(layout, tables, id, capacity, startIndex = 0, candidates = null) {
  const points = candidates || tableCandidatePoints(layout, capacity)
  for (let candidateIndex = startIndex; candidateIndex < points.length; candidateIndex += 1) {
    const point = points[candidateIndex]
    const table = {
      id,
      capacity,
      table_type: tableTypeForCapacity(capacity),
      rotation: 0,
      ...point,
      candidateIndex
    }
    if (!itemOverlapsLayout({ ...layout, tables }, 'table', id, point.x, point.y, table)) {
      return table
    }
  }
  return null
}

// 通过试放餐桌估算当前门窗布局下最多能支持多少座位。
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

// 根据初始配置生成门、窗口、餐桌和地面尺寸的默认布局。
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

// 增减窗口数量，新增窗口会自动寻找不碰撞的墙面位置。
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

// 增减入口数量，新增入口会沿墙面寻找空位。
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

// 在不改变餐桌容量的前提下按指定策略重新摆放餐桌。
export function arrangeLayoutTables(layout, mode = 'spread') {
  const tables = (layout?.tables || []).map((table, index) => ({
    ...table,
    id: table.id || `T${index + 1}`,
    table_type: table.table_type || tableTypeForCapacity(table.capacity),
    rotation: normalizeTableRotation(table.rotation)
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

// 当座位总数变化时重新生成餐桌，并在放不下时向下回退到可行座位数。
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

// 估算当前地面和门窗约束下允许的座位上限。
export function calculateLayoutSeatLimit(layout) {
  const baseLayout = {
    floor: sanitizeFloorSize(layout?.floor),
    doors: layout?.doors || [],
    windows: layout?.windows || [],
    tables: []
  }
  return Math.max(2, normalizeSeatCount(calculateCandidateSlotSeatLimit(baseLayout), LAYOUT_MAX_EDITABLE_SEATS))
}

// 调整食堂地面尺寸，并把门窗餐桌重新吸附到新边界内。
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
      rotation: normalizeTableRotation(table.rotation),
      ...point
    }
  })
  return { ...draft, tables }
}

// 根据拖拽的右边或下边控制点生成新的地面尺寸。
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

// 移动指定门、窗口或餐桌，并在需要时阻止碰撞后的更新。
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

// 修改单张餐桌容量，并在 footprint 变化导致碰撞时保留原值。
export function setTableCapacity(layout, id, capacity) {
  const sanitized = sanitizeCapacity(capacity)
  const bounds = floorBoundsForLayout(layout)
  const tables = (layout?.tables || []).map((table) => {
    if (table.id !== id) return table
    const candidate = { ...table, capacity: sanitized, rotation: normalizeTableRotation(table.rotation) }
    const point = snapAndClampPoint(table.x, table.y, 'table', candidate, bounds)
    if (itemOverlapsLayout(layout, 'table', id, point.x, point.y, candidate)) {
      return table
    }
    return {
      ...table,
      capacity: sanitized,
      table_type: tableTypeForCapacity(sanitized),
      rotation: candidate.rotation,
      x: point.x,
      y: point.y
    }
  })
  return { ...layout, tables }
}

// 修改单张餐桌旋转角，并在旋转后碰撞时拒绝更新。
export function setTableRotation(layout, id, rotation) {
  const sanitized = normalizeTableRotation(rotation)
  const bounds = floorBoundsForLayout(layout)
  const tables = (layout?.tables || []).map((table) => {
    if (table.id !== id) return table
    const candidate = { ...table, rotation: sanitized }
    const point = snapAndClampPoint(table.x, table.y, 'table', candidate, bounds)
    const moved = {
      ...candidate,
      x: point.x,
      y: point.y
    }
    if (itemOverlapsLayout(layout, 'table', id, moved.x, moved.y, moved)) {
      return table
    }
    return moved
  })
  return { ...layout, tables }
}

// 判断某个图元移动到目标位置后是否与布局中其他图元碰撞。
export function itemOverlapsLayout(layout, kind, id, x, y, itemOverride = null) {
  const movingItem = itemOverride || findItem(layout, kind, id)
  if (!movingItem) return false
  const movingBoxes = getItemCollisionBoxes(kind, { ...movingItem, x, y })
  return allLayoutItems(layout).some((candidate) => {
    if (candidate.kind === kind && candidate.item.id === id) return false
    return boxesOverlapAny(movingBoxes, getItemCollisionBoxes(candidate.kind, candidate.item))
  })
}

// 缩小地面时检查餐桌是否贴墙或与被迫移动的门窗发生碰撞。
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

// 判断餐桌碰撞盒是否触碰了本次缩小的地面边。
function tableTouchesFloorWall(table, bounds, changedSides) {
  const clearance = LAYOUT_ITEM_GAP
  return getItemCollisionBoxes('table', table).some((box) => (
    (changedSides.includes('left') && box.left < bounds.x + clearance) ||
    (changedSides.includes('right') && box.right > bounds.right - clearance) ||
    (changedSides.includes('top') && box.top < bounds.y + clearance) ||
    (changedSides.includes('bottom') && box.bottom > bounds.bottom - clearance)
  ))
}

// 比较缩放前后地面，找出哪些边向内收缩。
function changedFloorSides(previousFloor, nextFloor) {
  const sides = []
  if (nextFloor.x > previousFloor.x) sides.push('left')
  if (nextFloor.y > previousFloor.y) sides.push('top')
  if (nextFloor.x + nextFloor.width < previousFloor.x + previousFloor.width) sides.push('right')
  if (nextFloor.y + nextFloor.height < previousFloor.y + previousFloor.height) sides.push('bottom')
  return sides
}

// 判断门或窗口在地面缩放后是否被重新吸附到不同位置。
function openingChanged(previousLayout, kind, item) {
  if (!previousLayout) return true
  const previous = findItem(previousLayout, kind, item.id)
  if (!previous) return true
  return previous.x !== item.x || previous.y !== item.y || previous.wall_side !== item.wall_side
}

// 判断门或窗口的碰撞盒是否压到任意餐桌。
function itemOverlapsTables(layout, kind, item) {
  const movingBoxes = getItemCollisionBoxes(kind, item)
  return (layout?.tables || []).some((table) => (
    boxesOverlapAny(movingBoxes, getItemCollisionBoxes('table', table))
  ))
}

// 返回图元参与碰撞检测的一组矩形，餐桌包含桌面和椅子。
export function getItemCollisionBoxes(kind, item) {
  if (kind === 'table') {
    return tableShapeRects(item).map((rect) => localRectToBox(item, rect))
  }
  return [itemBounds(kind, item)]
}

// 根据 footprint 生成门或窗口的碰撞盒。
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

// 在对应集合中按 id 查找门、窗口或餐桌。
export function findItem(layout, kind, id) {
  const collection = collectionKeyForKind(kind)
  if (!collection) return null
  return (layout?.[collection] || []).find((item) => item.id === id) || null
}

// 重新按当前餐桌顺序生成连续的 T1、T2 编号。
export function reorderTableIds(layout) {
  const tables = (layout?.tables || []).map((table, index) => ({
    ...table,
    id: `T${index + 1}`
  }))
  return { ...layout, tables }
}

// 将餐桌容量规整为编辑器支持的 2、4、6 人桌。
function sanitizeCapacity(capacity) {
  const value = clampInteger(capacity, 1, 12)
  if (TABLE_CAPACITY_OPTIONS.includes(value)) return value
  if (value <= 2) return 2
  if (value <= 4) return 4
  return 6
}

// 从配置对象读取 floor 字段，兼容旧的 floor_width/floor_height 字段。
function floorSizeFromConfig(config) {
  return sanitizeFloorSize(config?.floor || {
    width: config?.floor_width,
    height: config?.floor_height
  })
}

// 清洗地面位置和尺寸，并在必要时套用最大面积约束。
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

// 清洗 SVG viewBox，保证宽高满足缩放上下限。
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

// 清洗 DOMRect，只保留坐标和非负宽高。
function sanitizeClientRect(rect = {}) {
  return {
    left: Number(rect.left) || 0,
    top: Number(rect.top) || 0,
    width: Math.max(0, Number(rect.width) || 0),
    height: Math.max(0, Number(rect.height) || 0)
  }
}

// 计算 SVG viewBox 在实际 DOM 矩形中的渲染缩放比例。
function viewBoxScaleForClientRect(rect, viewBox) {
  return Math.min(rect.width / viewBox.width, rect.height / viewBox.height) || 1
}

// 将数值限制到上下界内，并按指定步长取整。
function clampToStep(value, lower, upper, step, fallback = upper) {
  const raw = Number.isFinite(Number(value)) ? Number(value) : fallback
  const bounded = clampOptionalUpper(raw, lower, upper)
  return clampOptionalUpper(Math.round(bounded / step) * step, lower, upper)
}

// 只在上限存在时应用上限，同时始终保证不低于下限。
function clampOptionalUpper(value, lower, upper) {
  const boundedLower = Math.max(lower, Number(value) || lower)
  const numericUpper = upper === null || upper === undefined ? Number.NaN : Number(upper)
  return Number.isFinite(numericUpper)
    ? Math.min(numericUpper, boundedLower)
    : boundedLower
}

// 在保持用户调整意图的前提下限制地面最大面积。
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

// 按优先轴或较宽松轴逐步缩小地面，直到面积不超过上限。
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

// 将地面边长向下吸附到尺寸步长，并保证不低于最小值。
function snapFloorExtentDown(value, lower) {
  return Math.max(lower, Math.floor(Number(value) / LAYOUT_SIZE_LIMITS.step) * LAYOUT_SIZE_LIMITS.step)
}

// 清洗单个地面边长，按步长和上下限规整。
function sanitizeFloorDimension(value, lower, upper, step, fallback) {
  const raw = Number(value)
  if (!Number.isFinite(raw)) return fallback
  if (raw === fallback) return fallback
  return clampToStep(raw, lower, upper, step, fallback)
}

// 将地面边长按尺寸步长吸附并夹到允许范围。
function snapFloorExtent(value, lower, upper) {
  return clampToStep(value, lower, upper, LAYOUT_SIZE_LIMITS.step)
}

// 读取可选坐标值；缺失时使用调用方提供的默认位置。
function snapOptional(value, fallback) {
  const raw = Number(value)
  if (!Number.isFinite(raw)) return fallback
  return raw
}

// 把座位数向下规整为偶数。
function toEven(value) {
  return Math.floor(value / 2) * 2
}

// 将图元类型映射到布局对象中的集合字段名。
function collectionKeyForKind(kind) {
  if (kind === 'door') return 'doors'
  if (kind === 'window') return 'windows'
  if (kind === 'table') return 'tables'
  return null
}

// 把门、窗口、餐桌展平为统一的碰撞检测列表。
function allLayoutItems(layout) {
  return [
    ...(layout?.doors || []).map((item) => ({ kind: 'door', item })),
    ...(layout?.windows || []).map((item) => ({ kind: 'window', item })),
    ...(layout?.tables || []).map((item) => ({ kind: 'table', item }))
  ]
}

// 判断两个轴对齐矩形是否有重叠面积。
function boxesOverlap(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}

// 判断两组碰撞盒中是否存在任意一对重叠。
function boxesOverlapAny(leftBoxes, rightBoxes) {
  return leftBoxes.some((left) => rightBoxes.some((right) => boxesOverlap(left, right)))
}

// 生成餐桌桌面和椅子的局部矩形，并应用餐桌旋转。
function tableShapeRects(table) {
  const top = tableTopForCapacity(table?.capacity)
  const rects = [
    {
      key: 'top',
      x: -top.width / 2,
      y: -top.height / 2,
      width: top.width,
      height: top.height
    },
    ...tableChairRectsForCapacity(table?.capacity)
  ]
  return rects.map((rect) => rotateLocalRect(rect, normalizeTableRotation(table?.rotation)))
}

// 将图元局部矩形转换成布局世界坐标中的碰撞盒。
function localRectToBox(item, rect) {
  return {
    left: item.x + rect.x,
    right: item.x + rect.x + rect.width,
    top: item.y + rect.y,
    bottom: item.y + rect.y + rect.height
  }
}

// 根据 90 度旋转交换 footprint 的宽高。
function rotatedFootprint(footprint, item) {
  return normalizeTableRotation(item?.rotation) === 90
    ? { width: footprint.height, height: footprint.width }
    : footprint
}

// 将局部矩形绕原点旋转 90 度并重新计算包围盒。
function rotateLocalRect(rect, rotation) {
  if (rotation !== 90) return rect
  const corners = [
    rotatePoint(rect.x, rect.y),
    rotatePoint(rect.x + rect.width, rect.y),
    rotatePoint(rect.x, rect.y + rect.height),
    rotatePoint(rect.x + rect.width, rect.y + rect.height)
  ]
  const xs = corners.map((point) => point.x)
  const ys = corners.map((point) => point.y)
  return {
    ...rect,
    x: Math.min(...xs),
    y: Math.min(...ys),
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys)
  }
}

// 将局部坐标点绕原点旋转 90 度。
function rotatePoint(x, y) {
  return { x: -y, y: x }
}

// 将门窗吸附到最近墙面，并限制在该墙面的可用范围内。
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

// 根据点到四面墙的距离选择最近墙面。
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

// 根据墙面方向选择门或窗口的横向/纵向 footprint。
function wallFootprintFor(kind, item) {
  const side = normalizeWallSide(item?.wall_side, kind === 'door' ? 'left' : 'top')
  return side === 'top' || side === 'bottom'
    ? FOOTPRINTS[kind].horizontal
    : FOOTPRINTS[kind].vertical
}

// 校验墙面方向，非法值回退到调用方指定方向。
function normalizeWallSide(side, fallback) {
  return ['top', 'right', 'bottom', 'left'].includes(side) ? side : fallback
}

// 门窗移动后需要把吸附得到的 wall_side 写回布局对象。
function wallSidePatch(kind, point) {
  if (kind !== 'door' && kind !== 'window') return {}
  return { wall_side: point.wall_side }
}

// 在已有入口编号后寻找下一个可用的 D 编号。
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

// 在已有窗口编号后寻找下一个可用的 W 编号。
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
