# Campus Floor Demand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add floor-level campus demand so a selected cafeteria receives arrivals from all main-campus teaching buildings based on live, random, or manually edited occupancy.

**Architecture:** `backend/app/campus.py` owns static campus data loading, live/random floor occupancy, cafeteria choice probability, and arrival-schedule generation. `backend/app/simulation.py` consumes a precomputed campus arrival schedule when `campus_demand.enabled` is true. The Vue config screen exposes a campus mode with target cafeteria, live/random buttons, and editable per-floor counts.

**Tech Stack:** Python dataclasses, FastAPI/Pydantic, unittest, Vue 3, Element Plus, existing axios API wrapper.

---

### Task 1: Backend Campus Demand Core

**Files:**
- Create: `backend/app/campus.py`
- Modify: `backend/app/simulation.py`
- Modify: `backend/app/schemas.py`
- Test: `tests/test_campus_demand.py`

- [x] **Step 1: Write failing tests**

Add tests that import `CampusDemandConfigData`, `CampusBuildingDemandData`, `CampusFloorDemandData`, and `build_campus_arrival_schedule`. Verify that an upper floor arrives no earlier than a lower floor, the nearest cafeteria has the highest choice probability, and a `SimulationConfigData` with campus demand uses scheduled arrivals instead of Poisson arrivals.

- [x] **Step 2: Run tests to verify failure**

Run: `backend/.venv/bin/python -m unittest tests.test_campus_demand`
Expected: import errors for missing campus demand types/functions.

- [x] **Step 3: Implement minimal backend core**

Create `backend/app/campus.py` with static walk-time loading, `cafeteria_choice_probabilities`, `build_campus_arrival_schedule`, random floor generation, and yaya classroom response parsing. Extend `SimulationConfigData` and Pydantic schemas with `campus_demand`. Update `DiningSimulationRunner` to precompute `self.campus_arrival_schedule`, extend the arrival horizon to the last scheduled minute, and return scheduled arrivals in `_generate_arrivals`.

- [x] **Step 4: Run tests to verify pass**

Run: `backend/.venv/bin/python -m unittest tests.test_campus_demand`
Expected: all campus demand tests pass.

### Task 2: Campus API

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py`
- Test: `tests/test_api.py`

- [x] **Step 1: Write failing API tests**

Add tests for `GET /api/campus/locations` returning cafeterias and buildings, and `POST /api/campus/occupancy` returning floor rows for random mode.

- [x] **Step 2: Run tests to verify failure**

Run: `backend/.venv/bin/python -m unittest tests.test_api`
Expected: 404 for the new campus endpoints.

- [x] **Step 3: Implement API endpoints**

Add `/api/campus/locations` and `/api/campus/occupancy`. `source_mode=random` returns generated floor counts. `source_mode=live` attempts yaya classroom data and returns warning-backed fallback if the external request fails. `source_mode=manual` echoes submitted rows.

- [x] **Step 4: Run tests to verify pass**

Run: `backend/.venv/bin/python -m unittest tests.test_api`
Expected: API tests pass.

### Task 3: Frontend Campus Controls

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/layout.js`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/styles.css`
- Test: `frontend/test/recommendationPanel.test.mjs`

- [x] **Step 1: Write failing frontend tests**

Add source checks that the config screen contains campus arrival controls, two buttons labeled `获取实时数据` and `随机生成`, and that payload building includes `campus_demand`.

- [x] **Step 2: Run tests to verify failure**

Run: `npm test`
Expected: frontend test fails because campus controls and payload are missing.

- [x] **Step 3: Implement frontend controls**

Add campus mode state, load locations on mount, render target cafeteria select, live/random buttons, editable floor count inputs, and include `campus_demand` in simulation payload when campus mode is active.

- [x] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: frontend tests pass.

### Task 4: Full Verification

**Files:**
- All modified files

- [x] **Step 1: Run backend tests**

Run: `backend/.venv/bin/python -m unittest discover tests`
Expected: all backend tests pass.

- [x] **Step 2: Run frontend tests and build**

Run: `npm test`
Expected: all frontend tests pass.

Run: `npm run build`
Expected: Vite build completes.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add backend/app/campus.py backend/app/main.py backend/app/schemas.py backend/app/simulation.py frontend/src/App.vue frontend/src/api.js frontend/src/layout.js frontend/src/styles.css tests/test_api.py tests/test_campus_demand.py frontend/test/recommendationPanel.test.mjs docs/superpowers/specs/2026-05-03-campus-occupancy-arrival-design.md docs/superpowers/plans/2026-05-03-campus-floor-demand.md
git commit -m "feat: add campus floor demand simulation"
```
