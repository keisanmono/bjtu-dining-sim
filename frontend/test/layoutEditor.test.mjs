import assert from 'node:assert/strict'
import test from 'node:test'

import {
  LAYOUT_BOUNDS,
  LAYOUT_DEFAULT_FLOOR,
  LAYOUT_GRID_STEP,
  LAYOUT_SIZE_LIMITS,
  LAYOUT_VIEWBOX,
  LAYOUT_VIEWPORT_MARGIN,
  TABLE_CAPACITY_OPTIONS,
  LAYOUT_MAX_EDITABLE_SEATS,
  adjustLayoutDoorCount,
  adjustLayoutWindowCount,
  arrangeLayoutTables,
  buildTableCapacities,
  calculateLayoutSeatLimit,
  clampToBounds,
  clientPointToViewBoxPoint,
  createDefaultLayout,
  fitViewBoxForLayout,
  floorBoundsForLayout,
  findItem,
  getItemFootprint,
  getItemCollisionBoxes,
  itemBounds,
  itemOverlapsLayout,
  rebuildLayoutTablesForSeats,
  resizeLayoutFloor,
  resizeLayoutFloorFromHandle,
  setItemPosition,
  setTableCapacity,
  snapAndClampPoint,
  snapToGrid,
  tableTypeForCapacity,
  totalLayoutSeats,
  zoomViewBox
} from '../src/layoutEditor.js'
import { buildSimulationConfigPayload } from '../src/layout.js'

test('grid step snaps coordinates to multiples of 10', () => {
  assert.equal(snapToGrid(123), 120)
  assert.equal(snapToGrid(127), 130)
  assert.equal(snapToGrid(0), 0)
  assert.equal(LAYOUT_GRID_STEP, 10)
})

test('clampToBounds keeps centers inside the floor area accounting for footprint', () => {
  const fp = getItemFootprint('table', { capacity: 4 })
  const clamped = clampToBounds(0, 0, fp)

  assert.ok(clamped.x >= LAYOUT_BOUNDS.x + fp.width / 2)
  assert.ok(clamped.y >= LAYOUT_BOUNDS.y + fp.height / 2)

  const clampedHigh = clampToBounds(9999, 9999, fp)
  assert.ok(clampedHigh.x <= LAYOUT_BOUNDS.right - fp.width / 2)
  assert.ok(clampedHigh.y <= LAYOUT_BOUNDS.bottom - fp.height / 2)
})

test('snapAndClampPoint snaps and clamps in one shot', () => {
  const result = snapAndClampPoint(7, 5, 'window', null)

  assert.equal(result.x % LAYOUT_GRID_STEP, 0)
  assert.equal(result.y % LAYOUT_GRID_STEP, 0)
  assert.ok(result.x >= LAYOUT_BOUNDS.x + getItemFootprint('window', result).width / 2)
})

test('doors and windows snap to the nearest wall instead of floating inside the floor', () => {
  const topDoor = snapAndClampPoint(180, 25, 'door', { id: 'D1', wall_side: 'left' })
  const rightWindow = snapAndClampPoint(330, 315, 'window', { id: 'W1', wall_side: 'top' })

  assert.equal(topDoor.wall_side, 'top')
  assert.equal(topDoor.y, LAYOUT_BOUNDS.y + getItemFootprint('door', topDoor).height / 2)
  assert.equal(topDoor.x % LAYOUT_GRID_STEP, 0)

  assert.equal(rightWindow.wall_side, 'right')
  assert.equal(rightWindow.x, LAYOUT_BOUNDS.right - getItemFootprint('window', rightWindow).width / 2)
  assert.equal(rightWindow.y % LAYOUT_GRID_STEP, 0)
})

