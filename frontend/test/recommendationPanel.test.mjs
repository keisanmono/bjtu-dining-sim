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
  assert.equal(appSource.includes('optimizeLayoutForFlow'), true)
  assert.equal(appSource.includes('一键优化布局'), true)
  assert.equal(appSource.includes('optimizeCurrentLayout'), true)

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

// 验证结果分析页不再保留重复的生成推荐入口。
test('analysis page removes duplicate recommendation action', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const analysisStart = source.indexOf('<section v-show="activeView === \'analysis\'"')
  const recordsStart = source.indexOf('<section v-show="activeView === \'records\'"')
  const analysisSection = source.slice(analysisStart, recordsStart)

  assert.ok(analysisStart >= 0)
  assert.ok(recordsStart > analysisStart)
  assert.equal(analysisSection.includes('生成推荐'), false)
  assert.equal(analysisSection.includes('generateRecommendation'), false)
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

// 验证校园到达配置拆分教学楼实时人数和宿舍人口反推，避免混在一张长表里。
test('campus config separates teaching occupancy and residential population sections', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(source.includes('class="campus-source-tabs"'), true)
  assert.equal(source.includes('label="教学楼实时人数"'), true)
  assert.equal(source.includes('label="宿舍人口反推"'), true)
  assert.equal(source.includes(':data="campusRows"'), true)
  assert.equal(source.includes('height="420"'), true)
  assert.equal(source.includes('campusResidentialAreaSummaryRows'), true)
  assert.equal(source.includes('class="campus-detail-collapse"'), true)
  assert.equal(source.includes('title="详细权重输入"'), true)
  assert.equal(source.includes(':data="campusCombinedRows"'), false)
  assert.equal(source.includes('const campusCombinedRows'), false)
  assert.equal(source.includes('campusPopulationSummaryItems'), false)
  assert.equal(source.includes('campusSourceDetailRows'), false)
  assert.equal(source.includes('campusPopulationPoolPayload'), true)
  assert.equal(source.includes('population_pool: campusPopulationPoolPayload.value'), true)
  assert.equal(styleSource.includes('.campus-source-tabs'), true)
  assert.equal(styleSource.includes('.campus-residential-summary'), true)
  assert.equal(styleSource.includes('.campus-detail-collapse'), true)
})

// 验证校园到达配置保留教学楼和宿舍的原有可编辑字段，只是分区展示。
test('campus config keeps teaching floors and residential weights editable in separate tables', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes(':data="campusRows"'), true)
  assert.equal(source.includes('campusResidentialTableRows'), true)
  assert.equal(source.includes('campusResidentialAreaSummaryRows'), true)
  assert.equal(source.includes('campusTableWalkMinutes'), true)
  assert.equal(source.includes('campusTableChoiceProbability'), true)
  assert.equal(source.includes('residentialAllocatedPopulation'), true)
  assert.equal(source.includes('allocateResidentialPopulationByWeight'), true)
  assert.equal(source.includes('residentialWalkMinutes'), true)
  assert.equal(source.includes('residentialReleaseWindowLabel'), true)
  assert.equal(source.includes("source_type: '宿舍'"), true)
  assert.equal(source.includes('campusLocations.value.residential_walk_times'), true)
  assert.equal(source.includes(':model-value="residentialCapacityWeight(row.source_id)"'), true)
  assert.equal(source.includes('@update:model-value="updateResidentialCapacityWeight(row.source_id, $event)"'), true)
})

// 验证当前食堂到达人数会乘以食堂选择概率，而不是显示 source 原始人数。
test('campus table arrival population is weighted by cafeteria choice probability', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('campusTableArrivalPopulation'), true)
  assert.equal(source.includes('campusReleasedPopulation(row) * campusTableChoiceProbability(row)'), true)
  assert.equal(source.includes('row.population * campusTableChoiceProbability(row)'), true)
  assert.equal(source.includes('return `${formatNumber(campusTableArrivalPopulation(row))} 人`'), true)
  assert.equal(source.includes('if (isResidentialCampusRow(row)) return row.population_label'), false)
})

// 验证校园到达选择概率可以按百分比配置，并作为 choice_probability 提交后端。
test('campus cafeteria choice probability is editable and serialized', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('label="选择概率"'), true)
  assert.equal(source.includes('campusTableChoicePercent(row)'), true)
  assert.equal(source.includes('updateCampusRowChoicePercent(row, $event)'), true)
  assert.equal(source.includes('updateResidentialChoicePercent(row.source_id, $event)'), true)
  assert.equal(source.includes('choice_probability: campusTableChoiceProbability(row)'), true)
  assert.equal(source.includes('choice_probability: residentialChoiceProbability(source.id)'), true)
  assert.equal(source.includes('choice_percent: choicePercentFromProbability(building.choice_probability)'), true)
  assert.equal(source.includes('residentialChoicePercents[source.residential_id] = choicePercentFromProbability(source.choice_probability)'), true)
})

