import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildLayoutFromConfig,
  buildSimulationConfigPayload,
  defaultPartySizeDistribution
} from '../src/layout.js'

test('layout payload keeps resource counts and mixed table types in sync', () => {
  const layout = buildLayoutFromConfig({ num_windows: 5, num_seats: 16 })

  assert.equal(layout.doors.length, 1)
  assert.equal(layout.windows.length, 5)
  assert.equal(layout.tables.reduce((sum, table) => sum + table.capacity, 0), 16)
  assert.deepEqual(layout.tables.map((table) => table.capacity), [2, 4, 4, 6])
  assert.deepEqual([...new Set(layout.tables.map((table) => table.table_type))], ['two_seat', 'four_seat', 'six_seat'])
})

test('simulation config payload sends layout and party distribution to backend', () => {
  const payload = buildSimulationConfigPayload({
    num_windows: 4,
    num_seats: 20,
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
  })

  assert.equal(payload.layout.windows.length, 4)
  assert.equal(payload.layout.tables.reduce((sum, table) => sum + table.capacity, 0), 20)
  assert.deepEqual(payload.party_size_distribution, defaultPartySizeDistribution)
})

test('simulation config payload normalizes odd seat counts to the editable layout total', () => {
  const payload = buildSimulationConfigPayload({
    num_windows: 4,
    num_seats: 121,
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
  })

  assert.equal(payload.num_seats, 120)
  assert.equal(payload.layout.tables.reduce((sum, table) => sum + table.capacity, 0), 120)
})

test('simulation config payload includes campus demand when enabled', () => {
  const payload = buildSimulationConfigPayload({
    num_windows: 4,
    num_seats: 20,
    arrival_rate: 8,
    service_time_mean: 3,
    dining_time_mean: 20,
    duration_min: 60,
    seed: 20,
    peak_start_min: 15,
    peak_end_min: 40,
    peak_multiplier: 1.4,
    stagger_minutes: 0,
    seat_columns: 12,
    campus_demand: {
      enabled: true,
      cafeteria_id: 'xuesi',
      source_mode: 'manual',
      buildings: [
        {
          building_id: 'no9',
          dismissal_minute: 0,
          release_ratio: 1,
          floors: [{ floor: 1, count: 20 }]
        }
      ]
    }
  })

  assert.equal(payload.campus_demand.enabled, true)
  assert.equal(payload.campus_demand.cafeteria_id, 'xuesi')
  assert.equal(payload.campus_demand.buildings[0].floors[0].count, 20)
})
