import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('config recommendation panel does not render redundant candidate preview list', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('class="candidate-groups"'), false)
  assert.equal(source.includes('configCandidateGroups'), false)
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
