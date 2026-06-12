# Pedestrian Engine Design

## Module Structure

`backend/app/pedestrian/` contains the optional advanced movement system:

- `grid.py`: converts dining layouts into CA grids, blocked table cells, door targets, service cells, queue cells, and table approach cells.
- `fields.py`: builds static distance fields, maintains dynamic trace fields, computes local density, and adds wall/obstacle penalties.
- `agents.py`: defines `AgentState`, `PedestrianAgent`, and `PartyMovementState`.
- `queueing.py`: maps logical window queues onto physical service/queue cells.
- `engine.py`: runs CA ticks, computes candidate costs, resolves conflicts, emits movement events, and exposes snapshots/metrics.
- `metrics.py`: summarizes walking time, conflicts, stuck ticks, max density, and heatmap hotspots.
- `adapter.py`: connects static floor-field paths and advanced timeline events back to `DiningSimulationRunner`.

The legacy `backend/app/floor_field.py` remains as a compatibility wrapper around the new modules.

## State Machine

```text
ENTERING
  -> TO_WINDOW
  -> QUEUEING
  -> SERVICE
  -> WAITING_GROUP
  -> TO_TABLE
  -> SEATED
  -> TO_EXIT
  -> EXITED
```

The DES runner still owns service, seating, dining, and leaving decisions. The pedestrian engine mirrors those decisions into micro-position states when `movement_model = "advanced_floor_field"`.

## Tick Flow

```text
DiningSimulationRunner.step()           one simulated minute
  update service / seating / arrivals
  synchronize targets to PedestrianEngine
  PedestrianEngine.run_for_minute()
    tick 1
      refresh queue/table targets
      compute occupied cells and density
      score candidate current/neighbor cells
      choose intended moves
      resolve same-cell conflicts in parallel
      update cells, paths, frames, dynamic field
    tick 2..N
  merge movement events into snapshot.timeline
  build StepRecord snapshot and metrics
```

`movement_tick_seconds` controls tick size; `max_movement_ticks_per_minute` caps work per minute.

## Cost Function

```text
cost(cell, agent) =
    floor_static_weight * static_distance(cell, target)
  + floor_density_weight * density_penalty(cell)
  - floor_dynamic_weight * dynamic_field_value(cell)
  + floor_wall_weight * wall_penalty(cell)
  + floor_inertia_weight * turn_penalty(previous, current, cell)
  + floor_group_weight * group_distance_penalty(party, cell)
  + random_noise
```

Static distance comes from BFS over walkable cells. Occupied cells are not enterable, except the agent's current cell, which represents waiting. If no finite candidate exists, the agent waits and increments `stuck_ticks`.

## Conflict Resolution

All movable agents choose intended cells before any cell updates. When multiple agents choose the same target cell, the lower-cost move wins; losers stay in place and increment `conflict_count`. This keeps updates parallel and prevents two agents from entering the same cell in one tick.

## Queue Model

The logical `DiningSimulationRunner.queues` remains the source of service order. The pedestrian engine mirrors each window queue onto physical cells:

- position 0 targets the `service_cell`;
- later positions target queue cells behind it;
- when service starts, the student is marked `SERVICE` at the service cell and the remaining queue retargets forward.

This keeps existing service logic stable while making queue locations visible on the live map.

## Metrics

- `avg_walking_time`: average movement seconds among agents that moved at least one cell.
- `movement_conflict_count`: total same-cell conflict losers.
- `avg_stuck_ticks`: average wait/stuck tick count among non-exited agents.
- `max_density`: maximum observed local neighborhood density.
- `density_hotspots`: drawable heatmap points for the live map.

## Current Scope

The implementation is an optional Floor Field CA engine. It includes static fields, dynamic fields, density penalties, wall penalties, inertia, same-party cohesion, physical queue positions, and parallel conflict resolution.

It does not implement a full continuous Helbing/Molnar Social Force solver or ORCA. Those ideas are represented as cost terms inside the discrete CA decision rule.
