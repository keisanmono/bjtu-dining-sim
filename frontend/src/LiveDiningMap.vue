<!-- 文件说明：实时地图组件：把后端状态快照渲染成窗口、队列、餐桌和学生动画。 -->

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

      <g v-if="densityMarkers.length" class="density-heat-layer">
        <circle
          v-for="hotspot in densityMarkers"
          :key="hotspot.key"
          class="density-hotspot"
          :cx="hotspot.x"
          :cy="hotspot.y"
          :r="hotspot.radius"
          :style="{ opacity: hotspot.opacity }"
        />
      </g>

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

      <g v-if="queueRows.length" class="queue-group">
        <g
          v-for="row in queueRows"
          :key="`queue-row-${row.windowIndex}`"
          class="window-queue-row"
          :aria-label="queueRowAriaLabel(row)"
        >
          <rect
            v-for="capsule in row.capsules"
            :key="capsule.key"
            class="queue-capsule"
            :x="capsule.x"
            :y="capsule.y"
            :width="capsule.width"
            :height="capsule.height"
            :rx="capsule.rx"
            :ry="capsule.ry"
            :style="{ fill: capsule.color }"
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
        <g v-if="hasPedestrianAgents" class="party-group pedestrian-agent-group">
          <circle
            v-for="agent in pedestrianAgentMarkers"
            :key="agent.key"
            class="pedestrian-agent-dot"
            :class="`state-${String(agent.state).toLowerCase()}`"
            :cx="agent.x"
            :cy="agent.y"
            r="3"
            :style="{ fill: agent.color }"
          />
        </g>

        <g v-if="!hasPedestrianAgents" class="party-group service-group">
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

        <g v-if="!hasPedestrianAgents" class="party-group walking-group">
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

        <g v-if="!hasPedestrianAgents" class="party-group seated-group">
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
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
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
  buildDensityHotspotMarkers,
  buildLivePartyTargets,
  buildLivePartyTransitions,
  buildPedestrianAgentMarkers,
  buildQueueRows,
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

// 计算食堂地面边界，用于绘制地面和网格。
const floorBounds = computed(() => floorBoundsForLayout(props.layout))
// 将自动适配后的 viewBox 转成 SVG 属性字符串。
const viewBoxString = computed(() => {
  const viewBox = fitViewBoxForLayout(props.layout, 24)
  return `${viewBox.x} ${viewBox.y} ${viewBox.width} ${viewBox.height}`
})
// 读取后端实时状态快照，缺省时使用空对象避免模板报错。
const snapshot = computed(() => props.state || {})
// 读取布局中的餐桌列表。
const tables = computed(() => props.layout?.tables || [])
// 读取布局中的取餐窗口列表。
const windows = computed(() => props.layout?.windows || [])
// 读取布局中的入口列表。
const doors = computed(() => props.layout?.doors || [])
// 当前快照中的餐桌占用数组，动画落定后写入显示态。
const snapshotTableOccupancy = computed(() => snapshot.value.table_occupancy || [])
const backendPedestrianAgents = computed(() => snapshot.value.pedestrian_agents || [])
const backendDensityHotspots = computed(() => snapshot.value.density_hotspots || [])
const pedestrianAgentMarkers = computed(() => buildPedestrianAgentMarkers({
  snapshot: { pedestrian_agents: backendPedestrianAgents.value }
}))
const hasPedestrianAgents = computed(() => pedestrianAgentMarkers.value.length > 0)
const densityMarkers = computed(() => buildDensityHotspotMarkers({
  snapshot: { density_hotspots: backendDensityHotspots.value }
}))
const pedestrianSnapshotSignature = computed(() => {
  if (!hasPedestrianAgents.value) return ''
  const minute = Number.isFinite(Number(snapshot.value.minute)) ? Number(snapshot.value.minute) : ''
  const agents = backendPedestrianAgents.value || []
  const agentState = agents
    .map((agent) => [
      agent.agent_id ?? agent.student_id ?? '',
      agent.state ?? '',
      Number(agent.x ?? agent.cell?.[0] ?? 0).toFixed(1),
      Number(agent.y ?? agent.cell?.[1] ?? 0).toFixed(1)
    ].join(':'))
    .join('|')
  return `${minute}:${agents.length}:${agentState}`
})
const queueRows = computed(() => buildQueueRows({
  queueGroups: snapshot.value.queue_groups || [],
  queueLengths: snapshot.value.queue_lengths || [],
  windows: windows.value
}))

