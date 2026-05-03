<template>
  <div class="layout-editor" :class="{ 'is-dragging': isInteracting }">
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
        <div class="layout-size-controls" aria-label="食堂尺寸">
          <span>食堂宽度</span>
          <el-input-number
            :model-value="floorSize.width"
            :min="LAYOUT_SIZE_LIMITS.width.min"
            :max="LAYOUT_SIZE_LIMITS.width.max"
            :step="LAYOUT_SIZE_LIMITS.step"
            size="small"
            controls-position="right"
            @change="changeFloorSize('width', $event)"
          />
          <span>食堂深度</span>
          <el-input-number
            :model-value="floorSize.height"
            :min="LAYOUT_SIZE_LIMITS.height.min"
            :max="LAYOUT_SIZE_LIMITS.height.max"
            :step="LAYOUT_SIZE_LIMITS.step"
            size="small"
            controls-position="right"
            @change="changeFloorSize('height', $event)"
          />
          <el-tag size="small" effect="plain">最多 {{ seatLimit }} 座</el-tag>
        </div>
        <div class="layout-count-controls" aria-label="入口数量">
          <el-button size="small" :disabled="layout.doors.length <= 1" @click="changeDoorCount(-1)">入口 -</el-button>
          <el-button size="small" :disabled="layout.doors.length >= LAYOUT_MAX_DOORS" @click="changeDoorCount(1)">入口 +</el-button>
        </div>
        <div class="layout-viewport-controls" aria-label="视野缩放">
          <el-button size="small" circle :icon="ZoomOut" @click="zoomViewport(1.2)" />
          <el-button size="small" circle :icon="ZoomIn" @click="zoomViewport(0.82)" />
          <el-button size="small" :icon="FullScreen" @click="fitViewportToLayout">适应视野</el-button>
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
      :viewBox="viewBoxString"
      role="img"
      aria-label="食堂俯视布局编辑器"
      @pointerdown="onSvgPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerLeave"
      @wheel.prevent="onWheelZoom"
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
        fill="url(#layout-editor-grid)"
      />
      <rect
        class="wall-line"
        :x="floorBounds.x"
        :y="floorBounds.y"
        :width="floorBounds.right - floorBounds.x"
        :height="floorBounds.bottom - floorBounds.y"
      />

      <g class="layout-resize-handles">
        <rect
          class="layout-resize-handle is-right"
          :x="floorBounds.right - 5"
          :y="(floorBounds.y + floorBounds.bottom) / 2 - 28"
          width="10"
          height="56"
          rx="4"
          @pointerdown.stop="onResizePointerDown($event, 'right')"
        />
        <rect
          class="layout-resize-handle is-bottom"
          :x="(floorBounds.x + floorBounds.right) / 2 - 28"
          :y="floorBounds.bottom - 5"
          width="56"
          height="10"
          rx="4"
          @pointerdown.stop="onResizePointerDown($event, 'bottom')"
        />
        <rect
          class="layout-resize-handle is-corner"
          :x="floorBounds.right - 9"
          :y="floorBounds.bottom - 9"
          width="18"
          height="18"
          rx="4"
          @pointerdown.stop="onResizePointerDown($event, 'corner')"
        />
      </g>

      <!-- Doors -->
      <g
        v-for="door in layout.doors"
        :key="door.id"
        class="layout-item layout-door"
        :class="{
          'is-selected': isSelected('door', door.id),
          'is-overlapping': isCollisionHighlighted('door', door.id)
        }"
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
        :class="{
          'is-selected': isSelected('window', window.id),
          'is-overlapping': isCollisionHighlighted('window', window.id)
        }"
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
        :class="[
          `capacity-${table.capacity}`,
          {
            'is-selected': isSelected('table', table.id),
            'is-overlapping': isCollisionHighlighted('table', table.id)
          }
        ]"
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

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { FullScreen, Refresh, ZoomIn, ZoomOut } from '@element-plus/icons-vue'
import {
  LAYOUT_DEFAULT_FLOOR,
  LAYOUT_GRID_STEP,
  LAYOUT_MAX_DOORS,
  LAYOUT_SIZE_LIMITS,
  TABLE_CAPACITY_OPTIONS,
  adjustLayoutDoorCount,
  fitViewBoxForLayout,
  findItem,
  floorBoundsForLayout,
  getItemFootprint,
  itemOverlapsLayout,
  resizeLayoutFloor,
  resizeLayoutFloorFromHandle,
  setItemPosition,
  setTableCapacity,
  tableChairRectsForCapacity,
  tableTopForCapacity,
  totalLayoutSeats,
  zoomViewBox
} from './layoutEditor.js'

