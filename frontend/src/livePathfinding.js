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

export function buildObstacleBoxes(layout) {
  return (layout?.tables || []).flatMap((table) => (
    getItemCollisionBoxes('table', table).map((box) => expandBox(box, LIVE_PATH_OBSTACLE_PADDING))
  ))
}

export function pointInsideAnyBox(point, boxes) {
  return (boxes || []).some((box) => (
    point.x >= box.left &&
    point.x <= box.right &&
    point.y >= box.top &&
    point.y <= box.bottom
  ))
}

export function buildWalkableRoute({ layout = {}, start, end } = {}) {
  if (!isFinitePoint(start) || !isFinitePoint(end)) return []
  const bounds = insetBounds(floorBoundsForLayout(layout), LIVE_PATH_FLOOR_MARGIN)
  const boxes = buildObstacleBoxes(layout)
  const startCell = nearestWalkableCell(pointToCell(start, bounds), bounds, boxes)
  const endCell = nearestWalkableCell(pointToCell(end, bounds), bounds, boxes)
  if (!startCell || !endCell) return [cleanPoint(start), cleanPoint(end)]

  const cells = findRouteCells(startCell, endCell, bounds, boxes)
  if (!cells.length) return [cleanPoint(start), cleanPoint(end)]

  const routedPoints = simplifyPath(cells.map((cell) => cellToPoint(cell, bounds)))
  return dedupePoints([
    cleanPoint(start),
    ...routedPoints.filter((point) => !samePoint(point, start) && !samePoint(point, end)),
    cleanPoint(end)
  ])
}

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

export function pathLength(path) {
  const points = (path || []).filter(isFinitePoint)
  let total = 0
  for (let index = 1; index < points.length; index += 1) {
    total += distance(points[index - 1], points[index])
  }
  return total
}

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

function reconstructPath(cameFrom, current) {
  const path = [current]
  let cursor = current
  while (cameFrom.has(cellKey(cursor))) {
    cursor = cameFrom.get(cellKey(cursor))
    path.push(cursor)
  }
  return path.reverse()
}

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

function isWalkableCell(cell, bounds, boxes) {
  if (cell.col < 0 || cell.row < 0 || cell.col >= columnCount(bounds) || cell.row >= rowCount(bounds)) return false
  return !pointInsideAnyBox(cellToPoint(cell, bounds), boxes)
}

function pointToCell(point, bounds) {
  return {
    col: clamp(Math.round((point.x - bounds.x) / LIVE_PATH_GRID_STEP), 0, columnCount(bounds) - 1),
    row: clamp(Math.round((point.y - bounds.y) / LIVE_PATH_GRID_STEP), 0, rowCount(bounds) - 1)
  }
}

function cellToPoint(cell, bounds) {
  return cleanPoint({
    x: bounds.x + cell.col * LIVE_PATH_GRID_STEP,
    y: bounds.y + cell.row * LIVE_PATH_GRID_STEP
  })
}

function columnCount(bounds) {
  return Math.max(1, Math.floor((bounds.right - bounds.x) / LIVE_PATH_GRID_STEP) + 1)
}

function rowCount(bounds) {
  return Math.max(1, Math.floor((bounds.bottom - bounds.y) / LIVE_PATH_GRID_STEP) + 1)
}

function insetBounds(bounds, margin) {
  return {
    x: bounds.x + margin,
    y: bounds.y + margin,
    right: bounds.right - margin,
    bottom: bounds.bottom - margin
  }
}

function expandBox(box, padding) {
  return {
    left: box.left - padding,
    right: box.right + padding,
    top: box.top - padding,
    bottom: box.bottom + padding
  }
}

function dedupePoints(points) {
  const result = []
  for (const point of points || []) {
    const clean = cleanPoint(point)
    const previous = result[result.length - 1]
    if (!previous || !samePoint(previous, clean)) result.push(clean)
  }
  return result
}

function samePoint(left, right) {
  return Math.abs(Number(left?.x) - Number(right?.x)) < 0.01 &&
    Math.abs(Number(left?.y) - Number(right?.y)) < 0.01
}

function isFinitePoint(point) {
  return Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.y))
}

function cleanPoint(point) {
  return {
    x: round1(point.x),
    y: round1(point.y)
  }
}

function distance(left, right) {
  return Math.hypot(Number(left.x) - Number(right.x), Number(left.y) - Number(right.y))
}

function heuristic(left, right) {
  return Math.abs(left.col - right.col) + Math.abs(left.row - right.row)
}

function cellKey(cell) {
  return `${cell.col}:${cell.row}`
}

function lerp(start, end, amount) {
  return Number(start || 0) + (Number(end || 0) - Number(start || 0)) * amount
}

function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value))
}

function round1(value) {
  return Math.round(Number(value || 0) * 10) / 10
}