test('door and window footprints rotate based on the wall side', () => {
  const topDoor = getItemFootprint('door', { wall_side: 'top' })
  const leftDoor = getItemFootprint('door', { wall_side: 'left' })
  const topWindow = getItemFootprint('window', { wall_side: 'top' })
  const rightWindow = getItemFootprint('window', { wall_side: 'right' })

  assert.ok(topDoor.width > topDoor.height)
  assert.ok(leftDoor.height > leftDoor.width)
  assert.ok(topWindow.width > topWindow.height)
  assert.ok(rightWindow.height > rightWindow.width)
})

test('createDefaultLayout produces in-bounds, on-grid items for the given config', () => {
  const layout = createDefaultLayout({ num_windows: 4, num_seats: 120 })

  assert.equal(layout.doors.length, 1)
  assert.equal(layout.windows.length, 4)
  assert.equal(totalLayoutSeats(layout), 120)
  for (const item of layout.windows) {
    assert.equal(item.x % LAYOUT_GRID_STEP, 0)
    assert.equal(item.y % LAYOUT_GRID_STEP, 0)
    assert.ok(item.x >= LAYOUT_BOUNDS.x && item.x <= LAYOUT_BOUNDS.right)
    assert.ok(item.y >= LAYOUT_BOUNDS.y && item.y <= LAYOUT_BOUNDS.bottom)
  }
  for (const table of layout.tables) {
    assert.ok(TABLE_CAPACITY_OPTIONS.includes(table.capacity) || table.capacity <= 6)
    assert.equal(table.table_type, tableTypeForCapacity(table.capacity))
  }
})

test('seat counts are normalized to even table capacity totals', () => {
  assert.equal(buildTableCapacities(121).reduce((sum, value) => sum + value, 0), 120)

  const layout = createDefaultLayout({ num_windows: 4, num_seats: 121 })

  assert.equal(totalLayoutSeats(layout), 120)
  assert.equal(layout.tables.some((table) => table.capacity % 2 !== 0), false)
})

test('setItemPosition snaps and clamps the target item without touching others', () => {
  const layout = createDefaultLayout({ num_windows: 3, num_seats: 16 })
  const targetId = layout.windows[1].id
  const before = { ...layout.windows[1] }

  const next = setItemPosition(layout, 'window', targetId, 207, 158)

  const moved = findItem(next, 'window', targetId)
  assert.equal(moved.x, 320)
  assert.equal(moved.y, 160)
  assert.equal(moved.wall_side, 'right')
  // Original layout reference is untouched (immutable update style).
  assert.equal(findItem(layout, 'window', targetId).x, before.x)
  assert.equal(next.windows.length, layout.windows.length)
  assert.equal(next.doors[0].x, layout.doors[0].x)
})

test('setItemPosition forces extreme drags back into the floor bounds', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 8 })

  const next = setItemPosition(layout, 'window', layout.windows[0].id, -500, -500)
  const moved = findItem(next, 'window', layout.windows[0].id)
  const fp = getItemFootprint('window', moved)
  const bounds = floorBoundsForLayout(next)

  assert.equal(moved.x % LAYOUT_GRID_STEP, 0)
  assert.equal(moved.y % LAYOUT_GRID_STEP, 0)
  assert.ok(moved.x >= bounds.x - fp.width / 2)
  assert.ok(moved.y >= bounds.y - fp.height / 2)
})

test('setItemPosition rejects moves that overlap existing layout items', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 8 })
  const table = layout.tables[0]
  const blockingWindow = layout.windows[0]

  const next = setItemPosition(layout, 'table', table.id, blockingWindow.x, blockingWindow.y)

  const moved = findItem(next, 'table', table.id)
  assert.equal(moved.x, table.x)
  assert.equal(moved.y, table.y)
  assert.equal(itemOverlapsLayout(layout, 'table', table.id, blockingWindow.x, blockingWindow.y), true)
})

test('setItemPosition can allow temporary overlaps during drag', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 8 })
  const table = layout.tables[0]
  const blockingWindow = layout.windows[0]

  const next = setItemPosition(layout, 'table', table.id, blockingWindow.x, blockingWindow.y, { allowOverlap: true })

  const moved = findItem(next, 'table', table.id)
  assert.equal(moved.x, blockingWindow.x)
  assert.equal(moved.y, blockingWindow.y)
  assert.equal(itemOverlapsLayout(next, 'table', table.id, moved.x, moved.y), true)
})

