import assert from 'node:assert/strict'
import test from 'node:test'

import {
  QUEUE_VISIBLE_LIMIT,
  buildQueueRows
} from '../src/liveMapModel.js'

const topWindow = { id: 'W1', x: 120, y: 24, wall_side: 'top' }

test('buildQueueRows caps visible queue parties and aggregates hidden people', () => {
  const queueGroups = Array.from({ length: 50 }, (_item, index) => ({
    party_id: index + 1,
    size: 1,
    member_count: 1,
    window_index: 0,
    queue_position: index
  }))

  const [row] = buildQueueRows({
    queueGroups,
    queueLengths: [50],
    windows: [topWindow]
  })

  assert.equal(row.capsules.length, QUEUE_VISIBLE_LIMIT)
  assert.equal(row.overflow.hiddenPeople, 40)
  assert.equal(row.overflow.hiddenGroups, 40)
})

test('buildQueueRows stops reading queue groups after the visible window quota is filled', () => {
  const queueGroups = Array.from({ length: 50 }, (_item, index) => ({
    party_id: index + 1,
    size: 1,
    member_count: 1,
    window_index: 0,
    queue_position: index
  }))
  Object.defineProperty(queueGroups, QUEUE_VISIBLE_LIMIT, {
    get() {
      throw new Error('queue group beyond visible quota was read')
    }
  })

  const [row] = buildQueueRows({
    queueGroups,
    queueLengths: [50],
    windows: [topWindow]
  })

  assert.equal(row.capsules.length, QUEUE_VISIBLE_LIMIT)
  assert.equal(row.overflow.hiddenPeople, 40)
})

test('buildQueueRows scales the overflow tail with hidden queue size', () => {
  const groups = Array.from({ length: QUEUE_VISIBLE_LIMIT }, (_item, index) => ({
    party_id: index + 1,
    size: 1,
    member_count: 1,
    window_index: 0,
    queue_position: index
  }))

  const [shortTail] = buildQueueRows({
    queueGroups: groups,
    queueLengths: [12],
    windows: [topWindow]
  })
  const [longTail] = buildQueueRows({
    queueGroups: groups,
    queueLengths: [80],
    windows: [topWindow]
  })

  assert.ok(shortTail.overflow.width < longTail.overflow.width)
  assert.equal(shortTail.overflow.hiddenPeople, 2)
  assert.equal(longTail.overflow.hiddenPeople, 70)
})
