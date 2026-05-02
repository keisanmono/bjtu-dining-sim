import assert from 'node:assert/strict'
import test from 'node:test'

import {
  LAYOUT_BOUNDS,
  LAYOUT_GRID_STEP,
  LAYOUT_VIEWBOX,
  TABLE_CAPACITY_OPTIONS,
  LAYOUT_MAX_EDITABLE_SEATS,
  adjustLayoutDoorCount,
  adjustLayoutWindowCount,
  buildTableCapacities,
  clampToBounds,
  createDefaultLayout,
  findItem,
  getItemFootprint,
  itemOverlapsLayout,
  rebuildLayoutTablesForSeats,
  setItemPosition,
  setTableCapacity,
  snapAndClampPoint,
  snapToGrid,
  tableTypeForCapacity,
  totalLayoutSeats
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
  assert.ok(result.x >= LAYOUT_BOUNDS.x + getItemFootprint('window', null).width / 2)
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

test('setItemPosition snaps and clamps the target item without touching others', () => {
  const layout = createDefaultLayout({ num_windows: 3, num_seats: 16 })
  const targetId = layout.windows[1].id
  const before = { ...layout.windows[1] }

  const next = setItemPosition(layout, 'window', targetId, 207, 158)

  const moved = findItem(next, 'window', targetId)
  assert.equal(moved.x, 210)
  assert.equal(moved.y, 160)
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

  assert.ok(moved.x >= LAYOUT_BOUNDS.x + fp.width / 2)
  assert.ok(moved.y >= LAYOUT_BOUNDS.y + fp.height / 2)
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
  assert.equal(grown.doors[0].x, 70)
  assert.equal(grown.doors[1].id, 'D2')
  assert.equal(grown.doors[2].id, 'D3')

  const trimmed = adjustLayoutDoorCount(grown, 1)
  assert.equal(trimmed.doors.length, 1)
  assert.equal(trimmed.doors[0].x, 70)
})

test('adjustLayoutDoorCount places new entrances without overlapping existing items', () => {
  const layout = createDefaultLayout({ num_windows: 4, num_seats: 120 })

  const grown = adjustLayoutDoorCount(layout, 4)

  for (const door of grown.doors) {
    assert.equal(itemOverlapsLayout(grown, 'door', door.id, door.x, door.y), false, `${door.id} overlaps another item`)
  }
})

test('adjustLayoutWindowCount appends or trims windows while preserving custom positions', () => {
  const initial = createDefaultLayout({ num_windows: 3, num_seats: 8 })
  const dragged = setItemPosition(initial, 'window', initial.windows[0].id, 200, 200)

  const grown = adjustLayoutWindowCount(dragged, 5)
  assert.equal(grown.windows.length, 5)
  assert.equal(findItem(grown, 'window', initial.windows[0].id).x, 200)

  const shrunk = adjustLayoutWindowCount(grown, 2)
  assert.equal(shrunk.windows.length, 2)
  assert.equal(findItem(shrunk, 'window', initial.windows[0].id).x, 200)
})

test('rebuildLayoutTablesForSeats produces capacities that match the requested seat count', () => {
  const layout = createDefaultLayout({ num_windows: 2, num_seats: 16 })
  const rebuilt = rebuildLayoutTablesForSeats(layout, 32)

  assert.equal(totalLayoutSeats(rebuilt), 32)
  assert.deepEqual(buildTableCapacities(32), rebuilt.tables.map((t) => t.capacity))
})

test('default layout avoids table overlap at the editable seat limit', () => {
  const layout = createDefaultLayout({ num_windows: 4, num_seats: LAYOUT_MAX_EDITABLE_SEATS })
  const boxes = layout.tables.map((table) => tableBox(table))

  assert.equal(totalLayoutSeats(layout), LAYOUT_MAX_EDITABLE_SEATS)
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      assert.equal(boxesOverlap(boxes[i], boxes[j]), false, `${layout.tables[i].id} overlaps ${layout.tables[j].id}`)
    }
  }
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
  assert.equal(payload.layout.doors[0].x, 310)
  assert.equal(payload.layout.doors[0].y, 550)
  // Windows and table positions reach the backend exactly as edited.
  assert.equal(payload.layout.windows[0].x, 190)
  assert.equal(payload.layout.windows[0].y, 90)
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

function tableBox(table) {
  const fp = getItemFootprint('table', table)
  return {
    left: table.x - fp.width / 2,
    right: table.x + fp.width / 2,
    top: table.y - fp.height / 2,
    bottom: table.y + fp.height / 2
  }
}

function boxesOverlap(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}
