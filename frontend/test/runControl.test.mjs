import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldResetStepRun } from '../src/runControl.js'

test('single-step click events do not reset an existing run', () => {
  const clickEventLike = { type: 'click' }

  assert.equal(shouldResetStepRun(clickEventLike, 'run-1'), false)
})

test('single-step starts a run when there is no active run id', () => {
  assert.equal(shouldResetStepRun(false, ''), true)
})

test('explicit reset still starts a fresh run', () => {
  assert.equal(shouldResetStepRun(true, 'run-1'), true)
})
