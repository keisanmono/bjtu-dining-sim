<template>
  <div class="layout-editor" :class="{ 'is-dragging': dragState !== null }">
    <div class="layout-editor-toolbar">
      <div class="layout-editor-status">
        <el-tag size="small" :type="selection ? 'primary' : 'info'" effect="plain">
          {{ selectionLabel }}
        </el-tag>
        <span class="layout-editor-summary">
          {{ layout.doors.length }} 入口 / {{ layout.windows.length }} 窗口 / {{ layout.tables.length }} 桌 ({{ totalSeats }} 座)
        </span>
      </div>
      <div class="layout-editor-actions">
        <el-select
          v-if="selectedTable"
          :model-value="selectedTable.capacity"
          size="small"
          class="layout-capacity-select"
          @change="onSelectedCapacityChange"
        >
          <el-option
            v-for="option in capacityOptions"
            :key="option"
            :value="option"
            :label="`${option} 人桌`"
          />
        </el-select>
        <el-button size="small" :icon="Refresh" @click="$emit('reset')">重置布局</el-button>
      </div>
    </div>

    <svg
      ref="svgRef"
      class="dining-floor-plan"
      :viewBox="`0 0 ${LAYOUT_VIEWBOX.width} ${LAYOUT_VIEWBOX.height}`"
      role="img"
      aria-label="食堂俯视布局编辑器"
      @pointerdown="onSvgPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerLeave"
    >
      <defs>
        <pattern
          id="layout-editor-grid"
          :width="LAYOUT_GRID_STEP"
          :height="LAYOUT_GRID_STEP"
          patternUnits="userSpaceOnUse"
        >
          <path :d="`M ${LAYOUT_GRID_STEP} 0 L 0 0 0 ${LAYOUT_GRID_STEP}`" class="layout-grid-line" />
        </pattern>
      </defs>

      <rect class="floor-fill" x="10" y="10" width="340" height="620" rx="10" />
      <rect
        class="floor-grid"
        :x="LAYOUT_BOUNDS.x"
        :y="LAYOUT_BOUNDS.y"
        :width="LAYOUT_BOUNDS.right - LAYOUT_BOUNDS.x"
        :height="LAYOUT_BOUNDS.bottom - LAYOUT_BOUNDS.y"
        fill="url(#layout-editor-grid)"
      />
      <path
        class="wall-line"
        d="M24 24 H336 V616 H24 V204 M24 96 V24"
      />

      <!-- Service counter belt across the top -->
      <rect class="counter-belt" x="48" y="58" width="264" height="6" rx="3" />
      <text class="svg-label" x="48" y="50">取餐窗口</text>
      <text class="svg-note" x="312" y="50" text-anchor="end">{{ layout.windows.length }} 个开放</text>

      <!-- Queue lane indicator (decorative reference) -->
      <path class="queue-lane" :d="queueLanePath" />
      <text class="svg-note" x="48" y="218">排队动线：入口 → 窗口 → 就餐区</text>

      <!-- Dining zone label -->
      <text class="svg-label" x="48" y="234">就餐区桌椅</text>
      <text class="svg-note" x="312" y="234" text-anchor="end">{{ tableTypeSummary }}</text>

      <!-- Doors -->
      <g
        v-for="door in layout.doors"
        :key="door.id"
        class="layout-item layout-door"
        :class="{ 'is-selected': isSelected('door', door.id) }"
        :transform="`translate(${door.x}, ${door.y})`"
        @pointerdown.stop="onItemPointerDown($event, 'door', door.id)"
      >
        <rect
          :x="-FOOTPRINTS.door.width / 2"
          :y="-FOOTPRINTS.door.height / 2"
          :width="FOOTPRINTS.door.width"
          :height="FOOTPRINTS.door.height"
          rx="6"
        />
        <text x="0" y="4" text-anchor="middle">入口</text>
      </g>

      <!-- Windows -->
      <g
        v-for="(window, index) in layout.windows"
        :key="window.id"
        class="layout-item layout-window"
        :class="{ 'is-selected': isSelected('window', window.id) }"
        :transform="`translate(${window.x}, ${window.y})`"
        @pointerdown.stop="onItemPointerDown($event, 'window', window.id)"
      >
        <rect
          :x="-FOOTPRINTS.window.width / 2"
          :y="-FOOTPRINTS.window.height / 2"
          :width="FOOTPRINTS.window.width"
          :height="FOOTPRINTS.window.height"
          rx="6"
        />
        <text x="0" y="4" text-anchor="middle">窗口 {{ index + 1 }}</text>
      </g>

      <!-- Tables -->
      <g
        v-for="(table, index) in layout.tables"
        :key="table.id"
        class="layout-item layout-table"
        :class="[`capacity-${table.capacity}`, { 'is-selected': isSelected('table', table.id) }]"
        :transform="`translate(${table.x}, ${table.y})`"
        @pointerdown.stop="onItemPointerDown($event, 'table', table.id)"
      >
        <rect
          v-for="chair in chairLayoutFor(table)"
          :key="chair.key"
          class="dining-chair"
          :x="chair.x"
          :y="chair.y"
          :width="chair.width"
          :height="chair.height"
          rx="2"
        />
        <rect
          class="table-top"
          :x="-tableTopFor(table).width / 2"
          :y="-tableTopFor(table).height / 2"
          :width="tableTopFor(table).width"
          :height="tableTopFor(table).height"
          rx="4"
        />
        <text class="table-number" x="0" y="3" text-anchor="middle">
          T{{ index + 1 }}·{{ table.capacity }}
        </text>
      </g>
    </svg>

    <p class="layout-editor-hint">
      点击对象进行选择，按住拖动以网格步长 {{ LAYOUT_GRID_STEP }} 调整位置；选中餐桌后可在右上角切换桌型。
    </p>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import {
  LAYOUT_BOUNDS,
  LAYOUT_GRID_STEP,
  LAYOUT_VIEWBOX,
  TABLE_CAPACITY_OPTIONS,
  getItemFootprint,
  setItemPosition,
  setTableCapacity,
  totalLayoutSeats
} from './layoutEditor.js'

