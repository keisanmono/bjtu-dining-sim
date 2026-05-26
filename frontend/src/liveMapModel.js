// 文件说明：实时地图模型工具：把后端 snapshot 转成队列、服务、行走和入座标记。

import {
  getItemFootprint,
  tableTopForCapacity
} from './layoutEditor.js'
import {
  buildWalkableRoute,
  createPathPlanner,
  samplePathAtProgress
} from './livePathfinding.js'

export const PALETTE = ['#4d7ea8', '#cf8b3e', '#5e9c5e', '#9b6a8e', '#4f8b8d', '#a25b5b']

export const QUEUE_VISIBLE_LIMIT = 10
export const QUEUE_STEP = 9
export const QUEUE_OFFSET = 14
export const QUEUE_LONG_BASE = 6
export const QUEUE_LONG_INCREMENT = 1.4
export const QUEUE_SHORT = 5
export const QUEUE_OVERFLOW_LONG = 12
export const QUEUE_OVERFLOW_SHORT = 7
export const LIVE_TRANSITION_MS = 320
export const LIVE_TRANSITION_MIN_MS = 120
export const LIVE_TRANSITION_FRAME_BUFFER_MS = 40

// 将后端 queue_groups/queue_lengths 转成每个窗口外侧的可视排队胶囊。
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

// 统一后端小组字段，补齐人数、窗口、队列位置和餐桌索引默认值。
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

// 按小组 id 稳定映射颜色，保证同一小组在不同状态下颜色一致。
export function partyColor(group) {
  const id = group?.party_id ?? 'solo'
  const numeric = Number(id)
  const index = Number.isFinite(numeric)
    ? numeric
    : String(id).split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return PALETTE[Math.abs(index) % PALETTE.length]
}

// 返回门窗所在墙面指向食堂内部的方向。
export function wallNormal(item) {
  const side = item?.wall_side
  if (side === 'right') return { x: -1, y: 0 }
  if (side === 'bottom') return { x: 0, y: -1 }
  if (side === 'left') return { x: 1, y: 0 }
  return { x: 0, y: 1 }
}

// 将数值限制在指定闭区间内。
export function clamp(value, lower, upper) {
  return Math.max(lower, Math.min(upper, value))
}

// 将后端 snapshot 中服务、等座、入座小组转换为地图目标点。
export function buildLivePartyTargets({ snapshot = {}, layout = {} } = {}) {
  const windows = Array.isArray(layout?.windows) ? layout.windows : []
  const tables = Array.isArray(layout?.tables) ? layout.tables : []
  const targetsByKey = new Map()

  for (const target of buildServiceTargets(snapshot.window_services || [], windows)) {
    targetsByKey.set(target.key, target)
  }

  for (const target of buildWaitingTargets(snapshot.waiting_parties || [], windows, layout)) {
    targetsByKey.set(target.key, target)
  }

  const slotsByTable = new Map()
  for (const rawGroup of snapshot.seated_parties || []) {
    const group = normalizeGroup(rawGroup)
    const table = (group.table_id && tables.find((entry) => entry.id === group.table_id))
      || (Number.isFinite(group.table_index) ? tables[group.table_index] : null)
    if (!table) continue
    const tableKey = group.table_id ?? group.table_index ?? table.id
    const slot = slotsByTable.get(tableKey) || 0
    slotsByTable.set(tableKey, slot + 1)
    const offset = seatedSlotOffset(table, slot)
    const key = livePartyKey(group)
    targetsByKey.set(key, {
      ...group,
      key,
      role: 'seated',
      x: table.x + offset.x,
      y: table.y + offset.y,
      color: partyColor(group)
    })
  }

  return Array.from(targetsByKey.values()).sort((a, b) => String(a.key).localeCompare(String(b.key)))
}

