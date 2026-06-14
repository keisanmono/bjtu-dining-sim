// 文件说明：前端仿真请求体测试，验证布局、座位和校园到达字段会正确提交。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildLayoutFromConfig,
  buildSimulationConfigPayload,
  defaultPartySizeDistribution
} from '../src/layout.js'

// 验证默认布局会让窗口数、总座位数和混合桌型保持一致。
test('layout payload keeps resource counts and mixed table types in sync', () => {
  const layout = buildLayoutFromConfig({ num_windows: 5, num_seats: 16 })

  assert.equal(layout.doors.length, 1)
  assert.equal(layout.windows.length, 5)
  assert.equal(layout.tables.reduce((sum, table) => sum + table.capacity, 0), 16)
  assert.deepEqual(layout.tables.map((table) => table.capacity), [2, 4, 4, 6])
  assert.deepEqual([...new Set(layout.tables.map((table) => table.table_type))], ['two_seat', 'four_seat', 'six_seat'])
})

// 验证高容量默认布局会给窗口前方保留室内排队和通行走廊。
test('large default layout reserves an indoor service corridor before tables', () => {
  const layout = buildLayoutFromConfig({ num_windows: 4, num_seats: 120 })
  const firstTableY = Math.min(...layout.tables.map((table) => table.y))

  assert.equal(layout.tables.reduce((sum, table) => sum + table.capacity, 0), 120)
  assert.equal(layout.floor.height >= 720, true)
  assert.equal(firstTableY - layout.floor.y >= 150, true)
})

// 验证仿真请求体会携带布局和与餐桌容量匹配的结伴人数分布。
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

// 验证传入的可编辑布局会保留 floor 尺寸，避免后端 advanced 网格退回默认小平面。
test('simulation config payload preserves editable floor bounds', () => {
  const layout = buildLayoutFromConfig({ num_windows: 3, num_seats: 80, floor_width: 720, floor_height: 860 })
  const payload = buildSimulationConfigPayload({
    num_windows: 3,
    num_seats: 80,
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
  }, layout)

  assert.equal(payload.layout.floor.width, layout.floor.width)
  assert.equal(payload.layout.floor.height, layout.floor.height)
  assert.equal(payload.layout.floor.x, layout.floor.x)
  assert.equal(payload.layout.floor.y, layout.floor.y)
})

// 验证奇数座位输入会按可编辑餐桌布局规整为实际总座位数。
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

// 验证启用校园到达时请求体会保留 campus_demand 配置。
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
      meal_period: 'lunch',
      residential_sources: [],
      population_pool: {
        enabled: true,
        meal_period: 'lunch',
        total_population_pool: 15000,
        total_population_mode: 'manual',
        meal_participation_rate: 0.75,
        other_known_population: 400,
        residential_allocation_mode: 'capacity_weight',
        residual_policy: 'clamp_zero'
      },
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
  assert.equal(payload.campus_demand.population_pool.total_population_pool, 15000)
  assert.equal(payload.campus_demand.population_pool.other_known_population, 400)
  assert.deepEqual(payload.campus_demand.residential_sources, [])
})