const FOOTPRINTS = {
  door: getItemFootprint('door', null),
  window: getItemFootprint('window', null)
}

const props = defineProps({
  layout: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['update:layout', 'reset'])

const svgRef = ref(null)
const selection = ref(null)
const dragState = ref(null)

const capacityOptions = TABLE_CAPACITY_OPTIONS

const totalSeats = computed(() => totalLayoutSeats(props.layout))

const selectedTable = computed(() => {
  if (!selection.value || selection.value.kind !== 'table') return null
  return props.layout.tables.find((table) => table.id === selection.value.id) || null
})

const selectionLabel = computed(() => {
  if (!selection.value) return '未选中对象'
  const sel = selection.value
  if (sel.kind === 'door') return `已选 入口 ${sel.id}`
  if (sel.kind === 'window') {
    const idx = props.layout.windows.findIndex((item) => item.id === sel.id)
    return `已选 窗口 ${idx >= 0 ? idx + 1 : sel.id}`
  }
  if (sel.kind === 'table') {
    const idx = props.layout.tables.findIndex((item) => item.id === sel.id)
    const table = props.layout.tables[idx]
    return `已选 餐桌 T${idx >= 0 ? idx + 1 : '?'} (${table?.capacity || '-'} 人)`
  }
  return '未选中对象'
})

const tableTypeSummary = computed(() => {
  const capacities = [...new Set(props.layout.tables.map((table) => table.capacity))].sort((a, b) => a - b)
  if (!capacities.length) return '无桌椅'
  return `${capacities.join('/')} 座桌混排`
})

const queueLanePath = computed(() => {
  const door = props.layout.doors[0]
  if (!door || !props.layout.windows.length) {
    return 'M48 196 H312'
  }
  const firstWindow = props.layout.windows[0]
  const lastWindow = props.layout.windows[props.layout.windows.length - 1]
  const startX = door.x + FOOTPRINTS.door.width / 2 + 4
  const startY = door.y
  const midY = Math.min(firstWindow.y, lastWindow.y) + 18
  return `M${startX} ${startY} C ${startX + 30} ${startY}, ${startX + 30} ${midY}, ${firstWindow.x} ${midY} H ${lastWindow.x}`
})

function isSelected(kind, id) {
  return selection.value?.kind === kind && selection.value?.id === id
}

function tableTopFor(table) {
  const capacity = Math.max(1, Number(table.capacity) || 1)
  if (capacity <= 2) return { width: 28, height: 18 }
  if (capacity <= 4) return { width: 40, height: 26 }
  return { width: 52, height: 26 }
}

function chairLayoutFor(table) {
  const capacity = Math.max(1, Number(table.capacity) || 1)
  const top = tableTopFor(table)
  const halfW = top.width / 2
  const halfH = top.height / 2
  const chairSize = 10
  const gap = 2

  if (capacity <= 2) {
    // 2-seat: chair on each short side
    return [
      { key: 'L', x: -halfW - gap - chairSize, y: -chairSize / 2, width: chairSize, height: chairSize },
      { key: 'R', x: halfW + gap, y: -chairSize / 2, width: chairSize, height: chairSize }
    ]
  }
  if (capacity <= 4) {
    // 4-seat: one on each side
    return [
      { key: 'T', x: -chairSize / 2, y: -halfH - gap - chairSize, width: chairSize, height: chairSize },
      { key: 'B', x: -chairSize / 2, y: halfH + gap, width: chairSize, height: chairSize },
      { key: 'L', x: -halfW - gap - chairSize, y: -chairSize / 2, width: chairSize, height: chairSize },
      { key: 'R', x: halfW + gap, y: -chairSize / 2, width: chairSize, height: chairSize }
    ]
  }
  // 6-seat: 2 top, 2 bottom, 1 each side
  return [
    { key: 'T1', x: -halfW / 2 - chairSize / 2, y: -halfH - gap - chairSize, width: chairSize, height: chairSize },
    { key: 'T2', x: halfW / 2 - chairSize / 2, y: -halfH - gap - chairSize, width: chairSize, height: chairSize },
    { key: 'B1', x: -halfW / 2 - chairSize / 2, y: halfH + gap, width: chairSize, height: chairSize },
    { key: 'B2', x: halfW / 2 - chairSize / 2, y: halfH + gap, width: chairSize, height: chairSize },
    { key: 'L', x: -halfW - gap - chairSize, y: -chairSize / 2, width: chairSize, height: chairSize },
    { key: 'R', x: halfW + gap, y: -chairSize / 2, width: chairSize, height: chairSize }
  ]
}

function clientToSvgPoint(clientX, clientY) {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return { x: 0, y: 0 }
  return {
    x: ((clientX - rect.left) / rect.width) * LAYOUT_VIEWBOX.width,
    y: ((clientY - rect.top) / rect.height) * LAYOUT_VIEWBOX.height
  }
}

function onItemPointerDown(event, kind, id) {
  selection.value = { kind, id }
  const collectionKey = kind === 'door' ? 'doors' : kind === 'window' ? 'windows' : 'tables'
  const item = (props.layout[collectionKey] || []).find((entry) => entry.id === id)
  if (!item) return
  const point = clientToSvgPoint(event.clientX, event.clientY)
  dragState.value = {
    kind,
    id,
    offsetX: point.x - item.x,
    offsetY: point.y - item.y,
    pointerId: event.pointerId
  }
  if (event.target?.setPointerCapture) {
    try { event.target.setPointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
  }
  event.preventDefault()
}

function onSvgPointerDown(event) {
  // Clicking on background clears selection (only if we didn't start a drag).
  if (event.target === svgRef.value || event.target?.classList?.contains('floor-grid') || event.target?.classList?.contains('floor-fill')) {
    selection.value = null
  }
}

function onPointerMove(event) {
  const state = dragState.value
  if (!state) return
  const point = clientToSvgPoint(event.clientX, event.clientY)
  const targetX = point.x - state.offsetX
  const targetY = point.y - state.offsetY
  const next = setItemPosition(props.layout, state.kind, state.id, targetX, targetY)
  emit('update:layout', next)
  event.preventDefault()
}

function onPointerUp(event) {
  if (!dragState.value) return
  if (event.target?.releasePointerCapture && event.pointerId) {
    try { event.target.releasePointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
  }
  dragState.value = null
}

function onPointerLeave() {
  // Keep drag if pointer is captured; only clear when pointer truly leaves
  // and the drag state is no longer reachable. Pointer capture handles most
  // edge cases; this is a conservative reset for non-capturing browsers.
  if (dragState.value && !document?.elementFromPoint) {
    dragState.value = null
  }
}

function onSelectedCapacityChange(value) {
  if (!selectedTable.value) return
  const next = setTableCapacity(props.layout, selectedTable.value.id, Number(value))
  emit('update:layout', next)
}
</script>
