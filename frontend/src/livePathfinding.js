// 文件说明：实时路径规划工具：为地图动画生成避开餐桌的行走路径。

import {
  floorBoundsForLayout,
  getItemCollisionBoxes
} from './layoutEditor.js'

export const LIVE_PATH_GRID_STEP = 10
export const LIVE_PATH_OBSTACLE_PADDING = 7
export const LIVE_PATH_FLOOR_MARGIN = 6

const DIRECTIONS = [
  { dx: 1, dy: 0 },
  { dx: -1, dy: 0 },
  { dx: 0, dy: 1 },
  { dx: 0, dy: -1 }
]

// 讲解注释：buildObstacleBoxes() 组装展示、请求或内部计算所需的数据结构。
export function buildObstacleBoxes(layout) {
  return (layout?.tables || []).flatMap((table) => (
    getItemCollisionBoxes('table', table).map((box) => expandBox(box, LIVE_PATH_OBSTACLE_PADDING))
  ))
}

// 讲解注释：createPathPlanner() 创建默认对象或运行时辅助对象。
export function createPathPlanner(layout = {}) {
  return {
    bounds: insetBounds(floorBoundsForLayout(layout), LIVE_PATH_FLOOR_MARGIN),
    boxes: buildObstacleBoxes(layout),
    routeCache: new Map(),
    stats: {
      cacheHits: 0,
      cacheMisses: 0,
      astarRuns: 0
    }
  }
}

// 讲解注释：pointInsideAnyBox() 封装本文件中的一个独立处理步骤。
export function pointInsideAnyBox(point, boxes) {
  return (boxes || []).some((box) => (
    point.x >= box.left &&
    point.x <= box.right &&
    point.y >= box.top &&
    point.y <= box.bottom
  ))
}

// 讲解注释：buildWalkableRoute() 组装展示、请求或内部计算所需的数据结构。
export function buildWalkableRoute({ layout = {}, planner = null, start, end } = {}) {
  if (!isFinitePoint(start) || !isFinitePoint(end)) return []
  const activePlanner = planner || createPathPlanner(layout)
  const from = cleanPoint(start)
  const to = cleanPoint(end)
  const cacheKey = routeCacheKey(from, to)
  const cached = activePlanner.routeCache.get(cacheKey)
  if (cached) {
    activePlanner.stats.cacheHits += 1
    return cached
  }
  activePlanner.stats.cacheMisses += 1

  if (!segmentIntersectsAnyBox(from, to, activePlanner.boxes)) {
    const direct = dedupePoints([from, to])
    activePlanner.routeCache.set(cacheKey, direct)
    return direct
  }

  const { bounds, boxes } = activePlanner
  const startCell = nearestWalkableCell(pointToCell(from, bounds), bounds, boxes)
  const endCell = nearestWalkableCell(pointToCell(to, bounds), bounds, boxes)
  if (!startCell || !endCell) {
    const fallback = [from, to]
    activePlanner.routeCache.set(cacheKey, fallback)
    return fallback
  }

  activePlanner.stats.astarRuns += 1
  const cells = findRouteCells(startCell, endCell, bounds, boxes)
  if (!cells.length) {
    const fallback = [from, to]
    activePlanner.routeCache.set(cacheKey, fallback)
    return fallback
  }

  const routedPoints = simplifyPath(cells.map((cell) => cellToPoint(cell, bounds)))
  const route = dedupePoints([
    from,
    ...routedPoints.filter((point) => !samePoint(point, from) && !samePoint(point, to)),
    to
  ])
  activePlanner.routeCache.set(cacheKey, route)
  return route
}

// 讲解注释：samplePathAtProgress() 处理行走路径或路径采样。
export function samplePathAtProgress(path, progress) {
  const points = (path || []).filter(isFinitePoint).map(cleanPoint)
  if (!points.length) return { x: 0, y: 0 }
  if (points.length === 1) return points[0]
  const amount = clamp(Number(progress) || 0, 0, 1)
  if (amount <= 0) return points[0]
  if (amount >= 1) return points[points.length - 1]

  const segments = []
  let total = 0
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1]
    const to = points[index]
    const length = distance(from, to)
    if (length <= 0) continue
    segments.push({ from, to, length })
    total += length
  }
  if (total <= 0) return points[points.length - 1]

  let remaining = total * amount
  for (const segment of segments) {
    if (remaining <= segment.length) {
      const local = remaining / segment.length
      return cleanPoint({
        x: lerp(segment.from.x, segment.to.x, local),
        y: lerp(segment.from.y, segment.to.y, local)
      })
    }
    remaining -= segment.length
  }
  return points[points.length - 1]
}

// 讲解注释：pathLength() 处理行走路径或路径采样。
export function pathLength(path) {
  const points = (path || []).filter(isFinitePoint)
  let total = 0
  for (let index = 1; index < points.length; index += 1) {
    total += distance(points[index - 1], points[index])
  }
  return total
}

