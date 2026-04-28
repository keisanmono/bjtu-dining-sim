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
      <el-tab-pane label="优化推荐" name="recommend" />
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
              <el-form-item label="到达率">
                <el-input-number v-model="config.arrival_rate" :min="0.1" :step="0.5" controls-position="right" />
              </el-form-item>
              <el-form-item label="仿真时长">
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

        <el-card class="panel scenario-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Document /></el-icon>
              <span>场景说明</span>
            </div>
          </template>
          <div class="scenario-copy">
            <p>单食堂、单餐段、多窗口、多座位。</p>
            <p>学生按分钟到达，依次经历排队、取餐、入座、就餐和离场。</p>
            <p>当前候选推荐会比较窗口数、座位数和错峰分钟。</p>
          </div>
          <el-divider />
          <div class="candidate-block">
            <p class="block-label">推荐候选</p>
            <el-space wrap>
              <el-tag v-for="item in windowCandidates" :key="`w-${item}`">窗口 {{ item }}</el-tag>
              <el-tag v-for="item in seatCandidates" :key="`s-${item}`" type="success">座位 {{ item }}</el-tag>
              <el-tag v-for="item in staggerCandidates" :key="`g-${item}`" type="warning">错峰 {{ item }}</el-tag>
            </el-space>
          </div>
        </el-card>

        <el-card class="panel preview-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Grid /></el-icon>
              <span>仿真场景预览</span>
            </div>
          </template>
          <div class="window-preview">
            <div v-for="window in config.num_windows" :key="window" class="preview-window">
              <span>窗口 {{ window }}</span>
              <i />
              <i />
              <i />
              <i />
            </div>
          </div>
          <p class="block-label">座位网格预览</p>
          <div class="seat-grid preview-grid" :style="seatGridStyle">
            <span v-for="seat in previewSeats" :key="seat" class="seat-cell is-empty" />
          </div>
          <p v-if="config.num_seats > previewSeatLimit" class="muted">共 {{ config.num_seats }} 个座位，预览前 {{ previewSeatLimit }} 个。</p>
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

      <section v-show="activeView === 'recommend'" class="recommend-layout">
        <el-empty v-if="!recommendation" description="暂无推荐结果" />
        <template v-else>
          <div class="recommend-summary">
            <el-card class="metric-card highlight">
              <p>推荐窗口数</p>
              <strong>{{ recommendation.best.config.num_windows }} 个</strong>
              <span>{{ recommendation.best.strategy }}</span>
            </el-card>
            <el-card class="metric-card highlight">
              <p>推荐座位数</p>
              <strong>{{ recommendation.best.config.num_seats }} 个</strong>
              <span>错峰 {{ recommendation.best.config.stagger_minutes }} 分钟</span>
            </el-card>
            <el-card class="metric-card highlight">
              <p>综合评分</p>
              <strong>{{ formatNumber(recommendation.best.score) }}</strong>
              <span>越低越优</span>
            </el-card>
          </div>

          <div class="recommend-grid">
            <el-card class="panel">
              <template #header>
                <div class="panel-title">
                  <el-icon><DataAnalysis /></el-icon>
                  <span>多方案对比</span>
                </div>
              </template>
              <el-table :data="recommendation.ranking" size="small" height="360">
                <el-table-column label="方案" min-width="150">
                  <template #default="{ row }">{{ row.strategy }}</template>
                </el-table-column>
                <el-table-column label="窗口" width="70">
                  <template #default="{ row }">{{ row.config.num_windows }}</template>
                </el-table-column>
                <el-table-column label="座位" width="70">
                  <template #default="{ row }">{{ row.config.num_seats }}</template>
                </el-table-column>
                <el-table-column label="错峰" width="70">
                  <template #default="{ row }">{{ row.config.stagger_minutes }}</template>
                </el-table-column>
                <el-table-column label="平均等待" width="90">
                  <template #default="{ row }">{{ formatMinutes(row.metrics.avg_wait) }}</template>
                </el-table-column>
                <el-table-column label="峰值排队" width="90">
                  <template #default="{ row }">{{ row.metrics.peak_queue }}</template>
                </el-table-column>
              </el-table>
            </el-card>

            <el-card class="panel">
              <template #header>
                <div class="panel-title">
                  <el-icon><ChatLineRound /></el-icon>
                  <span>解释与策略建议</span>
                </div>
              </template>
              <p class="explain-text">{{ explanation?.text || recommendation.explanation_summary }}</p>
              <el-divider />
              <p class="block-label">备选策略</p>
              <el-timeline>
                <el-timeline-item v-for="item in alternativeStrategies" :key="item">
                  {{ item }}
                </el-timeline-item>
              </el-timeline>
              <p class="block-label">风险提示</p>
              <el-alert
                v-for="note in riskNotes"
                :key="note"
                class="risk-alert"
                type="warning"
                :title="note"
                :closable="false"
                show-icon
              />
            </el-card>
          </div>
        </template>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import {
  ChatLineRound,
  CircleCheck,
  DataAnalysis,
  Document,
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
import { canRenderChartElement } from './chartUtils'
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
const currentMinute = computed(() => currentRecord.value?.t ?? 0)
const currentRecord = computed(() => records.value.at(-1) || null)
const previewSeats = computed(() => Math.min(config.num_seats, previewSeatLimit))
const seatGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${Math.min(config.seat_columns, 20)}, minmax(10px, 1fr))`
}))
const visibleSeatMatrix = computed(() => {
  const matrix = currentState.value?.seat_matrix || []
  if (!matrix.length) {
    return Array.from({ length: Math.min(config.num_seats, previewSeatLimit) }, () => false)
  }
  return matrix.slice(0, previewSeatLimit)
})
const windowCandidates = computed(() => uniqueSorted([config.num_windows, config.num_windows + 1, config.num_windows + 2]))
const seatCandidates = computed(() => uniqueSorted([config.num_seats, config.num_seats + 20, config.num_seats + 40]))
const staggerCandidates = computed(() => [0, 5, 10])
const runCards = computed(() => {
  const record = currentRecord.value
  const queue = record ? totalQueue(record) : 0
  return [
    { label: '平均等待时间', value: metrics.value ? formatMinutes(metrics.value.avg_wait) : formatMinutes(record?.avg_wait_so_far || 0), hint: metrics.value?.bottleneck_type || '运行中' },
    { label: '峰值排队长度', value: metrics.value?.peak_queue ?? queue, hint: `当前 ${queue} 人` },
    { label: '空座位数', value: record?.empty_seats ?? config.num_seats, hint: `等座 ${record?.waiting_for_seat_count || 0} 人` },
    { label: '累计接待人数', value: record?.total_seated ?? metrics.value?.throughput ?? 0, hint: `到达 ${record?.total_arrived || 0} 人` }
  ]
})
const analysisCards = computed(() => {
  const m = metrics.value
  return [
    { label: '平均等待', value: formatMinutes(m?.avg_wait || 0), hint: `队列 ${formatMinutes(m?.avg_queue_wait || 0)}` },
    { label: '峰值排队', value: m?.peak_queue ?? 0, hint: `等座峰值 ${m?.peak_waiting_for_seat || 0}` },
    { label: '窗口利用率', value: formatPercent(m?.window_utilization || 0), hint: m?.bottleneck_type || '待分析' },
    { label: '座位利用率', value: formatPercent(m?.seat_utilization || 0), hint: `吞吐 ${m?.throughput || 0} 人` }
  ]
})
const recentRecords = computed(() => records.value.slice(-80).reverse())
const alternativeStrategies = computed(() => recommendation.value?.alternatives?.length ? recommendation.value.alternatives : ['保持当前基准方案'])
const riskNotes = computed(() => explanation.value?.risk_notes || ['请先生成推荐解释。'])

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
  validationMessage.value = ''
}

async function validateConfig() {
  const result = await api.validateConfig({ ...config })
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
      ? { config: { ...config }, reset: true }
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
    const response = await api.runSimulation({ ...config })
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
    const payload = {
      base_config: { ...config },
      window_options: windowCandidates.value,
      seat_options: seatCandidates.value,
      stagger_options: staggerCandidates.value,
      top_k: 4
    }
    recommendation.value = await api.recommend(payload)
    explanation.value = await api.explain({
      run_id: runId.value || null,
      baseline_config: { ...config },
      best_config: recommendation.value.best.config,
      baseline_metrics: recommendation.value.baseline_metrics,
      best_metrics: recommendation.value.best.metrics,
      root_cause_summary: metrics.value?.bottleneck_type || recommendation.value.baseline_metrics.bottleneck_type,
      recommended_strategy: recommendation.value.best.strategy
    })
    activeView.value = 'recommend'
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '生成推荐失败')
  }
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

function uniqueSorted(values) {
  return [...new Set(values.map((item) => Math.max(1, Math.round(item))))].sort((a, b) => a - b)
}
</script>
