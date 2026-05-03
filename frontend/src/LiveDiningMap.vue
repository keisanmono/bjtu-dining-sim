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

      <g
        v-for="door in layout.doors"
        :key="door.id"
        class="layout-item layout-door live-layout-item"
        :transform="`translate(${door.x}, ${door.y})`"
      >
        <rect v-bind="itemRectFor('door', door)" rx="6" />
        <rect class="layout-door-marker" v-bind="doorMarkerFor(door)" rx="2" />
      </g>

      <g
        v-for="(window, index) in layout.windows"
        :key="window.id"
        class="layout-item layout-window live-layout-item"
        :class="{ 'is-busy': busyWindowIndexes.has(index) }"
        :transform="`translate(${window.x}, ${window.y})`"
      >
        <rect v-bind="itemRectFor('window', window)" rx="6" />
        <rect class="layout-window-marker" v-bind="windowMarkerFor(window)" rx="2" />
        <circle class="window-service-dot" :class="{ 'is-active': busyWindowIndexes.has(index) }" r="4" :cx="serviceDotFor(window).x" :cy="serviceDotFor(window).y" />
      </g>

      <g
        v-for="(table, tableIndex) in layout.tables"
        :key="table.id"
        class="layout-item layout-table live-layout-item table-occupancy"
        :class="`capacity-${table.capacity}`"
        :transform="`translate(${table.x}, ${table.y})`"
      >
        <rect
          v-for="(chair, chairIndex) in chairLayoutFor(table)"
          :key="chair.key"
          class="dining-chair table-seat"
          :class="{ 'is-occupied': isChairOccupied(table, chairIndex) }"
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
        <g
          v-for="group in queuePartyGlyphs"
          :key="`queue-${group.window_index}-${group.party_id}-${group.queue_position}`"
          class="party-group queue-party"
          :transform="`translate(${group.x}, ${group.y})`"
        >
          <line
            v-for="link in partyLinks(group)"
            :key="link.key"
            class="party-link"
            :x1="link.x1"
            :y1="link.y1"
            :x2="link.x2"
            :y2="link.y2"
            :style="{ stroke: partyColor(group) }"
          />
          <circle
            v-for="dot in partyDots(group)"
            :key="dot.key"
            class="party-dot"
            :cx="dot.x"
            :cy="dot.y"
            r="3.8"
            :style="{ fill: partyColor(group) }"
          />
        </g>

        <g
          v-for="group in servicePartyGlyphs"
          :key="`service-${group.window_index}-${group.party_id}`"
          class="party-group service-party"
          :transform="`translate(${group.x}, ${group.y})`"
        >
          <circle class="service-halo" r="9" :style="{ stroke: partyColor(group) }" />
          <circle class="party-dot" r="4.2" :style="{ fill: partyColor(group) }" />
        </g>

        <g
          v-for="group in waitingPartyGlyphs"
          :key="`waiting-${group.party_id}-${group.wait_position}`"
          class="party-group waiting-party"
          :transform="`translate(${group.x}, ${group.y})`"
        >
          <line
            v-for="link in partyLinks(group)"
            :key="link.key"
            class="party-link"
            :x1="link.x1"
            :y1="link.y1"
            :x2="link.x2"
            :y2="link.y2"
            :style="{ stroke: partyColor(group) }"
          />
          <circle
            v-for="dot in partyDots(group)"
            :key="dot.key"
            class="party-dot"
            :cx="dot.x"
            :cy="dot.y"
            r="3.8"
            :style="{ fill: partyColor(group) }"
          />
        </g>

        <g
          v-for="group in seatedPartyGlyphs"
          :key="`seated-${group.table_id}-${group.party_id}`"
          class="party-group seated-party"
          :transform="`translate(${group.x}, ${group.y})`"
        >
          <line
            v-for="link in partyLinks(group)"
            :key="link.key"
            class="party-link"
            :x1="link.x1"
            :y1="link.y1"
            :x2="link.x2"
            :y2="link.y2"
            :style="{ stroke: partyColor(group) }"
          />
          <circle
            v-for="dot in partyDots(group)"
            :key="dot.key"
            class="party-dot"
            :cx="dot.x"
            :cy="dot.y"
            r="3.8"
            :style="{ fill: partyColor(group) }"
          />
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

const props = defineProps({
  layout: {
    type: Object,
    required: true
  },
  state: {
    type: Object,
    default: null
  }
})

const PARTY_COLORS = ['#2f65a3', '#d9912f', '#579a58', '#a94e4e', '#6f5ca8', '#2b8c8c', '#c45b2d']

