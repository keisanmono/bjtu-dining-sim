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
      <el-tab-pane label="场景预览" name="layout" />
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
            <div v-if="arrivalMode === 'manual'" class="config-section manual-arrival-section">
              <div class="config-section-title">手动到达</div>
              <div class="config-field-grid">
                <el-form-item label="平均每分钟到达人数">
                  <el-input-number v-model="config.arrival_rate" :min="0.1" :step="0.5" controls-position="right" />
                </el-form-item>
                <el-form-item label="到达持续时间">
                  <el-input-number v-model="config.duration_min" :min="5" :max="360" controls-position="right" />
                </el-form-item>
                <el-form-item label="错峰分钟">
                  <el-input-number v-model="config.stagger_minutes" :min="0" :max="120" controls-position="right" />
                </el-form-item>
                <el-form-item label="高峰开始">
                  <el-input-number v-model="config.peak_start_min" :min="0" controls-position="right" />
                </el-form-item>
                <el-form-item label="高峰结束">
                  <el-input-number v-model="config.peak_end_min" :min="0" controls-position="right" />
                </el-form-item>
              </div>
            </div>

            <div class="config-section service-random-section">
              <div class="config-section-title">服务与随机性</div>
              <div class="config-field-grid">
                <el-form-item label="平均打饭时长">
                  <el-input-number v-model="config.service_time_mean" :min="0.5" :step="0.5" controls-position="right" />
                </el-form-item>
                <el-form-item label="平均就餐时长">
                  <el-input-number v-model="config.dining_time_mean" :min="1" :step="1" controls-position="right" />
                </el-form-item>
                <el-form-item label="随机种子">
                  <el-input-number v-model="config.seed" :min="1" controls-position="right" />
                </el-form-item>
              </div>
            </div>
          </el-form>

          <div class="button-row config-action-bar">
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

        <el-card class="panel campus-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Grid /></el-icon>
              <span>校园到达</span>
            </div>
          </template>
          <el-form label-position="top" class="campus-form">
            <div class="campus-mode-strip">
              <el-form-item label="到达模式">
                <el-radio-group v-model="arrivalMode">
                  <el-radio-button label="manual">手动平均</el-radio-button>
                  <el-radio-button label="campus">校园人数</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </div>

            <template v-if="arrivalMode === 'campus'">
              <div class="campus-toolbar">
                <el-form-item label="目标食堂">
                  <el-select v-model="selectedCafeteriaId" placeholder="选择食堂">
                    <el-option
                      v-for="cafeteria in campusCafeterias"
                      :key="cafeteria.id"
                      :label="cafeteria.name"
                      :value="cafeteria.id"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="人数来源" class="campus-source-field">
                  <el-tag effect="light">{{ campusSourceLabel }}</el-tag>
                </el-form-item>
                <div class="campus-actions">
                  <el-button
                    :icon="Refresh"
                    :loading="campusLoadingSource === 'live'"
                    :disabled="campusLoadingSource !== '' && campusLoadingSource !== 'live'"
                    @click="loadCampusOccupancy('live')"
                  >
                    获取实时数据
                  </el-button>
                  <el-button
                    :icon="MagicStick"
                    :loading="campusLoadingSource === 'random'"
                    :disabled="campusLoadingSource !== '' && campusLoadingSource !== 'random'"
                    @click="loadCampusOccupancy('random')"
                  >
                    随机生成
                  </el-button>
                </div>
              </div>

              <el-alert
                v-if="campusWarning"
                class="validation-alert"
                type="warning"
                :title="campusWarning"
                show-icon
                :closable="false"
              />

              <el-table :data="campusRows" class="campus-table" size="small">
                <el-table-column prop="building_name" label="教学楼" width="112" />
                <el-table-column label="下课" width="104">
                  <template #default="{ row }">
                    <el-input-number v-model="row.dismissal_minute" :min="0" :max="240" size="small" controls-position="right" />
                  </template>
                </el-table-column>
                <el-table-column label="就餐比例" width="120">
                  <template #default="{ row }">
                    <div class="percent-input">
                      <el-input-number v-model="row.release_percent" :min="0" :max="100" :step="5" size="small" controls-position="right" />
                      <span class="percent-suffix">%</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="选择概率" width="92">
                  <template #default="{ row }">{{ formatPercent(campusChoiceProbability(row)) }}</template>
                </el-table-column>
                <el-table-column label="路程" width="78">
                  <template #default="{ row }">{{ campusWalkMinutes(row) }} min</template>
                </el-table-column>
                <el-table-column label="楼层人数（可手动填写）" min-width="280">
                  <template #default="{ row }">
                    <div class="floor-inputs">
                      <label v-for="floor in row.floors" :key="`${row.building_id}-${floor.floor}`" class="floor-input">
                        <span>{{ floor.floor }}F</span>
                        <el-input-number v-model="floor.count" :min="0" :max="999" size="small" controls-position="right" />
                      </label>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="合计" width="78">
                  <template #default="{ row }">{{ campusRowTotal(row) }}</template>
                </el-table-column>
              </el-table>
            </template>
          </el-form>
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
              <div class="candidate-range-grid">
                <div class="candidate-editor-row">
                  <span>窗口</span>
                  <el-input-number v-model="candidateSettings.windowMin" :min="1" :max="30" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.windowMax" :min="1" :max="30" size="small" controls-position="right" />
                </div>
                <div class="candidate-editor-row">
                  <span>座位</span>
                  <el-input-number v-model="candidateSettings.seatMin" :min="2" :max="layoutSeatLimit" :step="2" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.seatMax" :min="2" :max="layoutSeatLimit" :step="2" size="small" controls-position="right" />
                </div>
                <div class="candidate-editor-row candidate-editor-row-single">
                  <span>座位步长</span>
                  <el-input-number v-model="candidateSettings.seatStep" :min="2" :max="200" :step="2" size="small" controls-position="right" />
                  <span class="range-hint">候选间隔</span>
                </div>
                <div class="candidate-editor-row">
                  <span>错峰</span>
                  <el-input-number v-model="candidateSettings.staggerMin" :min="0" :max="120" :step="5" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.staggerMax" :min="0" :max="120" :step="5" size="small" controls-position="right" />
                </div>
                <div class="candidate-editor-row candidate-editor-row-single">
                  <span>错峰步长</span>
                  <el-input-number v-model="candidateSettings.staggerStep" :min="1" :max="60" :step="5" size="small" controls-position="right" />
                  <span class="range-hint">候选间隔</span>
                </div>
                <div class="candidate-editor-row">
                  <span>下课峰数</span>
                  <el-input-number v-model="candidateSettings.peakCountMin" :min="1" :max="6" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.peakCountMax" :min="1" :max="6" size="small" controls-position="right" />
                </div>
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

      </section>

      <section v-show="activeView === 'layout'" class="layout-page">
        <el-card class="panel layout-page-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Grid /></el-icon>
              <span>仿真场景预览</span>
            </div>
          </template>
          <LayoutEditor
            :layout="layout"
            :seat-limit="layoutSeatLimit"
            :window-count="config.num_windows"
            :seat-count="config.num_seats"
            @update:layout="onLayoutUpdate"
            @update:window-count="updateWindowCount"
            @update:seat-count="updateSeatCount"
            @reset="resetLayout"
          />
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
                <span>实时食堂地图</span>
              </div>
            </template>
            <LiveDiningMap
              :layout="layout"
              :state="currentState"
              @transition-settled="onLiveMapTransitionSettled"
            />
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
import { buildSimulationConfigPayload } from './layout'
import {
  adjustLayoutWindowCount,
  calculateLayoutSeatLimit,
  createDefaultLayout,
  LAYOUT_DEFAULT_FLOOR,
  normalizeSeatCount,
  rebuildLayoutTablesForSeats,
  totalLayoutSeats
} from './layoutEditor'
import LayoutEditor from './LayoutEditor.vue'
import LiveDiningMap from './LiveDiningMap.vue'
import { LIVE_TRANSITION_MS } from './liveMapModel'
import { applyRecommendedConfig, nextViewAfterRecommendation } from './recommendationFlow'
import { liveStepDelay, shouldRequestLiveStep, shouldResetStepRun } from './runControl'

