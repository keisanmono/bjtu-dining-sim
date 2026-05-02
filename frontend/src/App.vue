<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">20 组</p>
        <h1>北京交通大学就餐仿真系统</h1>
      </div>
      <div class="topbar-actions">
        <el-tag :type="healthOk ? 'success' : 'warning'" effect="light">{{ healthText }}</el-tag>
        <el-button :icon="Refresh" circle @click="checkHealth" />
      </div>
    </header>

    <el-tabs v-model="activeView" class="stage-tabs" @tab-change="renderCharts">
      <el-tab-pane label="参数配置" name="config" />
      <el-tab-pane label="实时运行" name="run" />
      <el-tab-pane label="结果分析" name="analysis" />
    </el-tabs>

    <main>
      <section v-show="activeView === 'config'" class="config-grid">
        <el-card class="panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Setting /></el-icon>
              <span>基础参数</span>
            </div>
          </template>
          <el-form label-position="top" :model="config" class="config-form">
            <div class="form-pair">
              <el-form-item label="开放窗口数">
                <el-input-number v-model="config.num_windows" :min="1" :max="30" controls-position="right" />
              </el-form-item>
              <el-form-item label="座位数">
                <el-input-number v-model="config.num_seats" :min="1" :max="2000" controls-position="right" />
              </el-form-item>
            </div>
            <div class="form-pair">
              <el-form-item label="平均每分钟到达人数">
                <el-input-number v-model="config.arrival_rate" :min="0.1" :step="0.5" controls-position="right" />
              </el-form-item>
              <el-form-item label="到达时段">
                <el-input-number v-model="config.duration_min" :min="5" :max="360" controls-position="right" />
              </el-form-item>
            </div>
            <div class="form-pair">
              <el-form-item label="平均打饭时长">
                <el-input-number v-model="config.service_time_mean" :min="0.5" :step="0.5" controls-position="right" />
              </el-form-item>
              <el-form-item label="平均就餐时长">
                <el-input-number v-model="config.dining_time_mean" :min="1" :step="1" controls-position="right" />
              </el-form-item>
            </div>
            <div class="form-pair">
              <el-form-item label="随机种子">
                <el-input-number v-model="config.seed" :min="1" controls-position="right" />
              </el-form-item>
              <el-form-item label="错峰分钟">
                <el-input-number v-model="config.stagger_minutes" :min="0" :max="120" controls-position="right" />
              </el-form-item>
            </div>
            <div class="form-pair">
              <el-form-item label="高峰开始">
                <el-input-number v-model="config.peak_start_min" :min="0" controls-position="right" />
              </el-form-item>
              <el-form-item label="高峰结束">
                <el-input-number v-model="config.peak_end_min" :min="0" controls-position="right" />
              </el-form-item>
            </div>
          </el-form>

          <div class="button-row">
            <el-button :icon="CircleCheck" @click="validateConfig">参数校验</el-button>
            <el-button :icon="Refresh" @click="loadDefault">加载默认场景</el-button>
            <el-button type="primary" :icon="VideoPlay" @click="startLiveRun">开始仿真</el-button>
          </div>

          <el-alert
            v-if="validationMessage"
            class="validation-alert"
            :type="validationType"
            :title="validationMessage"
            show-icon
            :closable="false"
          />
        </el-card>

        <el-card class="panel recommendation-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><MagicStick /></el-icon>
              <span>优化推荐</span>
            </div>
          </template>
          <div class="candidate-block">
            <div class="candidate-editor">
              <div class="candidate-editor-row">
                <span>窗口</span>
                <el-input-number v-model="candidateSettings.windowMin" :min="1" :max="30" size="small" controls-position="right" />
                <span class="range-separator">至</span>
                <el-input-number v-model="candidateSettings.windowMax" :min="1" :max="30" size="small" controls-position="right" />
              </div>
              <div class="candidate-editor-row">
                <span>座位</span>
                <el-input-number v-model="candidateSettings.seatMin" :min="1" :max="2000" :step="10" size="small" controls-position="right" />
                <span class="range-separator">至</span>
                <el-input-number v-model="candidateSettings.seatMax" :min="1" :max="2000" :step="10" size="small" controls-position="right" />
              </div>
              <div class="candidate-editor-row">
                <span>步长</span>
                <el-input-number v-model="candidateSettings.seatStep" :min="1" :max="200" :step="5" size="small" controls-position="right" />
                <span class="range-hint">座位候选间隔</span>
              </div>
              <div class="candidate-editor-row">
                <span>错峰</span>
                <el-input-number v-model="candidateSettings.staggerMin" :min="0" :max="120" :step="5" size="small" controls-position="right" />
                <span class="range-separator">至</span>
                <el-input-number v-model="candidateSettings.staggerMax" :min="0" :max="120" :step="5" size="small" controls-position="right" />
              </div>
              <div class="candidate-editor-row">
                <span>步长</span>
                <el-input-number v-model="candidateSettings.staggerStep" :min="1" :max="60" :step="5" size="small" controls-position="right" />
                <span class="range-hint">错峰候选间隔</span>
              </div>
              <div class="candidate-actions">
                <el-button size="small" :icon="Refresh" @click="resetCandidateSettings">按当前参数重置范围</el-button>
                <el-button type="primary" size="small" :icon="MagicStick" :loading="isRecommending" @click="generateRecommendation">生成推荐</el-button>
              </div>
            </div>

            <el-divider />
            <el-empty v-if="!recommendation" description="暂无推荐结果" />
            <template v-else>
              <div class="config-recommend-summary">
                <div class="recommend-result-item wide">
                  <div class="recommend-result-heading">
                    <div>
                      <p>推荐配置</p>
                      <strong>{{ formatConfigSummary(recommendation.best.config) }}</strong>
                    </div>
                    <el-button type="success" size="small" :icon="CircleCheck" @click="applyRecommendationConfig(recommendation.best.config)">
                      应用推荐方案
                    </el-button>
                  </div>
                </div>
                <div class="recommend-result-item">
                  <p>平均等待</p>
                  <strong>{{ formatMinutes(recommendation.best.metrics.avg_wait) }}</strong>
                </div>
                <div class="recommend-result-item">
                  <p>峰值排队</p>
                  <strong>{{ recommendation.best.metrics.peak_queue }}</strong>
                </div>
                <div class="recommend-result-item">
                  <p>完成就餐</p>
                  <strong>{{ recommendation.best.metrics.throughput }}</strong>
                </div>
                <div class="recommend-result-item">
                  <p>评分</p>
                  <strong>{{ formatNumber(recommendation.best.score) }}</strong>
                </div>
              </div>
              <p class="explain-text compact">{{ explanation?.text || recommendation.explanation_summary }}</p>
              <el-table :data="recommendation.ranking" class="config-effect-table" size="small" height="260">
                <el-table-column label="方案" min-width="130">
                  <template #default="{ row }">{{ row.strategy }}</template>
                </el-table-column>
                <el-table-column label="配置" min-width="130">
                  <template #default="{ row }">{{ formatConfigSummary(row.config) }}</template>
                </el-table-column>
                <el-table-column label="平均等待" width="92">
                  <template #default="{ row }">{{ formatMinutes(row.metrics.avg_wait) }}</template>
                </el-table-column>
                <el-table-column label="峰值排队" width="86">
                  <template #default="{ row }">{{ row.metrics.peak_queue }}</template>
                </el-table-column>
                <el-table-column label="完成就餐" width="90">
                  <template #default="{ row }">{{ row.metrics.throughput }}</template>
                </el-table-column>
                <el-table-column label="评分" width="74">
                  <template #default="{ row }">{{ formatNumber(row.score) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="92" fixed="right">
                  <template #default="{ row }">
                    <el-button type="primary" size="small" plain @click="applyRecommendationConfig(row.config)">应用方案</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </template>
          </div>
        </el-card>

        <el-card class="panel preview-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Grid /></el-icon>
              <span>仿真场景预览</span>
            </div>
          </template>
          <svg class="dining-floor-plan" viewBox="0 0 360 640" role="img" aria-label="食堂俯视平面图">
            <rect class="floor-fill" x="10" y="10" width="340" height="620" rx="10" />
            <path class="wall-line" d="M72 24 H336 V616 H24 V226 M24 104 V24 H54" />

            <text class="svg-label" x="35" y="92">入口</text>
            <rect class="svg-entrance-door" x="18" y="112" width="58" height="94" rx="14" />
            <text class="svg-door-text" x="47" y="164" text-anchor="middle">门</text>
            <path class="entry-arrow" d="M78 160 H112" />
            <text class="svg-note" x="32" y="226">入场</text>

            <text class="svg-label" x="132" y="52">取餐窗口</text>
            <text class="svg-note" x="310" y="52" text-anchor="end">{{ layoutPreview.windows.length }} 个开放</text>
            <rect class="counter-belt" x="118" y="64" width="218" height="12" rx="6" />
            <g
              v-for="counter in svgWindowCounters"
              :key="counter.id"
              class="svg-counter-window"
              :transform="`translate(${counter.x} ${counter.y})`"
            >
              <rect width="48" height="34" rx="8" />
              <text x="24" y="21" text-anchor="middle">窗口 {{ counter.label }}</text>
            </g>
            <text v-if="hiddenWindowCount" class="svg-note" x="124" y="194">
              另有 {{ hiddenWindowCount }} 个窗口未展开
            </text>

            <path class="queue-lane" d="M76 170 C106 170 100 132 132 132 H314" />
            <circle class="queue-dot" cx="102" cy="154" r="4" />
            <circle class="queue-dot" cx="144" cy="132" r="4" />
            <circle class="queue-dot" cx="186" cy="132" r="4" />
            <text class="svg-note" x="88" y="214">排队动线：入口 -> 窗口 -> 就餐区</text>

            <text class="svg-label" x="126" y="190">就餐区桌椅</text>
            <text class="svg-note" x="324" y="190" text-anchor="end">{{ tableTypeSummary }}</text>
            <g
              v-for="table in svgTableGroups"
              :key="table.id"
              class="dining-table-group"
              :transform="`translate(${table.x} ${table.y})`"
            >
              <rect
                v-for="chair in table.chairs"
                :key="chair.key"
                class="dining-chair"
                :x="chair.x"
                :y="chair.y"
                :width="chair.width"
                :height="chair.height"
                rx="4"
              />
              <rect class="table-top" :x="-table.width / 2" y="-14" :width="table.width" height="28" rx="8" />
              <text class="table-number" x="0" y="5" text-anchor="middle">{{ table.label }}</text>
            </g>
            <text v-if="hiddenTableCount" class="svg-note" x="180" y="612" text-anchor="middle">
              共 {{ totalTableCount }} 组桌椅，预览前 {{ svgTableGroups.length }} 组
            </text>
          </svg>
        </el-card>
      </section>

      <section v-show="activeView === 'run'" class="run-layout">
        <el-card class="panel run-controls">
          <div class="control-row">
            <el-button type="success" :icon="VideoPlay" :disabled="isRunning" @click="startLiveRun">开始</el-button>
            <el-button type="warning" :icon="VideoPause" :disabled="!isRunning" @click="pauseRun">暂停</el-button>
            <el-button :icon="Right" :disabled="isRunning || isDone" @click="singleStep(false)">单步</el-button>
            <el-button type="danger" :icon="Refresh" @click="resetRun">重置</el-button>
            <el-button :icon="Finished" @click="runFullSimulation">快速完成</el-button>
            <el-button :icon="Download" :disabled="!runId || !metrics" @click="exportRecords">导出记录</el-button>
            <div class="time-chip">当前时刻：t = {{ currentMinute }} min</div>
          </div>
        </el-card>

        <div class="metric-grid">
          <el-card v-for="card in runCards" :key="card.label" class="metric-card">
            <p>{{ card.label }}</p>
            <strong>{{ card.value }}</strong>
            <span>{{ card.hint }}</span>
          </el-card>
        </div>

        <div class="run-grid">
          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><Histogram /></el-icon>
                <span>窗口排队情况</span>
              </div>
            </template>
            <div ref="queueChartEl" class="chart-box" />
          </el-card>

          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><Grid /></el-icon>
                <span>座位占用矩阵</span>
              </div>
            </template>
            <div class="seat-grid" :style="seatGridStyle">
              <span
                v-for="(occupied, index) in visibleSeatMatrix"
                :key="index"
                class="seat-cell"
                :class="occupied ? 'is-occupied' : 'is-empty'"
              />
            </div>
            <div class="legend-row">
              <span><i class="legend occupied" />已占用</span>
              <span><i class="legend empty" />空座位</span>
            </div>
          </el-card>

          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><TrendCharts /></el-icon>
                <span>关键指标趋势</span>
              </div>
            </template>
            <div ref="trendChartEl" class="chart-box" />
          </el-card>
        </div>
      </section>

      <section v-show="activeView === 'analysis'" class="analysis-layout">
        <div class="metric-grid">
          <el-card v-for="card in analysisCards" :key="card.label" class="metric-card">
            <p>{{ card.label }}</p>
            <strong>{{ card.value }}</strong>
            <span>{{ card.hint }}</span>
          </el-card>
        </div>

        <div class="analysis-grid">
          <el-card class="panel wide-panel">
            <template #header>
              <div class="panel-title">
                <el-icon><TrendCharts /></el-icon>
                <span>运行趋势</span>
              </div>
            </template>
            <div ref="analysisChartEl" class="chart-box large" />
          </el-card>

          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><Tickets /></el-icon>
                <span>过程记录</span>
              </div>
            </template>
            <el-table :data="recentRecords" height="330" size="small">
              <el-table-column prop="t" label="t" width="58" />
              <el-table-column prop="arrived_count" label="到达" width="70" />
              <el-table-column prop="served_count" label="取餐" width="70" />
              <el-table-column prop="empty_seats" label="空座" width="70" />
              <el-table-column prop="waiting_for_seat_count" label="等座" width="70" />
              <el-table-column label="排队">
                <template #default="{ row }">{{ totalQueue(row) }}</template>
              </el-table-column>
            </el-table>
            <div class="button-row compact">
              <el-button type="primary" :icon="MagicStick" :disabled="!metrics" @click="generateRecommendation">生成推荐</el-button>
              <el-button :icon="Refresh" @click="activeView = 'config'">重新实验</el-button>
            </div>
          </el-card>
        </div>
      </section>

    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  Download,
  Finished,
  Grid,
  Histogram,
  MagicStick,
  Refresh,
  Right,
  Setting,
  Tickets,
  TrendCharts,
  VideoPause,
  VideoPlay
} from '@element-plus/icons-vue'
import { api } from './api'
import { buildCandidatesFromSettings, createDefaultCandidateSettings } from './candidates'
import { canRenderChartElement } from './chartUtils'
import { buildLayoutFromConfig, buildSimulationConfigPayload } from './layout'
import { applyRecommendedConfig, nextViewAfterRecommendation } from './recommendationFlow'
import { shouldResetStepRun } from './runControl'