const floorBounds = computed(() => floorBoundsForLayout(props.layout))
const viewBoxString = computed(() => {
  const viewBox = fitViewBoxForLayout(props.layout, 24)
  return `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`
})
const snapshot = computed(() => props.state || {})

const busyWindowIndexes = computed(() => new Set(
  (snapshot.value.busy_windows || [])
    .map((busy, index) => (busy ? index : null))
    .filter((index) => index !== null)
))

const tableOccupancyById = computed(() => {
  const entries = new Map()
  for (const [index, item] of (snapshot.value.table_occupancy || []).entries()) {
    if (item?.id) entries.set(item.id, item)
    entries.set(index, item)
  }
  return entries
})

const queuePartyGlyphs = computed(() => queueGroups().map((group, index) => ({
  ...group,
  ...windowQueuePosition(group, index)
})))

const servicePartyGlyphs = computed(() => (snapshot.value.window_services || []).map((group) => ({
  ...normalizePartyGroup(group),
  ...windowServicePosition(group)
})))

const waitingPartyGlyphs = computed(() => (snapshot.value.waiting_parties || []).map((group, index) => ({
  ...normalizePartyGroup(group),
  ...waitingPartyPosition(group, index)
})))

const seatedPartyGlyphs = computed(() => {
  const slotByTable = new Map()
  return (snapshot.value.seated_parties || []).map((group) => {
    const normalized = normalizePartyGroup(group)
    const table = tableForGroup(normalized)
    const tableKey = normalized.table_id || normalized.table_index || 'unknown'
    const slot = slotByTable.get(tableKey) || 0
    slotByTable.set(tableKey, slot + 1)
    return {
      ...normalized,
      table_id: normalized.table_id || table?.id,
      table_index: normalized.table_index,
      ...seatedPartyPosition(table, slot)
    }
  }).filter((group) => Number.isFinite(group.x) && Number.isFinite(group.y))
})

function queueGroups() {
  if (Array.isArray(snapshot.value.queue_groups)) {
    return snapshot.value.queue_groups.map(normalizePartyGroup)
  }
  return (snapshot.value.queue_lengths || []).flatMap((length, windowIndex) => (
    Array.from({ length: Math.min(Number(length) || 0, 12) }, (_item, index) => ({
      party_id: `fallback-${windowIndex}-${index}`,
      size: 1,
      member_count: 1,
      window_index: windowIndex,
      queue_position: index
    }))
  ))
}

function normalizePartyGroup(group) {
  return {
    ...group,
    party_id: group?.party_id ?? 'solo',
    size: Math.max(1, Number(group?.size) || 1),
    member_count: Math.max(1, Number(group?.member_count ?? group?.size) || 1),
    window_index: Number(group?.window_index) || 0,
    queue_position: Number(group?.queue_position) || 0,
    wait_position: Number(group?.wait_position) || 0
  }
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
    return {
      x: -footprint.width / 2 + 8,
      y: -3,
      width: footprint.width - 16,
      height: 6
    }
  }
  return {
    x: -3,
    y: -footprint.height / 2 + 8,
    width: 6,
    height: footprint.height - 16
  }
}

function windowMarkerFor(window) {
  const footprint = getItemFootprint('window', window)
  if (window.wall_side === 'left' || window.wall_side === 'right') {
    return {
      x: -3,
      y: -footprint.height / 2 + 6,
      width: 6,
      height: footprint.height - 12
    }
  }
  return {
    x: -footprint.width / 2 + 6,
    y: -3,
    width: footprint.width - 12,
    height: 6
  }
}

function tableTopFor(table) {
  return tableTopForCapacity(table.capacity)
}

function chairLayoutFor(table) {
  return tableChairRectsForCapacity(table.capacity)
}

function tableOccupancyFor(table, index = 0) {
  return tableOccupancyById.value.get(table.id) || tableOccupancyById.value.get(index) || {
    capacity: table.capacity,
    occupied: 0
  }
}

function isChairOccupied(table, chairIndex) {
  return chairIndex < (Number(tableOccupancyFor(table).occupied) || 0)
}

function serviceDotFor(window) {
  const normal = wallNormal(window)
  const footprint = getItemFootprint('window', window)
  return {
    x: normal.x * (footprint.width / 2 + 7),
    y: normal.y * (footprint.height / 2 + 7)
  }
}

