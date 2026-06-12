from __future__ import annotations

# 文件说明：Floor Field / Cellular Automaton 行人移动模型的轻量骨架。

from collections import deque
from typing import Any


DEFAULT_CELL_SIZE = 20.0
DEFAULT_WIDTH = 360.0
DEFAULT_HEIGHT = 640.0

Cell = tuple[int, int]


def grid_from_layout(layout: Any, cell_size: float = DEFAULT_CELL_SIZE) -> dict[str, Any]:
    """Convert a dining layout into a coarse CA grid with table cells marked blocked."""
    floor = _field(layout, "floor", {}) or {}
    width = float(_field(floor, "width", DEFAULT_WIDTH) or DEFAULT_WIDTH)
    height = float(_field(floor, "height", DEFAULT_HEIGHT) or DEFAULT_HEIGHT)
    cols = max(1, int(round(width / cell_size)))
    rows = max(1, int(round(height / cell_size)))
    blocked: set[Cell] = set()

    for table in _field(layout, "tables", []) or []:
        capacity = max(1, int(_field(table, "capacity", 4) or 4))
        if capacity <= 2:
            table_width, table_height = 52.0, 26.0
        elif capacity <= 4:
            table_width, table_height = 64.0, 50.0
        else:
            table_width, table_height = 76.0, 50.0
        x = float(_field(table, "x", 0.0) or 0.0)
        y = float(_field(table, "y", 0.0) or 0.0)
        left = x - table_width / 2
        right = x + table_width / 2
        top = y - table_height / 2
        bottom = y + table_height / 2
        for row in range(rows):
            for col in range(cols):
                center_x = (col + 0.5) * cell_size
                center_y = (row + 0.5) * cell_size
                if left <= center_x <= right and top <= center_y <= bottom:
                    blocked.add((col, row))

    return {
        "cell_size": cell_size,
        "cols": cols,
        "rows": rows,
        "blocked": blocked,
    }


def build_static_floor_field(layout: Any, target: Any) -> dict[str, Any]:
    """Build a static distance field from every reachable grid cell to target."""
    grid = grid_from_layout(layout)
    return _build_floor_field_for_grid(grid, target)


def _build_floor_field_for_grid(grid: dict[str, Any], target: Any) -> dict[str, Any]:
    target_cell = _to_cell(target, grid)
    distances: dict[Cell, int] = {target_cell: 0}
    frontier: deque[Cell] = deque([target_cell])
    blocked = grid["blocked"]

    while frontier:
        cell = frontier.popleft()
        for neighbor in _neighbors(cell, grid):
            if neighbor in blocked or neighbor in distances:
                continue
            distances[neighbor] = distances[cell] + 1
            frontier.append(neighbor)

    return {
        **grid,
        "target_cell": target_cell,
        "distance": distances,
    }


def next_cell_by_floor_field(
    agent: Any,
    grid: dict[str, Any],
    target: Any,
    occupied_cells: set[Cell] | None = None,
) -> Cell:
    """Return the next CA cell that best follows the static floor field."""
    occupied = occupied_cells or set()
    field = grid if "distance" in grid else _build_floor_field_for_grid(grid, target)
    current = _to_cell(agent, field)
    if current == field["target_cell"]:
        return current

    candidates = [current, *_neighbors(current, field)]
    candidates = [
        cell
        for cell in candidates
        if cell not in field["blocked"] and (cell == current or cell not in occupied)
    ]
    distances = field["distance"]
    return min(
        candidates,
        key=lambda cell: (
            distances.get(cell, float("inf")),
            abs(cell[0] - field["target_cell"][0]) + abs(cell[1] - field["target_cell"][1]),
            cell[1],
            cell[0],
        ),
    )


def _neighbors(cell: Cell, grid: dict[str, Any]) -> list[Cell]:
    col, row = cell
    raw = [(col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)]
    return [
        (next_col, next_row)
        for next_col, next_row in raw
        if 0 <= next_col < grid["cols"] and 0 <= next_row < grid["rows"]
    ]


def _to_cell(point: Any, grid: dict[str, Any]) -> Cell:
    if isinstance(point, tuple) and len(point) == 2:
        return (
            max(0, min(grid["cols"] - 1, int(point[0]))),
            max(0, min(grid["rows"] - 1, int(point[1]))),
        )
    cell_size = float(grid.get("cell_size") or DEFAULT_CELL_SIZE)
    x = float(_field(point, "x", 0.0) or 0.0)
    y = float(_field(point, "y", 0.0) or 0.0)
    return (
        max(0, min(grid["cols"] - 1, int(x // cell_size))),
        max(0, min(grid["rows"] - 1, int(y // cell_size))),
    )


def _field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
