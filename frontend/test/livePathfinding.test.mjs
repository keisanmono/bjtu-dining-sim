// 文件说明：前端源码文件。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildObstacleBoxes,
  buildWalkableRoute,
  createPathPlanner,
  pointInsideAnyBox,
  samplePathAtProgress
} from '../src/livePathfinding.js'

const layoutWithBlockingTable = {
  floor: { x: 0, y: 0, width: 240, height: 220 },
  doors: [{ id: 'D1', x: 0, y: 110, wall_side: 'left' }],
  windows: [{ id: 'W1', x: 220, y: 20, wall_side: 'top' }],
  tables: [{ id: 'T1', x: 120, y: 110, capacity: 4, table_type: 'four_seat', rotation: 0 }]
}

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildObstacleBoxes expands table and chair collision boxes', () => {
  const boxes = buildObstacleBoxes(layoutWithBlockingTable)

  assert.ok(boxes.length > 1)
  assert.equal(pointInsideAnyBox({ x: 120, y: 110 }, boxes), true)
  assert.equal(pointInsideAnyBox({ x: 36, y: 110 }, boxes), false)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildWalkableRoute routes around table obstacles instead of crossing them', () => {
  const start = { x: 36, y: 110 }
  const end = { x: 204, y: 110 }
  const boxes = buildObstacleBoxes(layoutWithBlockingTable)
  const route = buildWalkableRoute({ layout: layoutWithBlockingTable, start, end })

  assert.ok(route.length > 2, `expected routed polyline, got ${JSON.stringify(route)}`)
  assert.deepEqual(route[0], start)
  assert.deepEqual(route.at(-1), end)
  assert.equal(route.some((point) => Math.abs(point.y - 110) > 5), true)
  assert.equal(route.some((point) => pointInsideAnyBox(point, boxes)), false)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('samplePathAtProgress walks along the routed polyline', () => {
  const start = { x: 36, y: 110 }
  const end = { x: 204, y: 110 }
  const route = buildWalkableRoute({ layout: layoutWithBlockingTable, start, end })

  const beginning = samplePathAtProgress(route, 0)
  const middle = samplePathAtProgress(route, 0.5)
  const finish = samplePathAtProgress(route, 1)

  assert.deepEqual(beginning, start)
  assert.deepEqual(finish, end)
  assert.notEqual(middle.y, 110)
  assert.notEqual(middle.x, 120)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('createPathPlanner reuses cached routes for repeated endpoints', () => {
  const planner = createPathPlanner(layoutWithBlockingTable)
  const start = { x: 36, y: 110 }
  const end = { x: 204, y: 110 }

  const first = buildWalkableRoute({ planner, start, end })
  const second = buildWalkableRoute({ planner, start, end })

  assert.equal(first, second)
  assert.equal(planner.stats.cacheMisses, 1)
  assert.equal(planner.stats.cacheHits, 1)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('buildWalkableRoute skips A star when the straight segment is unobstructed', () => {
  const planner = createPathPlanner(layoutWithBlockingTable)
  const start = { x: 36, y: 180 }
  const end = { x: 204, y: 180 }

  const route = buildWalkableRoute({ planner, start, end })

  assert.deepEqual(route, [start, end])
  assert.equal(planner.stats.astarRuns, 0)
})
