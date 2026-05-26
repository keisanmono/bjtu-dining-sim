// 文件说明：实时运行控制测试，覆盖单步重置判断、自动步进延迟和请求条件。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  liveStepDelay,
  shouldRequestLiveStep,
  shouldResetStepRun
} from '../src/runControl.js'

// 验证普通点击对象不会被误判为 reset=true。
test('single-step click events do not reset an existing run', () => {
  const clickEventLike = { type: 'click' }

  assert.equal(shouldResetStepRun(clickEventLike, 'run-1'), false)
})

// 验证没有 run_id 时单步请求会自动新建运行。
test('single-step starts a run when there is no active run id', () => {
  assert.equal(shouldResetStepRun(false, ''), true)
})

// 验证显式 reset 会强制开始新的实时运行。
test('explicit reset still starts a fresh run', () => {
  assert.equal(shouldResetStepRun(true, 'run-1'), true)
})

// 验证自动步进延迟包含地图过渡时长和缓冲时间。
test('automatic live run waits beyond the party transition before requesting the next step', () => {
  assert.equal(liveStepDelay(320), 400)
  assert.equal(liveStepDelay(120), 200)
})

// 验证停止、已结束或请求在途时不会继续发起自动 step。
test('automatic live run skips requests while stopped done or already in flight', () => {
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: false, stepInFlight: false }), true)
  assert.equal(shouldRequestLiveStep({ isRunning: false, isDone: false, stepInFlight: false }), false)
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: true, stepInFlight: false }), false)
  assert.equal(shouldRequestLiveStep({ isRunning: true, isDone: false, stepInFlight: true }), false)
})