function windowQueuePosition(group, fallbackIndex) {
  const window = props.layout.windows[group.window_index] || props.layout.windows[0]
  if (!window) return { x: floorBounds.value.x + 32, y: floorBounds.value.y + 32 }
  const normal = wallNormal(window)
  const tangent = wallTangent(window)
  const footprint = getItemFootprint('window', window)
  const position = Number(group.queue_position ?? fallbackIndex) || 0
  const row = Math.floor(position / 4)
  const col = position % 4
  const perpendicular = (window.wall_side === 'left' || window.wall_side === 'right')
    ? footprint.width / 2
    : footprint.height / 2
  return {
    x: window.x + normal.x * (perpendicular + 18 + row * 18) + tangent.x * ((col - 1.5) * 14),
    y: window.y + normal.y * (perpendicular + 18 + row * 18) + tangent.y * ((col - 1.5) * 14)
  }
}

function windowServicePosition(group) {
  const window = props.layout.windows[group.window_index] || props.layout.windows[0]
  if (!window) return { x: floorBounds.value.x + 32, y: floorBounds.value.y + 32 }
  const normal = wallNormal(window)
  const footprint = getItemFootprint('window', window)
  const perpendicular = (window.wall_side === 'left' || window.wall_side === 'right')
    ? footprint.width / 2
    : footprint.height / 2
  return {
    x: window.x + normal.x * (perpendicular + 8),
    y: window.y + normal.y * (perpendicular + 8)
  }
}

function waitingPartyPosition(group, index) {
  const bounds = floorBounds.value
  const col = index % 5
  const row = Math.floor(index / 5)
  return {
    x: bounds.x + 42 + col * 18,
    y: bounds.y + Math.min(210, (bounds.bottom - bounds.y) * 0.36) + row * 18
  }
}

function seatedPartyPosition(table, slot) {
  if (!table) return { x: Number.NaN, y: Number.NaN }
  const offsets = [
    { x: 0, y: 0 },
    { x: -12, y: -8 },
    { x: 12, y: 8 },
    { x: 12, y: -8 },
    { x: -12, y: 8 }
  ]
  const offset = offsets[slot % offsets.length]
  return {
    x: table.x + offset.x,
    y: table.y + offset.y
  }
}

function tableForGroup(group) {
  if (group.table_id) {
    return props.layout.tables.find((table) => table.id === group.table_id)
  }
  return props.layout.tables[Number(group.table_index) || 0]
}

function partyDots(group) {
  const count = Math.min(8, Math.max(1, Number(group.member_count ?? group.size) || 1))
  if (count === 1) return [{ key: 'p0', x: 0, y: 0 }]
  if (count === 2) return [{ key: 'p0', x: -5, y: 0 }, { key: 'p1', x: 5, y: 0 }]
  if (count === 3) return [
    { key: 'p0', x: -6, y: 4 },
    { key: 'p1', x: 6, y: 4 },
    { key: 'p2', x: 0, y: -6 }
  ]
  if (count === 4) return [
    { key: 'p0', x: -6, y: -5 },
    { key: 'p1', x: 6, y: -5 },
    { key: 'p2', x: -6, y: 5 },
    { key: 'p3', x: 6, y: 5 }
  ]
  return Array.from({ length: count }, (_item, index) => {
    const angle = (Math.PI * 2 * index) / count - Math.PI / 2
    return {
      key: `p${index}`,
      x: Math.cos(angle) * 8,
      y: Math.sin(angle) * 8
    }
  })
}

function partyLinks(group) {
  const dots = partyDots(group)
  return dots.slice(1).map((dot, index) => ({
    key: `l${index}`,
    x1: dots[index].x,
    y1: dots[index].y,
    x2: dot.x,
    y2: dot.y
  }))
}

function partyColor(group) {
  const numeric = Number(group.party_id)
  const index = Number.isFinite(numeric)
    ? numeric
    : String(group.party_id).split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return PARTY_COLORS[Math.abs(index) % PARTY_COLORS.length]
}

function wallNormal(item) {
  const side = item.wall_side || nearestWallSide(item)
  if (side === 'right') return { x: -1, y: 0 }
  if (side === 'bottom') return { x: 0, y: -1 }
  if (side === 'left') return { x: 1, y: 0 }
  return { x: 0, y: 1 }
}

function wallTangent(item) {
  const side = item.wall_side || nearestWallSide(item)
  return side === 'left' || side === 'right'
    ? { x: 0, y: 1 }
    : { x: 1, y: 0 }
}

function nearestWallSide(item) {
  const bounds = floorBounds.value
  const distances = [
    { side: 'top', value: Math.abs(item.y - bounds.y) },
    { side: 'right', value: Math.abs(item.x - bounds.right) },
    { side: 'bottom', value: Math.abs(item.y - bounds.bottom) },
    { side: 'left', value: Math.abs(item.x - bounds.x) }
  ]
  return distances.reduce((nearest, candidate) => (
    candidate.value < nearest.value ? candidate : nearest
  )).side
}
</script>
