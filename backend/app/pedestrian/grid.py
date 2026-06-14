from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

Cell = tuple[int, int]

DEFAULT_CELL_SIZE = 12.0
DEFAULT_WIDTH = 360.0
DEFAULT_HEIGHT = 640.0
DEFAULT_QUEUE_CELLS = 48
MIN_SERPENTINE_QUEUE_CELLS = 120
MAX_SERPENTINE_QUEUE_CELLS = 240
QUEUE_ROW_SEGMENT_CELLS = 10


@dataclass(frozen=True)
class GridData:
    cell_size: float
    cols: int
    rows: int
    origin_x: float = 0.0
    origin_y: float = 0.0
    blocked_cells: set[Cell] = field(default_factory=set)
    door_cells: dict[int, Cell] = field(default_factory=dict)
    window_cells: dict[int, set[Cell]] = field(default_factory=dict)
    table_cells: dict[int, set[Cell]] = field(default_factory=dict)
    table_approach_cells: dict[int, set[Cell]] = field(default_factory=dict)
    exit_cells: set[Cell] = field(default_factory=set)
    service_cells: dict[int, Cell] = field(default_factory=dict)
    queue_cells_by_window: dict[int, list[Cell]] = field(default_factory=dict)


def grid_from_layout(layout: Any, cell_size: float, allow_diagonal: bool = False) -> GridData:
    cell_size = float(cell_size)
    if not math.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("cell_size must be a positive finite number")

    bounds = _floor_bounds(layout)
    cols = max(1, int(math.ceil(bounds["width"] / cell_size)))
    rows = max(1, int(math.ceil(bounds["height"] / cell_size)))
    grid = GridData(
        cell_size=cell_size,
        cols=cols,
        rows=rows,
        origin_x=bounds["x"],
        origin_y=bounds["y"],
    )

    blocked: set[Cell] = set()
    table_cells: dict[int, set[Cell]] = {}
    table_approach_cells: dict[int, set[Cell]] = {}
    for idx, table in enumerate(_field(layout, "tables", []) or []):
        cells = _cells_for_rect(_centered_box(table, _table_footprint(table)), grid)
        table_cells[idx] = cells
        blocked.update(cells)

    window_cells: dict[int, set[Cell]] = {}
    service_cells: dict[int, Cell] = {}
    queue_cells_by_window: dict[int, list[Cell]] = {}
    window_normals: dict[int, tuple[int, int]] = {}
    for idx, window in enumerate(_field(layout, "windows", []) or []):
        footprint_cells = _cells_for_rect(_centered_box(window, _opening_footprint("window", _wall_side(window))), grid)
        window_cells[idx] = footprint_cells
        window_normals[idx] = _wall_normal(_wall_side(window))

    object.__setattr__(grid, "blocked_cells", blocked)
    object.__setattr__(grid, "table_cells", table_cells)
    object.__setattr__(grid, "window_cells", window_cells)

    for idx, cells in table_cells.items():
        approach = _approach_ring(cells, grid, allow_diagonal=allow_diagonal)
        table_approach_cells[idx] = approach
    object.__setattr__(grid, "table_approach_cells", table_approach_cells)

    door_cells: dict[int, Cell] = {}
    for idx, door in enumerate(_field(layout, "doors", []) or []):
        normal = _wall_normal(_wall_side(door))
        footprint = _opening_footprint("door", _wall_side(door))
        half = footprint["width"] / 2 if _wall_side(door) in {"left", "right"} else footprint["height"] / 2
        point = {
            "x": float(_field(door, "x", 0.0)) + normal[0] * (half + cell_size * 0.5),
            "y": float(_field(door, "y", 0.0)) + normal[1] * (half + cell_size * 0.5),
        }
        door_cells[idx] = nearest_walkable_cell(point_to_cell(point, grid), grid)
    object.__setattr__(grid, "door_cells", door_cells)
    object.__setattr__(grid, "exit_cells", set(door_cells.values()))

    for idx, window in enumerate(_field(layout, "windows", []) or []):
        normal = _wall_normal(_wall_side(window))
        footprint = _opening_footprint("window", _wall_side(window))
        half = footprint["width"] / 2 if _wall_side(window) in {"left", "right"} else footprint["height"] / 2
        point = {
            "x": float(_field(window, "x", 0.0)) + normal[0] * (half + cell_size * 0.5),
            "y": float(_field(window, "y", 0.0)) + normal[1] * (half + cell_size * 0.5),
        }
        service = nearest_walkable_cell(point_to_cell(point, grid), grid)
        service_cells[idx] = service
    object.__setattr__(grid, "service_cells", service_cells)

    ingress_reserved = _ingress_reserved_cells(grid, radius=1)
    service_head_reserved = {
        idx: _service_head_reserved_cells(service, window_normals.get(idx, (0, 1)), grid, radius=3)
        for idx, service in service_cells.items()
    }
    reserved_queue_cells: set[Cell] = set()
    for idx, service in service_cells.items():
        forbidden = set(ingress_reserved)
        forbidden.update(cell for window_idx, cell in service_cells.items() if window_idx != idx)
        for window_idx, cells in service_head_reserved.items():
            if window_idx != idx:
                forbidden.update(cells)
        forbidden.update(reserved_queue_cells)
        queue_cells = _queue_cells_from_service(
            service,
            window_normals.get(idx, (0, 1)),
            grid,
            forbidden=forbidden,
            target_count=_queue_target_count(grid, window_count=len(service_cells)),
        )
        queue_cells_by_window[idx] = queue_cells
        reserved_queue_cells.update(queue_cells)
    object.__setattr__(grid, "queue_cells_by_window", queue_cells_by_window)
    return grid


