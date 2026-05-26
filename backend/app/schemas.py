from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .campus import (
    CampusBuildingDemandData,
    CampusDemandConfigData,
    CampusFloorDemandData,
)
from .simulation import (
    DiningLayoutData,
    LayoutDoorData,
    LayoutTableData,
    LayoutWindowData,
    SimulationConfigData,
)


# 布局相关模型直接对应前端 LayoutEditor 传来的入口、窗口和餐桌坐标。
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


class CampusFloorDemand(BaseModel):
    floor: int = Field(ge=1)
    count: int = Field(ge=0)


class CampusBuildingDemand(BaseModel):
    building_id: str
    dismissal_minute: int = Field(default=0, ge=0)
    release_ratio: float = Field(default=1.0, ge=0, le=1)
    floors: list[CampusFloorDemand] = Field(default_factory=list)


class CampusDemandConfig(BaseModel):
    enabled: bool = False
    cafeteria_id: str | None = None
    source_mode: str = "manual"
    buildings: list[CampusBuildingDemand] = Field(default_factory=list)


# SimulationConfig 是前端提交的核心配置；Field 用于限制接口入参范围。
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
    campus_demand: CampusDemandConfig | None = None

    def to_data(self) -> SimulationConfigData:
        # 接口层使用 Pydantic，仿真层使用 dataclass；这里完成两者之间的显式转换。
        payload = self.model_dump()
        layout = payload.pop("layout")
        campus_demand = payload.pop("campus_demand")
        if layout is not None:
            payload["layout"] = DiningLayoutData(
                doors=[LayoutDoorData(**door) for door in layout["doors"]],
                windows=[LayoutWindowData(**window) for window in layout["windows"]],
                tables=[LayoutTableData(**table) for table in layout["tables"]],
            )
        if campus_demand is not None:
            payload["campus_demand"] = CampusDemandConfigData(
                enabled=campus_demand["enabled"],
                cafeteria_id=campus_demand["cafeteria_id"],
                source_mode=campus_demand["source_mode"],
                buildings=[
                    CampusBuildingDemandData(
                        building_id=building["building_id"],
                        dismissal_minute=building["dismissal_minute"],
                        release_ratio=building["release_ratio"],
                        floors=[
                            CampusFloorDemandData(floor=floor["floor"], count=floor["count"])
                            for floor in building["floors"]
                        ],
                    )
                    for building in campus_demand["buildings"]
                ],
            )
        return SimulationConfigData(**payload)


# 参数校验接口返回：valid 表示是否可运行，warnings 用于提示潜在瓶颈。
class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


# 完整仿真返回：包含全部过程记录、最终指标和最终状态快照。
class RunResponse(BaseModel):
    run_id: str
    config: dict[str, Any]
    records: list[dict[str, Any]]
    metrics: dict[str, Any]
    final_state: dict[str, Any]


# 单步请求：首次或重置时带 config，后续请求只需 run_id 继续同一个 runner。
class StepRequest(BaseModel):
    run_id: str | None = None
    config: SimulationConfig | None = None
    reset: bool = False


# 单步返回：record 是本分钟记录，state 是地图实时状态，metrics 只在结束时返回。
class StepResponse(BaseModel):
    run_id: str
    done: bool
    record: dict[str, Any]
    state: dict[str, Any]
    metrics: dict[str, Any] | None = None


class CampusOccupancyRequest(BaseModel):
    source_mode: str = "random"
    buildings: list[str] = Field(default_factory=list)
    seed: int = 20


# 推荐接口请求：base_config 是基准方案，其余列表是后端枚举候选范围。
class RecommendationRequest(BaseModel):
    base_config: SimulationConfig
    window_options: list[int] = Field(default_factory=lambda: [3, 4, 5])
    seat_options: list[int] = Field(default_factory=lambda: [100, 120, 140])
    stagger_options: list[int] = Field(default_factory=lambda: [0, 5, 10])
    peak_count_options: list[int] = Field(default_factory=lambda: [1])
    top_k: int = Field(default=5, ge=1, le=20)


# 解释接口请求：把基准/推荐指标和策略传给规则化解释模块。
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
