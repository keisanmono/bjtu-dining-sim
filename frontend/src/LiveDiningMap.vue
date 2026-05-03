<template>
  <div class="live-dining-map-shell">
    <svg
      class="live-dining-map dining-floor-plan"
      :viewBox="viewBoxString"
      role="img"
      aria-label="实时食堂仿真地图"
      @click="clearSelection"
    >
      <defs>
        <pattern
          id="live-dining-grid"
          :width="LAYOUT_GRID_STEP"
          :height="LAYOUT_GRID_STEP"
          patternUnits="userSpaceOnUse"
        >
          <path :d="`M ${LAYOUT_GRID_STEP} 0 L 0 0 0 ${LAYOUT_GRID_STEP}`" class="layout-grid-line" />
        </pattern>
      </defs>

      <rect
        class="floor-fill"
        :x="floorBounds.x"
        :y="floorBounds.y"
        :width="floorBounds.right - floorBounds.x"
        :height="floorBounds.bottom - floorBounds.y"
        rx="10"
      />
      <rect
        class="floor-grid"
        :x="floorBounds.x"
        :y="floorBounds.y"
        :width="floorBounds.right - floorBounds.x"
        :height="floorBounds.bottom - floorBounds.y"
        fill="url(#live-dining-grid)"
      />
      <rect
        class="wall-line"
        :x="floorBounds.x"
        :y="floorBounds.y"
        :width="floorBounds.right - floorBounds.x"
        :height="floorBounds.bottom - floorBounds.y"
      />

      <g
        v-for="door in doors"
        :key="door.id"
        class="layout-item layout-door live-layout-item"
        :transform="`translate(${door.x}, ${door.y})`"
      >
        <rect class="layout-door-body" v-bind="itemRectFor('door', door)" rx="6" />
        <rect class="layout-door-marker" v-bind="doorMarkerFor(door)" rx="2" />
      </g>

      <g
        v-for="(window, idx) in windows"
        :key="window.id"
        class="layout-item layout-window live-layout-item live-clickable-item"
        :class="windowStateClasses(idx)"
        :transform="`translate(${window.x}, ${window.y})`"
        role="button"
        tabindex="0"
        :aria-label="windowAriaLabel(window, idx)"
        :aria-pressed="selectedWindowIndex === idx"
        @click.stop="toggleWindowSelection(idx)"
        @keydown.enter.prevent="toggleWindowSelection(idx)"
        @keydown.space.prevent="toggleWindowSelection(idx)"
      >
        <rect class="layout-window-body" v-bind="itemRectFor('window', window)" rx="6" />
        <rect class="layout-window-marker" v-bind="windowMarkerFor(window)" rx="2" />
      </g>

      <g
        v-for="(table, tableIndex) in tables"
        :key="table.id"
        class="layout-item layout-table live-layout-item table-occupancy"
        :class="[`capacity-${table.capacity}`, { 'has-occupancy': tableOccupancyFor(table, tableIndex).occupied > 0 }]"
        :transform="`translate(${table.x}, ${table.y})`"
      >
        <g class="table-shape" :transform="tableTransformFor(table)">
          <rect
            v-for="(chair, chairIndex) in chairLayoutFor(table)"
            :key="chair.key"
            class="dining-chair table-seat"
            :class="{ 'is-occupied': isChairOccupied(table, chairIndex, tableIndex) }"
            :x="chair.x"
            :y="chair.y"
            :width="chair.width"
            :height="chair.height"
            rx="2"
          />
          <rect
            class="table-top"
            :class="{ 'has-occupancy': tableOccupancyFor(table, tableIndex).occupied > 0 }"
            :x="-tableTopFor(table).width / 2"
            :y="-tableTopFor(table).height / 2"
            :width="tableTopFor(table).width"
            :height="tableTopFor(table).height"
            rx="4"
          />
        </g>
      </g>

      <g class="live-party-layer">
        <g class="party-group service-group">
          <circle
            v-for="dot in serviceMarkers"
            :key="dot.key"
            class="service-mark service-party"
            :cx="dot.x"
            :cy="dot.y"
            r="3.2"
            :style="{ fill: dot.color, opacity: dot.opacity }"
          />
        </g>

        <g class="party-group walking-group">
          <g
            v-for="cluster in walkingClusters"
            :key="cluster.key"
            class="walking-party walking-cluster moving-party"
            :transform="`translate(${cluster.cx}, ${cluster.cy})`"
            :style="{ opacity: cluster.opacity }"
          >
            <line
              v-for="link in cluster.links"
              :key="link.key"
              class="party-link"
              :x1="link.x1"
              :y1="link.y1"
              :x2="link.x2"
              :y2="link.y2"
              :style="{ stroke: cluster.color }"
            />
            <circle
              v-for="dot in cluster.dots"
              :key="dot.key"
              class="party-dot"
              :cx="dot.x"
              :cy="dot.y"
              r="1.7"
              :style="{ fill: cluster.color }"
            />
          </g>
        </g>

        <g class="party-group seated-group">
          <g
            v-for="cluster in seatedClusters"
            :key="cluster.key"
            class="seated-party seated-cluster moving-party"
            :transform="`translate(${cluster.cx}, ${cluster.cy})`"
            :style="{ opacity: cluster.opacity }"
          >
            <line
              v-for="link in cluster.links"
              :key="link.key"
              class="party-link"
              :x1="link.x1"
              :y1="link.y1"
              :x2="link.x2"
              :y2="link.y2"
              :style="{ stroke: cluster.color }"
            />
            <circle
              v-for="dot in cluster.dots"
              :key="dot.key"
              class="party-dot"
              :cx="dot.x"
              :cy="dot.y"
              r="1.6"
              :style="{ fill: cluster.color }"
            />
          </g>
        </g>
      </g>
    </svg>

    <div class="window-detail-bar">
      <div v-if="selectedWindowDetail" class="window-detail-panel">
        <div class="window-detail-header">
          <strong>窗口 {{ selectedWindowDetail.id }}</strong>
          <span class="window-detail-stats">
            排队 {{ selectedWindowDetail.totalPeople }} 人 · {{ selectedWindowDetail.totalGroups }} 组
            <template v-if="selectedWindowDetail.serving">· 正在取餐</template>
          </span>
          <button
            type="button"
            class="window-detail-close"
            aria-label="关闭排队详情"
            @click="clearSelection"
          >×</button>
        </div>
        <div v-if="selectedWindowDetail.parties.length" class="window-detail-queue">
          <span
            v-for="party in selectedWindowDetail.parties"
            :key="party.key"
            class="window-detail-capsule"
            :title="`${party.members} 人`"
            :style="{ background: party.color, width: `${party.width}px` }"
          />
          <span v-if="selectedWindowDetail.hiddenPeople" class="window-detail-overflow">+{{ selectedWindowDetail.hiddenPeople }}</span>
        </div>
        <div v-else class="window-detail-empty">该窗口暂无排队</div>
      </div>
      <div v-else class="window-detail-hint">点击地图中的任意窗口查看排队详情</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  LAYOUT_GRID_STEP,
  fitViewBoxForLayout,
  floorBoundsForLayout,
  getItemFootprint,
  normalizeTableRotation,
  tableChairRectsForCapacity,
  tableTopForCapacity
} from './layoutEditor.js'
import {
  LIVE_TRANSITION_MS,
  QUEUE_VISIBLE_LIMIT,
  backendTimelinePlaybackMs,
  buildBackendWalkingMarkers,
  buildLivePartyTargets,
  buildLivePartyTransitions,
  clamp,
  interpolateLivePartyMarkers,
  normalizeGroup,
  partyColor,
  transitionDurationForSnapshotGap
} from './liveMapModel.js'