// 默认仿真参数：检查时可从这里说明窗口数、座位数、到达率、服务时长、
// 就餐时长和随机种子如何组成后端 SimulationConfig。
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
  seat_columns: 12,
  campus_demand: null,
  floor_width: LAYOUT_DEFAULT_FLOOR.width,
  floor_height: LAYOUT_DEFAULT_FLOOR.height
}

const LIVE_RECORD_LIMIT = 600
const LIVE_CHART_RECORD_LIMIT = 240
const LIVE_CHART_RENDER_INTERVAL_MS = 900

// 页面级状态：activeView 控制四个页签，config/layout 保存用户配置，
// runId/records/metrics/currentState 分别对应一次运行的编号、分钟记录、
// 最终指标和地图实时状态，是检查时讲前后端数据流的主线。
const activeView = ref('config')
const config = reactive({ ...defaultConfig })
const layout = ref(createDefaultLayout(defaultConfig))
const isSyncingLayout = ref(false)
const candidateSettings = reactive(createDefaultCandidateSettings(defaultConfig))
const healthOk = ref(false)
const healthText = ref('后端未连接')
const validationMessage = ref('')
const validationType = ref('success')
const runId = ref('')
const records = ref([])
const livePeakQueue = ref(0)
const metrics = ref(null)
const currentState = ref(null)
const isRunning = ref(false)
const isDone = ref(false)
const timer = ref(null)
const isRecommending = ref(false)
const recommendation = ref(null)
const explanation = ref(null)
const arrivalMode = ref('manual')
const campusLocations = ref({ cafeterias: [], teaching_buildings: [], walk_times: {} })
const selectedCafeteriaId = ref('')
const campusRows = ref([])
const campusSourceMode = ref('manual')
const campusLoadingSource = ref('')
const campusWarning = ref('')

