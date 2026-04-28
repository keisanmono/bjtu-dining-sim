import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildConfigCandidateGroups,
  buildCandidateGroups,
  buildCandidatesFromSettings,
  buildIntegerRange,
  createDefaultCandidateSettings,
  formatStaggerCandidate
} from '../src/candidates.js'

test('stagger candidate labels avoid confusing zero-minute wording', () => {
  assert.equal(formatStaggerCandidate(0), '不启用')
  assert.equal(formatStaggerCandidate(10), '10 分钟')
})

test('candidate groups keep window seat and stagger options separated', () => {
  const groups = buildCandidateGroups([4, 5, 6], [120, 140, 160], [0, 5, 10])

  assert.deepEqual(groups.map((group) => group.label), ['窗口', '座位', '错峰'])
  assert.deepEqual(groups[0].values, ['4 个', '5 个', '6 个'])
  assert.deepEqual(groups[1].values, ['120 个', '140 个', '160 个'])
  assert.deepEqual(groups[2].values, ['不启用', '5 分钟', '10 分钟'])
})

test('config candidate groups map labels to editable config fields', () => {
  const groups = buildConfigCandidateGroups([3, 4, 5, 6], [80, 100, 120, 140, 160], [0, 5, 10])

  assert.deepEqual(groups, [
    {
      key: 'windows',
      label: '窗口',
      field: 'num_windows',
      values: [
        { value: 3, label: '3 个' },
        { value: 4, label: '4 个' },
        { value: 5, label: '5 个' },
        { value: 6, label: '6 个' }
      ]
    },
    {
      key: 'seats',
      label: '座位',
      field: 'num_seats',
      values: [
        { value: 80, label: '80 个' },
        { value: 100, label: '100 个' },
        { value: 120, label: '120 个' },
        { value: 140, label: '140 个' },
        { value: 160, label: '160 个' }
      ]
    },
    {
      key: 'stagger',
      label: '错峰',
      field: 'stagger_minutes',
      values: [
        { value: 0, label: '不启用' },
        { value: 5, label: '5 分钟' },
        { value: 10, label: '10 分钟' }
      ]
    }
  ])
})

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
    staggerStep: 5
  })
})

test('integer ranges include both ends and respect step size', () => {
  assert.deepEqual(buildIntegerRange(80, 150, 20), [80, 100, 120, 140, 150])
})

test('candidate settings build actual recommendation payload options', () => {
  const candidates = buildCandidatesFromSettings({
    windowMin: 2,
    windowMax: 4,
    seatMin: 80,
    seatMax: 120,
    seatStep: 20,
    staggerMin: 0,
    staggerMax: 15,
    staggerStep: 5
  })

  assert.deepEqual(candidates.windows, [2, 3, 4])
  assert.deepEqual(candidates.seats, [80, 100, 120])
  assert.deepEqual(candidates.staggers, [0, 5, 10, 15])
})
