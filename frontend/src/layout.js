export const defaultPartySizeDistribution = {
  1: 0.55,
  2: 0.30,
  3: 0.08,
  4: 0.04,
  5: 0.02,
  6: 0.01
}

export function buildSimulationConfigPayload(config) {
  const layout = buildLayoutFromConfig(config)
  return {
    ...config,
    layout,
    party_size_distribution: partyDistributionForLayout(layout)
  }
}

export function buildLayoutFromConfig(config) {
  const numWindows = clampInteger(config.num_windows, 1, 30)
  const numSeats = clampInteger(config.num_seats, 1, 2000)
  return {
    doors: [{ id: 'D1', x: 18, y: 145, arrival_share: 1 }],
    windows: Array.from({ length: numWindows }, (_item, index) => ({
      id: `W${index + 1}`,
      x: 126 + (index % 4) * 54,
      y: 82 + Math.floor(index / 4) * 42,
      service_rate_factor: 1
    })),
    tables: buildTableCapacities(numSeats).map((capacity, index) => ({
      id: `T${index + 1}`,
      x: 126 + (index % 4) * 62,
      y: 232 + Math.floor(index / 4) * 54,
      table_type: tableTypeForCapacity(capacity),
      capacity
    }))
  }
}

export function buildTableCapacities(numSeats) {
  let remaining = clampInteger(numSeats, 1, 2000)
  const pattern = [2, 4, 4, 6]
  const capacities = []
  let index = 0

  while (remaining > 0) {
    const capacity = Math.min(pattern[index % pattern.length], remaining)
    capacities.push(capacity)
    remaining -= capacity
    index += 1
  }
  return capacities
}

export function tableTypeForCapacity(capacity) {
  if (capacity <= 1) return 'single_seat'
  if (capacity <= 2) return 'two_seat'
  if (capacity <= 4) return 'four_seat'
  return 'six_seat'
}

function partyDistributionForLayout(layout) {
  const maxCapacity = Math.max(1, ...layout.tables.map((table) => table.capacity))
  return Object.fromEntries(
    Object.entries(defaultPartySizeDistribution)
      .filter(([size]) => Number(size) <= maxCapacity)
      .map(([size, weight]) => [Number(size), weight])
  )
}

function clampInteger(value, lower, upper) {
  return Math.min(upper, Math.max(lower, Math.round(Number(value) || lower)))
}
