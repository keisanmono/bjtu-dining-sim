// 文件说明：推荐候选范围测试，验证候选数组生成和座位上限处理。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildCandidatesFromSettings,
  buildIntegerRange,
  createDefaultCandidateSettings
} from '../src/candidates.js'
import { LAYOUT_MAX_EDITABLE_SEATS } from '../src/layoutEditor.js'

// 验证默认推荐候选范围会围绕当前窗口数和座位数展开。
test('default candidate settings provide an editable range around the baseline', () => {
  const settings = createDefaultCandidateSettings({ num_windows: 4, num_seats: 120 })

  assert.deepEqual(settings, {
    windowMin: 3,
    windowMax: 6,
    seatMin: 80,
    seatMax: 160,
    seatStep: 20,
    staggerMin: 0,
    staggerMax: 10,
    staggerStep: 5,
    peakCountMin: 1,
    peakCountMax: 3
  })
})

// 验证整数候选范围包含首尾值，并按步长插入中间候选。
test('integer ranges include both ends and respect step size', () => {
  assert.deepEqual(buildIntegerRange(80, 150, 20), [80, 100, 120, 140, 150])
})

// 验证页面候选设置能转换成推荐接口实际提交的数组。
test('candidate settings build actual recommendation payload options', () => {
  const candidates = buildCandidatesFromSettings({
    windowMin: 2,
    windowMax: 4,
    seatMin: 80,
    seatMax: 120,
    seatStep: 20,
    staggerMin: 0,
    staggerMax: 15,
    staggerStep: 5,
    peakCountMin: 1,
    peakCountMax: 3
  })

  assert.deepEqual(candidates.windows, [2, 3, 4])
  assert.deepEqual(candidates.seats, [80, 100, 120])
  assert.deepEqual(candidates.staggers, [0, 5, 10, 15])
  assert.deepEqual(candidates.peakCounts, [1, 2, 3])
})

// 验证座位候选会规整为偶数，以匹配 2/4/6 人桌。
test('seat candidates are even because editable tables are 2/4/6 seats', () => {
  const candidates = buildCandidatesFromSettings({
    windowMin: 2,
    windowMax: 2,
    seatMin: 81,
    seatMax: 125,
    seatStep: 15,
    staggerMin: 0,
    staggerMax: 0,
    staggerStep: 5
  })

  assert.deepEqual(candidates.seats, [80, 94, 108, 122, 124])
})

// 验证座位候选不会超过布局编辑器支持的最大座位数。
test('seat candidates stay within the editable layout capacity', () => {
  const candidates = buildCandidatesFromSettings({
    windowMin: 2,
    windowMax: 2,
    seatMin: 160,
    seatMax: 2000,
    seatStep: 20,
    staggerMin: 0,
    staggerMax: 0,
    staggerStep: 5
  })

  assert.equal(candidates.seats.at(-1), LAYOUT_MAX_EDITABLE_SEATS)
})