test('table collisions use the visible table and chair shapes instead of one footprint rectangle', () => {
  const first = { id: 'T1', capacity: 4, table_type: 'four_seat', x: 100, y: 100 }
  const second = { id: 'T2', capacity: 4, table_type: 'four_seat', x: 140, y: 130 }
  const layout = { doors: [], windows: [], tables: [first, second] }

  assert.equal(getItemCollisionBoxes('table', first).length, 5)
  assert.equal(boxesOverlap(itemBounds('table', first), itemBounds('table', second)), true)
  assert.equal(itemOverlapsLayout(layout, 'table', first.id, first.x, first.y, first), false)
})

test('table collisions still trigger when visible table parts intersect', () => {
  const first = { id: 'T1', capacity: 4, table_type: 'four_seat', x: 100, y: 100 }
  const second = { id: 'T2', capacity: 4, table_type: 'four_seat', x: 120, y: 100 }
  const layout = { doors: [], windows: [], tables: [first, second] }

  assert.equal(itemOverlapsLayout(layout, 'table', first.id, first.x, first.y, first), true)
})

test('setTableCapacity rounds to a supported size and updates table_type', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 16 })
  const tableId = layout.tables[0].id

  const updated = setTableCapacity(layout, tableId, 6)
  const found = findItem(updated, 'table', tableId)

  assert.equal(found.capacity, 6)
  assert.equal(found.table_type, 'six_seat')
  assert.equal(totalLayoutSeats(updated), totalLayoutSeats(layout) + (6 - layout.tables[0].capacity))
})

test('setTableCapacity keeps a larger table inside the editable bounds', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 8 })
  const tableId = layout.tables[0].id
  const nearCorner = setItemPosition(layout, 'table', tableId, 9999, 9999)

  const updated = setTableCapacity(nearCorner, tableId, 6)
  const found = findItem(updated, 'table', tableId)
  const fp = getItemFootprint('table', found)

  assert.ok(found.x <= LAYOUT_BOUNDS.right - fp.width / 2)
  assert.ok(found.y <= LAYOUT_BOUNDS.bottom - fp.height / 2)
  assert.equal(found.x % LAYOUT_GRID_STEP, 0)
  assert.equal(found.y % LAYOUT_GRID_STEP, 0)
})

test('adjustLayoutDoorCount appends and trims entrances while preserving existing positions', () => {
  const initial = createDefaultLayout({ num_windows: 2, num_seats: 8 })
  const moved = setItemPosition(initial, 'door', initial.doors[0].id, 70, 180)

  const grown = adjustLayoutDoorCount(moved, 3)

  assert.equal(grown.doors.length, 3)
  assert.equal(grown.doors[0].x, 40)
  assert.equal(grown.doors[0].wall_side, 'left')
  assert.equal(grown.doors[1].id, 'D2')
  assert.equal(grown.doors[2].id, 'D3')

  const trimmed = adjustLayoutDoorCount(grown, 1)
  assert.equal(trimmed.doors.length, 1)
  assert.equal(trimmed.doors[0].x, 40)
})

test('adjustLayoutDoorCount places new entrances without overlapping existing items', () => {
  const layout = createDefaultLayout({ num_windows: 4, num_seats: 120 })

  const grown = adjustLayoutDoorCount(layout, 4)

  for (const door of grown.doors) {
    assert.equal(itemOverlapsLayout(grown, 'door', door.id, door.x, door.y), false, `${door.id} overlaps another item`)
  }
})

test('adjustLayoutDoorCount skips wall slots already occupied by windows', () => {
  const layout = createDefaultLayout({ num_windows: 5, num_seats: 120 })

  const grown = adjustLayoutDoorCount(layout, 3)

  for (const door of grown.doors) {
    assert.equal(itemOverlapsLayout(grown, 'door', door.id, door.x, door.y), false, `${door.id} overlaps another item`)
  }
})

