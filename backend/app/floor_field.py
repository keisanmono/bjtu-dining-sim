from __future__ import annotations

# 文件说明：Floor Field / Cellular Automaton 兼容入口。

from typing import Any

from .pedestrian.fields import build_static_field
from .pedestrian.grid import (
    Cell,
    GridData,
    cell_to_point,
    grid_from_layout as pedestrian_grid_from_layout,
    is_walkable,
    nearest_walkable_cell,
    neighbors,
    point_to_cell,
)

DEFAULT_WIDTH = 360.0
DEFAULT_HEIGHT = 640.0
DEFAULT_CELL_SIZE = 20.0


def grid_from_layout(layout: Any, cell_size: float = DEFAULT_CELL_SIZE) -> dict[str, Any]:
    """Convert a dining layout into a CA grid with table cells marked blocked."""
    grid = pedestrian_grid_from_layout(layout, cell_size=cell_size)
    return _grid_to_legacy_dict(grid)


def build_static_floor_field(layout: Any, target: Any) -> dict[str, Any]:
    """Build a static distance field from every reachable grid cell to target."""
    grid = pedestrian_grid_from_layout(layout, cell_size=DEFAULT_CELL_SIZE)
    target_cell = nearest_walkable_cell(point_to_cell(target, grid), grid)
    distance = build_static_field(grid, {target_cell})
    return {
        **_grid_to_legacy_dict(grid),
        "target_cell": target_cell,
        "distance": distance,
    }


def next_cell_by_floor_field(
    agent: Any,
    grid: dict[str, Any],
    target: Any,
    occupied_cells: set[Cell] | None = None,
) -> Cell:
    """Return the next CA cell that best follows the static floor field."""
    occupied = occupied_cells or set()
    field = grid if "distance" in grid else _build_floor_field_for_grid(_legacy_grid_to_data(grid), target)
    grid_data = _legacy_grid_to_data(field)
    current = point_to_cell(agent, grid_data)
    target_cell = field["target_cell"]
    if current == target_cell:
        return current
    candidates = [current, *neighbors(current, grid_data, allow_diagonal=False)]
    candidates = [
        cell
        for cell in candidates
        if is_walkable(cell, grid_data) and (cell == current or cell not in occupied)
    ]
    if not candidates:
        return current
    distances = field["distance"]
    return min(
        candidates,
        key=lambda cell: (
            distances.get(cell, float("inf")),
            abs(cell[0] - target_cell[0]) + abs(cell[1] - target_cell[1]),
            cell[1],
            cell[0],
        ),
    )


def _build_floor_field_for_grid(grid: GridData, target: Any) -> dict[str, Any]:
    target_cell = nearest_walkable_cell(point_to_cell(target, grid), grid)
    distances = build_static_field(grid, {target_cell})
    return {
        **_grid_to_legacy_dict(grid),
        "target_cell": target_cell,
        "distance": distances,
    }


def _grid_to_legacy_dict(grid: GridData) -> dict[str, Any]:
    return {
        "cell_size": grid.cell_size,
        "cols": grid.cols,
        "rows": grid.rows,
        "origin_x": grid.origin_x,
        "origin_y": grid.origin_y,
        "blocked": set(grid.blocked_cells),
        "blocked_cells": set(grid.blocked_cells),
        "door_cells": dict(grid.door_cells),
        "window_cells": {idx: set(cells) for idx, cells in grid.window_cells.items()},
        "table_cells": {idx: set(cells) for idx, cells in grid.table_cells.items()},
        "table_approach_cells": {idx: set(cells) for idx, cells in grid.table_approach_cells.items()},
        "exit_cells": set(grid.exit_cells),
        "service_cells": dict(grid.service_cells),
        "queue_cells_by_window": {idx: list(cells) for idx, cells in grid.queue_cells_by_window.items()},
    }


def _legacy_grid_to_data(grid: dict[str, Any]) -> GridData:
    return GridData(
        cell_size=float(grid.get("cell_size") or DEFAULT_CELL_SIZE),
        cols=int(grid["cols"]),
        rows=int(grid["rows"]),
        origin_x=float(grid.get("origin_x", 0.0) or 0.0),
        origin_y=float(grid.get("origin_y", 0.0) or 0.0),
        blocked_cells=set(grid.get("blocked_cells") or grid.get("blocked") or set()),
        door_cells=dict(grid.get("door_cells") or {}),
        window_cells={idx: set(cells) for idx, cells in (grid.get("window_cells") or {}).items()},
        table_cells={idx: set(cells) for idx, cells in (grid.get("table_cells") or {}).items()},
        table_approach_cells={idx: set(cells) for idx, cells in (grid.get("table_approach_cells") or {}).items()},
        exit_cells=set(grid.get("exit_cells") or set()),
        service_cells=dict(grid.get("service_cells") or {}),
        queue_cells_by_window={idx: list(cells) for idx, cells in (grid.get("queue_cells_by_window") or {}).items()},
    )


def _to_cell(point: Any, grid: dict[str, Any]) -> Cell:
    return point_to_cell(point, _legacy_grid_to_data(grid))


def _neighbors(cell: Cell, grid: dict[str, Any]) -> list[Cell]:
    return neighbors(cell, _legacy_grid_to_data(grid))


def _field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
