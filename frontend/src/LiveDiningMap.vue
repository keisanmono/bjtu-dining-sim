<template>
  <div class="live-dining-map-shell">
    <svg
      class="live-dining-map dining-floor-plan"
      :viewBox="viewBoxString"
      role="img"
      aria-label="实时食堂仿真地图"
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

      <g class="waiting-zone">
        <rect
          class="waiting-zone-shape"
          :x="waitingZone.x"
          :y="waitingZone.y"
          :width="waitingZone.width"
          :height="waitingZone.height"
          rx="6"
        />
      </g>

      <g
        v-for="door in doors"
        :key="door.id"
        class="layout-item layout-door live-layout-item"
        :transform="`translate(${door.x}, ${door.y})`"
      >
        <rect v-bind="itemRectFor('door', door)" rx="6" />
        <rect class="layout-door-marker" v-bind="doorMarkerFor(door)" rx="2" />
      </g>

      <g
        v-for="(window, idx) in windows"
        :key="window.id"
        class="layout-item layout-window live-layout-item"
        :class="{ 'is-busy': busyWindowIndexes.has(idx) }"
        :transform="`translate(${window.x}, ${window.y})`"
      >
        <rect v-bind="itemRectFor('window', window)" rx="6" />
        <rect class="layout-window-marker" v-bind="windowMarkerFor(window)" rx="2" />
      </g>

      <g
        v-for="(table, tableIndex) in tables"
        :key="table.id"
        class="layout-item layout-table live-layout-item table-occupancy"
        :class="[`capacity-${table.capacity}`, { 'has-occupancy': tableOccupancyFor(table, tableIndex).occupied > 0 }]"
        :transform="`translate(${table.x}, ${table.y})`"
      >
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

      <g class="live-party-layer">
        <g class="party-group queue-group">
          <g
            v-for="row in queueRows"
            :key="`queue-${row.windowIndex}`"
            class="queue-party"
          >
            <rect
              v-for="cap in row.capsules"
              :key="cap.key"
              class="queue-capsule"
              :x="cap.x"
              :y="cap.y"
              :width="cap.width"
              :height="cap.height"
              :rx="cap.rx"
              :ry="cap.ry"
              :style="{ fill: cap.color }"
            />
            <rect
              v-if="row.overflow"
              class="queue-overflow"
              :x="row.overflow.x"
              :y="row.overflow.y"
              :width="row.overflow.width"
              :height="row.overflow.height"
              :rx="row.overflow.rx"
              :ry="row.overflow.ry"
            />
          </g>
        </g>

        <g class="party-group service-group">
          <circle
            v-for="dot in serviceMarkers"
            :key="dot.key"
            class="service-mark service-party"
            :cx="dot.cx"
            :cy="dot.cy"
            r="3.2"
            :style="{ fill: dot.color }"
          />
        </g>

        <g class="party-group waiting-group">
          <g
            v-for="cap in waitingMarkers.capsules"
            :key="cap.key"
            class="waiting-party waiting-cluster"
            :transform="`translate(${cap.cx}, ${cap.cy})`"
          >
            <line
              v-for="link in cap.links"
              :key="link.key"
              class="party-link"
              :x1="link.x1"
              :y1="link.y1"
              :x2="link.x2"
              :y2="link.y2"
              :style="{ stroke: cap.color }"
            />
            <circle
              v-for="dot in cap.dots"
              :key="dot.key"
              class="party-dot"
              :cx="dot.x"
              :cy="dot.y"
              r="1.9"
              :style="{ fill: cap.color }"
            />
          </g>
          <rect
            v-if="waitingMarkers.overflow"
            class="waiting-overflow"
            :x="waitingMarkers.overflow.x"
            :y="waitingMarkers.overflow.y"
            :width="waitingMarkers.overflow.width"
            :height="waitingMarkers.overflow.height"
            rx="3"
          />
        </g>

        <g class="party-group seated-group">
          <g
            v-for="cluster in seatedClusters"
            :key="cluster.key"
            class="seated-party seated-cluster"
            :transform="`translate(${cluster.cx}, ${cluster.cy})`"
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

    <div class="legend-row live-map-legend">
      <span><i class="legend queue" />排队</span>
      <span><i class="legend service" />取餐中</span>
      <span><i class="legend waiting" />等座</span>
      <span><i class="legend seated" />已入座</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  LAYOUT_GRID_STEP,
  fitViewBoxForLayout,
  floorBoundsForLayout,
  getItemFootprint,
  tableChairRectsForCapacity,
  tableTopForCapacity
} from './layoutEditor.js'
import {
  buildQueueRows,
  clamp,
  normalizeGroup,
  partyColor,
  wallNormal
} from './liveMapModel.js'

