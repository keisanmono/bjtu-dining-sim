from __future__ import annotations

from typing import Any

from .fields import DynamicField
from .grid import GridData, grid_from_layout


class PedestrianEngine:
    def __init__(self, layout: Any, config: Any, rng: Any):
        self.layout = layout
        self.config = config
        self.rng = rng
        self.grid: GridData = grid_from_layout(
            layout,
            cell_size=float(getattr(config, "floor_cell_size", 12.0)),
            allow_diagonal=bool(getattr(config, "floor_allow_diagonal", False)),
        )
        self.dynamic_field = DynamicField(
            decay=float(getattr(config, "dynamic_field_decay", 0.85)),
            diffusion=float(getattr(config, "dynamic_field_diffusion", 0.10)),
        )
        self.agents = {}
        self.party_states = {}
        self.max_density = 0
