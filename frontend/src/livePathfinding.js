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

// 将餐桌碰撞盒扩展成行走避障区域。
export function buildObstacleBoxes(layout) {
  return (layout?.tables || []).flatMap((table) => (
    getItemCollisionBoxes('table', table).map((box) => expandBox(box, LIVE_PATH_OBSTACLE_PADDING))
  ))
}

// 为一次快照动画创建路径规划上下文，包含边界、障碍和缓存统计。
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

// 判断点是否落入任意一个避障矩形。
export function pointInsideAnyBox(point, boxes) {
  return (boxes || []).some((box) => (
    point.x >= box.left &&
    point.x <= box.right &&
    point.y >= box.top &&
    point.y <= box.bottom
  ))
}

// 在起点和终点之间生成避开餐桌的可行走路径，直线无碰撞时直接返回。
export function buildWalkableRoute({ layout = {}, planner = null, start, end } = {}) {
  if (!isFinitePoint(start) || !isFinitePoint(end)) return []
  const activePlanner = planner || createPathPlanner(layout)
  const from = cleanPoint(start)
  const to = cleanPoint(end)
  const cacheKey = routeCacheKey(from, to)
  const cached = activePlanner.routeCache.get(cacheKey)
  if (cached) {
    // 同一快照里多个学生可能走相同路线，缓存避免重复跑 A*。
    activePlanner.stats.cacheHits += 1
    return cached
  }
  activePlanner.stats.cacheMisses += 1

  if (!segmentIntersectsAnyBox(from, to, activePlanner.boxes)) {
    // 直线不穿过餐桌障碍时直接返回两点路径，动画最自然。
    const direct = dedupePoints([from, to])
    activePlanner.routeCache.set(cacheKey, direct)
    return direct
  }

  const { bounds, boxes } = activePlanner
  const startCell = nearestWalkableCell(pointToCell(from, bounds), bounds, boxes)
  const endCell = nearestWalkableCell(pointToCell(to, bounds), bounds, boxes)
  if (!startCell || !endCell) {
    // 起点或终点完全找不到可行走网格时保留直线兜底，避免动画消失。
    const fallback = [from, to]
    activePlanner.routeCache.set(cacheKey, fallback)
    return fallback
  }

  activePlanner.stats.astarRuns += 1
  const cells = findRouteCells(startCell, endCell, bounds, boxes)
  if (!cells.length) {
    // A* 无路可走时同样兜底直线，前端展示不中断。
    const fallback = [from, to]
    activePlanner.routeCache.set(cacheKey, fallback)
    return fallback
  }

  const routedPoints = simplifyPath(cells.map((cell) => cellToPoint(cell, bounds)))
  // 最终路径保留真实起终点，中间网格点只负责绕开障碍。
  const route = dedupePoints([
    from,
    ...routedPoints.filter((point) => !samePoint(point, from) && !samePoint(point, to)),
    to
  ])
  activePlanner.routeCache.set(cacheKey, route)
  return route
}

// samplePathAtProgress() 处理行走路径或路径采样。
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
    // 先统计每段长度，后面才能按整条路径的距离比例采样。
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

// pathLength() 处理行走路径或路径采样。
export function pathLength(path) {
  const points = (path || []).filter(isFinitePoint)
  let total = 0
  for (let index = 1; index < points.length; index += 1) {
    total += distance(points[index - 1], points[index])
  }
  return total
}

