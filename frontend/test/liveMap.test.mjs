import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const mapSource = readFileSync(new URL('../src/LiveDiningMap.vue', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')
const modelSource = readFileSync(new URL('../src/liveMapModel.js', import.meta.url), 'utf8')

test('App.vue mounts the LiveDiningMap on the live run page', () => {
  assert.equal(appSource.includes("import LiveDiningMap from './LiveDiningMap.vue'"), true)
  assert.equal(appSource.includes('<LiveDiningMap'), true)
  assert.equal(appSource.includes(':layout="layout"'), true)
  assert.equal(appSource.includes(':state="currentState"'), true)
})

test('live run page no longer renders the legacy seat matrix or seat-grid', () => {
  assert.equal(appSource.includes('class="seat-grid"'), false)
  assert.equal(appSource.includes('seat_matrix'), false)
  assert.equal(appSource.includes('座位占用矩阵'), false)
  assert.equal(appSource.includes('visibleSeatMatrix'), false)
  assert.equal(appSource.includes('seatGridStyle'), false)
})

test('LiveDiningMap consumes the structured snapshot fields from the backend', () => {
  assert.equal(mapSource.includes('queue_groups'), true)
  assert.equal(mapSource.includes('window_services'), true)
  assert.equal(mapSource.includes('waiting_parties'), true)
  assert.equal(mapSource.includes('seated_parties'), true)
  assert.equal(mapSource.includes('table_occupancy'), true)
  assert.equal(mapSource.includes('busy_windows'), true)
})

test('LiveDiningMap is purely visual and never relies on <text> or seat matrix', () => {
  assert.equal(mapSource.includes('<text'), false)
  assert.equal(mapSource.includes('seat_matrix'), false)
})

test('LiveDiningMap caps how many queue and waiting glyphs it emits', () => {
  // The component must not flood the SVG with hundreds of points when arrival
  // rate is high, so it bounds the visible queue and waiting cohorts.
  assert.match(modelSource, /QUEUE_VISIBLE_LIMIT\s*=\s*\d+/)
  assert.match(mapSource, /WAITING_VISIBLE_LIMIT\s*=\s*\d+/)
  // overflow indicator must exist for both queue and waiting tail.
  assert.equal(mapSource.includes('queue-overflow'), true)
  assert.equal(mapSource.includes('waiting-overflow'), true)
})

test('LiveDiningMap renders the four logical layers as named groups', () => {
  assert.equal(mapSource.includes('queue-group'), true)
  assert.equal(mapSource.includes('waiting-group'), true)
  assert.equal(mapSource.includes('seated-group'), true)
  assert.equal(mapSource.includes('service-group'), true)
  assert.equal(mapSource.includes('queue-capsule'), true)
  assert.equal(mapSource.includes('waiting-cluster'), true)
  assert.equal(mapSource.includes('seated-cluster'), true)
  assert.equal(mapSource.includes('service-mark'), true)
})

test('LiveDiningMap places queue capsules on the inner side of each window', () => {
  // The queue computation should anchor on the window position and walk along
  // its inward normal, not scatter parties freely across the floor.
  assert.equal(modelSource.includes('wallNormal('), true)
  assert.equal(modelSource.includes('QUEUE_OFFSET'), true)
  assert.equal(modelSource.includes('QUEUE_STEP'), true)
})

test('LiveDiningMap uses a small finite color palette', () => {
  const paletteMatch = modelSource.match(/PALETTE\s*=\s*\[([^\]]+)\]/)
  assert.notEqual(paletteMatch, null)
  const colors = paletteMatch[1].match(/'#[0-9a-fA-F]+'|"#[0-9a-fA-F]+"/g) || []
  assert.ok(colors.length >= 4 && colors.length <= 8, `expected 4-8 palette colors, got ${colors.length}`)
})

test('LiveDiningMap renders the static layout layers without dragging', () => {
  assert.equal(mapSource.includes('layout-door'), true)
  assert.equal(mapSource.includes('layout-window'), true)
  assert.equal(mapSource.includes('layout-table'), true)
  assert.equal(mapSource.includes('dining-chair'), true)
  assert.equal(mapSource.includes('table-top'), true)
  assert.equal(mapSource.includes('layout-window-marker'), true)
  // Live map cells must not be draggable: they share the no-pointer class.
  assert.equal(mapSource.includes('live-layout-item'), true)
})

test('LiveDiningMap exposes a dedicated waiting zone shape between entrance and tables', () => {
  assert.equal(mapSource.includes('waiting-zone'), true)
  assert.equal(mapSource.includes('waiting-zone-shape'), true)
  // The zone is positioned via doors when available.
  assert.equal(mapSource.includes('doors.value[0]'), true)
})

test('busy windows can be highlighted by class and stylesheet', () => {
  assert.equal(mapSource.includes('is-busy'), true)
  assert.equal(styleSource.includes('.layout-window.is-busy'), true)
})

test('styles.css declares the new live map layers with restrained visuals', () => {
  assert.equal(styleSource.includes('.live-dining-map'), true)
  assert.equal(styleSource.includes('.queue-group'), true)
  assert.equal(styleSource.includes('.waiting-group'), true)
  assert.equal(styleSource.includes('.seated-group'), true)
  assert.equal(styleSource.includes('.service-group'), true)
  assert.equal(styleSource.includes('.table-occupancy'), true)
  assert.equal(styleSource.includes('.queue-party'), true)
  assert.equal(styleSource.includes('.waiting-party'), true)
  assert.equal(styleSource.includes('.seated-party'), true)
  assert.equal(styleSource.includes('.queue-capsule'), true)
  assert.equal(styleSource.includes('.queue-overflow'), true)
  assert.equal(styleSource.includes('.waiting-zone'), true)
  assert.equal(styleSource.includes('.waiting-zone-shape'), true)
})

test('styles.css drops the legacy heavy halo and noisy queue dot rules', () => {
  // Old visuals that produced the colorful debug-scatter look are gone.
  assert.equal(styleSource.includes('.window-service-dot'), false)
  assert.equal(styleSource.includes('.service-halo'), false)
  assert.equal(styleSource.includes('.queue-party .party-dot'), false)
  assert.equal(styleSource.includes('.waiting-party .party-dot'), false)
  assert.equal(styleSource.includes('.seated-party .party-dot'), false)
})