const defaultConfig = {
  num_windows: 4,
  num_seats: 120,
  arrival_rate: 8,
  service_time_mean: 3,
  dining_time_mean: 20,
  duration_min: 60,
  seed: 20,
  peak_start_min: 15,
  peak_end_min: 40,
  peak_multiplier: 1.4,
  stagger_minutes: 0,
  seat_columns: 12
}

const activeView = ref('config')
const config = reactive({ ...defaultConfig })
const candidateSettings = reactive(createDefaultCandidateSettings(defaultConfig))
const healthOk = ref(false)
const healthText = ref('后端未连接')
const validationMessage = ref('')
const validationType = ref('success')
const runId = ref('')
const records = ref([])
const metrics = ref(null)
const currentState = ref(null)
const isRunning = ref(false)
const isDone = ref(false)
const timer = ref(null)
const isRecommending = ref(false)
const recommendation = ref(null)
const explanation = ref(null)

const queueChartEl = ref(null)
const trendChartEl = ref(null)
const analysisChartEl = ref(null)
let queueChart
let trendChart
let analysisChart
let chartRenderFrame = 0

const previewSeatLimit = 240
const previewWindowLimit = 12
const previewTableLimit = 24
const currentMinute = computed(() => currentRecord.value?.t ?? 0)
const currentRecord = computed(() => records.value.at(-1) || null)
const seatGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${Math.min(config.seat_columns, 20)}, minmax(10px, 1fr))`
}))
const layoutPreview = computed(() => buildLayoutFromConfig(config))
const previewWindowItems = computed(() => {
  return layoutPreview.value.windows.slice(0, previewWindowLimit)
})
const svgWindowCounters = computed(() => previewWindowItems.value.map((id, index) => ({
  ...id,
  label: index + 1
})))
const hiddenWindowCount = computed(() => Math.max(0, layoutPreview.value.windows.length - previewWindowItems.value.length))
const totalTableCount = computed(() => layoutPreview.value.tables.length)
const svgTableGroups = computed(() => {
  const count = Math.min(totalTableCount.value, previewTableLimit)
  return layoutPreview.value.tables.slice(0, count).map((table, index) => {
    return {
      ...table,
      label: index + 1,
      width: tableWidthForCapacity(table.capacity),
      chairs: buildChairSlots(table.capacity)
    }
  })
})
const hiddenTableCount = computed(() => Math.max(0, totalTableCount.value - svgTableGroups.value.length))
const tableTypeSummary = computed(() => {
  const capacities = [...new Set(layoutPreview.value.tables.map((table) => table.capacity))].sort((a, b) => a - b)
  return `${capacities.join('/')} 座桌混排`
})
const visibleSeatMatrix = computed(() => {
  const matrix = currentState.value?.seat_matrix || []
  if (!matrix.length) {
    return Array.from({ length: Math.min(config.num_seats, previewSeatLimit) }, () => false)
  }
  return matrix.slice(0, previewSeatLimit)
})
const recommendationCandidates = computed(() => buildCandidatesFromSettings(candidateSettings))
const windowCandidates = computed(() => recommendationCandidates.value.windows)
const seatCandidates = computed(() => recommendationCandidates.value.seats)
const staggerCandidates = computed(() => recommendationCandidates.value.staggers.length ? recommendationCandidates.value.staggers : [0])
const runCards = computed(() => {
  const record = currentRecord.value
  const queue = record ? totalQueue(record) : 0
  const peakQueue = metrics.value?.peak_queue ?? Math.max(queue, ...records.value.map((item) => totalQueue(item)))
  return [
    { label: '平均等待时间', value: metrics.value ? formatMinutes(metrics.value.avg_wait) : formatMinutes(record?.avg_wait_so_far || 0), hint: metrics.value?.bottleneck_type || '运行中' },
    { label: '当前排队人数', value: queue, hint: `峰值排队 ${peakQueue} 人` },
    { label: '空座位数', value: record?.empty_seats ?? config.num_seats, hint: `当前等座 ${record?.waiting_for_seat_count || 0} 人` },
    { label: '累计接待人数', value: record?.total_seated ?? metrics.value?.throughput ?? 0, hint: `到达 ${record?.total_arrived || 0} 人` }
  ]
})
const analysisCards = computed(() => {
  const m = metrics.value
  return [
    { label: '平均等待', value: formatMinutes(m?.avg_wait || 0), hint: `取餐排队等待 ${formatMinutes(m?.avg_queue_wait || 0)}` },
    { label: '峰值排队', value: m?.peak_queue ?? 0, hint: `高峰最多等座 ${m?.peak_waiting_for_seat || 0} 人` },
    { label: '窗口利用率', value: formatPercent(m?.window_utilization || 0), hint: `瓶颈判断：${m?.bottleneck_type || '待分析'}` },
    { label: '平均座位利用率', value: formatPercent(m?.seat_utilization || 0), hint: `完成就餐 ${m?.throughput || 0} 人` }
  ]
})
const recentRecords = computed(() => records.value.slice(-80).reverse())

onMounted(() => {
  checkHealth()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  pauseRun()
  window.removeEventListener('resize', resizeCharts)
  if (chartRenderFrame) {
    window.cancelAnimationFrame(chartRenderFrame)
  }
  queueChart?.dispose()
  trendChart?.dispose()
  analysisChart?.dispose()
})

watch(records, renderCharts, { deep: true })
watch(metrics, renderCharts)
watch(activeView, renderCharts)

async function checkHealth() {
  try {
    const res = await api.health()
    healthOk.value = true
    healthText.value = res.message || 'backend ready'
  } catch {
    healthOk.value = false
    healthText.value = '后端未连接'
  }
}

function loadDefault() {
  Object.assign(config, defaultConfig)
  resetCandidateSettings()
  validationMessage.value = ''
}

function resetCandidateSettings() {
  Object.assign(candidateSettings, createDefaultCandidateSettings(config))
}

async function validateConfig() {
  const result = await api.validateConfig(buildSimulationConfigPayload(config))
  validationType.value = result.valid ? (result.warnings.length ? 'warning' : 'success') : 'error'
  validationMessage.value = result.valid
    ? result.warnings[0] || '参数校验通过。'
    : result.errors.join(' ')
  return result.valid
}

async function startLiveRun() {
  if (isRunning.value) return
  if (!runId.value || isDone.value) {
    resetRun(false)
    await singleStep(true)
  }
  if (isDone.value) return
  isRunning.value = true
  activeView.value = 'run'
  timer.value = window.setInterval(async () => {
    if (isRunning.value) {
      await singleStep(false)
    }
  }, 360)
}

function pauseRun() {
  isRunning.value = false
  if (timer.value) {
    window.clearInterval(timer.value)
    timer.value = null
  }
}

function resetRun(clearMessage = true) {
  pauseRun()
  runId.value = ''
  records.value = []
  metrics.value = null
  currentState.value = null
  isDone.value = false
  recommendation.value = null
  explanation.value = null
  if (clearMessage) ElMessage.info('仿真已重置')
  renderCharts()
}

async function singleStep(reset = false) {
  try {
    const payload = shouldResetStepRun(reset, runId.value)
      ? { config: buildSimulationConfigPayload(config), reset: true }
      : { run_id: runId.value }
    const response = await api.stepSimulation(payload)
    runId.value = response.run_id
    records.value = [...records.value, response.record]
    currentState.value = response.state
    isDone.value = response.done
    if (response.metrics) {
      metrics.value = response.metrics
      pauseRun()
      activeView.value = 'analysis'
    }
  } catch (error) {
    pauseRun()
    ElMessage.error(error?.response?.data?.detail || '单步运行失败')
  }
}

async function runFullSimulation() {
  try {
    pauseRun()
    const response = await api.runSimulation(buildSimulationConfigPayload(config))
    applyRunResponse(response)
    activeView.value = 'analysis'
    ElMessage.success('仿真运行完成')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '完整仿真失败')
  }
}

function applyRunResponse(response) {
  runId.value = response.run_id
  records.value = response.records
  metrics.value = response.metrics
  currentState.value = response.final_state
  isDone.value = true
}

async function generateRecommendation() {
  try {
    isRecommending.value = true
    const payload = {
      base_config: buildSimulationConfigPayload(config),
      window_options: windowCandidates.value,
      seat_options: seatCandidates.value,
      stagger_options: staggerCandidates.value,
      top_k: 4
    }
    recommendation.value = await api.recommend(payload)
    explanation.value = await api.explain({
      run_id: runId.value || null,
      baseline_config: buildSimulationConfigPayload(config),
      best_config: recommendation.value.best.config,
      baseline_metrics: recommendation.value.baseline_metrics,
      best_metrics: recommendation.value.best.metrics,
      root_cause_summary: metrics.value?.bottleneck_type || recommendation.value.baseline_metrics.bottleneck_type,
      recommended_strategy: recommendation.value.best.strategy
    })
    activeView.value = nextViewAfterRecommendation(activeView.value)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '生成推荐失败')
  } finally {
    isRecommending.value = false
  }
}

function applyRecommendationConfig(recommendedConfig) {
  applyRecommendedConfig(config, recommendedConfig)
  validationMessage.value = ''
  ElMessage.success('已应用方案到基础参数')
}

function exportRecords() {
  if (runId.value) {
    window.open(api.exportUrl(runId.value), '_blank')
  }
}

function renderCharts() {
  nextTick(() => {
    if (chartRenderFrame) {
      window.cancelAnimationFrame(chartRenderFrame)
    }
    chartRenderFrame = window.requestAnimationFrame(() => {
      chartRenderFrame = window.requestAnimationFrame(() => {
        chartRenderFrame = 0
        renderQueueChart()
        renderTrendChart()
        renderAnalysisChart()
      })
    })
  })
}

function renderQueueChart() {
  const element = queueChartEl.value
  if (!canRenderChartElement(element)) return
  queueChart ||= echarts.init(element)
  queueChart.resize()
  const lengths = currentRecord.value?.queue_lengths || Array.from({ length: config.num_windows }, () => 0)
  queueChart.setOption({
    color: ['#3f6fa9'],
    grid: { left: 34, right: 16, top: 24, bottom: 30 },
    xAxis: { type: 'category', data: lengths.map((_, index) => `W${index + 1}`) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: lengths, barMaxWidth: 44 }]
  })
}

function renderTrendChart() {
  const element = trendChartEl.value
  if (!canRenderChartElement(element)) return
  trendChart ||= echarts.init(element)
  trendChart.resize()
  trendChart.setOption(trendOption())
}

function renderAnalysisChart() {
  const element = analysisChartEl.value
  if (!canRenderChartElement(element)) return
  analysisChart ||= echarts.init(element)
  analysisChart.resize()
  analysisChart.setOption(trendOption(true))
}

function trendOption(large = false) {
  const chart = metrics.value?.chart_data || {
    times: records.value.map((item) => item.t),
    queue_totals: records.value.map((item) => totalQueue(item)),
    empty_seats: records.value.map((item) => item.empty_seats),
    throughput: records.value.map((item) => item.total_seated),
    avg_wait: records.value.map((item) => item.avg_wait_so_far),
    waiting_for_seat: records.value.map((item) => item.waiting_for_seat_count)
  }
  return {
    color: ['#2f65a3', '#d9912f', '#579a58', '#a94e4e'],
    tooltip: { trigger: 'axis' },
    legend: large ? { top: 0 } : { show: false },
    grid: { left: 42, right: 18, top: large ? 42 : 24, bottom: 30 },
    xAxis: { type: 'category', data: chart.times || [] },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '队列长度', type: 'line', smooth: true, data: chart.queue_totals || [] },
      { name: '空座位', type: 'line', smooth: true, data: chart.empty_seats || [] },
      { name: '累计接待', type: 'line', smooth: true, data: chart.throughput || [] },
      { name: '等座人数', type: 'line', smooth: true, data: chart.waiting_for_seat || [] }
    ]
  }
}

function resizeCharts() {
  queueChart?.resize()
  trendChart?.resize()
  analysisChart?.resize()
}

function buildChairSlots(capacity) {
  const slots = [
    { key: 1, x: -7, y: -29, width: 14, height: 14 },
    { key: 2, x: 24, y: -7, width: 14, height: 14 },
    { key: 3, x: -7, y: 15, width: 14, height: 14 },
    { key: 4, x: -38, y: -7, width: 14, height: 14 },
    { key: 5, x: 24, y: -29, width: 14, height: 14 },
    { key: 6, x: -38, y: 15, width: 14, height: 14 }
  ]
  return slots.slice(0, Math.max(1, Number(capacity) || 1))
}

function tableWidthForCapacity(capacity) {
  if (capacity <= 2) return 34
  if (capacity >= 6) return 48
  return 40
}

function totalQueue(record) {
  return (record?.queue_lengths || []).reduce((sum, value) => sum + value, 0)
}

function formatMinutes(value) {
  return `${formatNumber(value)} min`
}

function formatPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function formatNumber(value) {
  const number = Number(value) || 0
  return number.toFixed(number % 1 === 0 ? 0 : 1)
}

function formatConfigSummary(item) {
  return `${item.num_windows} 窗 / ${item.num_seats} 座 / ${formatStagger(item.stagger_minutes)}`
}

function formatStagger(value) {
  const minutes = Number(value) || 0
  return minutes === 0 ? '不启用错峰' : `错峰 ${minutes} 分钟`
}

function uniqueSorted(values) {
  return [...new Set(values.map((item) => Math.max(1, Math.round(item))))].sort((a, b) => a - b)
}
</script>