const props = defineProps({
  layout: { type: Object, required: true },
  state: { type: Object, default: null }
})
const emit = defineEmits(['transition-settled'])

const DETAIL_CAPSULE_BASE_PX = 18
const DETAIL_CAPSULE_INC_PX = 6

const floorBounds = computed(() => floorBoundsForLayout(props.layout))
const viewBoxString = computed(() => {
  const viewBox = fitViewBoxForLayout(props.layout, 24)
  return `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`
})
const snapshot = computed(() => props.state || {})
const tables = computed(() => props.layout?.tables || [])
const windows = computed(() => props.layout?.windows || [])
const doors = computed(() => props.layout?.doors || [])
const snapshotTableOccupancy = computed(() => snapshot.value.table_occupancy || [])

const selectedWindowIndex = ref(null)
const animatedPartyMarkers = ref([])
const walkingPartyMarkers = ref([])
const displayedTableOccupancy = ref([])
const livePartyTargets = computed(() => buildLivePartyTargets({
  snapshot: snapshot.value,
  layout: props.layout
}))
let lastSettledPartyTargets = []
let partyAnimationFrame = 0
let lastSnapshotArrivedAt = 0

watch(
  () => windows.value.length,
  (count) => {
    if (selectedWindowIndex.value !== null && selectedWindowIndex.value >= count) {
      selectedWindowIndex.value = null
    }
  }
)