test('adjustLayoutWindowCount appends or trims windows while preserving custom positions', () => {
  const initial = createDefaultLayout({ num_windows: 3, num_seats: 8 })
  const dragged = setItemPosition(initial, 'window', initial.windows[0].id, 200, 200)

  const grown = adjustLayoutWindowCount(dragged, 5)
  assert.equal(grown.windows.length, 5)
  assert.equal(findItem(grown, 'window', initial.windows[0].id).x, 320)

  const shrunk = adjustLayoutWindowCount(grown, 2)
  assert.equal(shrunk.windows.length, 2)
  assert.equal(findItem(shrunk, 'window', initial.windows[0].id).x, 320)
})

test('rebuildLayoutTablesForSeats produces capacities that match the requested seat count', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 16 })
  const rebuilt = rebuildLayoutTablesForSeats(layout, 32)

  assert.equal(totalLayoutSeats(rebuilt), 32)
  assert.deepEqual(buildTableCapacities(32), rebuilt.tables.map((t) => t.capacity))
})

test('default layout avoids table overlap at the editable seat limit', () => {
  const seedLayout = createDefaultLayout({ num_windows: 4, num_seats: 120 })
  const seatLimit = calculateLayoutSeatLimit(seedLayout)
  const layout = createDefaultLayout({ num_windows: 4, num_seats: seatLimit })

  assert.equal(totalLayoutSeats(layout), seatLimit)
  assertNoLayoutOverlaps(layout)
})

test('default layout avoids collisions between doors windows and tables', () => {
  const layout = createDefaultLayout({ num_windows: 30, num_seats: LAYOUT_MAX_EDITABLE_SEATS })

  assertNoLayoutOverlaps(layout)
})

test('rebuilt tables avoid existing doors and windows', () => {
  const layout = createDefaultLayout({ num_windows: 30, num_seats: 16 })

  const rebuilt = rebuildLayoutTablesForSeats(layout, LAYOUT_MAX_EDITABLE_SEATS)

  assertNoLayoutOverlaps(rebuilt)
})

test('layout floor can be resized and updates the active bounds', () => {
  const layout = createDefaultLayout({ num_windows: 4, num_seats: 120 })

  const resized = resizeLayoutFloor(layout, { width: 240, height: 380 })
  const bounds = floorBoundsForLayout(resized)

  assert.equal(resized.floor.width, 240)
  assert.equal(resized.floor.height, 380)
  assert.equal(bounds.x, (LAYOUT_VIEWBOX.width - 240) / 2)
  assert.equal(bounds.y, (LAYOUT_VIEWBOX.height - 380) / 2)
})

test('resize handles refuse to shrink walls into existing tables', () => {
  const layout = createDefaultLayout({ num_windows: 4, num_seats: 120 })
  const bounds = floorBoundsForLayout(layout)

  const blocked = resizeLayoutFloorFromHandle(layout, 'corner', bounds.right - 40, bounds.bottom - 40)

  assert.equal(blocked.floor.width, layout.floor.width)
  assert.equal(blocked.floor.height, layout.floor.height)
  assert.equal(blocked.tables.length, layout.tables.length)
  assert.equal(totalLayoutSeats(blocked), totalLayoutSeats(layout))
})

test('floor resize handles can grow the cafeteria beyond the default viewport frame', () => {
  const layout = createDefaultLayout({ num_windows: 4, num_seats: 120 })
  const before = floorBoundsForLayout(layout)

  const resized = resizeLayoutFloorFromHandle(layout, 'corner', before.right + 188, before.bottom + 128)
  const after = floorBoundsForLayout(resized)

  assert.ok(resized.floor.width > LAYOUT_DEFAULT_FLOOR.width)
  assert.ok(resized.floor.height > LAYOUT_DEFAULT_FLOOR.height)
  assert.ok(resized.floor.width > LAYOUT_VIEWBOX.width)
  assert.equal(after.x, before.x)
  assert.equal(after.y, before.y)
  assert.equal(resized.floor.width % LAYOUT_SIZE_LIMITS.step, 0)
  assert.equal(resized.floor.height % LAYOUT_SIZE_LIMITS.step, 0)
})

