<!-- 文件说明：布局编辑组件：处理入口、窗口、餐桌和食堂尺寸的交互编辑。 -->

<template>
  <div class="layout-editor" :class="{ 'is-dragging': isInteracting }">
    <div class="layout-editor-toolbar">
      <div class="layout-toolbar-header">
        <div class="layout-editor-status">
          <el-tag size="small" :type="selection ? 'primary' : 'info'" effect="plain">
            {{ selectionLabel }}
          </el-tag>
          <span class="layout-editor-summary">
            {{ layout.doors.length }} 入口 / {{ layout.windows.length }} 窗口 / {{ layout.tables.length }} 桌 ({{ totalSeats }} 座)
          </span>
        </div>
        <el-button size="small" :icon="Refresh" @click="$emit('reset')">重置布局</el-button>
      </div>
      <div class="layout-toolbar-main">
        <div class="layout-control-group layout-resource-controls" aria-label="场景规模">
          <span class="layout-control-heading">规模</span>
          <label class="layout-control-field">
            <span>窗口</span>
            <el-input-number
              :model-value="windowCount"
              aria-label="开放窗口数"
              :min="1"
              :max="30"
              size="small"
              controls-position="right"
              @change="changeWindowCount"
            />
          </label>
          <label class="layout-control-field">
            <span>座位</span>
            <el-input-number
              :model-value="seatCount"
              aria-label="座位数"
              :min="2"
              :max="seatLimit"
              :step="2"
              size="small"
              controls-position="right"
              @change="changeSeatCount"
            />
          </label>
          <el-tag class="layout-limit-tag" size="small" effect="plain">最多 {{ seatLimit }} 座</el-tag>
        </div>
        <div class="layout-control-group layout-size-controls" aria-label="食堂尺寸">
          <span class="layout-control-heading">尺寸</span>
          <label class="layout-control-field">
            <span>宽</span>
            <el-input-number
              :model-value="floorSize.width"
              aria-label="食堂宽度"
              :min="LAYOUT_SIZE_LIMITS.width.min"
              :max="floorWidthMax"
              :step="LAYOUT_SIZE_LIMITS.step"
              size="small"
              controls-position="right"
              data-size-policy="floor width is capped by max area"
              @change="changeFloorSize('width', $event)"
            />
          </label>
          <label class="layout-control-field">
            <span>深</span>
            <el-input-number
              :model-value="floorSize.height"
              aria-label="食堂深度"
              :min="LAYOUT_SIZE_LIMITS.height.min"
              :max="floorHeightMax"
              :step="LAYOUT_SIZE_LIMITS.step"
              size="small"
              controls-position="right"
              data-size-policy="floor height is capped by max area"
              @change="changeFloorSize('height', $event)"
            />
          </label>
        </div>
        <div class="layout-control-group layout-count-controls" aria-label="入口数量">
          <span class="layout-control-heading">入口</span>
          <el-button size="small" :disabled="layout.doors.length <= 1" @click="changeDoorCount(-1)">入口 -</el-button>
          <el-button size="small" :disabled="layout.doors.length >= LAYOUT_MAX_DOORS" @click="changeDoorCount(1)">入口 +</el-button>
        </div>
        <div class="layout-control-group layout-viewport-controls" aria-label="视野缩放">
          <span class="layout-control-heading">视野</span>
          <el-button size="small" circle :icon="ZoomOut" @click="zoomViewport(1.2)" />
          <el-button size="small" circle :icon="ZoomIn" @click="zoomViewport(0.82)" />
          <el-button size="small" :icon="FullScreen" @click="fitViewportToLayout">适应视野</el-button>
        </div>
        <div class="layout-control-group layout-arrange-controls" aria-label="自动排布座位">
          <span class="layout-control-heading">排布</span>
          <el-button size="small" :icon="Operation" @click="autoArrangeTables('spread')">均匀排布</el-button>
          <el-button size="small" :icon="Rank" @click="autoArrangeTables('compact')">密排座位</el-button>
        </div>
        <div v-if="selectedTable" class="layout-control-group layout-table-controls" aria-label="餐桌设置">
          <span class="layout-control-heading">餐桌</span>
          <el-button size="small" :icon="RefreshRight" @click="rotateSelectedTable">旋转餐桌</el-button>
          <el-select
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
        </div>
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
          :x="floorBounds.right - 9"
          :y="(floorBounds.y + floorBounds.bottom) / 2 - 42"
          width="18"
          height="84"
          rx="4"
          @pointerdown.stop="onResizePointerDown($event, 'right')"
        />
        <rect
          class="layout-resize-handle is-bottom"
          :x="(floorBounds.x + floorBounds.right) / 2 - 42"
          :y="floorBounds.bottom - 9"
          width="84"
          height="18"
          rx="4"
          @pointerdown.stop="onResizePointerDown($event, 'bottom')"
        />
        <rect
          class="layout-resize-handle is-corner"
          :x="floorBounds.right - 14"
          :y="floorBounds.bottom - 14"
          width="28"
          height="28"
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
          class="layout-hit-area"
          v-bind="itemHitRectFor('door', door)"
          rx="8"
        />
        <rect
          class="layout-door-body"
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
          class="layout-hit-area"
          v-bind="itemHitRectFor('window', window)"
          rx="8"
        />
        <rect
          class="layout-window-body"
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
          class="layout-hit-area"
          v-bind="itemHitRectFor('table', table)"
          rx="8"
        />
        <g class="table-shape" :transform="tableTransformFor(table)">
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
      </g>
    </svg>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { FullScreen, Operation, Rank, Refresh, RefreshRight, ZoomIn, ZoomOut } from '@element-plus/icons-vue'