watch(
  [livePartyTargets, () => snapshot.value.timeline],
  ([targets, timeline]) => {
    startPartyTransition(targets, timeline)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  cancelPartyAnimation()
})

function toggleWindowSelection(idx) {
  selectedWindowIndex.value = selectedWindowIndex.value === idx ? null : idx
}

function clearSelection() {
  if (selectedWindowIndex.value !== null) {
    selectedWindowIndex.value = null
  }
}

const busyWindowIndexes = computed(() => new Set(
  (snapshot.value.busy_windows || [])
    .map((busy, idx) => (busy ? idx : null))
    .filter((idx) => idx !== null)
))

const queueLengthByWindow = computed(() => {
  const map = new Map()
  ;(snapshot.value.queue_lengths || []).forEach((length, idx) => {
    const value = Math.max(0, Math.floor(Number(length) || 0))
    if (value > 0) map.set(idx, value)
  })
  if (!map.size && Array.isArray(snapshot.value.queue_groups)) {
    for (const group of snapshot.value.queue_groups) {
      const idx = Number.isFinite(Number(group?.window_index)) ? Number(group.window_index) : 0
      const members = Math.max(1, Number(group?.member_count) || Number(group?.size) || 1)
      map.set(idx, (map.get(idx) || 0) + members)
    }
  }
  return map
})

const queueGroupsByWindow = computed(() => {
  const map = new Map()
  for (const raw of snapshot.value.queue_groups || []) {
    const idx = Number.isFinite(Number(raw?.window_index)) ? Number(raw.window_index) : 0
    const list = map.get(idx) || []
    list.push(normalizeGroup(raw))
    map.set(idx, list)
  }
  map.forEach((list) => list.sort((a, b) => a.queue_position - b.queue_position))
  return map
})

const tableOccupancyById = computed(() => {
  const map = new Map()
  ;(displayedTableOccupancy.value || []).forEach((entry, idx) => {
    if (!entry) return
    if (entry.id) map.set(entry.id, entry)
    map.set(idx, entry)
  })
  return map
})

const selectedWindowDetail = computed(() => {
  if (selectedWindowIndex.value === null) return null
  const idx = selectedWindowIndex.value
  const windowItem = windows.value[idx]
  if (!windowItem) return null
  const groups = queueGroupsByWindow.value.get(idx) || []
  const totalPeople = queueLengthByWindow.value.get(idx) || 0
  const totalGroups = groups.length

  let visibleGroups = groups.slice(0, QUEUE_VISIBLE_LIMIT)
  if (!visibleGroups.length && totalPeople > 0) {
    const visibleCount = Math.min(totalPeople, QUEUE_VISIBLE_LIMIT)
    visibleGroups = Array.from({ length: visibleCount }, (_unused, position) => normalizeGroup({
      party_id: `q-${idx}-${position}`,
      size: 1,
      member_count: 1,
      window_index: idx,
      queue_position: position
    }))
  }

  const parties = visibleGroups.map((group, position) => {
    const members = Math.max(1, Number(group.member_count) || Number(group.size) || 1)
    return {
      key: `${idx}-${group.party_id ?? 'solo'}-${position}`,
      color: partyColor(group),
      members,
      width: DETAIL_CAPSULE_BASE_PX + Math.min(4, members - 1) * DETAIL_CAPSULE_INC_PX
    }
  })

  const visibleMembers = parties.reduce((sum, party) => sum + party.members, 0)
  const hiddenPeople = Math.max(0, totalPeople - visibleMembers)
  return {
    id: windowItem.id,
    totalPeople,
    totalGroups: totalGroups || parties.length,
    parties,
    hiddenPeople,
    serving: busyWindowIndexes.value.has(idx)
  }
})

const serviceMarkers = computed(() => (
  animatedPartyMarkers.value.filter((marker) => marker.role === 'service' && marker.opacity > 0)
))