const props = defineProps({
  layout: { type: Object, required: true },
  state: { type: Object, default: null }
})

const WAITING_VISIBLE_LIMIT = 8
const WAITING_STEP = 16
const WAITING_INSET = 36
const WAITING_THICKNESS = 22
const WAITING_OVERFLOW_LONG = 18
const WAITING_OVERFLOW_SHORT = 8

const floorBounds = computed(() => floorBoundsForLayout(props.layout))
const viewBoxString = computed(() => {
  const viewBox = fitViewBoxForLayout(props.layout, 24)
  return `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`
})
const snapshot = computed(() => props.state || {})
const tables = computed(() => props.layout?.tables || [])
const windows = computed(() => props.layout?.windows || [])
const doors = computed(() => props.layout?.doors || [])

const busyWindowIndexes = computed(() => new Set(
  (snapshot.value.busy_windows || [])
    .map((busy, idx) => (busy ? idx : null))
    .filter((idx) => idx !== null)
))

const tableOccupancyById = computed(() => {
  const map = new Map()
  ;(snapshot.value.table_occupancy || []).forEach((entry, idx) => {
    if (!entry) return
    if (entry.id) map.set(entry.id, entry)
    map.set(idx, entry)
  })
  return map
})

const queueRows = computed(() => buildQueueRows({
  queueGroups: snapshot.value.queue_groups,
  queueLengths: snapshot.value.queue_lengths || [],
  windows: windows.value
}))

const serviceMarkers = computed(() => {
  let services = []
  if (Array.isArray(snapshot.value.window_services) && snapshot.value.window_services.length) {
    services = snapshot.value.window_services.map(normalizeGroup)
  } else {
    services = Array.from(busyWindowIndexes.value).map((idx) => normalizeGroup({
      party_id: `service-${idx}`,
      size: 1,
      member_count: 1,
      window_index: idx
    }))
  }
  return services
    .map((service) => {
      const windowItem = windows.value[service.window_index] || windows.value[0]
      if (!windowItem) return null
      const normal = wallNormal(windowItem)
      const footprint = getItemFootprint('window', windowItem)
      const half = (windowItem.wall_side === 'left' || windowItem.wall_side === 'right')
        ? footprint.width / 2
        : footprint.height / 2
      return {
        key: `service-${service.window_index}-${service.party_id}`,
        cx: windowItem.x + normal.x * (half + 6),
        cy: windowItem.y + normal.y * (half + 6),
        color: partyColor(service)
      }
    })
    .filter(Boolean)
})