import {
  LAYOUT_DEFAULT_FLOOR,
  LAYOUT_GRID_STEP,
  LAYOUT_MAX_DOORS,
  LAYOUT_SIZE_LIMITS,
  TABLE_CAPACITY_OPTIONS,
  adjustLayoutDoorCount,
  arrangeLayoutTables,
  clientDeltaToViewBoxDelta,
  clientPointToViewBoxPoint,
  fitViewBoxForLayout,
  findItem,
  floorBoundsForLayout,
  getItemFootprint,
  itemOverlapsLayout,
  maxFloorDimensionForArea,
  normalizeTableRotation,
  resizeLayoutFloor,
  resizeLayoutFloorFromHandle,
  setItemPosition,
  setTableCapacity,
  setTableRotation,
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
  },
  windowCount: {
    type: Number,
    default: 1
  },
  seatCount: {
    type: Number,
    default: 2
  }
})

const emit = defineEmits(['update:layout', 'update:window-count', 'update:seat-count', 'reset'])

const svgRef = ref(null)
const selection = ref(null)
const dragState = ref(null)
const resizeState = ref(null)
const panState = ref(null)
const viewBox = ref(fitViewBoxForLayout(props.layout))
const keepViewportFitted = ref(true)

const capacityOptions = TABLE_CAPACITY_OPTIONS

// 统计当前布局中所有餐桌容量，用于和配置座位数保持同步。
const totalSeats = computed(() => totalLayoutSeats(props.layout))
// 读取当前食堂地面尺寸，缺省时使用编辑器默认尺寸。
const floorSize = computed(() => props.layout.floor || LAYOUT_DEFAULT_FLOOR)
// 根据最大面积约束计算宽度输入框的上限。
const floorWidthMax = computed(() => maxFloorDimensionForArea('width', floorSize.value))
// 根据最大面积约束计算高度输入框的上限。
const floorHeightMax = computed(() => maxFloorDimensionForArea('height', floorSize.value))
// 将 floor 的 x/y/width/height 转成拖拽和碰撞需要的边界。
const floorBounds = computed(() => floorBoundsForLayout(props.layout))
// 判断当前是否处于拖拽、缩放地面或平移视野的交互中。
const isInteracting = computed(() => Boolean(dragState.value || resizeState.value || panState.value))
// 把响应式 viewBox 对象转成 SVG 属性字符串。
const viewBoxString = computed(() => (
  `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.width} ${viewBox.value.height}`
))

// 仅当选中对象是餐桌时返回对应餐桌，供容量和旋转控件使用。
const selectedTable = computed(() => {
  if (!selection.value || selection.value.kind !== 'table') return null
  return props.layout.tables.find((table) => table.id === selection.value.id) || null
})

// 将当前选中对象转换成人可读的侧栏状态文本。
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

// 判断给定图元是否为当前选中对象。
function isSelected(kind, id) {
  return selection.value?.kind === kind && selection.value?.id === id
}