const selectedWindowIndex = ref(null)
const animatedPartyMarkers = ref([])
const walkingPartyMarkers = ref([])
const displayedTableOccupancy = ref([])
// 将后端 snapshot 转成实时地图中小组应处的位置。
const livePartyTargets = computed(() => buildLivePartyTargets({
  snapshot: hasPedestrianAgents.value ? {} : snapshot.value,
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

watch(
  pedestrianSnapshotSignature,
  (signature) => {
    settlePedestrianSnapshot(signature)
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  cancelPartyAnimation()
})

// 点击窗口时打开或关闭该窗口的排队详情。
function toggleWindowSelection(idx) {
  selectedWindowIndex.value = selectedWindowIndex.value === idx ? null : idx
}

// 点击空白区域时清除当前窗口详情选择。
function clearSelection() {
  if (selectedWindowIndex.value !== null) {
    selectedWindowIndex.value = null
  }
}

// 将后端 busy_windows 数组转换成忙碌窗口下标集合。
const busyWindowIndexes = computed(() => new Set(
  (snapshot.value.busy_windows || [])
    .map((busy, idx) => (busy ? idx : null))
    .filter((idx) => idx !== null)
))

// 按窗口聚合排队人数，优先使用 queue_lengths，缺失时从 queue_groups 回算。
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

// 按窗口聚合排队小组，并按队列位置排序。
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

// 将显示中的餐桌占用同时按 table.id 和数组下标建立索引。
const tableOccupancyById = computed(() => {
  const map = new Map()
  ;(displayedTableOccupancy.value || []).forEach((entry, idx) => {
    if (!entry) return
    if (entry.id) map.set(entry.id, entry)
    map.set(idx, entry)
  })
  return map
})

// 为选中窗口的详情面板准备可见小组、隐藏人数和服务状态。
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

// 当前正在窗口服务的小组标记。
const serviceMarkers = computed(() => (
  animatedPartyMarkers.value.filter((marker) => marker.role === 'service' && marker.opacity > 0)
))

// 已入座小组的圆点簇，按小组人数生成成员点和连接线。
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

// 正在从窗口走向餐桌的小组圆点簇。
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

// 根据新快照启动小组位置过渡；若后端提供 timeline 则优先播放后端帧。
function startPartyTransition(nextTargets, timeline = null) {
  cancelPartyAnimation()
  walkingPartyMarkers.value = []
  const backendPlaybackMs = backendTimelinePlaybackMs(timeline)
  if (backendPlaybackMs > 0) {
    // 后端 timeline 包含真实路径帧时，优先播放它而不是前端补间估算。
    startBackendTimelineTransition(nextTargets, timeline, backendPlaybackMs)
    return
  }
  const snapshotArrivedAt = now()
  const snapshotIntervalMs = lastSnapshotArrivedAt
    ? snapshotArrivedAt - lastSnapshotArrivedAt
    : LIVE_TRANSITION_MS
  lastSnapshotArrivedAt = snapshotArrivedAt
  // 根据快照实际到达间隔压缩动画时长，避免自动运行时越播越慢。
  const transitionDurationMs = transitionDurationForSnapshotGap(snapshotIntervalMs)
  const previousTargets = transitionStartTargets(lastSettledPartyTargets, animatedPartyMarkers.value)
  const transitions = buildLivePartyTransitions({
    previous: previousTargets,
    next: nextTargets,
    layout: props.layout
  })
  if (!transitions.length) {
    // 没有移动、出现或离开时直接固化快照，并通知父组件可以请求下一步。
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
  // 每帧按补间进度更新服务、等座和入座标记。
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

// 播放后端单步仿真返回的入座行走 timeline。
function startBackendTimelineTransition(nextTargets, timeline, playbackMs) {
  // 服务和已入座标记先按目标态展示，walkingPartyMarkers 单独负责播放行走学生。
  animatedPartyMarkers.value = settledMarkers(nextTargets)

  if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
    lastSettledPartyTargets = nextTargets
    walkingPartyMarkers.value = []
    settleTableOccupancy()
    emit('transition-settled')
    return
  }

  let timelinePlaybackStartedAt = null
  // 每帧按后端 timeline 的 elapsedMs 采样行走标记。
  const render = (timestamp) => {
    if (timelinePlaybackStartedAt === null) {
      timelinePlaybackStartedAt = timestamp
      // 第一帧固定 elapsed=0，保证学生从后端给出的起点开始。
      walkingPartyMarkers.value = buildBackendWalkingMarkers({ timeline, elapsedMs: 0 })
      partyAnimationFrame = window.requestAnimationFrame(render)
      return
    }
    const elapsedMs = clamp(timestamp - timelinePlaybackStartedAt, 0, playbackMs)
    // 每帧按 elapsedMs 在后端 frames/path 中采样，得到当前行走位置。
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

// advanced 行人模式直接渲染后端 agent 坐标，没有前端补间动画也必须通知父组件继续步进。
function settlePedestrianSnapshot(signature) {
  if (!signature || !hasPedestrianAgents.value) return
  cancelPartyAnimation()
  lastSettledPartyTargets = []
  animatedPartyMarkers.value = []
  walkingPartyMarkers.value = []
  settleTableOccupancy()
  nextTick(() => {
    if (hasPedestrianAgents.value && pedestrianSnapshotSignature.value === signature) {
      emit('transition-settled')
    }
  })
}

// 动画完成后将快照餐桌占用固化到显示态，避免行走中提前占座。
function settleTableOccupancy() {
  displayedTableOccupancy.value = snapshotTableOccupancy.value.map((entry) => ({ ...entry }))
}

// 过渡完成后只保留服务中的小组作为稳定标记。
function settledMarkers(targets) {
  // 过渡结束后隐藏等待和入座目标，只保留窗口服务中的点，座位占用由椅子颜色表达。
  return targets
    .filter((target) => target.role === 'service')
    .map((target) => ({ ...target, opacity: 1, progress: 1 }))
}

// 合并已稳定目标和当前可见标记，作为下一轮补间起点。
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

// 取消上一轮 requestAnimationFrame，避免新快照和旧动画叠加。
function cancelPartyAnimation() {
  if (partyAnimationFrame && typeof window !== 'undefined') {
    window.cancelAnimationFrame(partyAnimationFrame)
  }
  partyAnimationFrame = 0
}

// 优先使用 performance.now() 计算动画时间，测试环境下回退到 Date.now()。
function now() {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now()
}

// 按小组人数生成最多四个成员圆点的局部坐标。
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

// 用线段把同组成员点连接起来，突出结伴关系。
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

// 根据图元 footprint 返回可绘制的局部矩形。
function itemRectFor(kind, item) {
  const footprint = getItemFootprint(kind, item)
  return {
    x: -footprint.width / 2,
    y: -footprint.height / 2,
    width: footprint.width,
    height: footprint.height
  }
}

// 根据入口所在墙面生成门缝标记矩形。
function doorMarkerFor(door) {
  const footprint = getItemFootprint('door', door)
  if (door.wall_side === 'top' || door.wall_side === 'bottom') {
    return { x: -footprint.width / 2 + 8, y: -3, width: footprint.width - 16, height: 6 }
  }
  return { x: -3, y: -footprint.height / 2 + 8, width: 6, height: footprint.height - 16 }
}

// 根据窗口所在墙面生成窗口开口标记矩形。
function windowMarkerFor(window) {
  const footprint = getItemFootprint('window', window)
  if (window.wall_side === 'left' || window.wall_side === 'right') {
    return { x: -3, y: -footprint.height / 2 + 6, width: 6, height: footprint.height - 12 }
  }
  return { x: -footprint.width / 2 + 6, y: -3, width: footprint.width - 12, height: 6 }
}

// 根据餐桌容量返回桌面可视尺寸。
function tableTopFor(table) {
  return tableTopForCapacity(table.capacity)
}

// 根据餐桌容量返回椅子局部矩形。
function chairLayoutFor(table) {
  return tableChairRectsForCapacity(table.capacity)
}

// 将餐桌旋转角转换成 SVG transform。
function tableTransformFor(table) {
  return `rotate(${normalizeTableRotation(table.rotation)})`
}

// 按 table.id 或下标读取餐桌占用，缺失时回退为空桌。
function tableOccupancyFor(table, index = 0) {
  return tableOccupancyById.value.get(table.id)
    || tableOccupancyById.value.get(index)
    || { capacity: table.capacity, occupied: 0 }
}

// 根据 table_occupancy 判断指定椅子是否已被占用。
function isChairOccupied(table, chairIndex, tableIndex = 0) {
  const occupied = Number(tableOccupancyFor(table, tableIndex).occupied) || 0
  return chairIndex < occupied
}

// 根据忙碌、排队和选中状态生成窗口 CSS 类。
function windowStateClasses(idx) {
  return {
    'is-busy': busyWindowIndexes.value.has(idx),
    'has-queue': (queueLengthByWindow.value.get(idx) || 0) > 0,
    'is-selected': selectedWindowIndex.value === idx
  }
}

// 为窗口交互区域生成包含排队人数的可访问文本。
function windowAriaLabel(window, idx) {
  const total = queueLengthByWindow.value.get(idx) || 0
  return total > 0
    ? `窗口 ${window.id}，排队 ${total} 人，点击查看详情`
    : `窗口 ${window.id}，暂无排队，点击查看详情`
}

function queueRowAriaLabel(row) {
  const windowItem = windows.value[row.windowIndex]
  const total = queueLengthByWindow.value.get(row.windowIndex) || 0
  const hidden = row.overflow?.hiddenPeople || 0
  return hidden > 0
    ? `窗口 ${windowItem?.id || row.windowIndex + 1} 地图排队标记，排队 ${total} 人，另有 ${hidden} 人聚合显示`
    : `窗口 ${windowItem?.id || row.windowIndex + 1} 地图排队标记，排队 ${total} 人`
}
</script>