def point_to_cell(point: Any, grid: GridData) -> Cell:
    if isinstance(point, tuple) and len(point) == 2:
        return _clamp_cell((int(point[0]), int(point[1])), grid)
    x = float(_field(point, "x", 0.0) or 0.0)
    y = float(_field(point, "y", 0.0) or 0.0)
    return _clamp_cell(
        (
            int(math.floor((x - grid.origin_x) / grid.cell_size)),
            int(math.floor((y - grid.origin_y) / grid.cell_size)),
        ),
        grid,
    )


def cell_to_point(cell: Cell, grid: GridData) -> dict[str, float]:
    col, row = _clamp_cell(cell, grid)
    return {
        "x": round(grid.origin_x + (col + 0.5) * grid.cell_size, 1),
        "y": round(grid.origin_y + (row + 0.5) * grid.cell_size, 1),
    }


def neighbors(cell: Cell, grid: GridData, allow_diagonal: bool = False) -> list[Cell]:
    col, row = cell
    offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if allow_diagonal:
        offsets.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])
    result: list[Cell] = []
    for dc, dr in offsets:
        candidate = (col + dc, row + dr)
        if _in_bounds(candidate, grid):
            result.append(candidate)
    return result


def is_walkable(cell: Cell, grid: GridData) -> bool:
    return _in_bounds(cell, grid) and cell not in grid.blocked_cells


def nearest_walkable_cell(cell: Cell, grid: GridData) -> Cell:
    start = _clamp_cell(cell, grid)
    if is_walkable(start, grid):
        return start
    frontier: deque[Cell] = deque([start])
    seen = {start}
    while frontier:
        current = frontier.popleft()
        for neighbor in neighbors(current, grid, allow_diagonal=True):
            if neighbor in seen:
                continue
            if is_walkable(neighbor, grid):
                return neighbor
            seen.add(neighbor)
            frontier.append(neighbor)
    return start


def _queue_cells_from_service(
    service: Cell,
    normal: tuple[int, int],
    grid: GridData,
    forbidden: set[Cell] | None = None,
    target_count: int = DEFAULT_QUEUE_CELLS,
) -> list[Cell]:
    forbidden = forbidden or set()
    target_count = max(1, int(target_count))
    cells: list[Cell] = []
    reachable = _reachable_walkable_cells(service, grid)
    rows: dict[int, list[tuple[int, Cell]]] = {}
    for candidate in reachable:
        if candidate == service or candidate in forbidden:
            continue
        forward = _forward_distance(service, candidate, normal)
        if forward <= 0:
            continue
        rows.setdefault(forward, []).append((_lateral_distance(service, candidate, normal), candidate))

    initial_direction = _queue_initial_lateral_direction(rows)
    current_lateral = 0
    ordered_forwards = sorted(rows)
    for row_offset, forward in enumerate(ordered_forwards):
        if len(cells) >= target_count:
            break
        direction = initial_direction if row_offset % 2 == 0 else -initial_direction
        row_candidates = _serpentine_row_segment(
            rows[forward],
            current_lateral=current_lateral,
            direction=direction,
            limit=QUEUE_ROW_SEGMENT_CELLS,
        )
        next_forward = ordered_forwards[row_offset + 1] if row_offset + 1 < len(ordered_forwards) else None
        if next_forward is not None:
            row_candidates = _trim_row_for_next_row_transition(row_candidates, rows[next_forward])
        for lateral, candidate in row_candidates:
            cells.append(candidate)
            current_lateral = lateral
            if len(cells) >= target_count:
                break
    return cells