// 拖拽过程中当候选位置与其他图元碰撞时高亮当前图元。
function isCollisionHighlighted(kind, id) {
  const state = dragState.value
  if (!state) return false
  if (state.kind !== kind || state.id !== id) return false
  const candidateLayout = state.latestLayout || props.layout
  const current = findItem(candidateLayout, kind, id)
  if (!current) return false
  return itemOverlapsLayout(candidateLayout, kind, id, current.x, current.y, current)
}

// 生成门、窗口或餐桌主体在本地坐标中的 SVG 矩形。
function itemRectFor(kind, item) {
  const footprint = getItemFootprint(kind, item)
  return {
    x: -footprint.width / 2,
    y: -footprint.height / 2,
    width: footprint.width,
    height: footprint.height
  }
}

// 给图元增加点击热区，避免小窗口和小门难以选中。
function itemHitRectFor(kind, item) {
  const rect = itemRectFor(kind, item)
  const padding = kind === 'table' ? 12 : 10
  return {
    x: rect.x - padding,
    y: rect.y - padding,
    width: rect.width + padding * 2,
    height: rect.height + padding * 2
  }
}

// 根据门所在墙面生成门缝标记的局部矩形。
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

// 根据窗口所在墙面生成服务窗口标记的局部矩形。
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

// 根据餐桌容量返回桌面可视尺寸。
function tableTopFor(table) {
  return tableTopForCapacity(table.capacity)
}

// 根据餐桌容量返回椅子在餐桌局部坐标中的矩形列表。
function chairLayoutFor(table) {
  return tableChairRectsForCapacity(table.capacity)
}

// 将餐桌旋转角转换成 SVG transform。
function tableTransformFor(table) {
  return `rotate(${normalizeTableRotation(table.rotation)})`
}

// 把浏览器 client 坐标转换为当前 SVG viewBox 坐标。
function clientToSvgPoint(clientX, clientY) {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const rect = svg.getBoundingClientRect()
  return clientPointToViewBoxPoint(clientX, clientY, rect, viewBox.value)
}

// 把浏览器拖动距离转换成当前 SVG viewBox 下的距离。
function clientDeltaToSvg(deltaX, deltaY, sourceViewBox) {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const rect = svg.getBoundingClientRect()
  return clientDeltaToViewBoxDelta(deltaX, deltaY, rect, sourceViewBox)
}

// 开始拖拽门、窗口或餐桌，并记录指针到图元中心的偏移。
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