// 比较上一帧和下一帧目标点，生成小组移动、出现和离开的动画路径。
export function buildLivePartyTransitions({ previous = [], next = [], layout = {} } = {}) {
  const previousByKey = keyedTargets(previous)
  const nextByKey = keyedTargets(next)
  const keys = new Set([...previousByKey.keys(), ...nextByKey.keys()])
  const planner = createPathPlanner(layout)

  return Array.from(keys)
    .sort((a, b) => String(a).localeCompare(String(b)))
    .map((key) => {
      const previousTarget = previousByKey.get(key)
      const nextTarget = nextByKey.get(key)
      if (previousTarget && !nextTarget && shouldSuppressServiceExit(previousTarget, nextByKey)) {
        return null
      }
      const previousMotionTarget = previousTarget || samePartyPreviousTarget(nextTarget, previousByKey)
      const from = previousMotionTarget || entryPointForTarget(nextTarget, layout)
      const to = nextTarget || entryPointForTarget(previousTarget, layout)
      const basis = nextTarget || previousTarget
      const appearing = !previousMotionTarget && Boolean(nextTarget)
      const leaving = Boolean(previousTarget) && !nextTarget
      const samePosition = pointDistance(from, to) < 0.5
      if (previousTarget && nextTarget && basis.role !== 'service' && samePosition) {
        return null
      }
      const path = pointDistance(from, to) < 0.5
        ? [cleanPoint(from)]
        : buildWalkableRoute({ planner, start: from, end: to })
      return {
        ...basis,
        key,
        from,
        to,
        path,
        appearing,
        leaving,
        color: basis.color || partyColor(basis)
      }
    })
    .filter(Boolean)
}

// 根据实时 step 返回间隔调整前端补间动画时长。
export function transitionDurationForSnapshotGap(snapshotGapMs, fallbackMs = LIVE_TRANSITION_MS) {
  const fallback = Math.max(LIVE_TRANSITION_MIN_MS, Number(fallbackMs) || LIVE_TRANSITION_MS)
  const gap = Number(snapshotGapMs)
  if (!Number.isFinite(gap) || gap <= 0) {
    return Math.min(LIVE_TRANSITION_MS, fallback)
  }
  return clamp(gap - LIVE_TRANSITION_FRAME_BUFFER_MS, LIVE_TRANSITION_MIN_MS, LIVE_TRANSITION_MS)
}

// 读取后端 timeline 声明或事件终点，得到本 step 需要播放的总时长。
export function backendTimelinePlaybackMs(timeline = {}) {
  const declared = Number(timeline?.playback_ms)
  const eventEnd = Math.max(0, ...(timeline?.events || []).map((event) => (
    Number(event?.playback_end_ms) || (
      (Number(event?.playback_start_ms) || 0) + backendEventPlaybackDurationMs(event)
    )
  )))
  return Math.max(Number.isFinite(declared) ? declared : 0, eventEnd)
}

// 按播放进度从后端逐秒行走帧中采样正在移动的小组标记。
export function buildBackendWalkingMarkers({ timeline = {}, elapsedMs = 0 } = {}) {
  const elapsed = Math.max(0, Number(elapsedMs) || 0)
  return (timeline?.events || [])
    .map((event) => {
      const playbackStart = Math.max(0, Number(event?.playback_start_ms) || 0)
      const playbackDuration = backendEventPlaybackDurationMs(event)
      const playbackEnd = playbackStart + playbackDuration
      if (elapsed < playbackStart || elapsed > playbackEnd) return null
      const progress = clamp((elapsed - playbackStart) / playbackDuration, 0, 1)
      const point = sampleBackendWalkingEvent(event, progress)
      const group = normalizeGroup(event)
      return {
        ...group,
        key: `walking-${group.party_id}-${event?.start_time_sec ?? playbackStart}`,
        role: 'walking',
        table_id: event?.table_id ?? group.table_id,
        x: point.x,
        y: point.y,
        opacity: 1,
        progress: round2(progress),
        color: partyColor(group)
      }
    })
    .filter(Boolean)
}

// 沿补间路径采样小组当前位置，同时处理出现和离开的透明度。
export function interpolateLivePartyMarkers({ previous = [], next = [], progress = 1, layout = {}, transitions = null } = {}) {
  const amount = clamp(Number(progress) || 0, 0, 1)
  const items = transitions || buildLivePartyTransitions({ previous, next, layout })

  return items.map((transition) => {
    const opacity = transition.appearing
      ? amount
      : transition.leaving
        ? 1 - amount
        : 1
    const point = samplePathAtProgress(transition.path, amount)

    return {
      ...transition,
      x: point.x,
      y: point.y,
      opacity: round2(opacity),
      progress: round2(amount),
      path: transition.path,
      color: transition.color || partyColor(transition)
    }
  })
}