// findRouteCells() 计算可行走路线。
function findRouteCells(start, end, bounds, boxes) {
  const open = [start]
  const cameFrom = new Map()
  const gScore = new Map([[cellKey(start), 0]])
  const fScore = new Map([[cellKey(start), heuristic(start, end)]])
  const openKeys = new Set([cellKey(start)])
  const closed = new Set()

  while (open.length) {
    // 简单数组排序实现 A* 优先队列，数据量小于地图网格规模时足够使用。
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
      // 找到更短路径时更新父节点和代价。
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

// reconstructPath() 处理行走路径或路径采样。
function reconstructPath(cameFrom, current) {
  const path = [current]
  let cursor = current
  while (cameFrom.has(cellKey(cursor))) {
    cursor = cameFrom.get(cellKey(cursor))
    path.push(cursor)
  }
  return path.reverse()
}

// 当起点或终点落在障碍中时，向外扩圈寻找最近可行走网格。
function nearestWalkableCell(origin, bounds, boxes) {
  if (isWalkableCell(origin, bounds, boxes)) return origin
  const maxRadius = Math.max(columnCount(bounds), rowCount(bounds))
  for (let radius = 1; radius <= maxRadius; radius += 1) {
    const candidates = []
    // 按方形环逐圈扩展，只检查当前半径边界上的网格。
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

// simplifyPath() 处理行走路径或路径采样。
function simplifyPath(points) {
  const clean = dedupePoints(points)
  if (clean.length <= 2) return clean
  const simplified = [clean[0]]
  for (let index = 1; index < clean.length - 1; index += 1) {
    const previous = simplified[simplified.length - 1]
    const current = clean[index]
    const next = clean[index + 1]
    if ((previous.x === current.x && current.x === next.x) || (previous.y === current.y && current.y === next.y)) {
      // 连续三点共线时删掉中间点，减少 SVG 动画拐点。
      continue
    }
    simplified.push(current)
  }
  simplified.push(clean[clean.length - 1])
  return simplified
}

// 判断网格单元是否在地面范围内且没有落入障碍。
function isWalkableCell(cell, bounds, boxes) {
  if (cell.col < 0 || cell.row < 0 || cell.col >= columnCount(bounds) || cell.row >= rowCount(bounds)) return false
  return !pointInsideAnyBox(cellToPoint(cell, bounds), boxes)
}

// 将世界坐标点映射到路径规划网格单元。
function pointToCell(point, bounds) {
  return {
    col: clamp(Math.round((point.x - bounds.x) / LIVE_PATH_GRID_STEP), 0, columnCount(bounds) - 1),
    row: clamp(Math.round((point.y - bounds.y) / LIVE_PATH_GRID_STEP), 0, rowCount(bounds) - 1)
  }
}

// 将路径规划网格单元映射回世界坐标点。
function cellToPoint(cell, bounds) {
  return cleanPoint({
    x: bounds.x + cell.col * LIVE_PATH_GRID_STEP,
    y: bounds.y + cell.row * LIVE_PATH_GRID_STEP
  })
}

// 计算当前地面范围在路径网格中的列数。
function columnCount(bounds) {
  return Math.max(1, Math.floor((bounds.right - bounds.x) / LIVE_PATH_GRID_STEP) + 1)
}

// 计算当前地面范围在路径网格中的行数。
function rowCount(bounds) {
  return Math.max(1, Math.floor((bounds.bottom - bounds.y) / LIVE_PATH_GRID_STEP) + 1)
}

// 给地面边界内缩一圈，避免行走路径贴住墙线。
function insetBounds(bounds, margin) {
  return {
    x: bounds.x + margin,
    y: bounds.y + margin,
    right: bounds.right - margin,
    bottom: bounds.bottom - margin
  }
}

// 给餐桌障碍矩形增加安全边距。
function expandBox(box, padding) {
  return {
    left: box.left - padding,
    right: box.right + padding,
    top: box.top - padding,
    bottom: box.bottom + padding
  }
}

// 判断线段是否穿过任意一个避障矩形。
function segmentIntersectsAnyBox(start, end, boxes) {
  return (boxes || []).some((box) => segmentIntersectsBox(start, end, box))
}

// 判断线段是否进入或穿过单个避障矩形。
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

// 使用方向测试判断两条线段是否相交。
function segmentsIntersect(a, b, c, d) {
  const abC = orientation(a, b, c)
  const abD = orientation(a, b, d)
  const cdA = orientation(c, d, a)
  const cdB = orientation(c, d, b)
  return abC * abD <= 0 && cdA * cdB <= 0
}

// 计算三点转向方向，接近共线时返回 0。
function orientation(a, b, c) {
  const value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y)
  if (Math.abs(value) < 0.0001) return 0
  return value > 0 ? 1 : -1
}

// routeCacheKey() 计算可行走路线。
function routeCacheKey(start, end) {
  return `${start.x},${start.y}->${end.x},${end.y}`
}

// 清洗路径点并删除连续重复坐标。
function dedupePoints(points) {
  const result = []
  for (const point of points || []) {
    const clean = cleanPoint(point)
    const previous = result[result.length - 1]
    if (!previous || !samePoint(previous, clean)) result.push(clean)
  }
  return result
}

// 以很小容差判断两个世界坐标点是否相同。
function samePoint(left, right) {
  return Math.abs(Number(left?.x) - Number(right?.x)) < 0.01 &&
    Math.abs(Number(left?.y) - Number(right?.y)) < 0.01
}

// 确认点对象包含可用的有限 x/y 坐标。
function isFinitePoint(point) {
  return Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.y))
}

// 规范路径点精度，避免动画坐标出现长小数。
function cleanPoint(point) {
  return {
    x: round1(point.x),
    y: round1(point.y)
  }
}

// 计算两个世界坐标点之间的欧氏距离。
function distance(left, right) {
  return Math.hypot(Number(left.x) - Number(right.x), Number(left.y) - Number(right.y))
}

// A* 使用曼哈顿距离估算网格代价。
function heuristic(left, right) {
  return Math.abs(left.col - right.col) + Math.abs(left.row - right.row)
}

// 将网格坐标转换为 Map/Set 可用的字符串 key。
function cellKey(cell) {
  return `${cell.col}:${cell.row}`
}

// 在两个数值之间按进度线性插值。
function lerp(start, end, amount) {
  return Number(start || 0) + (Number(end || 0) - Number(start || 0)) * amount
}

// 将进度或网格下标限制在给定范围内。
function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value))
}

// 将路径坐标保留一位小数。
function round1(value) {
  return Math.round(Number(value || 0) * 10) / 10
}
