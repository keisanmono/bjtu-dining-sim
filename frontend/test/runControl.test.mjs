// 文件说明：前端源码文件。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  liveStepDelay,
  shouldRequestLiveStep,
  shouldResetStepRun
} from '../src/runControl.js'

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('single-step click events do not reset an existing run', () => {
  const clickEventLike = { type: 'click' }

  assert.equal(shouldResetStepRun(clickEventLike, 'run-1'), false)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('single-step starts a run when there is no active run id', () => {
  assert.equal(shouldResetStepRun(false, ''), true)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('explicit reset still starts a fresh run', () => {
  assert.equal(shouldResetStepRun(true, 'run-1'), true)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('automatic live run waits beyond the party transition before requesting the next step', () => {
  assert.equal(liveStepDelay(320), 400)
  assert.equal(liveStepDelay(120), 200)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('automatic live run skips requests while stopped done or already in flight', () => {
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: false, stepInFlight: false }), true)
  assert.equal(shouldRequestLiveStep({ isRunning: false, isDone: false, stepInFlight: false }), false)
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: true, stepInFlight: false }), false)
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: false, stepInFlight: true }), false)
})
