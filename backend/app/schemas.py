from __future__ import annotations

# 文件说明：接口模型模块：定义前端请求和后端响应的数据结构。

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


# 食堂入口坐标和到达权重，前端 LayoutEditor 会把这些字段传给后端。
class LayoutDoor(BaseModel):
    id: str
    x: float
    y: float
    wall_side: str = "left"
    arrival_share: float = Field(default=1.0, ge=0)


# 取餐窗口坐标和服务能力系数，仿真时用于排队选择和服务时长采样。
class LayoutWindow(BaseModel):
    id: str
    x: float
    y: float
    wall_side: str = "top"
    service_rate_factor: float = Field(default=1.0, gt=0)


# 餐桌坐标、容量、类型和旋转角度，后端用它计算选座与碰撞路径。
class LayoutTable(BaseModel):
    id: str
    x: float
    y: float
    table_type: str = "four_seat"
    capacity: int = Field(default=4, ge=1)
    rotation: int = 0


# 一张完整食堂平面图，包含入口、窗口和餐桌三类对象。
class DiningLayout(BaseModel):
    doors: list[LayoutDoor]
    windows: list[LayoutWindow]
    tables: list[LayoutTable]


# 校园到达模式下单个楼层的释放人数。
class CampusFloorDemand(BaseModel):
    floor: int = Field(ge=1)
    count: int = Field(ge=0)


# 校园到达模式下单栋教学楼的下课时间、释放比例和楼层人数。
class CampusBuildingDemand(BaseModel):
    building_id: str
    dismissal_minute: int = Field(default=0, ge=0)
    release_ratio: float = Field(default=1.0, ge=0, le=1)
    floors: list[CampusFloorDemand] = Field(default_factory=list)


# 校园到达模式的接口配置，启用后后端会按教学楼人数生成到达表。
class CampusDemandConfig(BaseModel):
    enabled: bool = False
    cafeteria_id: str | None = None
    source_mode: str = "manual"
    buildings: list[CampusBuildingDemand] = Field(default_factory=list)


# 前端提交的核心仿真配置；Field 约束保证接口层先挡住明显非法参数。
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
    window_choice_temperature: float = Field(default=0.0, ge=0)
    table_choice_temperature: float = Field(default=0.0, ge=0)
    preempt_seat_probability: float = Field(default=0.0, ge=0, le=1)
    seat_holder_min_party_size: int = Field(default=2, ge=1)
    movement_model: str = "path"
    movement_tick_seconds: int = Field(default=5, gt=0, le=15)
    floor_cell_size: float = Field(default=12.0, gt=0)
    floor_allow_diagonal: bool = False
    floor_static_weight: float = Field(default=1.0, ge=0)
    floor_density_weight: float = Field(default=1.2, ge=0)
    floor_dynamic_weight: float = Field(default=0.35, ge=0)
    floor_wall_weight: float = Field(default=0.6, ge=0)
    floor_inertia_weight: float = Field(default=0.25, ge=0)
    floor_group_weight: float = Field(default=0.8, ge=0)
    floor_randomness: float = Field(default=0.05, ge=0)
    dynamic_field_decay: float = Field(default=0.85, ge=0, le=1)
    dynamic_field_diffusion: float = Field(default=0.10, ge=0, le=1)
    max_movement_ticks_per_minute: int = Field(default=12, ge=1)
    queue_spacing_cells: int = Field(default=1, ge=0)
    personal_space_radius_cells: int = Field(default=1, ge=0)
    congestion_density_threshold: int = Field(default=3, ge=0)

    # 把接口层 Pydantic 模型转换为仿真层 dataclass，同时递归转换 layout/campus_demand。
    def to_data(self) -> SimulationConfigData:
        # 接口层使用 Pydantic，仿真层使用 dataclass；这里完成两者之间的显式转换。
        payload = self.model_dump()
        # layout/campus_demand 含嵌套对象，先从普通字段里取出单独转换。
        layout = payload.pop("layout")
        campus_demand = payload.pop("campus_demand")
        if layout is not None:
            # 前端传来的平面图会变成仿真层 dataclass，后续算法只依赖 dataclass 字段。
            payload["layout"] = DiningLayoutData(
                doors=[LayoutDoorData(**door) for door in layout["doors"]],
                windows=[LayoutWindowData(**window) for window in layout["windows"]],
                tables=[LayoutTableData(**table) for table in layout["tables"]],
            )
        if campus_demand is not None:
            # 校园到达数据同样显式转换，保留下课时间、释放比例和楼层人数。
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


# 参数校验接口返回结构：errors 阻止运行，warnings 只提醒潜在风险。
class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


# 完整仿真返回结构，包含 run_id、配置、全部记录、指标和最终快照。
class RunResponse(BaseModel):
    run_id: str
    config: dict[str, Any]
    records: list[dict[str, Any]]
    metrics: dict[str, Any]
    final_state: dict[str, Any]


# 单步请求结构：首次/重置带 config，后续只带 run_id 继续内存中的 runner。
class StepRequest(BaseModel):
    run_id: str | None = None
    config: SimulationConfig | None = None
    reset: bool = False


# 单步返回结构：每分钟都有 record/state，只有仿真结束时才带 metrics。
class StepResponse(BaseModel):
    run_id: str
    done: bool
    record: dict[str, Any]
    state: dict[str, Any]
    metrics: dict[str, Any] | None = None


# 校园人数接口请求结构，source_mode 决定读取实时、随机还是手动来源。
class CampusOccupancyRequest(BaseModel):
    source_mode: str = "random"
    buildings: list[str] = Field(default_factory=list)
    seed: int = 20


# 推荐接口请求结构：基准配置加候选窗口/座位/错峰/峰数范围。
class RecommendationRequest(BaseModel):
    base_config: SimulationConfig
    window_options: list[int] = Field(default_factory=lambda: [3, 4, 5])
    seat_options: list[int] = Field(default_factory=lambda: [100, 120, 140])
    stagger_options: list[int] = Field(default_factory=lambda: [0, 5, 10])
    peak_count_options: list[int] = Field(default_factory=lambda: [1])
    top_k: int = Field(default=5, ge=1, le=20)


# 解释接口请求结构：把基准/推荐指标和策略传给规则化解释模块。
class ExplanationRequest(BaseModel):
    run_id: str | None = None
    baseline_config: dict[str, Any] | None = None
    best_config: dict[str, Any] | None = None
    baseline_metrics: dict[str, Any] | None = None
    best_metrics: dict[str, Any] | None = None
    root_cause_summary: str | None = None
    recommended_strategy: str | None = None
    risk_notes: list[str] = Field(default_factory=list)


# 解释接口返回结构，包含解释编号、说明文本和风险提示。
class ExplanationResponse(BaseModel):
    exp_id: str
    text: str
    risk_notes: list[str]