test('clientPointToViewBoxPoint accounts for centered SVG letterboxing', () => {
  const rect = { left: 100, top: 50, width: 1000, height: 500 }
  const viewBox = { x: 0, y: 0, width: 400, height: 400 }

  const center = clientPointToViewBoxPoint(600, 300, rect, viewBox)
  const moved = clientPointToViewBoxPoint(700, 300, rect, viewBox)

  assert.equal(center.x, 200)
  assert.equal(center.y, 200)
  assert.equal(moved.x - center.x, 80)
})

test('compact table auto-arrangement packs seats toward the upper-left', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 32 })
  const compact = arrangeLayoutTables(layout, 'compact')
  const bounds = floorBoundsForLayout(compact)
  const minX = Math.min(...compact.tables.map((table) => table.x))
  const minY = Math.min(...compact.tables.map((table) => table.y))

  assert.equal(totalLayoutSeats(compact), totalLayoutSeats(layout))
  assertNoLayoutOverlaps(compact)
  assert.ok(minX < bounds.x + 110)
  assert.ok(minY < bounds.y + 110)
})

test('spread table auto-arrangement uses more of the existing floor than compact packing', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 32 })
  const compact = arrangeLayoutTables(layout, 'compact')
  const spread = arrangeLayoutTables(layout, 'spread')
  const compactWidth = Math.max(...compact.tables.map((table) => table.x)) - Math.min(...compact.tables.map((table) => table.x))
  const spreadWidth = Math.max(...spread.tables.map((table) => table.x)) - Math.min(...spread.tables.map((table) => table.x))
  const compactHeight = Math.max(...compact.tables.map((table) => table.y)) - Math.min(...compact.tables.map((table) => table.y))
  const spreadHeight = Math.max(...spread.tables.map((table) => table.y)) - Math.min(...spread.tables.map((table) => table.y))

  assert.equal(totalLayoutSeats(spread), totalLayoutSeats(layout))
  assertNoLayoutOverlaps(spread)
  assert.ok(spreadWidth >= compactWidth)
  assert.ok(spreadHeight > compactHeight)
})

test('fit viewBox includes an oversized cafeteria without relying on a fixed border', () => {
  const layout = resizeLayoutFloorFromHandle(
    createDefaultLayout({ num_windows: 2, num_seats: 32 }),
    'corner',
    LAYOUT_VIEWBOX.width + 300,
    LAYOUT_VIEWBOX.height + 200
  )
  const bounds = floorBoundsForLayout(layout)
  const viewBox = fitViewBoxForLayout(layout)

  assert.ok(viewBox.x <= bounds.x - LAYOUT_VIEWPORT_MARGIN)
  assert.ok(viewBox.y <= bounds.y - LAYOUT_VIEWPORT_MARGIN)
  assert.ok(viewBox.x + viewBox.width >= bounds.right + LAYOUT_VIEWPORT_MARGIN)
  assert.ok(viewBox.y + viewBox.height >= bounds.bottom + LAYOUT_VIEWPORT_MARGIN)
})

test('zoomViewBox scales around the requested focal point', () => {
  const initial = { x: 0, y: 0, width: 400, height: 300 }
  const zoomed = zoomViewBox(initial, 0.5, { x: 100, y: 75 })

  assert.equal(zoomed.width, 200)
  assert.equal(zoomed.height, 150)
  assert.equal(zoomed.x, 50)
  assert.equal(zoomed.y, 37.5)
})