// 计算单个后端行走事件的播放时长，缺失字段时用路径秒数兜底。
function backendEventPlaybackDurationMs(event) {
  const declared = Number(event?.playback_duration_ms)
  if (Number.isFinite(declared) && declared > 0) return declared
  const durationSec = Number(event?.duration_sec)
  return clamp(
    Number.isFinite(durationSec) && durationSec > 0 ? durationSec * 90 : LIVE_TRANSITION_MS,
    LIVE_TRANSITION_MS,
    900
  )
}

// 优先按后端 frames 逐秒插值采样；没有 frames 时退回 path 采样。
function sampleBackendWalkingEvent(event, progress) {
  const frames = Array.isArray(event?.frames)
    ? event.frames
      .filter((frame) => Number.isFinite(Number(frame?.time_sec)))
      .map((frame) => ({
        time_sec: Number(frame.time_sec),
        x: Number(frame.x),
        y: Number(frame.y),
        progress: Number(frame.progress)
      }))
      .filter((frame) => Number.isFinite(frame.x) && Number.isFinite(frame.y))
      .sort((left, right) => left.time_sec - right.time_sec)
    : []
  if (frames.length) {
    const startSec = Number(event?.start_time_sec)
    const endSec = Number(event?.arrive_time_sec)
    const first = frames[0]
    const last = frames[frames.length - 1]
    const targetSec = Number.isFinite(startSec) && Number.isFinite(endSec)
      ? startSec + (endSec - startSec) * progress
      : first.time_sec + (last.time_sec - first.time_sec) * progress
    if (targetSec <= first.time_sec) return cleanPoint(first)
    if (targetSec >= last.time_sec) return cleanPoint(last)
    for (let index = 1; index < frames.length; index += 1) {
      const previous = frames[index - 1]
      const next = frames[index]
      if (targetSec <= next.time_sec) {
        const span = Math.max(1, next.time_sec - previous.time_sec)
        const local = clamp((targetSec - previous.time_sec) / span, 0, 1)
        return cleanPoint({
          x: previous.x + (next.x - previous.x) * local,
          y: previous.y + (next.y - previous.y) * local
        })
      }
    }
    return cleanPoint(last)
  }

  const fallbackPath = Array.isArray(event?.path) && event.path.length
    ? event.path
    : [event?.from, event?.to].filter(Boolean)
  return samplePathAtProgress(fallbackPath, progress)
}

// 把正在窗口服务的小组放到对应窗口内侧服务点。
function buildServiceTargets(services, windows) {
  return (services || []).map((rawService) => {
    const group = normalizeGroup(rawService)
    const windowItem = windows[group.window_index] || windows[0]
    if (!windowItem) return null
    const point = servicePointForWindow(windowItem)
    return {
      ...group,
      key: serviceTargetKey(group),
      role: 'service',
      x: round1(point.x),
      y: round1(point.y),
      member_count: Math.max(1, Number(group.member_count) || 1),
      color: partyColor(group)
    }
  }).filter(Boolean)
}

// 服务状态使用 party_id 和 window_index 组成独立 key，避免与入座 key 冲突。
function serviceTargetKey(group) {
  return `service-${group?.party_id ?? 'solo'}-${group?.window_index ?? 0}`
}

// 同一小组刚从服务转入等座/入座时，不额外播放一次离场动画。
function shouldSuppressServiceExit(previousTarget, nextByKey) {
  if (previousTarget?.role !== 'service') return false
  const partyTarget = nextByKey.get(livePartyKey(previousTarget))
  return Boolean(partyTarget && partyTarget.role !== 'service')
}

// 为等座或入座目标寻找同组刚完成服务的位置作为动画起点。
function samePartyPreviousTarget(nextTarget, previousByKey) {
  if (!nextTarget || nextTarget.role === 'service') return null
  const candidates = Array.from(previousByKey.values())
    .filter((target) => target?.role === 'service' && String(target.party_id) === String(nextTarget.party_id))
  if (!candidates.length) return null
  return candidates.sort((left, right) => pointDistance(left, nextTarget) - pointDistance(right, nextTarget))[0]
}

// 把等座小组放到对应窗口外侧的等待区。
function buildWaitingTargets(waitingParties, windows, layout) {
  return (waitingParties || [])
    .map((rawGroup) => {
      const group = normalizeGroup(rawGroup)
      const windowItem = windows[group.window_index] || windows[0]
      const point = windowItem
        ? waitingPointForWindow(windowItem, group.wait_position)
        : entryPointForTarget(group, layout)
      const key = livePartyKey(group)
      return {
        ...group,
        key,
        role: 'waiting',
        x: point.x,
        y: point.y,
        color: partyColor(group)
      }
    })
}

