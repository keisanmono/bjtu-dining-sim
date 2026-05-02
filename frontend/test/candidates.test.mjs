import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildCandidatesFromSettings,
  buildIntegerRange,
  createDefaultCandidateSettings
} from '../src/candidates.js'
import { LAYOUT_MAX_EDITABLE_SEATS } from '../src/layoutEditor.js'

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
