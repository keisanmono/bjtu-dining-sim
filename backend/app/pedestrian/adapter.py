from __future__ import annotations

"""Adapter helpers between the minute-level DES runner and pedestrian engine."""

from typing import Any

from .fields import build_static_field
from .grid import cell_to_point, grid_from_layout, is_walkable, nearest_walkable_cell, neighbors, point_to_cell


def static_floor_field_path(layout: Any, config: Any, start: dict[str, float], end: dict[str, float]) -> list[dict[str, float]]:
    grid = grid_from_layout(
        layout,
        cell_size=float(getattr(config, "floor_cell_size", 12.0)),
        allow_diagonal=bool(getattr(config, "floor_allow_diagonal", False)),
    )
    start_cell = nearest_walkable_cell(point_to_cell(start, grid), grid)
    target_cell = nearest_walkable_cell(point_to_cell(end, grid), grid)
    field = build_static_field(grid, {target_cell})
    if start_cell not in field:
        return [start, end]

    path_cells = [start_cell]
    current = start_cell
    seen = {current}
    allow_diagonal = bool(getattr(config, "floor_allow_diagonal", False))
    max_steps = max(1, grid.cols * grid.rows)
    for _step in range(max_steps):
        if current == target_cell:
            break
        candidates = [
            cell
            for cell in neighbors(current, grid, allow_diagonal=allow_diagonal)
            if is_walkable(cell, grid) and cell in field
        ]
        if not candidates:
            break
        next_cell = min(
            candidates,
            key=lambda cell: (
                field.get(cell, float("inf")),
                abs(cell[0] - target_cell[0]) + abs(cell[1] - target_cell[1]),
                cell[1],
                cell[0],
            ),
        )
        if next_cell in seen and field.get(next_cell, float("inf")) >= field.get(current, float("inf")):
            break
        current = next_cell
        seen.add(current)
        path_cells.append(current)

    return _dedupe_points([cell_to_point(cell, grid) for cell in path_cells])


def merge_timelines(existing: dict[str, Any] | None, pedestrian: dict[str, Any] | None) -> dict[str, Any] | None:
    if not existing:
        return pedestrian
    if not pedestrian:
        return existing
    events = [*(existing.get("events") or []), *(pedestrian.get("events") or [])]
    if not events:
        return None
    return {
        "start_time_sec": min(existing.get("start_time_sec", pedestrian.get("start_time_sec", 0)), pedestrian.get("start_time_sec", existing.get("start_time_sec", 0))),
        "end_time_sec": max(existing.get("end_time_sec", pedestrian.get("end_time_sec", 0)), pedestrian.get("end_time_sec", existing.get("end_time_sec", 0))),
        "playback_ms": max(existing.get("playback_ms", 0), pedestrian.get("playback_ms", 0)),
        "events": events,
    }


def _dedupe_points(points: list[dict[str, float]]) -> list[dict[str, float]]:
    deduped: list[dict[str, float]] = []
    for point in points:
        if deduped and abs(deduped[-1]["x"] - point["x"]) < 0.1 and abs(deduped[-1]["y"] - point["y"]) < 0.1:
            continue
        deduped.append(point)
    return deduped