// 计算窗口内侧服务点，供服务中小组和行走起点使用。
function servicePointForWindow(windowItem) {
  const normal = wallNormal(windowItem)
  const footprint = getItemFootprint('window', windowItem)
  const half = (windowItem.wall_side === 'left' || windowItem.wall_side === 'right')
    ? footprint.width / 2
    : footprint.height / 2
  return {
    x: windowItem.x + normal.x * (half + 6),
    y: windowItem.y + normal.y * (half + 6)
  }
}

// 计算窗口外侧等座点，并按等待顺序横向错开。
function waitingPointForWindow(windowItem, waitPosition = 0) {
  const base = servicePointForWindow(windowItem)
  const normal = wallNormal(windowItem)
  const lateral = normal.x === 0 ? { x: 1, y: 0 } : { x: 0, y: 1 }
  const position = Math.max(0, Number(waitPosition) || 0)
  const laneOffset = Math.min(4, position) * 7
  return cleanPoint({
    x: base.x + normal.x * 12 + lateral.x * laneOffset,
    y: base.y + normal.y * 12 + lateral.y * laneOffset
  })
}

// 为同桌多个小组提供轻微偏移，避免圆点完全重叠。
function seatedSlotOffset(table, slot) {
  const top = tableTopForCapacity(table.capacity)
  const horizontalSpan = Math.max(0, top.width / 2 - 6)
  const offsets = [
    { x: 0, y: 0 },
    { x: horizontalSpan, y: 0 },
    { x: -horizontalSpan, y: 0 }
  ]
  return offsets[slot % offsets.length] || { x: 0, y: 0 }
}

// 根据目标来源入口计算新出现或离开动画的门内侧端点。
function entryPointForTarget(target, layout) {
  if (!target) return { x: 0, y: 0 }
  const doors = Array.isArray(layout?.doors) ? layout.doors : []
  const door = doors[target.door_index] || doors[0]
  if (!door) return { x: target.x, y: target.y }
  const normal = wallNormal(door)
  const footprint = getItemFootprint('door', door)
  const half = (door.wall_side === 'left' || door.wall_side === 'right')
    ? footprint.width / 2
    : footprint.height / 2
  return {
    x: door.x + normal.x * (half + 10),
    y: door.y + normal.y * (half + 10)
  }
}

// 将小组 id 规范成地图目标点的稳定 key。
function livePartyKey(group) {
  return `party-${group?.party_id ?? 'solo'}`
}

// 将目标数组按 key 建索引，方便比较前后快照。
function keyedTargets(targets) {
  const map = new Map()
  for (const target of targets || []) {
    if (!target) continue
    map.set(target.key || livePartyKey(target), target)
  }
  return map
}

// 计算两个地图点之间的距离，用于判断是否需要动画。
function pointDistance(left, right) {
  return Math.hypot(Number(left?.x) - Number(right?.x), Number(left?.y) - Number(right?.y))
}

// 规范坐标精度，避免 SVG 属性出现过长小数。
function cleanPoint(point) {
  return {
    x: round1(point.x),
    y: round1(point.y)
  }
}

// 将数值保留一位小数。
function round1(value) {
  return Math.round(Number(value || 0) * 10) / 10
}

// 将数值保留两位小数。
function round2(value) {
  return Math.round(Number(value || 0) * 100) / 100
}

// 取得某个窗口的排队聚合桶，没有时创建。
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

// 判断活跃窗口是否已经收集到足够的可见排队信息。
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

// 根据窗口朝向把可见队列胶囊排在窗口外侧。
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

// 为单个排队小组生成一个大小随人数变化的胶囊。
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

// 根据隐藏排队人数生成溢出胶囊尺寸。
function queueOverflowSize(wide, hiddenPeople) {
  const weight = Math.max(1, Number(hiddenPeople) || 1)
  const longGrowth = Math.min(24, Math.ceil(Math.log2(weight + 1)) * 3)
  const shortGrowth = Math.min(5, Math.ceil(Math.log2(weight + 1)))
  return {
    width: wide ? QUEUE_OVERFLOW_LONG + longGrowth : QUEUE_OVERFLOW_SHORT + shortGrowth,
    height: wide ? QUEUE_OVERFLOW_SHORT + shortGrowth : QUEUE_OVERFLOW_LONG + longGrowth
  }
}
