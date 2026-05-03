import { getItemFootprint } from './layoutEditor.js'

export const PALETTE = ['#4d7ea8', '#cf8b3e', '#5e9c5e', '#9b6a8e', '#4f8b8d', '#a25b5b']

export const QUEUE_VISIBLE_LIMIT = 10
export const QUEUE_STEP = 9
export const QUEUE_OFFSET = 14
export const QUEUE_LONG_BASE = 6
export const QUEUE_LONG_INCREMENT = 1.4
export const QUEUE_SHORT = 5
export const QUEUE_OVERFLOW_LONG = 12
export const QUEUE_OVERFLOW_SHORT = 7

export function buildQueueRows({ queueGroups = [], queueLengths = [], windows = [] } = {}) {
  const rows = []
  const buckets = new Map()
  const totals = queueLengths.map((length) => Math.max(0, Math.floor(Number(length) || 0)))
  const knownTotals = totals.length > 0
  const activeWindows = new Set(
    totals
      .map((total, index) => (total > 0 ? index : null))
      .filter((index) => index !== null)
  )

  if (Array.isArray(queueGroups) && queueGroups.length) {
    for (const raw of queueGroups) {
      const windowIndex = Number.isFinite(Number(raw?.window_index)) ? Number(raw.window_index) : 0
      if (!windows[windowIndex]) continue
      const bucket = bucketFor(buckets, windowIndex)
      if (bucket.visible.length < QUEUE_VISIBLE_LIMIT) {
        const group = normalizeGroup(raw)
        bucket.visible.push(group)
        bucket.visiblePeople += group.member_count
      } else if (!knownTotals) {
        const group = normalizeGroup(raw)
        bucket.hiddenPeople += group.member_count
        bucket.hiddenGroups += 1
      }
      if (knownTotals && activeWindows.size && allActiveWindowsFilled(buckets, activeWindows, totals)) {
        break
      }
    }
  }

  totals.forEach((total, windowIndex) => {
    if (total <= 0 || !windows[windowIndex]) return
    const bucket = bucketFor(buckets, windowIndex)
    if (!bucket.visible.length) {
      const visible = Math.min(total, QUEUE_VISIBLE_LIMIT)
      for (let index = 0; index < visible; index += 1) {
        bucket.visible.push(normalizeGroup({
          party_id: `q-${windowIndex}-${index}`,
          size: 1,
          member_count: 1,
          window_index: windowIndex,
          queue_position: index
        }))
        bucket.visiblePeople += 1
      }
    }
    bucket.hiddenPeople = Math.max(0, total - bucket.visiblePeople)
    bucket.hiddenGroups = Math.max(0, total - bucket.visible.length)
  })

  buckets.forEach((bucket, windowIndex) => {
    const windowItem = windows[windowIndex]
    if (!windowItem) return
    const visible = bucket.visible
      .slice(0, QUEUE_VISIBLE_LIMIT)
      .sort((a, b) => a.queue_position - b.queue_position)
    const hiddenPeople = Math.max(0, bucket.hiddenPeople)
    const hiddenGroups = Math.max(0, bucket.hiddenGroups)
    if (!visible.length && hiddenPeople <= 0) return
    rows.push(buildWindowQueueRow({
      windowIndex,
      windowItem,
      visible,
      hiddenPeople,
      hiddenGroups
    }))
  })

  return rows.sort((a, b) => a.windowIndex - b.windowIndex)
}

export function normalizeGroup(group) {
  const id = group?.party_id ?? 'solo'
  return {
    ...group,
    party_id: id,
    size: Math.max(1, Number(group?.size) || 1),
    member_count: Math.max(1, Number(group?.member_count ?? group?.size) || 1),
    window_index: Number.isFinite(Number(group?.window_index)) ? Number(group.window_index) : 0,
    queue_position: Number.isFinite(Number(group?.queue_position)) ? Number(group.queue_position) : 0,
    wait_position: Number.isFinite(Number(group?.wait_position)) ? Number(group.wait_position) : 0,
    table_id: group?.table_id ?? null,
    table_index: Number.isFinite(Number(group?.table_index)) ? Number(group.table_index) : null
  }
}

