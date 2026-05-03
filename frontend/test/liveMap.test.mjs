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
  assert.equal(mapSource.includes('buildLivePartyTargets'), true)
  assert.equal(modelSource.includes('window_services'), true)
  assert.equal(modelSource.includes('seated_parties'), true)
  assert.equal(mapSource.includes('table_occupancy'), true)
  assert.equal(mapSource.includes('busy_windows'), true)
  // waiting_parties is intentionally not consumed: the metric card already
  // shows the waiting count, so the map does not render those parties.
  assert.equal(mapSource.includes('waiting_parties'), false)
})

test('LiveDiningMap delays table occupancy changes until party movement settles', () => {
  assert.equal(mapSource.includes('displayedTableOccupancy'), true)
  assert.equal(mapSource.includes('settleTableOccupancy'), true)
  assert.equal(mapSource.includes('snapshotTableOccupancy'), true)
  assert.equal(mapSource.includes('tableOccupancyById = computed(() => {'), true)
  assert.equal(mapSource.includes('displayedTableOccupancy.value'), true)
  assert.equal(mapSource.includes('snapshot.value.table_occupancy'), true)
})

test('LiveDiningMap interpolates party positions between minute snapshots', () => {
  assert.equal(mapSource.includes('animatedPartyMarkers'), true)
  assert.equal(mapSource.includes('requestAnimationFrame'), true)
  assert.equal(mapSource.includes('LIVE_TRANSITION_MS'), true)
  assert.equal(mapSource.includes('interpolateLivePartyMarkers'), true)
  assert.equal(mapSource.includes('buildLivePartyTransitions'), true)
  assert.equal(mapSource.includes('motion-path'), false)
  assert.equal(modelSource.includes('buildLivePartyTargets'), true)
  assert.equal(modelSource.includes('interpolateLivePartyMarkers'), true)
  assert.equal(modelSource.includes('buildWalkableRoute'), true)
  assert.equal(modelSource.includes('samplePathAtProgress'), true)
  assert.equal(modelSource.includes('createPathPlanner'), true)
})

test('LiveDiningMap is purely visual and never relies on <text> or seat matrix', () => {
  assert.equal(mapSource.includes('<text'), false)
  assert.equal(mapSource.includes('seat_matrix'), false)
})

test('LiveDiningMap caps how many parties it emits and bounds the queue panel', () => {
  // The queue cap lives in the model file (used by the detail panel).
  assert.match(modelSource, /QUEUE_VISIBLE_LIMIT\s*=\s*\d+/)
  // overflow indicator for the queue lives in the detail panel, not the map.
  assert.equal(mapSource.includes('window-detail-overflow'), true)
})

test('LiveDiningMap renders only the seated and service layers as named groups', () => {
  // No queue, no waiting parties on the map: queues live in the detail panel,
  // and waiting count is reported by the metric card outside this component.
  assert.equal(mapSource.includes('queue-group'), false)
  assert.equal(mapSource.includes('queue-capsule'), false)
  assert.equal(mapSource.includes('queue-overflow'), false)
  assert.equal(mapSource.includes('selectedQueueRow'), false)
  assert.equal(mapSource.includes('waiting-group'), false)
  assert.equal(mapSource.includes('waiting-cluster'), false)
  assert.equal(mapSource.includes('waiting-overflow'), false)
  assert.equal(mapSource.includes('waiting-zone'), false)
  // The remaining live layers are still drawn on the map.
  assert.equal(mapSource.includes('seated-group'), true)
  assert.equal(mapSource.includes('service-group'), true)
  assert.equal(mapSource.includes('seated-cluster'), true)
  assert.equal(mapSource.includes('service-mark'), true)
})

test('LiveDiningMap keeps the queue out of the SVG entirely', () => {
  // Selecting a window must not paint capsules onto the map; the queue is
  // shown only in the detail panel below.
  assert.equal(/<g[^>]*queue-group/.test(mapSource), false)
  assert.equal(mapSource.includes('selectedWindowIndex'), true)
  assert.equal(mapSource.includes('selectedWindowDetail'), true)
})

