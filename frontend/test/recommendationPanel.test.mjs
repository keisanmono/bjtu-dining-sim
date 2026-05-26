// 文件说明：推荐和配置页面结构测试，通过源码断言确认页面入口和旧 UI 移除。

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

// 验证配置页推荐面板不再渲染冗余候选预览列表。
test('config recommendation panel does not render redundant candidate preview list', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('class="candidate-groups"'), false)
  assert.equal(source.includes('configCandidateGroups'), false)
})

// 验证推荐结果留在配置页内展示，没有独立推荐 tab 或旧布局样式。
test('recommendations stay inside config page without a separate tab or page', () => {
  const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(appSource.includes('name="recommend"'), false)
  assert.equal(appSource.includes("activeView === 'recommend'"), false)
  assert.equal(appSource.includes('class="recommend-layout"'), false)
  assert.equal(appSource.includes('class="recommend-summary"'), false)
  assert.equal(appSource.includes('class="recommend-grid"'), false)
  assert.equal(appSource.includes('alternativeStrategies'), false)
  assert.equal(appSource.includes('riskNotes'), false)
  assert.equal(styleSource.includes('.recommend-layout'), false)
  assert.equal(styleSource.includes('.recommend-summary'), false)
  assert.equal(styleSource.includes('.recommend-grid'), false)
})