// 开始拖拽地面尺寸控制点，并记录当前边界偏移。
function onResizePointerDown(event, handle) {
  const point = clientToSvgPoint(event.clientX, event.clientY)
  const bounds = floorBounds.value
  resizeState.value = {
    handle,
    latestLayout: props.layout,
    offsetX: point.x - bounds.right,
    offsetY: point.y - bounds.bottom,
    pointerId: event.pointerId
  }
  if (event.target?.setPointerCapture) {
    try { event.target.setPointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
  }
  event.preventDefault()
}

// 在空白地面按下时清除选择并进入 SVG 视野平移模式。
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

// 根据当前交互状态分别处理地面缩放、视野平移或图元拖拽。
function onPointerMove(event) {
  if (resizeState.value) {
    const state = resizeState.value
    const point = clientToSvgPoint(event.clientX, event.clientY)
    // 地面缩放使用当前指针位置减去初始偏移，保证拖住手柄时边界不跳动。
    const next = resizeLayoutFloorFromHandle(
      state.latestLayout || props.layout,
      state.handle,
      point.x - state.offsetX,
      point.y - state.offsetY
    )
    state.latestLayout = next
    emit('update:layout', next, { source: 'resize', transient: true })
    event.preventDefault()
    return
  }
  if (panState.value) {
    const state = panState.value
    // 平移视野只改变 viewBox，不修改任何布局对象。
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
  // 拖拽中允许临时重叠，用高亮提示；最终是否接受在 pointerup 里判断。
  const next = setItemPosition(state.latestLayout || props.layout, state.kind, state.id, targetX, targetY, { allowOverlap: true })
  state.latestLayout = next
  emit('update:layout', next, { source: 'item', kind: state.kind, transient: true })
  event.preventDefault()
}

// 结束当前指针交互，并在拖拽图元碰撞时回滚位置。
function onPointerUp(event) {
  if (resizeState.value) {
    const state = resizeState.value
    if (event.target?.releasePointerCapture && event.pointerId) {
      try { event.target.releasePointerCapture(event.pointerId) } catch (_error) { /* ignore */ }
    }
    // 缩放结束后强制父组件重新计算座位上限。
    emit('update:layout', state.latestLayout || props.layout, { source: 'resize', transient: false, forceSeatLimit: true })
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
  const reverted = revertInvalidDrag(state)
  if (!reverted) {
    // 门窗移动可能改变可用座位上限，餐桌移动只影响自身位置。
    emit('update:layout', state.latestLayout || props.layout, {
      source: 'item',
      kind: state.kind,
      transient: false,
      forceSeatLimit: state.kind !== 'table'
    })
  }
  dragState.value = null
}

// 兼容不支持 pointer capture 的环境，必要时清理拖拽状态。
function onPointerLeave() {
  // Keep drag if pointer is captured; only clear when pointer truly leaves
  // and the drag state is no longer reachable. Pointer capture handles most
  // edge cases; this is a conservative reset for non-capturing browsers.
  if (dragState.value && !document?.elementFromPoint) {
    dragState.value = null
  }
}

// onWheelZoom() 处理 SVG 视野缩放。
function onWheelZoom(event) {
  const point = clientToSvgPoint(event.clientX, event.clientY)
  zoomViewport(event.deltaY < 0 ? 0.86 : 1.16, point)
}

// zoomViewport() 处理 SVG 视野缩放。
function zoomViewport(factor, focusPoint = null) {
  keepViewportFitted.value = false
  viewBox.value = zoomViewBox(viewBox.value, factor, focusPoint)
}

// 将 SVG 视野重新对齐到当前食堂地面范围。
function fitViewportToLayout() {
  keepViewportFitted.value = true
  viewBox.value = fitViewBoxForLayout(props.layout)
}

// 用户修改餐桌容量时同步更新选中餐桌并触发父组件保存。
function onSelectedCapacityChange(value) {
  if (!selectedTable.value) return
  const next = setTableCapacity(props.layout, selectedTable.value.id, Number(value))
  emit('update:layout', next)
}

// 在 0 度和 90 度之间切换选中餐桌的摆放方向。
function rotateSelectedTable() {
  if (!selectedTable.value) return
  const nextRotation = Number(selectedTable.value.rotation) === 90 ? 0 : 90
  const next = setTableRotation(props.layout, selectedTable.value.id, nextRotation)
  emit('update:layout', next)
}

// 增减入口数量，并让布局工具自动选择不碰撞的墙面位置。
function changeDoorCount(delta) {
  const next = adjustLayoutDoorCount(props.layout, props.layout.doors.length + delta)
  emit('update:layout', next)
}

// 把窗口数量变更交给父组件配置，再由 watch 同步布局。
function changeWindowCount(value) {
  emit('update:window-count', Number(value))
}

// 把座位总数变更交给父组件配置，再重建餐桌布局。
function changeSeatCount(value) {
  emit('update:seat-count', Number(value))
}

// 按紧凑或分散模式重新排列现有餐桌。
function autoArrangeTables(mode) {
  const next = arrangeLayoutTables(props.layout, mode)
  emit('update:layout', next, { source: 'arrange', transient: false })
}

// 修改食堂地面宽高，并在缩小时阻止会压住餐桌的变更。
function changeFloorSize(axis, value) {
  const nextSize = {
    ...floorSize.value,
    [axis]: Number(value)
  }
  // 输入框修改和拖拽缩放共用 resizeLayoutFloor，保持碰撞策略一致。
  emit('update:layout', resizeLayoutFloor(props.layout, nextSize, { blockTableConflicts: true }))
}

// revertInvalidDrag() 处理拖拽交互过程中的状态。
function revertInvalidDrag(state) {
  const candidateLayout = state.latestLayout || props.layout
  const current = findItem(candidateLayout, state.kind, state.id)
  if (!current) return false
  if (!itemOverlapsLayout(candidateLayout, state.kind, state.id, current.x, current.y, current)) return false
  // 只有落点仍发生碰撞时才回滚到 pointerdown 记录的原始位置。
  emit('update:layout', replaceLayoutItem(candidateLayout, state.kind, state.originalItem), {
    source: 'item',
    kind: state.kind,
    transient: false,
    forceSeatLimit: state.kind !== 'table'
  })
  return true
}

// 将某个布局图元替换回指定版本，用于非法拖拽回滚。
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
