import assert from 'node:assert/strict'
import test from 'node:test'

import { canRenderChartElement } from '../src/chartUtils.js'

test('hidden chart containers are not renderable', () => {
  assert.equal(canRenderChartElement({ clientWidth: 0, clientHeight: 260 }), false)
  assert.equal(canRenderChartElement({ clientWidth: 420, clientHeight: 0 }), false)
})

test('visible chart containers are renderable', () => {
  assert.equal(canRenderChartElement({ clientWidth: 420, clientHeight: 260 }), true)
})
