import assert from 'node:assert/strict'
import test from 'node:test'

import {
  liveStepDelay,
  shouldRequestLiveStep,
  shouldResetStepRun
} from '../src/runControl.js'

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

test('automatic live run waits beyond the party transition before requesting the next step', () => {
  assert.equal(liveStepDelay(320), 400)
  assert.equal(liveStepDelay(120), 200)
})

test('automatic live run skips requests while stopped done or already in flight', () => {
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: false, stepInFlight: false }), true)
  assert.equal(shouldRequestLiveStep({ isRunning: false, isDone: false, stepInFlight: false }), false)
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: true, stepInFlight: false }), false)
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: false, stepInFlight: true }), false)
})