// 验证场景预览页通过 LayoutEditor 渲染真实可编辑食堂平面图。
test('simulation preview renders a realistic cafeteria floor plan via LayoutEditor', () => {
  const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const editorSource = readFileSync(new URL('../src/LayoutEditor.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  // App.vue delegates the floor plan to a LayoutEditor component.
  assert.equal(appSource.includes("import LayoutEditor from './LayoutEditor.vue'"), true)
  assert.equal(appSource.includes('<LayoutEditor'), true)
  assert.equal(appSource.includes('<el-tab-pane label="场景预览" name="layout"'), true)
  assert.equal(appSource.includes("activeView === 'layout'"), true)
  assert.equal(appSource.includes('class="layout-page"'), true)
  assert.equal(appSource.includes('class="panel layout-page-panel"'), true)
  assert.equal(appSource.includes('class="panel preview-panel"'), false)
  assert.equal(appSource.includes(':layout="layout"'), true)
  assert.equal(appSource.includes('@update:layout="onLayoutUpdate"'), true)
  assert.equal(appSource.includes('@reset="resetLayout"'), true)
  assert.equal(appSource.includes(':seat-limit="layoutSeatLimit"'), true)
  assert.equal(appSource.includes(':window-count="config.num_windows"'), true)
  assert.equal(appSource.includes(':seat-count="config.num_seats"'), true)
  assert.equal(appSource.includes('@update:window-count="updateWindowCount"'), true)
  assert.equal(appSource.includes('@update:seat-count="updateSeatCount"'), true)
  assert.equal(appSource.includes('layoutSeatLimit'), true)
  assert.equal(appSource.includes(':step="2"'), true)
  assert.equal(appSource.includes('<el-form-item label="开放窗口数">'), false)
  assert.equal(appSource.includes('<el-form-item label="座位数">'), false)
  assert.equal(appSource.includes('v-model="config.num_windows"'), false)
  assert.equal(appSource.includes('v-model="config.num_seats"'), false)

  // The LayoutEditor itself renders the SVG floor plan with a zoomable viewBox.
  assert.equal(editorSource.includes('class="dining-floor-plan"'), true)
  assert.equal(editorSource.includes(':viewBox="viewBoxString"'), true)
  assert.equal(editorSource.includes('layout-toolbar-header'), true)
  assert.equal(editorSource.includes('layout-toolbar-main'), true)
  assert.equal(editorSource.includes('layout-control-group'), true)
  assert.equal(editorSource.includes('layout-control-field'), true)
  assert.equal(editorSource.includes('layout-control-heading'), true)
  assert.equal(editorSource.includes('layout-window'), true)
  assert.equal(editorSource.includes('layout-table'), true)
  assert.equal(editorSource.includes('layout-door'), true)
  assert.equal(editorSource.includes('table-shape'), true)
  assert.equal(editorSource.includes('tableTransformFor'), true)
  assert.equal(editorSource.includes('setTableRotation'), true)
  assert.equal(editorSource.includes('rotateSelectedTable'), true)
  assert.equal(editorSource.includes('旋转餐桌'), true)
  assert.equal(editorSource.includes('table-top'), true)
  assert.equal(editorSource.includes('dining-chair'), true)
  assert.equal(editorSource.includes('queue-lane'), false)
  assert.equal(editorSource.includes('counter-belt'), false)
  assert.equal(editorSource.includes('<text'), false)
  assert.equal(editorSource.includes('wall-line"'), true)
  assert.equal(editorSource.includes('V204 M24 96'), false)
  assert.equal(editorSource.includes('allowOverlap: true'), true)
  assert.equal(editorSource.includes('revertInvalidDrag'), true)
  assert.equal(editorSource.includes('is-overlapping'), true)
  assert.equal(editorSource.includes('isCollisionHighlighted'), true)
  assert.equal(editorSource.includes('食堂宽度'), true)
  assert.equal(editorSource.includes('食堂深度'), true)
  assert.equal(editorSource.includes('aria-label="场景规模"'), true)
  assert.equal(editorSource.includes('开放窗口数'), true)
  assert.equal(editorSource.includes('座位数'), true)
  assert.equal(editorSource.includes(':model-value="windowCount"'), true)
  assert.equal(editorSource.includes(':model-value="seatCount"'), true)
  assert.equal(editorSource.includes('changeWindowCount'), true)
  assert.equal(editorSource.includes('changeSeatCount'), true)
  assert.equal(editorSource.includes('update:window-count'), true)
  assert.equal(editorSource.includes('update:seat-count'), true)
  assert.equal(editorSource.includes(':max="LAYOUT_SIZE_LIMITS.width.max"'), false)
  assert.equal(editorSource.includes(':max="LAYOUT_SIZE_LIMITS.height.max"'), false)
  assert.equal(editorSource.includes(':max="floorWidthMax"'), true)
  assert.equal(editorSource.includes(':max="floorHeightMax"'), true)
  assert.equal(editorSource.includes('floor width is capped by max area'), true)
  assert.equal(editorSource.includes('floor height is capped by max area'), true)
  assert.equal(editorSource.includes('resizeLayoutFloor'), true)
  assert.equal(editorSource.includes('resizeLayoutFloorFromHandle'), true)
  assert.equal(editorSource.includes('layout-resize-handle'), true)
  assert.equal(editorSource.includes('viewBoxString'), true)
  assert.equal(editorSource.includes('@wheel.prevent="onWheelZoom"'), true)
  assert.equal(editorSource.includes('fitViewportToLayout'), true)
  assert.equal(editorSource.includes('zoomViewBox'), true)
  assert.equal(editorSource.includes('arrangeLayoutTables'), true)
  assert.equal(editorSource.includes('autoArrangeTables'), true)
  assert.equal(editorSource.includes('均匀排布'), true)
  assert.equal(editorSource.includes('密排座位'), true)
  assert.equal(editorSource.includes('transient: true'), true)
  assert.equal(editorSource.includes('forceSeatLimit'), true)
  assert.equal(editorSource.includes('state.kind !== kind || state.id !== id'), true)
  assert.equal(editorSource.includes('layout-hit-area'), true)
  assert.equal(editorSource.includes('seatLimit'), true)
  assert.equal(editorSource.includes('adjustLayoutDoorCount'), true)
  assert.equal(editorSource.includes('入口 +'), true)
  assert.equal(appSource.includes('function onLayoutUpdate(nextLayout, meta = {})'), true)
  assert.equal(appSource.includes('meta?.transient'), true)
  assert.equal(appSource.includes('meta?.forceSeatLimit'), true)

  // The old card-style preview is gone.
  assert.equal(appSource.includes('<section class="entrance-zone"'), false)
  assert.equal(appSource.includes('service-counter-bank'), false)
  assert.equal(appSource.includes('entrance-zone'), false)
  assert.equal(appSource.includes('previewTableGroups'), false)
  assert.equal(appSource.includes('svgWindowCounters'), false)
  assert.equal(appSource.includes('svgTableGroups'), false)
  assert.equal(appSource.includes('座位网格预览'), false)

  // Stylesheet keeps the floor-plan look-and-feel and adds editor primitives.
  assert.equal(styleSource.includes('.dining-floor-plan'), true)
  assert.equal(styleSource.includes('height: min(72vh, 760px)'), true)
  assert.equal(styleSource.includes('.layout-page'), true)
  assert.equal(styleSource.includes('.layout-page-panel'), true)
  assert.equal(styleSource.includes('.layout-editor'), true)
  assert.equal(styleSource.includes('.layout-toolbar-header'), true)
  assert.equal(styleSource.includes('.layout-toolbar-main'), true)
  assert.equal(styleSource.includes('.layout-control-group'), true)
  assert.equal(styleSource.includes('.layout-control-field'), true)
  assert.equal(styleSource.includes('.layout-control-heading'), true)
  assert.equal(styleSource.includes('.layout-viewport-controls'), true)
  assert.equal(styleSource.includes('.layout-arrange-controls'), true)
  assert.equal(styleSource.includes('.layout-resize-handle'), true)
  assert.equal(styleSource.includes('.layout-hit-area'), true)
  assert.equal(styleSource.includes('.layout-window'), true)
  assert.equal(styleSource.includes('.layout-table'), true)
  assert.equal(styleSource.includes('.layout-door'), true)
  assert.equal(styleSource.includes('.layout-item.is-overlapping'), true)
  assert.equal(styleSource.includes('.table-top'), true)
  assert.equal(styleSource.includes('.dining-chair'), true)
  assert.equal(styleSource.includes('.queue-lane'), false)
  assert.equal(styleSource.includes('.counter-belt'), false)
  assert.equal(styleSource.includes('.floor-zone'), false)
  assert.equal(styleSource.includes('.service-counter-bank'), false)
  assert.equal(styleSource.includes('.preview-grid'), false)
})

// 验证仿真、校验、推荐和解释接口都使用当前可编辑布局 payload。
test('frontend sends the editable dining layout to simulation APIs', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes("from './layout'"), true)
  assert.equal(source.includes('buildSimulationConfigPayload(config, layout.value)'), true)
  assert.equal(source.includes('base_config: buildSimulationConfigPayload(config, layout.value)'), true)
  assert.equal(source.includes('api.runSimulation(buildSimulationConfigPayload(config, layout.value))'), true)
  // The validation, step, and explanation calls also pass through the live layout.
  assert.equal(source.includes('api.validateConfig(buildSimulationConfigPayload(config, layout.value))'), true)
  assert.equal(source.includes('config: buildSimulationConfigPayload(config, layout.value)'), true)
  assert.equal(source.includes('baseline_config: buildSimulationConfigPayload(config, layout.value)'), true)
})

