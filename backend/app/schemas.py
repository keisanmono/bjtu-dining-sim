from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .simulation import (
    DiningLayoutData,
    LayoutDoorData,
    LayoutTableData,
    LayoutWindowData,
    SimulationConfigData,
)


class LayoutDoor(BaseModel):
    id: str
    x: float
    y: float
    wall_side: str = "left"
    arrival_share: float = Field(default=1.0, ge=0)


class LayoutWindow(BaseModel):
    id: str
    x: float
    y: float
    wall_side: str = "top"
    service_rate_factor: float = Field(default=1.0, gt=0)


class LayoutTable(BaseModel):
    id: str
    x: float
    y: float
    table_type: str = "four_seat"
    capacity: int = Field(default=4, ge=1)
    rotation: int = 0


class DiningLayout(BaseModel):
    doors: list[LayoutDoor]
    windows: list[LayoutWindow]
    tables: list[LayoutTable]


class SimulationConfig(BaseModel):
    num_windows: int = Field(default=4, ge=1, le=30)
    num_seats: int = Field(default=120, ge=1, le=2000)
    arrival_rate: float = Field(default=8.0, gt=0)
    service_time_mean: float = Field(default=3.0, gt=0)
    dining_time_mean: float = Field(default=20.0, gt=0)
    duration_min: int = Field(default=60, ge=5, le=360)
    seed: int = Field(default=20)
    peak_start_min: int = Field(default=15, ge=0)
    peak_end_min: int = Field(default=40, ge=0)
    peak_multiplier: float = Field(default=1.4, ge=0.5, le=5.0)
    stagger_minutes: int = Field(default=0, ge=0, le=120)
    seat_columns: int = Field(default=12, ge=4, le=40)
    layout: DiningLayout | None = None
    party_size_distribution: dict[int, float] = Field(default_factory=lambda: {1: 1.0})

    def to_data(self) -> SimulationConfigData:
        payload = self.model_dump()
        layout = payload.pop("layout")
        if layout is not None:
            payload["layout"] = DiningLayoutData(
                doors=[LayoutDoorData(**door) for door in layout["doors"]],
                windows=[LayoutWindowData(**window) for window in layout["windows"]],
                tables=[LayoutTableData(**table) for table in layout["tables"]],
            )
        return SimulationConfigData(**payload)


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class RunResponse(BaseModel):
    run_id: str
    config: dict[str, Any]
    records: list[dict[str, Any]]
    metrics: dict[str, Any]
    final_state: dict[str, Any]


class StepRequest(BaseModel):
    run_id: str | None = None
    config: SimulationConfig | None = None
    reset: bool = False


class StepResponse(BaseModel):
    run_id: str
    done: bool
    record: dict[str, Any]
    state: dict[str, Any]
    metrics: dict[str, Any] | None = None


class RecommendationRequest(BaseModel):
    base_config: SimulationConfig
    window_options: list[int] = Field(default_factory=lambda: [3, 4, 5])
    seat_options: list[int] = Field(default_factory=lambda: [100, 120, 140])
    stagger_options: list[int] = Field(default_factory=lambda: [0, 5, 10])
    top_k: int = Field(default=5, ge=1, le=20)


class ExplanationRequest(BaseModel):
    run_id: str | None = None
    baseline_config: dict[str, Any] | None = None
    best_config: dict[str, Any] | None = None
    baseline_metrics: dict[str, Any] | None = None
    best_metrics: dict[str, Any] | None = None
    root_cause_summary: str | None = None
    recommended_strategy: str | None = None
    risk_notes: list[str] = Field(default_factory=list)


class ExplanationResponse(BaseModel):
    exp_id: str
    text: str
    risk_notes: list[str]