test('LiveDiningMap windows are clickable and toggle the selected window', () => {
  assert.equal(mapSource.includes('live-clickable-item'), true)
  assert.equal(mapSource.includes('@click.stop="toggleWindowSelection(idx)"'), true)
  assert.equal(mapSource.includes('toggleWindowSelection'), true)
  assert.equal(mapSource.includes('clearSelection'), true)
  // SVG-level click clears any current selection so users can dismiss the popup.
  assert.match(mapSource, /class="live-dining-map[^"]*"[\s\S]{0,200}@click="clearSelection"/)
})

test('LiveDiningMap surfaces queue details outside the SVG when a window is selected', () => {
  assert.equal(mapSource.includes('window-detail-panel'), true)
  assert.equal(mapSource.includes('window-detail-header'), true)
  assert.equal(mapSource.includes('window-detail-queue'), true)
  assert.equal(mapSource.includes('window-detail-capsule'), true)
  assert.equal(mapSource.includes('window-detail-overflow'), true)
  assert.equal(mapSource.includes('window-detail-hint'), true)
  assert.equal(mapSource.includes('selectedWindowDetail'), true)
})

test('LiveDiningMap exposes window state classes for queue, busy, selected', () => {
  assert.equal(mapSource.includes("'is-busy'"), true)
  assert.equal(mapSource.includes("'has-queue'"), true)
  assert.equal(mapSource.includes("'is-selected'"), true)
  assert.equal(styleSource.includes('.layout-window.has-queue'), true)
  assert.equal(styleSource.includes('.layout-window.is-busy'), true)
  assert.equal(styleSource.includes('.layout-window.is-selected'), true)
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

test('LiveDiningMap does not render a waiting zone or waiting parties', () => {
  // The waiting-for-seat count is shown by the metric card outside this
  // component, so the map should not duplicate it with shapes or clusters.
  assert.equal(mapSource.includes('waiting-zone'), false)
  assert.equal(mapSource.includes('waiting-zone-shape'), false)
  assert.equal(mapSource.includes('waiting-party'), false)
  assert.equal(mapSource.includes('waiting-cluster'), false)
  assert.equal(mapSource.includes('waitingZone'), false)
  assert.equal(mapSource.includes('waitingMarkers'), false)
})

test('busy windows can be highlighted by class and stylesheet', () => {
  assert.equal(mapSource.includes('is-busy'), true)
  assert.equal(styleSource.includes('.layout-window.is-busy'), true)
})

test('styles.css declares the live map layers with restrained visuals', () => {
  assert.equal(styleSource.includes('.live-dining-map'), true)
  assert.equal(styleSource.includes('.seated-group'), true)
  assert.equal(styleSource.includes('.service-group'), true)
  assert.equal(styleSource.includes('.table-occupancy'), true)
  assert.equal(styleSource.includes('.seated-party'), true)
  assert.equal(styleSource.includes('.window-detail-panel'), true)
  assert.equal(styleSource.includes('.window-detail-capsule'), true)
  assert.equal(styleSource.includes('.window-detail-overflow'), true)
  assert.equal(styleSource.includes('.live-clickable-item'), true)
  // The SVG queue layer is gone, so its dedicated rules should be gone too.
  assert.equal(styleSource.includes('.queue-group .queue-party .queue-capsule'), false)
  assert.equal(styleSource.includes('.queue-group .queue-overflow'), false)
  // Same for waiting visuals: removed from styles since map no longer paints them.
  assert.equal(styleSource.includes('.waiting-zone'), false)
  assert.equal(styleSource.includes('.waiting-group'), false)
  assert.equal(styleSource.includes('.waiting-overflow'), false)
})

test('styles.css drops the legacy heavy halo and noisy queue dot rules', () => {
  // Old visuals that produced the colorful debug-scatter look are gone.
  assert.equal(styleSource.includes('.window-service-dot'), false)
  assert.equal(styleSource.includes('.service-halo'), false)
  assert.equal(styleSource.includes('.queue-party .party-dot'), false)
  assert.equal(styleSource.includes('.waiting-party .party-dot'), false)
  assert.equal(styleSource.includes('.seated-party .party-dot'), false)
})