// 验证门窗点击热区不会作为可见图形误显示。
test('door and window hit areas are not rendered as visible sprites', () => {
  const editorSource = readFileSync(new URL('../src/LayoutEditor.vue', import.meta.url), 'utf8')
  const mapSource = readFileSync(new URL('../src/LiveDiningMap.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(editorSource.includes('layout-door-body'), true)
  assert.equal(editorSource.includes('layout-window-body'), true)
  assert.equal(mapSource.includes('layout-door-body'), true)
  assert.equal(mapSource.includes('layout-window-body'), true)
  assert.equal(styleSource.includes('.layout-door-body'), true)
  assert.equal(styleSource.includes('.layout-window-body'), true)
  assert.equal(styleSource.includes('.layout-door rect {'), false)
  assert.equal(styleSource.includes('.layout-window rect {'), false)
  assert.equal(styleSource.includes('rect:first-child'), false)
})

// 验证配置页推荐面板会展示候选效果指标。
test('config recommendation panel shows effect metrics for alternatives', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('class="config-effect-table"'), true)
  assert.equal(source.includes('label="平均等待"'), true)
  assert.equal(source.includes('label="峰值排队"'), true)
  assert.equal(source.includes('label="完成就餐"'), true)
  assert.equal(source.includes('label="评分"'), true)
})

// 验证推荐主方案和备选方案都可以应用回当前配置。
test('config recommendation panel can apply recommended and alternative plans', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('应用推荐方案'), true)
  assert.equal(source.includes('应用方案'), true)
  assert.equal(source.includes('applyRecommendationConfig'), true)
})

// 验证基础参数表单使用更明确的到达人数标签。
test('config form uses a clear arrival volume label', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('label="平均每分钟到达人数"'), true)
  assert.equal(source.includes('label="到达率"'), false)
})

// 验证校园到达模式下手动到达相关控件会隐藏。
test('campus mode hides manual arrival controls from base parameters', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes(`v-if="arrivalMode === 'manual'"`), true)
  assert.equal(source.includes('label="到达持续时间"'), true)
  assert.equal(source.includes('label="到达时段"'), false)
  assert.equal(source.includes('label="平均每分钟到达人数"'), true)
  assert.equal(source.includes('label="错峰分钟"'), true)
  assert.equal(source.includes('label="高峰开始"'), true)
  assert.equal(source.includes('label="高峰结束"'), true)
})

