from __future__ import annotations

from .grid import Cell, GridData


def build_window_queue_cells(grid: GridData, window_index: int) -> list[Cell]:
    return list(grid.queue_cells_by_window.get(window_index, []))
