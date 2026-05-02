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
        <div class="layout-count-controls" aria-label="入口数量">
          <el-button size="small" :disabled="layout.doors.length <= 1" @click="changeDoorCount(-1)">入口 -</el-button>
          <el-button size="small" :disabled="layout.doors.length >= LAYOUT_MAX_DOORS" @click="changeDoorCount(1)">入口 +</el-button>
        </div>
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
      <rect
        class="wall-line"
        :x="LAYOUT_BOUNDS.x"
        :y="LAYOUT_BOUNDS.y"
        :width="LAYOUT_BOUNDS.right - LAYOUT_BOUNDS.x"
        :height="LAYOUT_BOUNDS.bottom - LAYOUT_BOUNDS.y"
      />

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
          v-bind="itemRectFor('door', door)"
          rx="6"
        />
        <rect
          class="layout-door-marker"
          v-bind="doorMarkerFor(door)"
          rx="2"
        />
      </g>

      <!-- Windows -->
      <g
        v-for="window in layout.windows"
        :key="window.id"
        class="layout-item layout-window"
        :class="{ 'is-selected': isSelected('window', window.id) }"
        :transform="`translate(${window.x}, ${window.y})`"
        @pointerdown.stop="onItemPointerDown($event, 'window', window.id)"
      >
        <rect
          v-bind="itemRectFor('window', window)"
          rx="6"
        />
        <rect
          class="layout-window-marker"
          v-bind="windowMarkerFor(window)"
          rx="2"
        />
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
  LAYOUT_MAX_DOORS,
  LAYOUT_VIEWBOX,
  TABLE_CAPACITY_OPTIONS,
  adjustLayoutDoorCount,
  findItem,
  getItemFootprint,
  itemOverlapsLayout,
  setItemPosition,
  setTableCapacity,
  totalLayoutSeats
} from './layoutEditor.js'

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

function isSelected(kind, id) {
  return selection.value?.kind === kind && selection.value?.id === id
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
    originalItem: { ...item },
    latestLayout: props.layout,
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
  const next = setItemPosition(props.layout, state.kind, state.id, targetX, targetY, { allowOverlap: true })
  state.latestLayout = next
  emit('update:layout', next)
  event.preventDefault()
}

function onPointerUp(event) {
  const state = dragState.value
  if (!state) return
  if (event.target?.releasePointerCapture && event.pointerId) {
    try { event.target.releasePointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
  }
  revertInvalidDrag(state)
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

function changeDoorCount(delta) {
  const next = adjustLayoutDoorCount(props.layout, props.layout.doors.length + delta)
  emit('update:layout', next)
}

function revertInvalidDrag(state) {
  const candidateLayout = state.latestLayout || props.layout
  const current = findItem(candidateLayout, state.kind, state.id)
  if (!current) return
  if (!itemOverlapsLayout(candidateLayout, state.kind, state.id, current.x, current.y, current)) return
  emit('update:layout', replaceLayoutItem(candidateLayout, state.kind, state.originalItem))
}

function replaceLayoutItem(layout, kind, replacement) {
  const collectionKey = kind === 'door' ? 'doors' : kind === 'window' ? 'windows' : 'tables'
  return {
    ...layout,
    [collectionKey]: (layout[collectionKey] || []).map((item) => (
      item.id === replacement.id ? { ...replacement } : item
    ))
  }
}
</script>
