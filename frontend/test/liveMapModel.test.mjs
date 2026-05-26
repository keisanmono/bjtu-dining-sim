// 文件说明：前端源码文件。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildLivePartyTargets,
  buildLivePartyTransitions,
  QUEUE_VISIBLE_LIMIT,
  buildQueueRows,
  interpolateLivePartyMarkers,
  backendTimelinePlaybackMs,
  buildBackendWalkingMarkers,
  transitionDurationForSnapshotGap
} from '../src/liveMapModel.js'

const topWindow = { id: 'W1', x: 120, y: 24, wall_side: 'top' }
const baseLayout = {
  doors: [{ id: 'D1', x: 24, y: 120, wall_side: 'left' }],
  windows: [
    { id: 'W1', x: 120, y: 24, wall_side: 'top' },
    { id: 'W2', x: 160, y: 24, wall_side: 'top' }
  ],
  tables: [{ id: 'T1', x: 220, y: 180, capacity: 4, table_type: 'four_seat' }]
}
const blockingLayout = {
  floor: { x: 0, y: 0, width: 240, height: 220 },
  doors: [{ id: 'D1', x: 0, y: 110, wall_side: 'left' }],
  windows: [{ id: 'W1', x: 220, y: 20, wall_side: 'top' }],
  tables: [{ id: 'T1', x: 120, y: 110, capacity: 4, table_type: 'four_seat', rotation: 0 }]
}

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
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

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
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

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
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

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildLivePartyTargets keeps split party services anchored to their actual windows', () => {
  const targets = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [
        { party_id: 7, size: 2, member_count: 1, window_index: 0, door_index: 0 },
        { party_id: 7, size: 2, member_count: 1, window_index: 1, door_index: 0 }
      ],
      seated_parties: []
    }
  })

  assert.equal(targets.length, 2)
  assert.deepEqual(targets.map((target) => target.key), ['service-7-0', 'service-7-1'])
  assert.deepEqual(targets.map((target) => target.role), ['service', 'service'])
  assert.equal(targets[0].x, baseLayout.windows[0].x)
  assert.equal(targets[1].x, baseLayout.windows[1].x)
  assert.ok(targets.every((target) => target.y > baseLayout.windows[0].y))
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildLivePartyTransitions moves newly seated parties from a same-party service window', () => {
  const [serviceTarget] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [{ party_id: 19, size: 1, member_count: 1, window_index: 1, door_index: 0 }],
      seated_parties: []
    }
  })
  const [seatedTarget] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [],
      seated_parties: [{ party_id: 19, size: 1, member_count: 1, table_index: 0, table_id: 'T1', door_index: 0 }]
    }
  })

  const transitions = buildLivePartyTransitions({
    previous: [serviceTarget],
    next: [seatedTarget],
    layout: baseLayout
  })
  const seatedTransition = transitions.find((transition) => transition.role === 'seated')

  assert.equal(transitions.some((transition) => transition.role === 'service' && transition.leaving), false)
  assert.equal(seatedTransition.from.x, serviceTarget.x)
  assert.equal(seatedTransition.from.y, serviceTarget.y)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildLivePartyTargets keeps waiting parties as hidden motion anchors near their window', () => {
  const targets = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [],
      waiting_parties: [{ party_id: 17, size: 1, member_count: 1, window_index: 1, wait_position: 0, door_index: 0 }],
      seated_parties: []
    }
  })

  assert.equal(targets.length, 1)
  assert.equal(targets[0].key, 'party-17')
  assert.equal(targets[0].role, 'waiting')
  assert.equal(targets[0].x, baseLayout.windows[1].x)
  assert.ok(targets[0].y > baseLayout.windows[1].y)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildLivePartyTransitions starts seating movement from the waiting anchor when available', () => {
  const [waitingTarget] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      waiting_parties: [{ party_id: 18, size: 1, member_count: 1, window_index: 1, wait_position: 0, door_index: 0 }],
      seated_parties: []
    }
  })
  const [seatedTarget] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [],
      waiting_parties: [],
      seated_parties: [{ party_id: 18, size: 1, member_count: 1, table_index: 0, table_id: 'T1', door_index: 0 }]
    }
  })

  const [transition] = buildLivePartyTransitions({
    previous: [waitingTarget],
    next: [seatedTarget],
    layout: baseLayout
  })

  assert.equal(transition.role, 'seated')
  assert.equal(transition.from.x, waitingTarget.x)
  assert.equal(transition.from.y, waitingTarget.y)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('transitionDurationForSnapshotGap keeps animation inside the observed snapshot cadence', () => {
  assert.equal(transitionDurationForSnapshotGap(undefined), 320)
  assert.equal(transitionDurationForSnapshotGap(1000), 320)
  assert.equal(transitionDurationForSnapshotGap(220), 180)
  assert.equal(transitionDurationForSnapshotGap(80), 120)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('interpolateLivePartyMarkers moves the same party between minute snapshots', () => {
  const [serviceTarget] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [{ party_id: 7, size: 2, member_count: 1, window_index: 0, door_index: 0 }],
      seated_parties: []
    }
  })
  const [seatedTarget] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [],
      seated_parties: [{ party_id: 7, size: 2, member_count: 2, table_index: 0, table_id: 'T1', door_index: 0 }]
    }
  })

  const [halfway] = interpolateLivePartyMarkers({
    previous: [serviceTarget],
    next: [seatedTarget],
    progress: 0.5,
    layout: baseLayout
  })

  assert.equal(halfway.key, 'party-7')
  assert.equal(halfway.role, 'seated')
  assert.equal(halfway.opacity, 1)
  assert.ok(halfway.x > Math.min(serviceTarget.x, seatedTarget.x))
  assert.ok(halfway.x < Math.max(serviceTarget.x, seatedTarget.x))
  assert.ok(halfway.y > Math.min(serviceTarget.y, seatedTarget.y))
  assert.ok(halfway.y < Math.max(serviceTarget.y, seatedTarget.y))
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildBackendWalkingMarkers samples backend timeline frames instead of inventing targets', () => {
  const timeline = {
    playback_ms: 600,
    events: [
      {
        party_id: 41,
        size: 2,
        member_count: 2,
        table_index: 0,
        table_id: 'T1',
        start_time_sec: 300,
        arrive_time_sec: 306,
        playback_start_ms: 0,
        playback_duration_ms: 600,
        frames: [
          { time_sec: 300, x: 120, y: 42, progress: 0 },
          { time_sec: 303, x: 150, y: 90, progress: 0.5 },
          { time_sec: 306, x: 180, y: 138, progress: 1 }
        ]
      }
    ]
  }

  const [marker] = buildBackendWalkingMarkers({ timeline, elapsedMs: 300 })

  assert.equal(marker.key, 'walking-41-300')
  assert.equal(marker.role, 'walking')
  assert.equal(marker.member_count, 2)
  assert.equal(marker.x, 150)
  assert.equal(marker.y, 90)
  assert.equal(marker.progress, 0.5)
  assert.equal(backendTimelinePlaybackMs(timeline), 600)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('interpolateLivePartyMarkers fades new parties in from their door', () => {
  const [target] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [{ party_id: 11, size: 1, member_count: 1, window_index: 0, door_index: 0 }],
      seated_parties: []
    }
  })

  const [start] = interpolateLivePartyMarkers({
    previous: [],
    next: [target],
    progress: 0,
    layout: baseLayout
  })
  const [end] = interpolateLivePartyMarkers({
    previous: [],
    next: [target],
    progress: 1,
    layout: baseLayout
  })

  assert.equal(start.key, target.key)
  assert.equal(start.opacity, 0)
  assert.notEqual(start.x, target.x)
  assert.notEqual(start.y, target.y)
  assert.equal(end.x, target.x)
  assert.equal(end.y, target.y)
  assert.equal(end.opacity, 1)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('interpolateLivePartyMarkers fades removed parties back toward their door', () => {
  const [target] = buildLivePartyTargets({
    layout: baseLayout,
    snapshot: {
      window_services: [],
      seated_parties: [{ party_id: 13, size: 1, member_count: 1, table_index: 0, table_id: 'T1', door_index: 0 }]
    }
  })

  const [end] = interpolateLivePartyMarkers({
    previous: [target],
    next: [],
    progress: 1,
    layout: baseLayout
  })

  assert.equal(end.key, target.key)
  assert.equal(end.opacity, 0)
  assert.notEqual(end.x, target.x)
  assert.notEqual(end.y, target.y)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('interpolateLivePartyMarkers follows walkable routes around table obstacles', () => {
  const [marker] = interpolateLivePartyMarkers({
    previous: [{ key: 'party-21', party_id: 21, role: 'service', member_count: 1, x: 36, y: 110, door_index: 0 }],
    next: [{ key: 'party-21', party_id: 21, role: 'seated', member_count: 1, x: 204, y: 110, door_index: 0 }],
    progress: 0.5,
    layout: blockingLayout
  })

  assert.equal(marker.key, 'party-21')
  assert.ok(marker.path.length > 2, `expected routed path, got ${JSON.stringify(marker.path)}`)
  assert.notEqual(marker.y, 110)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildLivePartyTransitions skips stable seated parties after they settle', () => {
  const seated = {
    key: 'party-31',
    party_id: 31,
    role: 'seated',
    member_count: 2,
    x: 220,
    y: 180,
    door_index: 0
  }

  const transitions = buildLivePartyTransitions({
    previous: [seated],
    next: [seated],
    layout: baseLayout
  })

  assert.equal(transitions.length, 0)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildLivePartyTransitions keeps stable service markers visible', () => {
  const service = {
    key: 'party-32',
    party_id: 32,
    role: 'service',
    member_count: 1,
    x: 120,
    y: 40,
    door_index: 0
  }

  const transitions = buildLivePartyTransitions({
    previous: [service],
    next: [service],
    layout: baseLayout
  })

  assert.equal(transitions.length, 1)
  assert.equal(transitions[0].role, 'service')
})
