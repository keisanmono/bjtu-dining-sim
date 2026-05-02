import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('config recommendation panel does not render redundant candidate preview list', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('class="candidate-groups"'), false)
  assert.equal(source.includes('configCandidateGroups'), false)
})

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

test('simulation preview renders a realistic cafeteria floor plan via LayoutEditor', () => {
  const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const editorSource = readFileSync(new URL('../src/LayoutEditor.vue', import.meta.url), 'utf8')
  const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  // App.vue delegates the floor plan to a LayoutEditor component.
  assert.equal(appSource.includes("import LayoutEditor from './LayoutEditor.vue'"), true)
  assert.equal(appSource.includes('<LayoutEditor'), true)
  assert.equal(appSource.includes(':layout="layout"'), true)
  assert.equal(appSource.includes('@update:layout="onLayoutUpdate"'), true)
  assert.equal(appSource.includes('@reset="resetLayout"'), true)

  // The LayoutEditor itself renders the SVG floor plan with the agreed viewBox.
  assert.equal(editorSource.includes('class="dining-floor-plan"'), true)
  assert.equal(editorSource.includes('LAYOUT_VIEWBOX.width'), true)
  assert.equal(editorSource.includes('LAYOUT_VIEWBOX.height'), true)
  assert.equal(editorSource.includes('layout-window'), true)
  assert.equal(editorSource.includes('layout-table'), true)
  assert.equal(editorSource.includes('layout-door'), true)
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
  assert.equal(editorSource.includes('adjustLayoutDoorCount'), true)
  assert.equal(editorSource.includes('入口 +'), true)

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
  assert.equal(styleSource.includes('aspect-ratio: 360 / 640'), true)
  assert.equal(styleSource.includes('.layout-editor'), true)
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

test('config recommendation panel shows effect metrics for alternatives', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('class="config-effect-table"'), true)
  assert.equal(source.includes('label="平均等待"'), true)
  assert.equal(source.includes('label="峰值排队"'), true)
  assert.equal(source.includes('label="完成就餐"'), true)
  assert.equal(source.includes('label="评分"'), true)
})

test('config recommendation panel can apply recommended and alternative plans', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('应用推荐方案'), true)
  assert.equal(source.includes('应用方案'), true)
  assert.equal(source.includes('applyRecommendationConfig'), true)
})

test('config form uses a clear arrival volume label', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('label="平均每分钟到达人数"'), true)
  assert.equal(source.includes('label="到达率"'), false)
})

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

test('seat utilization label states it is an average over the run', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes("label: '平均座位利用率'"), true)
  assert.equal(source.includes("label: '座位利用率'"), false)
  assert.equal(source.includes('`当前等座 ${record?.waiting_for_seat_count || 0} 人`'), true)
})

test('live run queue card shows current queue first and peak queue as context', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('const peakQueue = metrics.value?.peak_queue ?? Math.max(queue, ...records.value.map((item) => totalQueue(item)))'), true)
  assert.equal(source.includes("{ label: '当前排队人数', value: queue, hint: `峰值排队 ${peakQueue} 人` }"), true)
  assert.equal(source.includes("label: '峰值排队长度'"), false)
  assert.equal(source.includes('hint: `当前 ${queue} 人`'), false)
})
