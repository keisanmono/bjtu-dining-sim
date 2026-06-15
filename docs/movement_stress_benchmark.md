# Movement Stress Benchmark

This document describes the quality-mode stress benchmark for the advanced floor-field movement engine.

## Quality Queue Model

`quality` uses `movement_model="advanced_floor_field"` with `advanced_movement_coupling=True`.
Window queues are slot-based physical FIFO queues:

- `window_walkers` are students that already chose a window and are walking to their assigned queue slot. They are not eligible for service yet.
- `physical_queue_lengths` measures `window_queues`, the students that have entered physical FIFO queue slots.
- Only the physical FIFO head can be served, and only after it reaches the service cell or the front queue segment.
- Non-head students cannot reserve or enter another window's service/head reserved area.

Local repair is a short-horizon prioritized reservation-table repair. It is intended to resolve local blocking around stuck agents; it is not a globally optimal MAPF solver.

`incomplete_party_ids` and `warnings` are failure signals for quality stress runs. In normal layouts they should be empty. They are expected only in deliberately invalid or unreachable table layouts.

## Running

```bash
python scripts/run_quality_stress.py
```

The default matrix covers arrival rates `8`, `12`, and `16`, duration `20` minutes, six windows, roughly 160 seats, and seeds `20`, `42`, `20260613`, `20260614`, and `20260615`.

For a shorter smoke matrix:

```bash
python scripts/run_quality_stress.py --arrival-rate 8 --arrival-rate 12 --arrival-rate 16 --seed 20 --seed 42
```

Outputs:

- `data/benchmarks/quality_stress_summary.json`
- `data/benchmarks/quality_stress_results.csv`

The script records per-scenario totals, physical queue lengths, walking-to-window count, entry waiting count, waiting pressure, movement conflicts, stuck metrics, max density, incomplete parties, warnings, static-field cache size, and per-minute `sum(physical_queue_lengths)`.

## Deadlock Detection

The benchmark fails with diagnostics when the post-arrival queue appears frozen. A possible deadlock requires consecutive snapshots where:

- the arrival horizon has passed;
- `total_served` does not increase;
- `sum(physical_queue_lengths)` does not decrease;
- at least one window is idle;
- `walking_to_window_count` and `entry_waiting_count` do not show reasonable progress.

Failure diagnostics include:

- last per-minute snapshots;
- per-window queue length, FIFO head id, head cell, head slot, service cell, distance, and stuck ticks;
- service/head reserved-area occupants;
- top stuck agents;
- `incomplete_party_ids`, `warnings`, and static-field cache size.

The wall-clock timeout and max-step limit are outer test protections only. If either triggers, the benchmark fails. A timeout is never treated as a successful simulation end. Production `run_simulation` still ends only when the runner reaches natural `done`.

## Passing Criteria

A normal quality stress scenario passes only when:

- `runner.done` is reached naturally;
- `total_served == total_arrived`;
- `total_seated == total_arrived`;
- final `physical_queue_lengths` sum to zero;
- `walking_to_window_count == 0`;
- `entry_waiting_count == 0`;
- `incomplete_party_ids` and `warnings` are empty;
- no possible-deadlock detector fires.

## Latest Smoke Matrix

Command:

```bash
python scripts/run_quality_stress.py --arrival-rate 8 --arrival-rate 12 --arrival-rate 16 --seed 20 --seed 42 --duration-min 20 --scenario-timeout-sec 300 --max-steps 420
```

| seed | arrival_rate | total_arrived | total_served | total_seated | peak physical queue | max pressure | avg_stuck_ticks | movement_conflict_count | incomplete_party_ids | natural done |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 20 | 8 | 157 | 157 | 157 | 9 | 28 | 0.0 | 147 | 0 | yes |
| 42 | 8 | 150 | 150 | 150 | 13 | 32 | 0.0 | 115 | 0 | yes |
| 20 | 12 | 242 | 242 | 242 | 31 | 97 | 0.0 | 3143 | 0 | yes |
| 42 | 12 | 244 | 244 | 244 | 24 | 107 | 0.0 | 2489 | 0 | yes |
| 20 | 16 | 323 | 323 | 323 | 19 | 156 | 0.0 | 24170 | 0 | yes |
| 42 | 16 | 355 | 355 | 355 | 24 | 171 | 0.0 | 68623 | 0 | yes |
