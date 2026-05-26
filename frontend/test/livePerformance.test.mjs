// 文件说明：前端源码文件。

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('live run appends records without copying the full history every step', () => {
  assert.equal(appSource.includes('appendRunRecord(response.record)'), true)
  assert.equal(appSource.includes('records.value = [...records.value, response.record]'), false)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('live charts render from a bounded rolling window', () => {
  assert.equal(appSource.includes('LIVE_CHART_RECORD_LIMIT'), true)
  assert.equal(appSource.includes('chartRecords'), true)
  assert.equal(appSource.includes('chartRecords.value.map'), true)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('live chart rendering is throttled during automatic runs', () => {
  assert.equal(appSource.includes('LIVE_CHART_RENDER_INTERVAL_MS'), true)
  assert.equal(appSource.includes('chartRenderScheduledAt'), true)
  assert.equal(appSource.includes('renderChartsThrottled'), true)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('automatic live run self-schedules after each completed step', () => {
  assert.equal(appSource.includes('scheduleNextLiveStep'), true)
  assert.equal(appSource.includes('runScheduledLiveStep'), true)
  assert.equal(appSource.includes('window.setTimeout'), true)
  assert.equal(appSource.includes('window.setInterval'), false)
  assert.equal(appSource.includes('window.clearInterval'), false)
  assert.equal(appSource.includes('stepInFlight'), true)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('automatic live run waits for the map transition before scheduling another snapshot', () => {
  assert.equal(appSource.includes('@transition-settled="onLiveMapTransitionSettled"'), true)
  assert.equal(appSource.includes('awaitingLiveMapTransition'), true)
  assert.equal(appSource.includes('onLiveMapTransitionSettled'), true)
})