// 验证校园到达记录页展示采集时间，并支持单条导入和多条平均导入。
test('campus arrival records can be saved and imported from the records page', () => {
  const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const apiSource = readFileSync(new URL('../src/api.js', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(appSource.includes('<el-tab-pane label="记录页" name="records"'), true)
  assert.equal(appSource.includes("activeView === 'records'"), true)
  assert.equal(appSource.includes('校园到达记录'), true)
  assert.equal(appSource.includes('prop="created_at" label="记录时间"'), true)
  assert.equal(appSource.includes('formatCampusRecordTime'), true)
  assert.equal(appSource.includes('saveCampusArrivalRecord'), true)
  assert.equal(appSource.includes('loadCampusArrivalRecords'), true)
  assert.equal(appSource.includes('importCampusArrivalRecord(row)'), true)
  assert.equal(appSource.includes('importSelectedCampusArrivalAverage'), true)
  assert.equal(appSource.includes('api.saveCampusArrivalRecord'), true)
  assert.equal(appSource.includes('api.campusArrivalRecordAverage'), true)
  assert.equal(appSource.includes('await saveCampusArrivalRecord({ silent: true, sourceMode })'), true)
  assert.equal(appSource.includes('applyCampusDemandConfig(average.campus_demand)'), true)
  assert.equal(apiSource.includes("campusArrivalRecords: () => client.get('/campus/arrival-records')"), true)
  assert.equal(apiSource.includes("saveCampusArrivalRecord: (payload) => client.post('/campus/arrival-records', payload)"), true)
  assert.equal(apiSource.includes("campusArrivalRecordAverage: (payload) => client.post('/campus/arrival-records/average', payload)"), true)
  assert.equal(styleSource.includes('.records-layout'), true)
  assert.equal(styleSource.includes('.records-toolbar'), true)
})

// 验证校园人口池、宿舍释放窗口、宿舍参与率和宿舍权重都能手动编辑。
test('campus residential population parameters are manually editable', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(source.includes('class="campus-population-controls"'), true)
  assert.equal(source.includes('label="潜在人群池"'), true)
  assert.equal(source.includes('v-model="campusPopulationPoolForm.total_population_pool"'), true)
  assert.equal(source.includes('label="食堂参与率"'), true)
  assert.equal(source.includes('v-model="campusPopulationPoolForm.meal_participation_percent"'), true)
  assert.equal(source.includes('label="其他已知来源"'), true)
  assert.equal(source.includes('v-model="campusPopulationPoolForm.other_known_population"'), true)
  assert.equal(source.includes('label="宿舍参与率"'), true)
  assert.equal(source.includes('v-model="campusResidentialProfileForm.residential_participation_percent"'), true)
  assert.equal(source.includes('v-model="campusResidentialProfileForm.start_time"'), true)
  assert.equal(source.includes('v-model="campusResidentialProfileForm.end_time"'), true)
  assert.equal(source.includes('v-model="campusResidentialProfileForm.peak_time"'), true)
  assert.equal(source.includes(':model-value="residentialCapacityWeight(row.source_id)"'), true)
  assert.equal(source.includes('@update:model-value="updateResidentialCapacityWeight(row.source_id, $event)"'), true)
  assert.equal(source.includes('residential_release_profile: campusResidentialReleaseProfilePayload.value'), true)
  assert.equal(styleSource.includes('.campus-population-controls'), true)
})

// 验证校园楼层人数表使用固定高度，防止撑高参数配置页。
test('campus teaching population table uses a fixed height inside a bounded campus panel', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(source.includes(':data="campusRows"'), true)
  assert.equal(source.includes('class="campus-table"'), true)
  assert.equal(source.includes('height="420"'), true)
  assert.equal(source.includes('class="campus-table" size="small" max-height='), false)
  assert.equal(styleSource.includes('max-height: calc(100vh - 190px);'), true)
  assert.equal(styleSource.includes('.campus-panel > .el-card__body'), true)
  assert.equal(styleSource.includes('overflow: auto;'), true)
})

