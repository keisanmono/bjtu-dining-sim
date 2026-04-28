import assert from 'node:assert/strict'
import test from 'node:test'

import { applyRecommendedConfig, nextViewAfterRecommendation } from '../src/recommendationFlow.js'

test('generating recommendations keeps the user on the current page', () => {
  assert.equal(nextViewAfterRecommendation('config'), 'config')
  assert.equal(nextViewAfterRecommendation('analysis'), 'analysis')
})

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