const waitingZone = computed(() => {
  const bounds = floorBounds.value
  const door = doors.value[0]
  let normal = { x: 0, y: 1 }
  let baseX = (bounds.x + bounds.right) / 2
  let baseY = bounds.bottom - WAITING_INSET
  if (door) {
    normal = wallNormal(door)
    const footprint = getItemFootprint('door', door)
    const half = (door.wall_side === 'left' || door.wall_side === 'right')
      ? footprint.width / 2
      : footprint.height / 2
    baseX = door.x + normal.x * (half + WAITING_INSET)
    baseY = door.y + normal.y * (half + WAITING_INSET)
  }
  const tangent = (Math.abs(normal.x) > Math.abs(normal.y))
    ? { x: 0, y: 1 }
    : { x: 1, y: 0 }
  const length = Math.min(170, Math.max(96, (bounds.right - bounds.x) * 0.42))
  const width = tangent.x !== 0 ? length : WAITING_THICKNESS
  const height = tangent.y !== 0 ? length : WAITING_THICKNESS
  const cx = clamp(baseX, bounds.x + width / 2 + 4, bounds.right - width / 2 - 4)
  const cy = clamp(baseY, bounds.y + height / 2 + 4, bounds.bottom - height / 2 - 4)
  return {
    cx,
    cy,
    nx: normal.x,
    ny: normal.y,
    tx: tangent.x,
    ty: tangent.y,
    length,
    width,
    height,
    x: cx - width / 2,
    y: cy - height / 2
  }
})

const waitingMarkers = computed(() => {
  const zone = waitingZone.value
  const groups = (snapshot.value.waiting_parties || []).map(normalizeGroup)
  const visible = groups.slice(0, WAITING_VISIBLE_LIMIT)
  const hidden = groups.slice(WAITING_VISIBLE_LIMIT)
  const denominator = Math.max(1, visible.length - 1)
  const step = visible.length > 1
    ? Math.min(WAITING_STEP, (zone.length - 18) / denominator)
    : 0
  const offsetIdx = (visible.length - 1) / 2
  const capsules = visible.map((group, idx) => {
    const cx = zone.cx + zone.tx * (idx - offsetIdx) * step
    const cy = zone.cy + zone.ty * (idx - offsetIdx) * step
    const dots = clusterDots(group)
    return {
      key: `wait-${group.party_id}-${idx}`,
      cx,
      cy,
      color: partyColor(group),
      dots,
      links: clusterLinks(dots)
    }
  })
  let overflow = null
  if (hidden.length) {
    const idx = visible.length
    const cx = zone.cx + zone.tx * (idx - offsetIdx) * step
    const cy = zone.cy + zone.ty * (idx - offsetIdx) * step
    const width = zone.tx !== 0 ? WAITING_OVERFLOW_LONG : WAITING_OVERFLOW_SHORT
    const height = zone.ty !== 0 ? WAITING_OVERFLOW_LONG : WAITING_OVERFLOW_SHORT
    overflow = {
      x: cx - width / 2,
      y: cy - height / 2,
      width,
      height
    }
  }
  return { capsules, overflow }
})

const seatedClusters = computed(() => {
  const items = []
  const slotByTable = new Map()
  ;(snapshot.value.seated_parties || []).forEach((rawGroup) => {
    const group = normalizeGroup(rawGroup)
    const table = (group.table_id && tables.value.find((entry) => entry.id === group.table_id))
      || (Number.isFinite(group.table_index) ? tables.value[group.table_index] : null)
    if (!table) return
    const tableKey = group.table_id ?? group.table_index ?? table.id
    const slot = slotByTable.get(tableKey) || 0
    slotByTable.set(tableKey, slot + 1)
    const offset = seatedSlotOffset(table, slot)
    const dots = clusterDots(group)
    items.push({
      key: `seat-${tableKey}-${group.party_id}-${slot}`,
      cx: table.x + offset.x,
      cy: table.y + offset.y,
      color: partyColor(group),
      dots,
      links: clusterLinks(dots)
    })
  })
  return items
})

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

function tableOccupancyFor(table, index = 0) {
  return tableOccupancyById.value.get(table.id)
    || tableOccupancyById.value.get(index)
    || { capacity: table.capacity, occupied: 0 }
}

function isChairOccupied(table, chairIndex, tableIndex = 0) {
  const occupied = Number(tableOccupancyFor(table, tableIndex).occupied) || 0
  return chairIndex < occupied
}

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

</script>