export function partyColor(group) {
  const id = group?.party_id ?? 'solo'
  const numeric = Number(id)
  const index = Number.isFinite(numeric)
    ? numeric
    : String(id).split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return PALETTE[Math.abs(index) % PALETTE.length]
}

export function wallNormal(item) {
  const side = item?.wall_side
  if (side === 'right') return { x: -1, y: 0 }
  if (side === 'bottom') return { x: 0, y: -1 }
  if (side === 'left') return { x: 1, y: 0 }
  return { x: 0, y: 1 }
}

export function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value))
}

function bucketFor(buckets, windowIndex) {
  const existing = buckets.get(windowIndex)
  if (existing) return existing
  const bucket = {
    visible: [],
    visiblePeople: 0,
    hiddenPeople: 0,
    hiddenGroups: 0
  }
  buckets.set(windowIndex, bucket)
  return bucket
}

function allActiveWindowsFilled(buckets, activeWindows, totals) {
  for (const windowIndex of activeWindows) {
    const bucket = buckets.get(windowIndex)
    if (!bucket) return false
    const total = totals[windowIndex] || 0
    if (total > QUEUE_VISIBLE_LIMIT) {
      if (bucket.visible.length < QUEUE_VISIBLE_LIMIT) return false
      continue
    }
    if (bucket.visiblePeople < total && bucket.visible.length < QUEUE_VISIBLE_LIMIT) return false
  }
  return true
}

function buildWindowQueueRow({ windowIndex, windowItem, visible, hiddenPeople, hiddenGroups }) {
  const normal = wallNormal(windowItem)
  const footprint = getItemFootprint('window', windowItem)
  const half = (windowItem.wall_side === 'left' || windowItem.wall_side === 'right')
    ? footprint.width / 2
    : footprint.height / 2
  const startX = windowItem.x + normal.x * (half + QUEUE_OFFSET)
  const startY = windowItem.y + normal.y * (half + QUEUE_OFFSET)
  const wide = windowItem.wall_side === 'top' || windowItem.wall_side === 'bottom'
  const capsules = visible.map((group, position) => queueCapsuleFor({
    group,
    position,
    windowIndex,
    startX,
    startY,
    normal,
    wide
  }))

  let overflow = null
  if (hiddenPeople > 0 || hiddenGroups > 0) {
    const position = visible.length
    const cx = startX + normal.x * position * QUEUE_STEP
    const cy = startY + normal.y * position * QUEUE_STEP
    const size = queueOverflowSize(wide, hiddenPeople || hiddenGroups)
    overflow = {
      key: `overflow-${windowIndex}`,
      x: cx - size.width / 2,
      y: cy - size.height / 2,
      width: size.width,
      height: size.height,
      rx: size.height / 2,
      ry: size.height / 2,
      hiddenPeople,
      hiddenGroups
    }
  }
  return { windowIndex, capsules, overflow }
}

function queueCapsuleFor({ group, position, windowIndex, startX, startY, normal, wide }) {
  const size = clamp(Number(group.member_count) || Number(group.size) || 1, 1, 6)
  const long = QUEUE_LONG_BASE + Math.min(4, size - 1) * QUEUE_LONG_INCREMENT
  const cx = startX + normal.x * position * QUEUE_STEP
  const cy = startY + normal.y * position * QUEUE_STEP
  const width = wide ? long : QUEUE_SHORT
  const height = wide ? QUEUE_SHORT : long
  return {
    key: `${windowIndex}-${group.party_id}-${position}`,
    x: cx - width / 2,
    y: cy - height / 2,
    width,
    height,
    rx: QUEUE_SHORT / 2,
    ry: QUEUE_SHORT / 2,
    color: partyColor(group)
  }
}

function queueOverflowSize(wide, hiddenPeople) {
  const weight = Math.max(1, Number(hiddenPeople) || 1)
  const longGrowth = Math.min(24, Math.ceil(Math.log2(weight + 1)) * 3)
  const shortGrowth = Math.min(5, Math.ceil(Math.log2(weight + 1)))
  return {
    width: wide ? QUEUE_OVERFLOW_LONG + longGrowth : QUEUE_OVERFLOW_SHORT + shortGrowth,
    height: wide ? QUEUE_OVERFLOW_SHORT + shortGrowth : QUEUE_OVERFLOW_LONG + longGrowth
  }
}
