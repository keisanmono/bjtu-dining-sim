from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .agents import AgentState, PedestrianAgent
from .grid import Cell, GridData, cell_to_point


@dataclass(frozen=True)
class MovementMetrics:
    avg_walking_time: float
    movement_conflict_count: int
    avg_stuck_ticks: float
    max_density: int
    avg_walking_distance_ratio: float


def movement_metrics(agents: dict[int, PedestrianAgent], tick_seconds: int, max_density: int = 0) -> MovementMetrics:
    tracked = list(agents.values())
    walking_seconds = [
        float(getattr(agent, "walking_time_seconds", 0.0) or 0.0)
        for agent in tracked
        if float(getattr(agent, "walking_time_seconds", 0.0) or 0.0) > 0
    ]
    avg_walking_time = sum(walking_seconds) / len(walking_seconds) if walking_seconds else 0.0
    distance_ratios = [
        ratio
        for agent in tracked
        if (ratio := _walking_distance_ratio(agent)) is not None
    ]
    avg_walking_distance_ratio = sum(distance_ratios) / len(distance_ratios) if distance_ratios else 0.0
    moving_states = {
        AgentState.ENTERING,
        AgentState.TO_WINDOW,
        AgentState.TO_TABLE,
        AgentState.TO_EXIT,
    }
    moving = [agent for agent in tracked if agent.state in moving_states]
    avg_stuck_ticks = sum(agent.stuck_ticks for agent in moving) / len(moving) if moving else 0.0
    return MovementMetrics(
        avg_walking_time=round(avg_walking_time, 2),
        movement_conflict_count=sum(agent.conflict_count for agent in tracked),
        avg_stuck_ticks=round(avg_stuck_ticks, 2),
        max_density=max_density,
        avg_walking_distance_ratio=round(avg_walking_distance_ratio, 2),
    )


def _walking_distance_ratio(agent: PedestrianAgent) -> float | None:
    leg_ratios = [
        float(ratio)
        for ratio in (getattr(agent, "movement_leg_distance_ratios", []) or [])
        if float(ratio) > 0
    ]
    active_ratio = _active_movement_leg_ratio(agent)
    if active_ratio is not None:
        leg_ratios.append(active_ratio)
    if leg_ratios:
        return sum(leg_ratios) / len(leg_ratios)

    path = list(getattr(agent, "path_cells", []) or [])
    if len(path) < 2:
        return None
    start = path[0]
    end = path[-1]
    straight_distance = math.hypot(end[0] - start[0], end[1] - start[1])
    if straight_distance <= 0:
        return None
    actual_distance = _path_distance(path)
    if actual_distance <= 0:
        actual_distance = float(getattr(agent, "walking_distance_cells", 0) or 0)
    if actual_distance <= 0:
        return None
    return actual_distance / straight_distance


def _active_movement_leg_ratio(agent: PedestrianAgent) -> float | None:
    start = getattr(agent, "movement_leg_start_cell", None)
    distance = float(getattr(agent, "movement_leg_distance_cells", 0.0) or 0.0)
    if start is None or distance <= 0:
        return None
    current = agent.cell
    straight_distance = math.hypot(current[0] - start[0], current[1] - start[1])
    if straight_distance <= 0:
        return None
    return distance / straight_distance


def _path_distance(path: list[Cell]) -> float:
    distance = 0.0
    for start, end in zip(path, path[1:]):
        distance += math.hypot(end[0] - start[0], end[1] - start[1])
    return distance


def density_hotspots(occupied_cells: set[Cell], grid: GridData, threshold: int = 3) -> list[dict[str, float | int]]:
    counts = Counter(occupied_cells)
    hotspots = []
    for cell, count in counts.items():
        if count < threshold:
            continue
        point = cell_to_point(cell, grid)
        hotspots.append({"cell": [cell[0], cell[1]], "x": point["x"], "y": point["y"], "density": count})
    return sorted(hotspots, key=lambda item: (-int(item["density"]), item["cell"][1], item["cell"][0]))