// ECharts 容器和实例：records 或 metrics 变化后会触发图表刷新。
const queueChartEl = ref(null)
const trendChartEl = ref(null)
const analysisChartEl = ref(null)
let queueChart
let trendChart
let analysisChart
let chartRenderFrame = 0
let chartRenderTimer = 0
let chartRenderScheduledAt = 0
let stepInFlight = false
let awaitingLiveMapTransition = false

const currentMinute = computed(() => currentRecord.value?.t ?? 0)
const currentRecord = computed(() => records.value.at(-1) || null)
const chartRecords = computed(() => records.value.slice(-LIVE_CHART_RECORD_LIMIT))
const recommendationCandidates = computed(() => buildCandidatesFromSettings(candidateSettings))
const windowCandidates = computed(() => recommendationCandidates.value.windows)
const seatCandidates = computed(() => {
  const seats = recommendationCandidates.value.seats.filter((value) => value <= layoutSeatLimit.value)
  return seats.length ? seats : [config.num_seats]
})
const staggerCandidates = computed(() => recommendationCandidates.value.staggers.length ? recommendationCandidates.value.staggers : [0])
const peakCountCandidates = computed(() => recommendationCandidates.value.peakCounts.length ? recommendationCandidates.value.peakCounts : [1])
const layoutSeatLimit = ref(calculateLayoutSeatLimit(layout.value))
const runCards = computed(() => {
  const record = currentRecord.value
  const queue = record ? totalQueue(record) : 0
  const peakQueue = metrics.value?.peak_queue ?? livePeakQueue.value
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
const campusCafeterias = computed(() => campusLocations.value.cafeterias || [])
const campusSourceLabel = computed(() => {
  if (campusSourceMode.value === 'live') return '实时数据'
  if (campusSourceMode.value === 'random') return '随机生成'
  return '手动填写'
})

onMounted(() => {
  checkHealth()
  loadCampusLocations()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  pauseRun()
  window.removeEventListener('resize', resizeCharts)
  if (chartRenderFrame) {
    window.cancelAnimationFrame(chartRenderFrame)
  }
  if (chartRenderTimer) {
    window.clearTimeout(chartRenderTimer)
  }
  queueChart?.dispose()
  trendChart?.dispose()
  analysisChart?.dispose()
})

watch(metrics, renderCharts)
watch(activeView, renderCharts)

// 布局编辑器和基础参数需要双向同步：检查时可说明窗口/餐桌拖拽后，
// 最终仍会转成同一份 layout payload 发送给后端。
watch(
  () => config.num_windows,
  (newCount) => {
    if (isSyncingLayout.value) return
    if (!Number.isFinite(newCount) || newCount < 1) return
    if (layout.value.windows.length === newCount) return
    onLayoutUpdate(adjustLayoutWindowCount(layout.value, newCount))
  }
)

watch(
  () => config.num_seats,
  (newCount) => {
    if (isSyncingLayout.value) return
    if (!Number.isFinite(newCount) || newCount < 2) return
    const safeCount = normalizeSeatCount(newCount, layoutSeatLimit.value)
    if (safeCount !== newCount) {
      isSyncingLayout.value = true
      config.num_seats = safeCount
      nextTick(() => { isSyncingLayout.value = false })
      return
    }
    if (totalLayoutSeats(layout.value) === safeCount) return
    onLayoutUpdate(rebuildLayoutTablesForSeats(layout.value, safeCount))
  }
)

// 健康检查只调用 /api/health，用于确认 Vite proxy 后面的 FastAPI 是否可达。
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

async function loadCampusLocations() {
  try {
    const payload = await api.campusLocations()
    campusLocations.value = payload
    if (!selectedCafeteriaId.value && payload.cafeterias?.length) {
      selectedCafeteriaId.value = payload.cafeterias[0].id
    }
    if (!campusRows.value.length) {
      campusRows.value = buildEmptyCampusRows(payload.teaching_buildings || [])
    }
  } catch {
    campusWarning.value = '校园位置数据加载失败。'
  }
}

function buildEmptyCampusRows(buildings) {
  return buildings.map((building) => ({
    building_id: building.id,
    building_name: building.name,
    dismissal_minute: config.peak_start_min,
    release_percent: 100,
    source: 'manual',
    floors: Array.from({ length: Math.max(1, Number(building.default_floor_count || 5)) }, (_, index) => ({
      floor: index + 1,
      count: 0,
      capacity: 0
    }))
  }))
}

async function loadCampusOccupancy(sourceMode) {
  if (campusLoadingSource.value) return
  try {
    campusLoadingSource.value = sourceMode
    campusWarning.value = ''
    const buildings = campusRows.value.length
      ? campusRows.value.map((row) => row.building_id)
      : (campusLocations.value.teaching_buildings || []).map((item) => item.id)
    const payload = await api.campusOccupancy({
      source_mode: sourceMode,
      buildings,
      seed: config.seed
    })
    applyCampusOccupancyItems(payload.items || [], sourceMode)
    campusSourceMode.value = sourceMode
    campusWarning.value = (payload.warnings || []).join(' ')
    arrivalMode.value = 'campus'
    ElMessage.success(sourceMode === 'live' ? '已获取校园实时人数' : '已随机生成校园人数')
  } catch (error) {
    campusWarning.value = error?.response?.data?.detail || '校园人数加载失败'
  } finally {
    if (campusLoadingSource.value === sourceMode) {
      campusLoadingSource.value = ''
    }
  }
}

function applyCampusOccupancyItems(items, sourceMode) {
  const byId = new Map(items.map((item) => [item.building_id, item]))
  const baseRows = campusRows.value.length
    ? campusRows.value
    : items.map((item) => ({
      building_id: item.building_id,
      building_name: item.building_name,
      dismissal_minute: config.peak_start_min,
      release_percent: 100,
      source: sourceMode,
      floors: []
    }))
  campusRows.value = baseRows.map((row) => {
    const item = byId.get(row.building_id)
    if (!item) return row
    const releasePercent = Number.isFinite(Number(row.release_percent))
      ? Number(row.release_percent)
      : releasePercentFromRatio(row.release_ratio ?? 1)
    return {
      ...row,
      release_percent: releasePercent,
      source: item.source || sourceMode,
      floors: (item.floors || []).map((floor) => ({
        floor: Number(floor.floor) || 1,
        count: Number(floor.count) || 0,
        capacity: Number(floor.capacity) || 0
      }))
    }
  })
}

function applyCampusDemandConfig(campusDemand) {
  if (!campusDemand?.enabled) return
  arrivalMode.value = 'campus'
  selectedCafeteriaId.value = campusDemand.cafeteria_id || selectedCafeteriaId.value
  campusSourceMode.value = campusDemand.source_mode || 'manual'
  const buildingNames = new Map(
    (campusLocations.value.teaching_buildings || []).map((building) => [building.id, building.name])
  )
  campusRows.value = (campusDemand.buildings || []).map((building) => ({
    building_id: building.building_id,
    building_name: buildingNames.get(building.building_id) || building.building_id,
    dismissal_minute: Math.max(0, Math.round(Number(building.dismissal_minute) || 0)),
    release_percent: releasePercentFromRatio(building.release_ratio ?? 1),
    source: campusSourceMode.value,
    floors: (building.floors || []).map((floor) => ({
      floor: Math.max(1, Math.round(Number(floor.floor) || 1)),
      count: Math.max(0, Math.round(Number(floor.count) || 0)),
      capacity: Number(floor.capacity) || 0
    }))
  }))
}

function loadDefault() {
  isSyncingLayout.value = true
  Object.assign(config, defaultConfig)
  arrivalMode.value = 'manual'
  campusSourceMode.value = 'manual'
  campusWarning.value = ''
  campusRows.value = buildEmptyCampusRows(campusLocations.value.teaching_buildings || [])
  layout.value = createDefaultLayout(defaultConfig)
  layoutSeatLimit.value = calculateLayoutSeatLimit(layout.value)
  resetCandidateSettings()
  validationMessage.value = ''
  nextTick(() => { isSyncingLayout.value = false })
}

function resetLayout() {
  isSyncingLayout.value = true
  layout.value = createDefaultLayout(config)
  layoutSeatLimit.value = calculateLayoutSeatLimit(layout.value)
  config.num_seats = totalLayoutSeats(layout.value)
  config.num_windows = layout.value.windows.length
  ElMessage.info('已根据当前参数重置布局')
  nextTick(() => { isSyncingLayout.value = false })
}

function updateWindowCount(value) {
  config.num_windows = Math.min(30, Math.max(1, Math.round(Number(value) || 1)))
}

function updateSeatCount(value) {
  config.num_seats = normalizeSeatCount(value, layoutSeatLimit.value)
}

function onLayoutUpdate(nextLayout, meta = {}) {
  const shouldRefreshSeatLimit = Boolean(meta?.forceSeatLimit) || (
    !meta?.transient && layoutCapacitySignature(layout.value) !== layoutCapacitySignature(nextLayout)
  )
  const limit = shouldRefreshSeatLimit ? calculateLayoutSeatLimit(nextLayout) : layoutSeatLimit.value
  if (shouldRefreshSeatLimit) {
    layoutSeatLimit.value = limit
  }
  const boundedLayout = totalLayoutSeats(nextLayout) > limit
    ? rebuildLayoutTablesForSeats(nextLayout, limit)
    : nextLayout
  layout.value = boundedLayout
  const total = totalLayoutSeats(boundedLayout)
  if (config.num_seats !== total) {
    isSyncingLayout.value = true
    config.num_seats = total
    nextTick(() => { isSyncingLayout.value = false })
  }
  if (config.num_windows !== boundedLayout.windows.length) {
    isSyncingLayout.value = true
    config.num_windows = boundedLayout.windows.length
    nextTick(() => { isSyncingLayout.value = false })
  }
  if (boundedLayout.floor) {
    config.floor_width = boundedLayout.floor.width
    config.floor_height = boundedLayout.floor.height
  }
}

function layoutCapacitySignature(targetLayout) {
  const floor = targetLayout?.floor || {}
  const doors = (targetLayout?.doors || []).map((item) => `${item.id}:${item.x}:${item.y}:${item.wall_side}`).join('|')
  const windows = (targetLayout?.windows || []).map((item) => `${item.id}:${item.x}:${item.y}:${item.wall_side}`).join('|')
  return `${floor.x}:${floor.y}:${floor.width}:${floor.height}::${doors}::${windows}`
}

function resetCandidateSettings() {
  Object.assign(candidateSettings, createDefaultCandidateSettings(config))
}

// 参数校验会把当前表单和布局整理成后端请求体，再交给 FastAPI/Pydantic 校验。
async function validateConfig() {
  refreshCampusDemandConfig()
  const result = await api.validateConfig(buildSimulationConfigPayload(config, layout.value))
  validationType.value = result.valid ? (result.warnings.length ? 'warning' : 'success') : 'error'
  validationMessage.value = result.valid
    ? result.warnings[0] || '参数校验通过。'
    : result.errors.join(' ')
  return result.valid
}

// 点击“开始仿真”的入口：第一次运行会 reset 并请求首个单步，
// 后续自动运行则由定时器持续调用 singleStep(false)。
async function startLiveRun() {
  if (isRunning.value) return
  isRunning.value = true
  activeView.value = 'run'
  if (!runId.value || isDone.value) {
    resetRun(false)
    isRunning.value = true
    activeView.value = 'run'
    const response = await singleStep(true, { waitForMapTransition: true })
    if (!response) {
      awaitingLiveMapTransition = false
      return
    }
    if (isDone.value) return
    return
  }
  if (isDone.value) return
  scheduleNextLiveStep()
}

function pauseRun() {
  isRunning.value = false
  if (timer.value) {
    window.clearTimeout(timer.value)
    timer.value = null
  }
}

function scheduleNextLiveStep(delayMs = liveStepDelay(LIVE_TRANSITION_MS)) {
  if (typeof window === 'undefined' || !isRunning.value || isDone.value) return
  if (timer.value) {
    window.clearTimeout(timer.value)
  }
  timer.value = window.setTimeout(runScheduledLiveStep, delayMs)
}

async function runScheduledLiveStep() {
  timer.value = null
  if (!shouldRequestLiveStep({ isRunning: isRunning.value, isDone: isDone.value, stepInFlight })) {
    return
  }
  const response = await singleStep(false, { waitForMapTransition: true })
  if (!response) {
    awaitingLiveMapTransition = false
  }
}

function onLiveMapTransitionSettled() {
  if (!awaitingLiveMapTransition) return
  awaitingLiveMapTransition = false
  if (isRunning.value && !isDone.value) {
    scheduleNextLiveStep(liveStepDelay(0))
  }
}

function resetRun(clearMessage = true) {
  pauseRun()
  awaitingLiveMapTransition = false
  runId.value = ''
  records.value = []
  livePeakQueue.value = 0
  metrics.value = null
  currentState.value = null
  isDone.value = false
  recommendation.value = null
  explanation.value = null
  if (clearMessage) ElMessage.info('仿真已重置')
  renderCharts()
}

// 后端每返回一条 StepRecord，就追加到 records；指标卡片和趋势图都从这里取数据。
function appendRunRecord(record) {
  if (!record) return
  records.value.push(record)
  const overflow = records.value.length - LIVE_RECORD_LIMIT
  if (overflow > 0) {
    records.value.splice(0, overflow)
  }
  livePeakQueue.value = Math.max(livePeakQueue.value, totalQueue(record))
  renderChartsThrottled()
}

// 实时仿真的核心前端请求：reset=true 时携带完整 config 新建 runner，
// reset=false 时只携带 run_id，让后端继续推进同一个 DiningSimulationRunner。
async function singleStep(reset = false, options = {}) {
  if (stepInFlight) return null
  stepInFlight = true
  try {
    refreshCampusDemandConfig()
    const payload = shouldResetStepRun(reset, runId.value)
      ? { config: buildSimulationConfigPayload(config, layout.value), reset: true }
      : { run_id: runId.value }
    const response = await api.stepSimulation(payload)
    runId.value = response.run_id
    appendRunRecord(response.record)
    if (options?.waitForMapTransition) {
      awaitingLiveMapTransition = true
    }
    currentState.value = response.state
    isDone.value = response.done
    if (response.metrics) {
      metrics.value = response.metrics
      pauseRun()
      activeView.value = 'analysis'
    }
    return response
  } catch (error) {
    pauseRun()
    ElMessage.error(error?.response?.data?.detail || '单步运行失败')
    return null
  } finally {
    stepInFlight = false
  }
}

async function runFullSimulation() {
  try {
    pauseRun()
    refreshCampusDemandConfig()
    const response = await api.runSimulation(buildSimulationConfigPayload(config, layout.value))
    applyRunResponse(response)
    activeView.value = 'analysis'
    ElMessage.success('仿真运行完成')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '完整仿真失败')
  }
}

function applyRunResponse(response) {
  runId.value = response.run_id
  records.value = (response.records || []).slice(-LIVE_RECORD_LIMIT)
  metrics.value = response.metrics
  livePeakQueue.value = response.metrics?.peak_queue ?? records.value.reduce((peak, record) => Math.max(peak, totalQueue(record)), 0)
  currentState.value = response.final_state
  isDone.value = true
  renderCharts()
}

// 优化推荐链路：前端只提交基准配置和候选范围，后端负责枚举、评分和规则化解释。
async function generateRecommendation() {
  try {
    isRecommending.value = true
    refreshCampusDemandConfig()
    const payload = {
      base_config: buildSimulationConfigPayload(config, layout.value),
      window_options: windowCandidates.value,
      seat_options: seatCandidates.value,
      stagger_options: staggerCandidates.value,
      peak_count_options: peakCountCandidates.value,
      top_k: 4
    }
    recommendation.value = await api.recommend(payload)
    explanation.value = await api.explain({
      run_id: runId.value || null,
      baseline_config: buildSimulationConfigPayload(config, layout.value),
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

function refreshCampusDemandConfig() {
  config.campus_demand = buildCampusDemandPayload()
}

function buildCampusDemandPayload() {
  if (arrivalMode.value !== 'campus') return null
  return {
    enabled: true,
    cafeteria_id: selectedCafeteriaId.value,
    source_mode: campusSourceMode.value,
    buildings: campusRows.value.map((row) => ({
      building_id: row.building_id,
      dismissal_minute: Math.max(0, Math.round(Number(row.dismissal_minute) || 0)),
      release_ratio: releasePercentToRatio(row.release_percent),
      floors: (row.floors || []).map((floor) => ({
        floor: Math.max(1, Math.round(Number(floor.floor) || 1)),
        count: Math.max(0, Math.round(Number(floor.count) || 0))
      }))
    }))
  }
}

function campusRowTotal(row) {
  return (row.floors || []).reduce((sum, floor) => sum + (Number(floor.count) || 0), 0)
}

function campusWalkMinutes(row) {
  const route = campusLocations.value.walk_times?.[row.building_id]?.[selectedCafeteriaId.value]
  return route?.duration_min ?? '-'
}

function releasePercentFromRatio(value) {
  const ratio = Math.min(1, Math.max(0, Number(value) || 0))
  return Math.round(ratio * 100)
}

function releasePercentToRatio(value) {
  const percent = Math.min(100, Math.max(0, Number(value) || 0))
  return percent / 100
}

function campusChoiceProbability(row) {
  const routes = campusLocations.value.walk_times?.[row.building_id]
  if (!routes || !selectedCafeteriaId.value || !routes[selectedCafeteriaId.value]) return 0
  const durations = Object.fromEntries(
    Object.entries(routes).map(([cafeteriaId, route]) => [cafeteriaId, Math.max(1, Number(route.duration_s) || 1)])
  )
  const nearest = Math.min(...Object.values(durations))
  const weights = Object.fromEntries(
    Object.entries(durations).map(([cafeteriaId, duration]) => [cafeteriaId, Math.pow(nearest / duration, 2.4)])
  )
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0)
  return total > 0 ? weights[selectedCafeteriaId.value] / total : 0
}

function applyRecommendationConfig(recommendedConfig) {
  applyRecommendedConfig(config, recommendedConfig)
  if (recommendedConfig.campus_demand) {
    applyCampusDemandConfig(recommendedConfig.campus_demand)
  }
  isSyncingLayout.value = true
  layout.value = createDefaultLayout(config)
  validationMessage.value = ''
  ElMessage.success('已应用方案到基础参数')
  nextTick(() => { isSyncingLayout.value = false })
}

function exportRecords() {
  if (runId.value) {
    window.open(api.exportUrl(runId.value), '_blank')
  }
}

function renderChartsThrottled() {
  const nowMs = Date.now()
  const elapsed = nowMs - chartRenderScheduledAt
  if (elapsed >= LIVE_CHART_RENDER_INTERVAL_MS) {
    chartRenderScheduledAt = nowMs
    renderCharts()
    return
  }
  if (chartRenderTimer) return
  chartRenderTimer = window.setTimeout(() => {
    chartRenderTimer = 0
    chartRenderScheduledAt = Date.now()
    renderCharts()
  }, LIVE_CHART_RENDER_INTERVAL_MS - elapsed)
}

// 图表刷新使用 requestAnimationFrame，避免实时单步返回太快时频繁重绘。
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
    animation: false,
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

// 趋势图数据优先使用后端最终 metrics.chart_data；实时运行未结束时，
// 则从最近的 StepRecord 临时拼出队列、空座、吞吐和等座曲线。
function trendOption(large = false) {
  const chart = metrics.value?.chart_data || {
    times: chartRecords.value.map((item) => item.t),
    queue_totals: chartRecords.value.map((item) => totalQueue(item)),
    empty_seats: chartRecords.value.map((item) => item.empty_seats),
    throughput: chartRecords.value.map((item) => item.total_seated),
    avg_wait: chartRecords.value.map((item) => item.avg_wait_so_far),
    waiting_for_seat: chartRecords.value.map((item) => item.waiting_for_seat_count)
  }
  return {
    animation: false,
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
</script>