test('seat limit is computed from floor size and wall openings', () => {
  const roomy = createDefaultLayout({ num_windows: 1, num_seats: 120 })
  const compact = resizeLayoutFloor(roomy, {
    width: LAYOUT_SIZE_LIMITS.width.min,
    height: LAYOUT_SIZE_LIMITS.height.min
  })
  const compactWithManyOpenings = resizeLayoutFloor(createDefaultLayout({ num_windows: 30, num_seats: 120 }), {
    width: LAYOUT_SIZE_LIMITS.width.min,
    height: LAYOUT_SIZE_LIMITS.height.min
  })

  assert.ok(calculateLayoutSeatLimit(roomy) > calculateLayoutSeatLimit(compact))
  assert.ok(calculateLayoutSeatLimit(compact) > calculateLayoutSeatLimit(compactWithManyOpenings))
  assert.equal(calculateLayoutSeatLimit(roomy) % 2, 0)
})

test('rebuilt table count is clamped to the computed floor capacity', () => {
  const layout = resizeLayoutFloor(createDefaultLayout({ num_windows: 30, num_seats: 120 }), {
    width: LAYOUT_SIZE_LIMITS.width.min,
    height: LAYOUT_SIZE_LIMITS.height.min
  })
  const limit = calculateLayoutSeatLimit(layout)

  const rebuilt = rebuildLayoutTablesForSeats(layout, limit + 101)

  assert.equal(totalLayoutSeats(rebuilt), limit)
  assertNoLayoutOverlaps(rebuilt)
})

test('drag-edited layout flows into the simulation payload coordinates', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 8 })
  const draggedDoor = setItemPosition(layout, 'door', layout.doors[0].id, 307, 548)
  const draggedWindow = setItemPosition(draggedDoor, 'window', layout.windows[0].id, 192, 88)
  const draggedTable = setItemPosition(draggedWindow, 'table', layout.tables[0].id, 264, 304)
  const finalLayout = setTableCapacity(draggedTable, draggedTable.tables[1].id, 6)

  const payload = buildSimulationConfigPayload(
    {
      num_windows: 2,
      num_seats: totalLayoutSeats(finalLayout),
      arrival_rate: 8,
      service_time_mean: 3,
      dining_time_mean: 20,
      duration_min: 60,
      seed: 20,
      peak_start_min: 15,
      peak_end_min: 40,
      peak_multiplier: 1.4,
      stagger_minutes: 0,
      seat_columns: 12
    },
    finalLayout
  )

  // Door coordinates survive snapping AND are sent to the backend.
  assert.equal(payload.layout.doors[0].x, 320)
  assert.equal(payload.layout.doors[0].y, 550)
  // Windows and table positions reach the backend exactly as edited.
  assert.equal(payload.layout.windows[0].x, 190)
  assert.equal(payload.layout.windows[0].y, 40)
  assert.equal(payload.layout.windows[0].wall_side, 'top')
  assert.equal(payload.layout.tables[0].x, 260)
  assert.equal(payload.layout.tables[0].y, 300)
  // Capacity edits are propagated into the payload too.
  const reconfiguredTable = payload.layout.tables[1]
  assert.equal(reconfiguredTable.capacity, 6)
  assert.equal(reconfiguredTable.table_type, 'six_seat')
})

test('LAYOUT_VIEWBOX is the agreed 360x640 frame', () => {
  assert.equal(LAYOUT_VIEWBOX.width, 360)
  assert.equal(LAYOUT_VIEWBOX.height, 640)
})

function boxesOverlap(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}

function assertNoLayoutOverlaps(layout) {
  const items = [
    ...layout.doors.map((item) => ({ kind: 'door', item })),
    ...layout.windows.map((item) => ({ kind: 'window', item })),
    ...layout.tables.map((item) => ({ kind: 'table', item }))
  ]
  for (const { kind, item } of items) {
    assert.equal(
      itemOverlapsLayout(layout, kind, item.id, item.x, item.y, item),
      false,
      `${kind} ${item.id} overlaps another layout item`
    )
  }
}
