import assert from 'node:assert/strict'
import test from 'node:test'

import { nextViewAfterRecommendation } from '../src/recommendationFlow.js'

test('generating recommendations keeps the user on the current page', () => {
  assert.equal(nextViewAfterRecommendation('config'), 'config')
  assert.equal(nextViewAfterRecommendation('analysis'), 'analysis')
})
