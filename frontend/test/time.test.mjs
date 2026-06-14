// 文件说明：仿真时钟显示测试，验证前端把相对分钟展示为真实 HH:MM。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clockMinuteFromRecord,
  formatClockMinute,
  parseClockTime
} from '../src/time.js'

test('formatClockMinute renders absolute minutes as HH:MM', () => {
  assert.equal(formatClockMinute(690), '11:30')
  assert.equal(formatClockMinute(1020), '17:00')
  assert.equal(formatClockMinute(24 * 60 + 15), '00:15')
})

test('parseClockTime accepts HH:MM input for campus dismissal time', () => {
  assert.equal(parseClockTime('11:30'), 690)
  assert.equal(parseClockTime('7:05'), 425)
  assert.equal(parseClockTime(' 18:00 '), 1080)
})

test('clockMinuteFromRecord prefers backend clock minute and falls back to simulation start plus t', () => {
  assert.equal(clockMinuteFromRecord({ clock_minute: 690, t: 30 }, 660), 690)
  assert.equal(clockMinuteFromRecord({ t: 68 }, 660), 728)
  assert.equal(formatClockMinute(clockMinuteFromRecord({ t: 68 }, 660)), '12:08')
})
