from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .grid import Cell, GridData, is_walkable, nearest_walkable_cell, neighbors


def build_static_field(grid: GridData, target_cells: set[Cell] | list[Cell] | tuple[Cell, ...]) -> dict[Cell, float]:
    targets = {
        nearest_walkable_cell(cell, grid)
        for cell in target_cells
    }
    targets = {cell for cell in targets if is_walkable(cell, grid)}
    distances: dict[Cell, float] = {cell: 0.0 for cell in targets}
    frontier: deque[Cell] = deque(sorted(targets))

    while frontier:
        cell = frontier.popleft()
        for neighbor in neighbors(cell, grid, allow_diagonal=False):
            if not is_walkable(neighbor, grid) or neighbor in distances:
                continue
            distances[neighbor] = distances[cell] + 1.0
            frontier.append(neighbor)
    return distances


@dataclass
class DynamicField:
    values: dict[Cell, float] = field(default_factory=dict)
    decay: float = 0.85
    diffusion: float = 0.10

    def deposit(self, cell: Cell, amount: float = 1.0) -> None:
        self.values[cell] = self.values.get(cell, 0.0) + max(0.0, float(amount))

    def step(self, grid: GridData) -> None:
        decay = max(0.0, min(1.0, float(self.decay)))
        diffusion = max(0.0, min(1.0, float(self.diffusion)))
        next_values: dict[Cell, float] = {}
        for cell, value in list(self.values.items()):
            if value <= 0 or not is_walkable(cell, grid):
                continue
            decayed = value * decay
            retained = decayed * (1.0 - diffusion)
            if retained > 1e-9:
                next_values[cell] = next_values.get(cell, 0.0) + retained
            open_neighbors = [
                neighbor
                for neighbor in neighbors(cell, grid, allow_diagonal=False)
                if is_walkable(neighbor, grid)
            ]
            if not open_neighbors:
                continue
            share = decayed * diffusion / len(open_neighbors)
            for neighbor in open_neighbors:
                if share > 1e-9:
                    next_values[neighbor] = next_values.get(neighbor, 0.0) + share
        self.values = {cell: value for cell, value in next_values.items() if value > 1e-9}


@dataclass(frozen=True)
class DensityField:
    densities: dict[Cell, int]

    @classmethod
    def from_occupied_cells(cls, occupied_cells: set[Cell], grid: GridData, radius: int = 1) -> "DensityField":
        radius = max(0, int(radius))
        densities: dict[Cell, int] = {}
        for col in range(grid.cols):
            for row in range(grid.rows):
                cell = (col, row)
                if not is_walkable(cell, grid):
                    continue
                count = 0
                for occupied in occupied_cells:
                    if max(abs(occupied[0] - col), abs(occupied[1] - row)) <= radius:
                        count += 1
                if count:
                    densities[cell] = count
        return cls(densities=densities)

    def density(self, cell: Cell) -> int:
        return self.densities.get(cell, 0)

    def penalty(self, cell: Cell, threshold: int = 3) -> float:
        density = self.density(cell)
        if density <= 0:
            return 0.0
        return float(max(0, density - max(0, threshold) + 1))


def wall_distance_or_penalty(cell: Cell, grid: GridData) -> float:
    if not is_walkable(cell, grid):
        return float("inf")
    col, row = cell
    penalty = 0.0
    if col == 0 or col == grid.cols - 1:
        penalty += 1.0
    if row == 0 or row == grid.rows - 1:
        penalty += 1.0
    for neighbor in neighbors(cell, grid, allow_diagonal=True):
        if neighbor in grid.blocked_cells:
            penalty += 0.35
    missing_neighbors = 8 - len(neighbors(cell, grid, allow_diagonal=True))
    return penalty + missing_neighbors * 0.15
