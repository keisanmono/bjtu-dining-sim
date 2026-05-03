# Campus Peak Recommendation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add campus-aware recommendation search that can choose how many dismissal peaks to split teaching buildings into while keeping interaction latency low.

**Architecture:** The backend recommendation request gains `peak_count_options` while reusing `stagger_options` as peak gap candidates. In campus-demand mode, each candidate builds a copied `campus_demand` whose buildings are greedily assigned to balanced peak buckets by estimated released demand, then delayed by `peak_index * gap`. Manual-average and campus recommendation candidates are scored with a fast aggregate queue estimator instead of full minute-by-minute student simulation; applying the recommendation still lets the user run the real simulator.

**Tech Stack:** Python dataclasses and unittest for backend recommendation logic; Pydantic schemas for API input; Vue/Element Plus and node tests for frontend controls.

---

### Task 1: Backend Campus Peak Search

**Files:**
- Modify: `backend/app/optimization.py`
- Test: `tests/test_simulation.py`

- [ ] **Step 1: Write failing tests** for `peak_count_options=[3]` in campus mode, asserting returned candidate keeps the same buildings, distributes them across three dismissal minutes, and labels the strategy with `3 峰下课`.
- [ ] **Step 2: Run backend test** with `backend/.venv/bin/python -m unittest tests.test_simulation.CafeteriaSimulationTests.test_recommendation_splits_campus_buildings_into_dismissal_peaks` and confirm it fails before implementation.
- [ ] **Step 3: Implement minimal backend support** by adding `peak_count_options`, greedy peak assignment, campus demand copying, campus-specific strategy labels, peak count delay cost, and a fast aggregate estimator for manual-average and campus candidate metrics.
- [ ] **Step 4: Re-run backend tests** for the new cases and existing recommendation tests.

### Task 2: API And Frontend Controls

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/candidates.js`
- Test: `tests/test_api.py`
- Test: `frontend/test/candidates.test.mjs`
- Test: `frontend/test/recommendationPanel.test.mjs`

- [ ] **Step 1: Write failing tests** that API accepts `peak_count_options`, frontend candidate settings expose peak count min/max, and recommendation payload sends `peak_count_options`.
- [ ] **Step 2: Implement schema and frontend payload changes** while preserving the existing `stagger_options` field as the peak interval list.
- [ ] **Step 3: Re-run frontend and backend tests**.

### Task 3: Final Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run** `backend/.venv/bin/python -m unittest discover tests`.
- [ ] **Step 2: Run** `npm test` in `frontend`.
- [ ] **Step 3: Run** `npm run build` in `frontend`.
- [ ] **Step 4: Run** `git diff --check`.