// 验证基础配置控件按手动到达和服务随机性分组对齐。
test('config form groups base controls into aligned sections', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(source.includes('class="config-section manual-arrival-section"'), true)
  assert.equal(source.includes('class="config-section service-random-section"'), true)
  assert.equal(source.includes('class="config-section-title"'), true)
  assert.equal(source.includes('手动到达'), true)
  assert.equal(source.includes('服务与随机性'), true)
  assert.equal(source.includes('class="config-field-grid"'), true)
  assert.equal(source.includes('class="button-row config-action-bar"'), true)
  assert.equal(source.includes('class="form-pair"'), false)
  assert.equal(styleSource.includes('.config-field-grid'), true)
  assert.equal(styleSource.includes('.config-action-bar'), true)
})

// 验证校园到达配置提供实时数据和随机生成人数入口。
test('config form exposes campus demand controls with live and random buttons', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('校园到达'), true)
  assert.equal(source.includes('获取实时数据'), true)
  assert.equal(source.includes('随机生成'), true)
  assert.equal(source.includes('campusRows'), true)
  assert.equal(source.includes('selectedCafeteriaId'), true)
  assert.equal(source.includes('loadCampusOccupancy'), true)
})

// 验证校园楼层人数表按内容自然展开，而不是固定高度滚动。
test('campus floor population table expands vertically instead of scrolling', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('<el-table :data="campusRows" class="campus-table" size="small">'), true)
  assert.equal(source.includes('class="campus-table" size="small" height='), false)
  assert.equal(source.includes('class="campus-table" size="small" max-height='), false)
})

// 验证校园配置和推荐候选编辑区使用对齐的网格外壳。
test('campus and recommendation controls use aligned grid shells', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(source.includes('class="campus-mode-strip"'), true)
  assert.equal(source.includes('class="campus-toolbar"'), true)
  assert.equal(source.includes('class="campus-actions"'), true)
  assert.equal(source.includes('class="candidate-range-grid"'), true)
  assert.equal(source.includes('class="candidate-editor-row candidate-editor-row-single"'), true)
  assert.equal(styleSource.includes('.campus-panel'), true)
  assert.equal(styleSource.includes('grid-row: 1 / span 2'), true)
  assert.equal(styleSource.includes('.campus-toolbar'), true)
  assert.equal(styleSource.includes('.candidate-range-grid'), true)
  assert.equal(styleSource.includes('.candidate-editor-row-single'), true)
})

// 验证推荐候选范围行保持单列全宽排布。
test('recommendation candidate editor keeps range rows full width', () => {
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(styleSource.includes('.candidate-range-grid {\n  display: grid;\n  grid-template-columns: 1fr;'), true)
  assert.equal(styleSource.includes('grid-template-columns: 86px minmax(0, 1fr) 22px minmax(0, 1fr);'), true)
  assert.equal(styleSource.includes('grid-template-columns: 86px minmax(0, 1fr) minmax(72px, auto);'), true)
  assert.equal(styleSource.includes('grid-template-columns: repeat(2, minmax(220px, 1fr));'), false)
})

// 验证推荐请求会提交下课峰数候选。
test('recommendation panel sends dismissal peak count candidates', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('下课峰数'), true)
  assert.equal(source.includes('candidateSettings.peakCountMin'), true)
  assert.equal(source.includes('candidateSettings.peakCountMax'), true)
  assert.equal(source.includes('const peakCountCandidates = computed'), true)
  assert.equal(source.includes('peak_count_options: peakCountCandidates.value'), true)
})

// 验证应用校园推荐后会把高峰排程写回可编辑教学楼表格。
test('applying campus recommendation writes peak schedule back to editable rows', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('applyCampusDemandConfig(recommendedConfig.campus_demand)'), true)
  assert.equal(source.includes("arrivalMode.value = 'campus'"), true)
  assert.equal(source.includes('selectedCafeteriaId.value = campusDemand.cafeteria_id'), true)
  assert.equal(source.includes('release_percent: releasePercentFromRatio(building.release_ratio ?? 1)'), true)
})

// 验证校园就餐比例在页面上按百分比编辑并转换为后端比例。
test('campus release control is edited as a percentage', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('label="就餐比例"'), true)
  assert.equal(source.includes('v-model="row.release_percent"'), true)
  assert.equal(source.includes('class="percent-suffix"'), true)
  assert.equal(source.includes('release_ratio: releasePercentToRatio(row.release_percent)'), true)
  assert.equal(source.includes('label="释放"'), false)
  assert.equal(source.includes('v-model="row.release_ratio" :min="0" :max="1"'), false)
})

// 验证校园人数加载按钮只对当前请求来源显示 loading。
test('campus occupancy buttons show loading only for the requested source', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes(`:loading="campusLoadingSource === 'live'"`), true)
  assert.equal(source.includes(`:loading="campusLoadingSource === 'random'"`), true)
  assert.equal(source.includes('campusLoadingSource.value = sourceMode'), true)
  assert.equal(source.includes("campusLoadingSource.value = ''"), true)
  assert.equal(source.includes(':loading="campusLoading"'), false)
})