const seatedClusters = computed(() => {
  return animatedPartyMarkers.value
    .filter((marker) => marker.role === 'seated' && marker.opacity > 0)
    .map((marker) => {
      const dots = clusterDots(marker)
      return {
        ...marker,
        cx: marker.x,
        cy: marker.y,
        dots,
        links: clusterLinks(dots)
      }
    })
})

const walkingClusters = computed(() => {
  return walkingPartyMarkers.value
    .filter((marker) => marker.opacity > 0)
    .map((marker) => {
      const dots = clusterDots(marker)
      return {
        ...marker,
        cx: marker.x,
        cy: marker.y,
        dots,
        links: clusterLinks(dots)
      }
    })
})

function startPartyTransition(nextTargets, timeline = null) {
  cancelPartyAnimation()
  walkingPartyMarkers.value = []
  const backendPlaybackMs = backendTimelinePlaybackMs(timeline)
  if (backendPlaybackMs > 0) {
    startBackendTimelineTransition(nextTargets, timeline, backendPlaybackMs)
    return
  }
  const snapshotArrivedAt = now()
  const snapshotIntervalMs = lastSnapshotArrivedAt
    ? snapshotArrivedAt - lastSnapshotArrivedAt
    : LIVE_TRANSITION_MS
  lastSnapshotArrivedAt = snapshotArrivedAt
  const transitionDurationMs = transitionDurationForSnapshotGap(snapshotIntervalMs)
  const previousTargets = transitionStartTargets(lastSettledPartyTargets, animatedPartyMarkers.value)
  const transitions = buildLivePartyTransitions({
    previous: previousTargets,
    next: nextTargets,
    layout: props.layout
  })
  if (!transitions.length) {
    lastSettledPartyTargets = nextTargets
    animatedPartyMarkers.value = settledMarkers(nextTargets)
    settleTableOccupancy()
    emit('transition-settled')
    return
  }

  if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
    animatedPartyMarkers.value = settledMarkers(nextTargets)
    lastSettledPartyTargets = nextTargets
    settleTableOccupancy()
    emit('transition-settled')
    return
  }

  const startedAt = snapshotArrivedAt
  const render = (timestamp) => {
    const progress = clamp((timestamp - startedAt) / transitionDurationMs, 0, 1)
    animatedPartyMarkers.value = interpolateLivePartyMarkers({
      transitions,
      progress,
      layout: props.layout
    })
    if (progress < 1) {
      partyAnimationFrame = window.requestAnimationFrame(render)
      return
    }
    partyAnimationFrame = 0
    lastSettledPartyTargets = nextTargets
    animatedPartyMarkers.value = settledMarkers(nextTargets)
    settleTableOccupancy()
    emit('transition-settled')
  }

  animatedPartyMarkers.value = interpolateLivePartyMarkers({
    transitions,
    progress: 0,
    layout: props.layout
  })
  partyAnimationFrame = window.requestAnimationFrame(render)
}

function startBackendTimelineTransition(nextTargets, timeline, playbackMs) {
  animatedPartyMarkers.value = settledMarkers(nextTargets)

  if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
    lastSettledPartyTargets = nextTargets
    walkingPartyMarkers.value = []
    settleTableOccupancy()
    emit('transition-settled')
    return
  }

  let timelinePlaybackStartedAt = null
  const render = (timestamp) => {
    if (timelinePlaybackStartedAt === null) {
      timelinePlaybackStartedAt = timestamp
      walkingPartyMarkers.value = buildBackendWalkingMarkers({ timeline, elapsedMs: 0 })
      partyAnimationFrame = window.requestAnimationFrame(render)
      return
    }
    const elapsedMs = clamp(timestamp - timelinePlaybackStartedAt, 0, playbackMs)
    walkingPartyMarkers.value = buildBackendWalkingMarkers({ timeline, elapsedMs })
    if (elapsedMs < playbackMs) {
      partyAnimationFrame = window.requestAnimationFrame(render)
      return
    }
    partyAnimationFrame = 0
    lastSettledPartyTargets = nextTargets
    walkingPartyMarkers.value = []
    animatedPartyMarkers.value = settledMarkers(nextTargets)
    settleTableOccupancy()
    emit('transition-settled')
  }

  walkingPartyMarkers.value = buildBackendWalkingMarkers({ timeline, elapsedMs: 0 })
  partyAnimationFrame = window.requestAnimationFrame(render)
}