const props = defineProps({
  layout: {
    type: Object,
    required: true
  },
  seatLimit: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['update:layout', 'reset'])

const svgRef = ref(null)
const selection = ref(null)
const dragState = ref(null)
const resizeState = ref(null)
const panState = ref(null)
const viewBox = ref(fitViewBoxForLayout(props.layout))
const keepViewportFitted = ref(true)

const capacityOptions = TABLE_CAPACITY_OPTIONS

const totalSeats = computed(() => totalLayoutSeats(props.layout))
const floorSize = computed(() => props.layout.floor || LAYOUT_DEFAULT_FLOOR)
const floorBounds = computed(() => floorBoundsForLayout(props.layout))
const isInteracting = computed(() => Boolean(dragState.value || resizeState.value || panState.value))
const viewBoxString = computed(() => (
  `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.width} ${viewBox.value.height}`
))

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

watch(
  () => props.layout.floor,
  () => {
    if (keepViewportFitted.value) {
      viewBox.value = fitViewBoxForLayout(props.layout)
    }
  },
  { deep: true }
)

function isSelected(kind, id) {
  return selection.value?.kind === kind && selection.value?.id === id
}

function isCollisionHighlighted(kind, id) {
  const state = dragState.value
  if (!state) return false
  const candidateLayout = state.latestLayout || props.layout
  const current = findItem(candidateLayout, kind, id)
  if (!current) return false
  return itemOverlapsLayout(candidateLayout, kind, id, current.x, current.y, current)
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

function clientToSvgPoint(clientX, clientY) {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return { x: 0, y: 0 }
  const current = viewBox.value
  return {
    x: current.x + ((clientX - rect.left) / rect.width) * current.width,
    y: current.y + ((clientY - rect.top) / rect.height) * current.height
  }
}

function clientDeltaToSvg(deltaX, deltaY, sourceViewBox) {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const rect = svg.getBoundingClientRect()
  if (!rect.width || !rect.height) return { x: 0, y: 0 }
  return {
    x: (deltaX / rect.width) * sourceViewBox.width,
    y: (deltaY / rect.height) * sourceViewBox.height
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

function onResizePointerDown(event, handle) {
  const point = clientToSvgPoint(event.clientX, event.clientY)
  const bounds = floorBounds.value
  resizeState.value = {
    handle,
    offsetX: point.x - bounds.right,
    offsetY: point.y - bounds.bottom,
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
    panState.value = {
      startClientX: event.clientX,
      startClientY: event.clientY,
      startViewBox: { ...viewBox.value },
      pointerId: event.pointerId
    }
    keepViewportFitted.value = false
    if (svgRef.value?.setPointerCapture) {
      try { svgRef.value.setPointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
    }
    event.preventDefault()
  }
}

function onPointerMove(event) {
  if (resizeState.value) {
    const state = resizeState.value
    const point = clientToSvgPoint(event.clientX, event.clientY)
    const next = resizeLayoutFloorFromHandle(
      props.layout,
      state.handle,
      point.x - state.offsetX,
      point.y - state.offsetY
    )
    emit('update:layout', next)
    event.preventDefault()
    return
  }
  if (panState.value) {
    const state = panState.value
    const delta = clientDeltaToSvg(event.clientX - state.startClientX, event.clientY - state.startClientY, state.startViewBox)
    viewBox.value = {
      ...state.startViewBox,
      x: state.startViewBox.x - delta.x,
      y: state.startViewBox.y - delta.y
    }
    event.preventDefault()
    return
  }
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
  if (resizeState.value) {
    if (event.target?.releasePointerCapture && event.pointerId) {
      try { event.target.releasePointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
    }
    resizeState.value = null
    return
  }
  if (panState.value) {
    if (svgRef.value?.releasePointerCapture && event.pointerId) {
      try { svgRef.value.releasePointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
    }
    panState.value = null
    return
  }
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

function onWheelZoom(event) {
  const point = clientToSvgPoint(event.clientX, event.clientY)
  zoomViewport(event.deltaY < 0 ? 0.86 : 1.16, point)
}

function zoomViewport(factor, focusPoint = null) {
  keepViewportFitted.value = false
  viewBox.value = zoomViewBox(viewBox.value, factor, focusPoint)
}

function fitViewportToLayout() {
  keepViewportFitted.value = true
  viewBox.value = fitViewBoxForLayout(props.layout)
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

function changeFloorSize(axis, value) {
  const nextSize = {
    ...floorSize.value,
    [axis]: Number(value)
  }
  emit('update:layout', resizeLayoutFloor(props.layout, nextSize))
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