// 验证分析卡片使用面向展示说明的中文指标说明。
test('analysis cards explain secondary metrics without jargon', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('取餐排队等待'), true)
  assert.equal(source.includes('高峰最多等座'), true)
  assert.equal(source.includes('瓶颈判断：'), true)
  assert.equal(source.includes('完成就餐'), true)
  assert.equal(source.includes('`队列 ${formatMinutes'), false)
  assert.equal(source.includes('`等座峰值 ${'), false)
  assert.equal(source.includes('`吞吐 ${'), false)
})

// 验证座位利用率标签明确表示运行平均值。
test('seat utilization label states it is an average over the run', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes("label: '平均座位利用率'"), true)
  assert.equal(source.includes("label: '座位利用率'"), false)
  assert.equal(source.includes('`当前等座 ${record?.waiting_for_seat_count || 0} 人`'), true)
})

// 验证运行页排队卡片优先显示当前排队，并把峰值作为提示。
test('live run queue card shows current queue first and peak queue as context', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('const peakQueue = metrics.value?.peak_queue ?? livePeakQueue.value'), true)
  assert.equal(source.includes("{ label: '当前排队人数', value: queue, hint: `峰值排队 ${peakQueue} 人` }"), true)
  assert.equal(source.includes("label: '峰值排队长度'"), false)
  assert.equal(source.includes('hint: `当前 ${queue} 人`'), false)
})

// 验证实时运行页使用可编辑布局地图展示小组状态，而不是座位矩阵。
test('live run renders the editable layout as a live dining map with party groups', () => {
  const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const mapSource = readFileSync(new URL('../src/LiveDiningMap.vue', import.meta.url), 'utf8')
  const modelSource = readFileSync(new URL('../src/liveMapModel.js', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(appSource.includes("import LiveDiningMap from './LiveDiningMap.vue'"), true)
  assert.equal(appSource.includes('<LiveDiningMap'), true)
  assert.equal(appSource.includes(':layout="layout"'), true)
  assert.equal(appSource.includes(':state="currentState"'), true)
  assert.equal(appSource.includes('座位占用矩阵'), false)
  assert.equal(appSource.includes('class="seat-grid"'), false)
  assert.equal(appSource.includes('visibleSeatMatrix'), false)
  assert.equal(appSource.includes('seatGridStyle'), false)

  assert.equal(mapSource.includes('live-dining-map'), true)
  assert.equal(mapSource.includes('layout-door'), true)
  assert.equal(mapSource.includes('layout-window'), true)
  assert.equal(mapSource.includes('layout-table'), true)
  assert.equal(mapSource.includes('tableTransformFor'), true)
  assert.equal(mapSource.includes('table-shape'), true)
  assert.equal(mapSource.includes('table-occupancy'), true)
  assert.equal(mapSource.includes('party-group'), true)
  // Queue and waiting parties are not painted on the map. The queue is shown
  // in the detail panel below; the waiting count is reported by the metric card.
  assert.equal(mapSource.includes('queue-party'), false)
  assert.equal(mapSource.includes('waiting-party'), false)
  assert.equal(mapSource.includes('waiting-zone'), false)
  assert.equal(mapSource.includes('window-detail-panel'), true)
  assert.equal(mapSource.includes('seated-party'), true)
  assert.equal(mapSource.includes('party-link'), true)
  assert.equal(mapSource.includes('queue_groups'), true)
  assert.equal(mapSource.includes('buildLivePartyTargets'), true)
  assert.equal(mapSource.includes('buildLivePartyTransitions'), true)
  assert.equal(mapSource.includes('animatedPartyMarkers'), true)
  assert.equal(mapSource.includes('motion-path'), false)
  assert.equal(modelSource.includes('window_services'), true)
  assert.equal(modelSource.includes('seated_parties'), true)
  assert.equal(modelSource.includes('interpolateLivePartyMarkers'), true)
  assert.equal(modelSource.includes('samplePathAtProgress'), true)
  assert.equal(modelSource.includes('createPathPlanner'), true)
  assert.equal(mapSource.includes('seat_matrix'), false)
  assert.equal(mapSource.includes('<text'), false)

  assert.equal(styleSource.includes('.live-dining-map'), true)
  assert.equal(styleSource.includes('.party-group'), true)
  assert.equal(styleSource.includes('.party-link'), true)
  assert.equal(styleSource.includes('.table-occupancy'), true)
  assert.equal(styleSource.includes('.window-detail-panel'), true)
})
