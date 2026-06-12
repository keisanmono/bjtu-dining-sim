// 文件说明：推荐流程工具测试，验证推荐后页面策略和配置字段应用。

import assert from 'node:assert/strict'
import test from 'node:test'

import { applyRecommendedConfig, nextViewAfterRecommendation } from '../src/recommendationFlow.js'

// 验证生成推荐后不会强制切换当前页面。
test('generating recommendations keeps the user on the current page', () => {
  assert.equal(nextViewAfterRecommendation('config'), 'config')
  assert.equal(nextViewAfterRecommendation('analysis'), 'analysis')
})

// 验证应用推荐时只覆盖候选中提供的配置字段。
test('applying a recommendation writes the candidate config into current parameters', () => {
  const current = {
    num_windows: 4,
    num_seats: 120,
    arrival_rate: 8,
    stagger_minutes: 0
  }

  applyRecommendedConfig(current, {
    num_windows: 6,
    num_seats: 140,
    stagger_minutes: 10
  })

  assert.deepEqual(current, {
    num_windows: 6,
    num_seats: 140,
    arrival_rate: 8,
    stagger_minutes: 10
  })
})
