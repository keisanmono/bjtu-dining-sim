import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('live run appends records without copying the full history every step', () => {
  assert.equal(appSource.includes('appendRunRecord(response.record)'), true)
  assert.equal(appSource.includes('records.value = [...records.value, response.record]'), false)
})

test('live charts render from a bounded rolling window', () => {
  assert.equal(appSource.includes('LIVE_CHART_RECORD_LIMIT'), true)
  assert.equal(appSource.includes('chartRecords'), true)
  assert.equal(appSource.includes('chartRecords.value.map'), true)
})

test('live chart rendering is throttled during automatic runs', () => {
  assert.equal(appSource.includes('LIVE_CHART_RENDER_INTERVAL_MS'), true)
  assert.equal(appSource.includes('chartRenderScheduledAt'), true)
  assert.equal(appSource.includes('renderChartsThrottled'), true)
})