def _queue_initial_lateral_direction(rows: dict[int, list[tuple[int, Cell]]]) -> int:
    positive_span = 0
    negative_span = 0
    for row in rows.values():
        for lateral, _cell in row:
            positive_span = max(positive_span, lateral)
            negative_span = min(negative_span, lateral)
    return 1 if positive_span >= abs(negative_span) else -1


def _serpentine_row_segment(
    row: list[tuple[int, Cell]],
    current_lateral: int,
    direction: int,
    limit: int,
) -> list[tuple[int, Cell]]:
    ordered = sorted(row)
    if direction >= 0:
        segment = [item for item in ordered if item[0] >= current_lateral]
        if not segment:
            segment = ordered
    else:
        segment = [item for item in reversed(ordered) if item[0] <= current_lateral]
        if not segment:
            segment = list(reversed(ordered))
    closest = min(ordered, key=lambda item: abs(item[0] - current_lateral))
    if segment and abs(segment[0][0] - current_lateral) > abs(closest[0] - current_lateral):
        if closest[0] >= current_lateral:
            segment = [item for item in ordered if item[0] >= current_lateral]
        else:
            segment = [item for item in reversed(ordered) if item[0] <= current_lateral]
    contiguous: list[tuple[int, Cell]] = []
    for item in segment:
        if contiguous and abs(item[0] - contiguous[-1][0]) > 2:
            break
        contiguous.append(item)
        if len(contiguous) >= max(1, int(limit)):
            break
    return contiguous or segment[:1]


def _trim_row_for_next_row_transition(
    row_candidates: list[tuple[int, Cell]],
    next_row: list[tuple[int, Cell]],
) -> list[tuple[int, Cell]]:
    if len(row_candidates) <= 1 or not next_row:
        return row_candidates
    next_cells = [cell for _lateral, cell in next_row]
    trimmed = list(row_candidates)
    while len(trimmed) > 1:
        last = trimmed[-1][1]
        if min(abs(last[0] - cell[0]) + abs(last[1] - cell[1]) for cell in next_cells) <= 3:
            break
        trimmed.pop()
    return trimmed


def _queue_target_count(grid: GridData, window_count: int) -> int:
    window_count = max(1, int(window_count))
    walkable_cells = max(1, grid.cols * grid.rows - len(grid.blocked_cells))
    fair_share = walkable_cells // (window_count * 2)
    return max(DEFAULT_QUEUE_CELLS, min(MAX_SERPENTINE_QUEUE_CELLS, max(MIN_SERPENTINE_QUEUE_CELLS, fair_share)))


def _reachable_walkable_cells(start: Cell, grid: GridData) -> set[Cell]:
    if not is_walkable(start, grid):
        return set()
    frontier: deque[Cell] = deque([start])
    seen = {start}
    while frontier:
        current = frontier.popleft()
        for candidate in neighbors(current, grid, allow_diagonal=False):
            if candidate in seen or not is_walkable(candidate, grid):
                continue
            seen.add(candidate)
            frontier.append(candidate)
    return seen


def _queue_neighbor_order(cell: Cell, normal: tuple[int, int]) -> list[Cell]:
    side = (normal[1], normal[0])
    offsets = [
        normal,
        side,
        (-side[0], -side[1]),
        (-normal[0], -normal[1]),
    ]
    return [(cell[0] + dc, cell[1] + dr) for dc, dr in offsets]


def _forward_distance(service: Cell, candidate: Cell, normal: tuple[int, int]) -> int:
    return (candidate[0] - service[0]) * normal[0] + (candidate[1] - service[1]) * normal[1]


def _lateral_distance(service: Cell, candidate: Cell, normal: tuple[int, int]) -> int:
    side = (normal[1], normal[0])
    return (candidate[0] - service[0]) * side[0] + (candidate[1] - service[1]) * side[1]


def _service_head_reserved_cells(service: Cell, normal: tuple[int, int], grid: GridData, radius: int) -> set[Cell]:
    side = (normal[1], normal[0])
    reserved: set[Cell] = set()
    for forward in range(0, max(0, radius) + 1):
        for lateral in range(-radius, radius + 1):
            if forward + abs(lateral) > radius:
                continue
            candidate = (
                service[0] + normal[0] * forward + side[0] * lateral,
                service[1] + normal[1] * forward + side[1] * lateral,
            )
            if is_walkable(candidate, grid):
                reserved.add(candidate)
    return reserved