// 讲解注释：findRouteCells() 计算可行走路线。
function findRouteCells(start, end, bounds, boxes) {
  const open = [start]
  const cameFrom = new Map()
  const gScore = new Map([[cellKey(start), 0]])
  const fScore = new Map([[cellKey(start), heuristic(start, end)]])
  const openKeys = new Set([cellKey(start)])
  const closed = new Set()

  while (open.length) {
    open.sort((left, right) => (fScore.get(cellKey(left)) || Infinity) - (fScore.get(cellKey(right)) || Infinity))
    const current = open.shift()
    const currentKey = cellKey(current)
    openKeys.delete(currentKey)
    if (currentKey === cellKey(end)) {
      return reconstructPath(cameFrom, current)
    }
    closed.add(currentKey)

    for (const direction of DIRECTIONS) {
      const neighbor = { col: current.col + direction.dx, row: current.row + direction.dy }
      const neighborKey = cellKey(neighbor)
      if (closed.has(neighborKey) || !isWalkableCell(neighbor, bounds, boxes)) continue
      const tentative = (gScore.get(currentKey) || 0) + 1
      if (tentative >= (gScore.get(neighborKey) ?? Infinity)) continue
      cameFrom.set(neighborKey, current)
      gScore.set(neighborKey, tentative)
      fScore.set(neighborKey, tentative + heuristic(neighbor, end))
      if (!openKeys.has(neighborKey)) {
        open.push(neighbor)
        openKeys.add(neighborKey)
      }
    }
  }
  return []
}

// 讲解注释：reconstructPath() 处理行走路径或路径采样。
function reconstructPath(cameFrom, current) {
  const path = [current]
  let cursor = current
  while (cameFrom.has(cellKey(cursor))) {
    cursor = cameFrom.get(cellKey(cursor))
    path.push(cursor)
  }
  return path.reverse()
}

// 讲解注释：nearestWalkableCell() 封装本文件中的一个独立处理步骤。
function nearestWalkableCell(origin, bounds, boxes) {
  if (isWalkableCell(origin, bounds, boxes)) return origin
  const maxRadius = Math.max(columnCount(bounds), rowCount(bounds))
  for (let radius = 1; radius <= maxRadius; radius += 1) {
    const candidates = []
    for (let dx = -radius; dx <= radius; dx += 1) {
      candidates.push({ col: origin.col + dx, row: origin.row - radius })
      candidates.push({ col: origin.col + dx, row: origin.row + radius })
    }
    for (let dy = -radius + 1; dy <= radius - 1; dy += 1) {
      candidates.push({ col: origin.col - radius, row: origin.row + dy })
      candidates.push({ col: origin.col + radius, row: origin.row + dy })
    }
    const found = candidates
      .filter((cell) => isWalkableCell(cell, bounds, boxes))
      .sort((left, right) => heuristic(left, origin) - heuristic(right, origin))[0]
    if (found) return found
  }
  return null
}

// 讲解注释：simplifyPath() 处理行走路径或路径采样。
function simplifyPath(points) {
  const clean = dedupePoints(points)
  if (clean.length <= 2) return clean
  const simplified = [clean[0]]
  for (let index = 1; index < clean.length - 1; index += 1) {
    const previous = simplified[simplified.length - 1]
    const current = clean[index]
    const next = clean[index + 1]
    if ((previous.x === current.x && current.x === next.x) || (previous.y === current.y && current.y === next.y)) {
      continue
    }
    simplified.push(current)
  }
  simplified.push(clean[clean.length - 1])
  return simplified
}

// 讲解注释：isWalkableCell() 封装本文件中的一个独立处理步骤。
function isWalkableCell(cell, bounds, boxes) {
  if (cell.col < 0 || cell.row < 0 || cell.col >= columnCount(bounds) || cell.row >= rowCount(bounds)) return false
  return !pointInsideAnyBox(cellToPoint(cell, bounds), boxes)
}

// 讲解注释：pointToCell() 封装本文件中的一个独立处理步骤。
function pointToCell(point, bounds) {
  return {
    col: clamp(Math.round((point.x - bounds.x) / LIVE_PATH_GRID_STEP), 0, columnCount(bounds) - 1),
    row: clamp(Math.round((point.y - bounds.y) / LIVE_PATH_GRID_STEP), 0, rowCount(bounds) - 1)
  }
}

// 讲解注释：cellToPoint() 封装本文件中的一个独立处理步骤。
function cellToPoint(cell, bounds) {
  return cleanPoint({
    x: bounds.x + cell.col * LIVE_PATH_GRID_STEP,
    y: bounds.y + cell.row * LIVE_PATH_GRID_STEP
  })
}