// 验证参数配置页使用左侧 sticky sidebar 和右侧校园面板，且移除旧跨行定位。
test('config page uses sticky sidebar and removes old spanning grid placement', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.equal(source.includes('class="config-sidebar"'), true)
  assert.equal(source.includes('class="panel config-basic-panel"'), true)
  assert.equal(source.includes('class="panel recommendation-panel"'), true)
  assert.equal(source.includes('class="panel campus-panel"'), true)
  assert.equal(source.includes('class="campus-mode-strip"'), true)
  assert.equal(source.includes('class="campus-toolbar"'), true)
  assert.equal(source.includes('class="campus-actions"'), true)
  assert.equal(source.includes('class="candidate-range-grid"'), true)
  assert.equal(source.includes('class="candidate-editor-row candidate-editor-row-single"'), true)
  assert.equal(styleSource.includes('.config-sidebar'), true)
  assert.equal(styleSource.includes('position: sticky;'), true)
  assert.equal(styleSource.includes('top: 18px;'), true)
  assert.equal(styleSource.includes('.campus-panel'), true)
  assert.equal(styleSource.includes('grid-column: 2;'), false)
  assert.equal(styleSource.includes('grid-row: 1 / span 2'), false)
  assert.equal(styleSource.includes('grid-row: 2;'), false)
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

// 验证应用校园推荐后同步宿舍/人口池表单源，避免下一次运行重新序列化旧默认值。
test('applying campus recommendation syncs residential and population pool forms', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('applyCampusPopulationPoolConfig(campusDemand.population_pool)'), true)
  assert.equal(source.includes('applyCampusResidentialProfileConfig(campusDemand.residential_release_profile)'), true)
  assert.equal(source.includes('applyCampusResidentialSourcesConfig(campusDemand.residential_sources)'), true)
  assert.equal(source.includes('campusPopulationPoolForm.total_population_pool = Math.max(0, Math.round(Number(pool.total_population_pool) || 0))'), true)
  assert.equal(source.includes('campusResidentialProfileForm.start_time = formatClockMinute(profile.start_minute)'), true)
  assert.equal(source.includes('residentialPopulationOverrides[source.residential_id] = Math.max(0, Math.round(Number(source.population_override) || 0))'), true)
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

// 验证实时运行页使用真实时钟显示，不再暴露抽象 t 分钟。
test('run page displays concrete clock time instead of abstract t minutes', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('当前时刻：{{ currentClockLabel }}'), true)
  assert.equal(source.includes('t = {{ currentMinute }} min'), false)
  assert.equal(source.includes('const currentClockMinute = computed'), true)
  assert.equal(source.includes('formatClockMinute(currentClockMinute.value)'), true)
})

// 验证教学楼下课时间按 HH:MM 输入并转换为绝对分钟提交。
test('campus dismissal control uses concrete clock time strings', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('v-model="row.dismissal_time"'), true)
  assert.equal(source.includes('parseClockTime(row.dismissal_time ?? row.dismissal_minute)'), true)
  assert.equal(source.includes('dismissal_time: formatClockMinute'), true)
  assert.equal(source.includes('v-model="row.dismissal_minute" :min="0" :max="240"'), false)
})

// 验证分析页指标说明区分完成就餐、已入座、全程利用率和等座排队等待。
test('analysis metric labels separate seating, dining completion, and seat queue wait semantics', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes("label: '全程窗口利用率'"), true)
  assert.equal(source.includes('服务忙碌期'), true)
  assert.equal(source.includes('完成就餐 ${m?.total_left || 0} 人 / 已入座 ${m?.throughput || 0} 人'), true)
  assert.equal(source.includes('等座排队等待 ${formatMinutes(m?.avg_party_seat_wait || 0)}'), true)
  assert.equal(source.includes('入座完成耗时 ${formatMinutes(m?.avg_post_service_to_seat_time || 0)}'), true)
  assert.equal(source.includes('hint: `等座等待 ${formatMinutes(m?.avg_party_seat_wait || 0)}`'), false)
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

// 验证快速/平衡模式隐藏高级移动细分指标，只在质量模式展示。
test('fast and balanced modes hide advanced movement detail cards', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('const showMovementDetailCards = computed'), true)
  assert.equal(source.includes("config.movement_quality_preset === 'quality'"), true)
  assert.equal(source.includes('const movementDetailCards = ['), true)
  assert.equal(source.includes('const analysisMovementDetailCards = ['), true)
  assert.equal(source.includes('...(showMovementDetailCards.value ? movementDetailCards : [])'), true)
  assert.equal(source.includes('...(showMovementDetailCards.value ? analysisMovementDetailCards : [])'), true)
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
  assert.equal(source.includes('const entryWaiting = record?.snapshot?.entry_waiting_count'), true)
  assert.equal(source.includes("{ label: '当前排队人数', value: queue, hint: `峰值 ${peakQueue} 人 / 边界待入 ${entryWaiting} 人` }"), true)
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
  // Window queues are painted on the map so long queues remain visible without
  // opening the detail panel. Waiting-for-seat parties remain a metric only.
  assert.equal(mapSource.includes('queue-group'), true)
  assert.equal(mapSource.includes('queue-capsule'), true)
  assert.equal(mapSource.includes('queue-overflow'), true)
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
