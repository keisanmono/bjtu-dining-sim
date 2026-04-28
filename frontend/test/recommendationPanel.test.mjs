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
  assert.equal(source.includes('label="吞吐"'), true)
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
