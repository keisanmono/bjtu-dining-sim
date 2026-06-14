from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .agents import PedestrianAgent
from .grid import Cell, GridData, cell_to_point


@dataclass(frozen=True)
class MovementMetrics:
    avg_walking_time: float
    movement_conflict_count: int
    avg_stuck_ticks: float
    max_density: int


def movement_metrics(agents: dict[int, PedestrianAgent], tick_seconds: int, max_density: int = 0) -> MovementMetrics:
    tracked = list(agents.values())
    walking_seconds = [
        agent.walking_distance_cells * tick_seconds
        for agent in tracked
        if agent.walking_distance_cells > 0
    ]
    avg_walking_time = sum(walking_seconds) / len(walking_seconds) if walking_seconds else 0.0
    avg_stuck_ticks = sum(agent.stuck_ticks for agent in tracked) / len(tracked) if tracked else 0.0
    return MovementMetrics(
        avg_walking_time=round(avg_walking_time, 2),
        movement_conflict_count=sum(agent.conflict_count for agent in tracked),
        avg_stuck_ticks=round(avg_stuck_ticks, 2),
        max_density=max_density,
    )


def density_hotspots(occupied_cells: set[Cell], grid: GridData, threshold: int = 3) -> list[dict[str, float | int]]:
    counts = Counter(occupied_cells)
    hotspots = []
    for cell, count in counts.items():
        if count < threshold:
            continue
        point = cell_to_point(cell, grid)
        hotspots.append({"cell": [cell[0], cell[1]], "x": point["x"], "y": point["y"], "density": count})
    return sorted(hotspots, key=lambda item: (-int(item["density"]), item["cell"][1], item["cell"][0]))
