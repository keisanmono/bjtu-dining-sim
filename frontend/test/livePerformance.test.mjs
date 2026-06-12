// 文件说明：实时运行性能约束测试，防止记录追加、图表刷新和自动步进退化。

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

// 验证实时 step 追加记录时不会每步复制完整历史数组。
test('live run appends records without copying the full history every step', () => {
  assert.equal(appSource.includes('appendRunRecord(response.record)'), true)
  assert.equal(appSource.includes('records.value = [...records.value, response.record]'), false)
})

// 验证实时图表只从有限滚动窗口读取记录。
test('live charts render from a bounded rolling window', () => {
  assert.equal(appSource.includes('LIVE_CHART_RECORD_LIMIT'), true)
  assert.equal(appSource.includes('chartRecords'), true)
  assert.equal(appSource.includes('chartRecords.value.map'), true)
})

// 验证自动运行期间图表刷新有节流控制。
test('live chart rendering is throttled during automatic runs', () => {
  assert.equal(appSource.includes('LIVE_CHART_RENDER_INTERVAL_MS'), true)
  assert.equal(appSource.includes('chartRenderScheduledAt'), true)
  assert.equal(appSource.includes('renderChartsThrottled'), true)
})

// 验证自动运行使用 setTimeout 自调度而不是固定 interval。
test('automatic live run self-schedules after each completed step', () => {
  assert.equal(appSource.includes('scheduleNextLiveStep'), true)
  assert.equal(appSource.includes('runScheduledLiveStep'), true)
  assert.equal(appSource.includes('window.setTimeout'), true)
  assert.equal(appSource.includes('window.setInterval'), false)
  assert.equal(appSource.includes('window.clearInterval'), false)
  assert.equal(appSource.includes('stepInFlight'), true)
})

// 验证下一次实时快照会等地图过渡结束后再调度。
test('automatic live run waits for the map transition before scheduling another snapshot', () => {
  assert.equal(appSource.includes('@transition-settled="onLiveMapTransitionSettled"'), true)
  assert.equal(appSource.includes('awaitingLiveMapTransition'), true)
  assert.equal(appSource.includes('onLiveMapTransitionSettled'), true)
})