def _ingress_reserved_cells(grid: GridData, radius: int) -> set[Cell]:
    reserved: set[Cell] = set()
    for door_cell in grid.door_cells.values():
        frontier: deque[tuple[Cell, int]] = deque([(door_cell, 0)])
        seen = {door_cell}
        while frontier:
            current, distance = frontier.popleft()
            if is_walkable(current, grid):
                reserved.add(current)
            if distance >= radius:
                continue
            for neighbor in neighbors(current, grid, allow_diagonal=True):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                frontier.append((neighbor, distance + 1))
    return reserved


def _approach_ring(cells: set[Cell], grid: GridData, allow_diagonal: bool) -> set[Cell]:
    ring: set[Cell] = set()
    for cell in cells:
        for neighbor in neighbors(cell, grid, allow_diagonal=True):
            if is_walkable(neighbor, grid):
                ring.add(neighbor)
    if not allow_diagonal:
        cardinal_ring = {
            neighbor
            for cell in cells
            for neighbor in neighbors(cell, grid, allow_diagonal=False)
            if is_walkable(neighbor, grid)
        }
        return cardinal_ring or ring
    return ring


def _cells_for_rect(box: dict[str, float], grid: GridData) -> set[Cell]:
    left = max(0, int(math.floor((box["left"] - grid.origin_x) / grid.cell_size)))
    right = min(
        grid.cols - 1,
        int(math.floor((max(box["left"], box["right"] - 1e-6) - grid.origin_x) / grid.cell_size)),
    )
    top = max(0, int(math.floor((box["top"] - grid.origin_y) / grid.cell_size)))
    bottom = min(
        grid.rows - 1,
        int(math.floor((max(box["top"], box["bottom"] - 1e-6) - grid.origin_y) / grid.cell_size)),
    )
    return {
        (col, row)
        for col in range(left, right + 1)
        for row in range(top, bottom + 1)
        if _in_bounds((col, row), grid)
    }


def _centered_box(item: Any, footprint: dict[str, float]) -> dict[str, float]:
    x = float(_field(item, "x", 0.0) or 0.0)
    y = float(_field(item, "y", 0.0) or 0.0)
    return {
        "left": x - footprint["width"] / 2,
        "top": y - footprint["height"] / 2,
        "right": x + footprint["width"] / 2,
        "bottom": y + footprint["height"] / 2,
    }


def _table_footprint(table: Any) -> dict[str, float]:
    capacity = max(1, int(_field(table, "capacity", 4) or 4))
    if capacity <= 2:
        footprint = {"width": 52.0, "height": 26.0}
    elif capacity <= 4:
        footprint = {"width": 64.0, "height": 50.0}
    else:
        footprint = {"width": 76.0, "height": 50.0}
    rotation = ((round(float(_field(table, "rotation", 0) or 0)) % 180) + 180) % 180
    if 45 <= rotation < 135:
        return {"width": footprint["height"], "height": footprint["width"]}
    return footprint


def _opening_footprint(kind: str, wall_side: str) -> dict[str, float]:
    if kind == "door":
        horizontal = {"width": 52.0, "height": 32.0}
        vertical = {"width": 32.0, "height": 52.0}
    else:
        horizontal = {"width": 36.0, "height": 32.0}
        vertical = {"width": 32.0, "height": 36.0}
    return horizontal if wall_side in {"top", "bottom"} else vertical


def _wall_normal(wall_side: str) -> tuple[int, int]:
    if wall_side == "right":
        return (-1, 0)
    if wall_side == "bottom":
        return (0, -1)
    if wall_side == "left":
        return (1, 0)
    return (0, 1)


def _wall_side(item: Any) -> str:
    side = str(_field(item, "wall_side", "top") or "top")
    return side if side in {"left", "right", "top", "bottom"} else "top"


def _floor_bounds(layout: Any) -> dict[str, float]:
    floor = _field(layout, "floor", None)
    width = float(_field(floor, "width", DEFAULT_WIDTH) or DEFAULT_WIDTH)
    height = float(_field(floor, "height", DEFAULT_HEIGHT) or DEFAULT_HEIGHT)
    x = float(_field(floor, "x", 0.0) or 0.0)
    y = float(_field(floor, "y", 0.0) or 0.0)
    return {
        "x": x if math.isfinite(x) else 0.0,
        "y": y if math.isfinite(y) else 0.0,
        "width": max(DEFAULT_CELL_SIZE, width),
        "height": max(DEFAULT_CELL_SIZE, height),
    }


def _clamp_cell(cell: Cell, grid: GridData) -> Cell:
    return (
        max(0, min(grid.cols - 1, int(cell[0]))),
        max(0, min(grid.rows - 1, int(cell[1]))),
    )


def _in_bounds(cell: Cell, grid: GridData) -> bool:
    return 0 <= cell[0] < grid.cols and 0 <= cell[1] < grid.rows


def _field(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