// 讲解注释：columnCount() 封装本文件中的一个独立处理步骤。
function columnCount(bounds) {
  return Math.max(1, Math.floor((bounds.right - bounds.x) / LIVE_PATH_GRID_STEP) + 1)
}

// 讲解注释：rowCount() 封装本文件中的一个独立处理步骤。
function rowCount(bounds) {
  return Math.max(1, Math.floor((bounds.bottom - bounds.y) / LIVE_PATH_GRID_STEP) + 1)
}

// 讲解注释：insetBounds() 封装本文件中的一个独立处理步骤。
function insetBounds(bounds, margin) {
  return {
    x: bounds.x + margin,
    y: bounds.y + margin,
    right: bounds.right - margin,
    bottom: bounds.bottom - margin
  }
}

// 讲解注释：expandBox() 封装本文件中的一个独立处理步骤。
function expandBox(box, padding) {
  return {
    left: box.left - padding,
    right: box.right + padding,
    top: box.top - padding,
    bottom: box.bottom + padding
  }
}

// 讲解注释：segmentIntersectsAnyBox() 封装本文件中的一个独立处理步骤。
function segmentIntersectsAnyBox(start, end, boxes) {
  return (boxes || []).some((box) => segmentIntersectsBox(start, end, box))
}

// 讲解注释：segmentIntersectsBox() 封装本文件中的一个独立处理步骤。
function segmentIntersectsBox(start, end, box) {
  if (pointInsideAnyBox(start, [box]) || pointInsideAnyBox(end, [box])) return true
  const left = box.left
  const right = box.right
  const top = box.top
  const bottom = box.bottom
  if (Math.max(start.x, end.x) < left || Math.min(start.x, end.x) > right) return false
  if (Math.max(start.y, end.y) < top || Math.min(start.y, end.y) > bottom) return false
  return segmentsIntersect(start, end, { x: left, y: top }, { x: right, y: top }) ||
    segmentsIntersect(start, end, { x: right, y: top }, { x: right, y: bottom }) ||
    segmentsIntersect(start, end, { x: right, y: bottom }, { x: left, y: bottom }) ||
    segmentsIntersect(start, end, { x: left, y: bottom }, { x: left, y: top })
}

// 讲解注释：segmentsIntersect() 封装本文件中的一个独立处理步骤。
function segmentsIntersect(a, b, c, d) {
  const abC = orientation(a, b, c)
  const abD = orientation(a, b, d)
  const cdA = orientation(c, d, a)
  const cdB = orientation(c, d, b)
  return abC * abD <= 0 && cdA * cdB <= 0
}

// 讲解注释：orientation() 封装本文件中的一个独立处理步骤。
function orientation(a, b, c) {
  const value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y)
  if (Math.abs(value) < 0.0001) return 0
  return value > 0 ? 1 : -1
}

// 讲解注释：routeCacheKey() 计算可行走路线。
function routeCacheKey(start, end) {
  return `${start.x},${start.y}->${end.x},${end.y}`
}

// 讲解注释：dedupePoints() 封装本文件中的一个独立处理步骤。
function dedupePoints(points) {
  const result = []
  for (const point of points || []) {
    const clean = cleanPoint(point)
    const previous = result[result.length - 1]
    if (!previous || !samePoint(previous, clean)) result.push(clean)
  }
  return result
}

// 讲解注释：samePoint() 封装本文件中的一个独立处理步骤。
function samePoint(left, right) {
  return Math.abs(Number(left?.x) - Number(right?.x)) < 0.01 &&
    Math.abs(Number(left?.y) - Number(right?.y)) < 0.01
}

// 讲解注释：isFinitePoint() 封装本文件中的一个独立处理步骤。
function isFinitePoint(point) {
  return Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.y))
}

// 讲解注释：cleanPoint() 封装本文件中的一个独立处理步骤。
function cleanPoint(point) {
  return {
    x: round1(point.x),
    y: round1(point.y)
  }
}

// 讲解注释：distance() 封装本文件中的一个独立处理步骤。
function distance(left, right) {
  return Math.hypot(Number(left.x) - Number(right.x), Number(left.y) - Number(right.y))
}

// 讲解注释：heuristic() 封装本文件中的一个独立处理步骤。
function heuristic(left, right) {
  return Math.abs(left.col - right.col) + Math.abs(left.row - right.row)
}

// 讲解注释：cellKey() 封装本文件中的一个独立处理步骤。
function cellKey(cell) {
  return `${cell.col}:${cell.row}`
}

// 讲解注释：lerp() 封装本文件中的一个独立处理步骤。
function lerp(start, end, amount) {
  return Number(start || 0) + (Number(end || 0) - Number(start || 0)) * amount
}

// 讲解注释：clamp() 把数值限制在允许范围内。
function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value))
}

// 讲解注释：round1() 对数值做取整或精度处理。
function round1(value) {
  return Math.round(Number(value || 0) * 10) / 10
}