function settleTableOccupancy() {
  displayedTableOccupancy.value = snapshotTableOccupancy.value.map((entry) => ({ ...entry }))
}

function settledMarkers(targets) {
  return targets
    .filter((target) => target.role === 'service')
    .map((target) => ({ ...target, opacity: 1, progress: 1 }))
}

function transitionStartTargets(settledTargets, visibleMarkers) {
  const targets = new Map()
  for (const target of settledTargets || []) {
    targets.set(target.key, target)
  }
  for (const marker of visibleMarkers || []) {
    targets.set(marker.key, marker)
  }
  return Array.from(targets.values())
}

function cancelPartyAnimation() {
  if (partyAnimationFrame && typeof window !== 'undefined') {
    window.cancelAnimationFrame(partyAnimationFrame)
  }
  partyAnimationFrame = 0
}

function now() {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now()
}

function clusterDots(group) {
  const size = clamp(Number(group?.member_count) || Number(group?.size) || 1, 1, 4)
  if (size === 1) return [{ key: 'p0', x: 0, y: 0 }]
  if (size === 2) return [
    { key: 'p0', x: -2.6, y: 0 },
    { key: 'p1', x: 2.6, y: 0 }
  ]
  if (size === 3) return [
    { key: 'p0', x: -2.8, y: 1.6 },
    { key: 'p1', x: 2.8, y: 1.6 },
    { key: 'p2', x: 0, y: -2.6 }
  ]
  return [
    { key: 'p0', x: -2.6, y: -2.4 },
    { key: 'p1', x: 2.6, y: -2.4 },
    { key: 'p2', x: -2.6, y: 2.4 },
    { key: 'p3', x: 2.6, y: 2.4 }
  ]
}

function clusterLinks(dots) {
  if (!Array.isArray(dots) || dots.length < 2) return []
  return dots.slice(1).map((dot, idx) => ({
    key: `l${idx}`,
    x1: dots[idx].x,
    y1: dots[idx].y,
    x2: dot.x,
    y2: dot.y
  }))
}

function itemRectFor(kind, item) {
  const footprint = getItemFootprint(kind, item)
  return {
    x: -footprint.width / 2,
    y: -footprint.height / 2,
    width: footprint.width,
    height: footprint.height
  }
}

function doorMarkerFor(door) {
  const footprint = getItemFootprint('door', door)
  if (door.wall_side === 'top' || door.wall_side === 'bottom') {
    return { x: -footprint.width / 2 + 8, y: -3, width: footprint.width - 16, height: 6 }
  }
  return { x: -3, y: -footprint.height / 2 + 8, width: 6, height: footprint.height - 16 }
}

function windowMarkerFor(window) {
  const footprint = getItemFootprint('window', window)
  if (window.wall_side === 'left' || window.wall_side === 'right') {
    return { x: -3, y: -footprint.height / 2 + 6, width: 6, height: footprint.height - 12 }
  }
  return { x: -footprint.width / 2 + 6, y: -3, width: footprint.width - 12, height: 6 }
}

function tableTopFor(table) {
  return tableTopForCapacity(table.capacity)
}

function chairLayoutFor(table) {
  return tableChairRectsForCapacity(table.capacity)
}

function tableTransformFor(table) {
  return `rotate(${normalizeTableRotation(table.rotation)})`
}

function tableOccupancyFor(table, index = 0) {
  return tableOccupancyById.value.get(table.id)
    || tableOccupancyById.value.get(index)
    || { capacity: table.capacity, occupied: 0 }
}

function isChairOccupied(table, chairIndex, tableIndex = 0) {
  const occupied = Number(tableOccupancyFor(table, tableIndex).occupied) || 0
  return chairIndex < occupied
}

function windowStateClasses(idx) {
  return {
    'is-busy': busyWindowIndexes.value.has(idx),
    'has-queue': (queueLengthByWindow.value.get(idx) || 0) > 0,
    'is-selected': selectedWindowIndex.value === idx
  }
}

function windowAriaLabel(window, idx) {
  const total = queueLengthByWindow.value.get(idx) || 0
  return total > 0
    ? `窗口 ${window.id}，排队 ${total} 人，点击查看详情`
    : `窗口 ${window.id}，暂无排队，点击查看详情`
}
</script>
