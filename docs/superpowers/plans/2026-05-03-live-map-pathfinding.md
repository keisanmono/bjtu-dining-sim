# Live Map Pathfinding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real-time party markers move along walkable aisles between doors, windows, and tables instead of linearly crossing tables.

**Architecture:** Add a focused frontend pathfinding model that builds a coarse grid from the editable layout, marks expanded table and chair footprints as blocked cells, finds A* routes between live-party target points, and samples animation positions along the route. Keep the backend simulation and metric calculations unchanged.

**Tech Stack:** Vue 3, SVG, existing `liveMapModel.js`, new pure JavaScript pathfinding helpers, Node test runner.

---

### Task 1: Pathfinding Model

**Files:**
- Create: `frontend/src/livePathfinding.js`
- Modify: `frontend/test/liveMapModel.test.mjs`

- [ ] **Step 1: Write failing tests**

Add tests that import `buildWalkableRoute`, `samplePathAtProgress`, and `buildObstacleBoxes`. Use a layout with one table obstacle between start and end. Assert the route has intermediate points, no point lies inside obstacle boxes, and route sampling at progress `0`, `0.5`, `1` returns start, middle, and end positions.

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend && npm test`
Expected: FAIL because `livePathfinding.js` does not exist or exports are missing.

- [ ] **Step 3: Implement minimal pathfinding**

Implement grid A* with `LIVE_PATH_GRID_STEP = 10`, obstacle inflation, 4-neighbor search, nearest free-cell fallback for endpoints, and a fallback route `[start, end]` if no path exists. Export path length and sampler helpers.

- [ ] **Step 4: Run tests to verify pass**

Run: `cd frontend && npm test`
Expected: all frontend tests pass.

### Task 2: Animated Route Integration

**Files:**
- Modify: `frontend/src/liveMapModel.js`
- Modify: `frontend/src/LiveDiningMap.vue`
- Modify: `frontend/test/liveMap.test.mjs`
- Modify: `frontend/test/recommendationPanel.test.mjs`

- [ ] **Step 1: Write failing tests**

Update source-level tests to require `buildWalkableRoute`, `samplePathAtProgress`, and a stored `path` on interpolated markers. Add a model test proving `interpolateLivePartyMarkers` samples the route rather than direct midpoint when a table blocks the straight line.

- [ ] **Step 2: Run tests to verify failure**

Run: `cd frontend && npm test`
Expected: FAIL because marker interpolation still uses direct linear interpolation.

- [ ] **Step 3: Implement route-aware interpolation**

In `interpolateLivePartyMarkers`, build a route from previous position to next target using layout obstacles, sample the route by progress, preserve fade in/out behavior, and expose each marker's `path`. In `LiveDiningMap.vue`, optionally render a subtle `motion-path` polyline for currently moving seated/service markers.

- [ ] **Step 4: Run tests to verify pass**

Run: `cd frontend && npm test`
Expected: all frontend tests pass.

### Task 3: Verification and Commit

**Files:**
- All changed frontend files.

- [ ] **Step 1: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Vite build succeeds.

- [ ] **Step 2: Run backend tests**

Run: `backend/.venv/bin/python -m unittest discover -s tests`
Expected: backend tests pass, confirming metrics and APIs are unchanged.

- [ ] **Step 3: Check whitespace**

Run: `git diff --check`
Expected: no output.

- [ ] **Step 4: Commit**

Run: `git add ... && git commit -m "Route live map parties around tables"`
Expected: one focused commit with frontend pathfinding changes.
