from __future__ import annotations

# 文件说明：核心仿真模块：按分钟推进学生到达、排队、取餐、等座、入座和离开。

import heapq
import math
import random
import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .campus import (
    CampusBuildingDemandData,
    CampusDemandConfigData,
    CampusFloorDemandData,
    build_campus_arrival_schedule,
    build_mixed_campus_arrival_schedule,
    known_building_ids,
    known_cafeteria_ids,
)
from .pedestrian.agents import AgentState
from .pedestrian.adapter import merge_timelines, static_floor_field_path
from .pedestrian.engine import PedestrianEngine

# 核心离散时间仿真模块：所有学生、队列、窗口、餐桌和指标都在这里推进。
# 展示时重点说明 DiningSimulationRunner.step() 的分钟级顺序，而不是前端展示细节。
WALKING_SPEED_UNITS_PER_SEC = 38.0
MIN_WALKING_DURATION_SEC = 3
MAX_WALKING_DURATION_SEC = 45
TIMELINE_BASE_PLAYBACK_MS = 720
WALKING_PLAYBACK_MS_PER_SEC = 90
MIN_WALKING_PLAYBACK_MS = 320
MAX_WALKING_PLAYBACK_MS = 900
PATH_OBSTACLE_PADDING = 7
MOVEMENT_QUALITY_PRESET_ORDER = ["fast", "balanced", "quality"]
MOVEMENT_QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "label": "快速 Fast",
        "role": "high_speed_baseline",
        "expected_use_case": "批量实验、参数搜索、课堂演示",
        "settings": {
            "movement_model": "path",
            "advanced_movement_coupling": False,
            "max_movement_ticks_per_minute": 1,
            "floor_cell_size": 18.0,
            "window_choice_temperature": 0.0,
            "window_switch_cooldown_min": 0,
        },
    },
    "balanced": {
        "label": "平衡 Balanced",
        "role": "geometry_aware_baseline",
        "expected_use_case": "常规实验报告、较大规模场景",
        "settings": {
            "movement_model": "static_floor_field",
            "advanced_movement_coupling": False,
            "max_movement_ticks_per_minute": 1,
            "floor_cell_size": 14.0,
            "window_choice_temperature": 0.6,
            "window_switch_cooldown_min": 0,
        },
    },
    "quality": {
        "label": "质量 Quality",
        "role": "spatially_coupled_ca",
        "expected_use_case": "真实性评估、小规模精细分析、拥堵热点研究",
        "settings": {
            "movement_model": "advanced_floor_field",
            "advanced_movement_coupling": True,
            "max_movement_ticks_per_minute": 12,
            "floor_cell_size": 12.0,
            "window_choice_temperature": 0.45,
            "window_switch_cooldown_min": 2,
            "window_switch_threshold_min": 1.5,
            "window_switch_penalty_min": 0.5,
        },
    },
}
MOVEMENT_PRESET_FIELDS = {
    "movement_model",
    "advanced_movement_coupling",
    "max_movement_ticks_per_minute",
    "floor_cell_size",
    "window_choice_temperature",
    "window_switch_cooldown_min",
    "window_switch_threshold_min",
    "window_switch_penalty_min",
}


# 前端布局编辑器传来的入口、窗口、餐桌，后端用坐标计算排队选择和入座路径。
@dataclass(frozen=True)
# 单个入口的坐标、墙面方向和学生到达分流比例。
class LayoutDoorData:
    id: str
    x: float
    y: float
    wall_side: str = "left"
    arrival_share: float = 1.0


@dataclass(frozen=True)
# 单个取餐窗口的坐标、墙面方向和服务速度系数。
class LayoutWindowData:
    id: str
    x: float
    y: float
    wall_side: str = "top"
    service_rate_factor: float = 1.0


@dataclass(frozen=True)
# 单张餐桌的几何位置、容量、类型和旋转角度。
class LayoutTableData:
    id: str
    x: float
    y: float
    table_type: str = "four_seat"
    capacity: int = 4
    rotation: int = 0


@dataclass(frozen=True)
# 食堂地面边界；advanced floor field 用它决定 CA 网格尺寸。
class LayoutFloorData:
    width: float = 360.0
    height: float = 640.0
    x: float = 0.0
    y: float = 0.0


@dataclass(frozen=True)
# 一份完整食堂平面布局，后端按它计算排队距离和入座路径。
class DiningLayoutData:
    floor: LayoutFloorData | None = None
    doors: list[LayoutDoorData] = field(default_factory=list)
    windows: list[LayoutWindowData] = field(default_factory=list)
    tables: list[LayoutTableData] = field(default_factory=list)


# SimulationConfigData 是仿真内部配置，来自 schemas.SimulationConfig.to_data()。
@dataclass(frozen=True)
# 仿真内部配置对象，合并手动到达、校园到达、服务时间和布局参数。
class SimulationConfigData:
    num_windows: int = 4
    num_seats: int = 120
    arrival_rate: float = 8.0
    service_time_mean: float = 0.5
    dining_time_mean: float = 20.0
    duration_min: int = 60
    simulation_start_minute: int = 0
    meal_period: str = "lunch"
    seed: int = 20
    peak_start_min: int = 15
    peak_end_min: int = 40
    peak_multiplier: float = 1.4
    stagger_minutes: int = 0
    seat_columns: int = 12
    layout: DiningLayoutData | None = None
    party_size_distribution: dict[int, float] = field(default_factory=lambda: {1: 1.0})
    campus_demand: CampusDemandConfigData | None = None
    window_choice_temperature: float = 0.0
    window_switch_cooldown_min: int = 0
    window_switch_threshold_min: float = 2.0
    window_switch_penalty_min: float = 0.5
    table_choice_temperature: float = 0.0
    preempt_seat_probability: float = 0.0
    seat_holder_min_party_size: int = 2
    movement_quality_preset: str | None = None
    movement_model: str = "path"
    movement_tick_seconds: int = 5
    floor_cell_size: float = 12.0
    floor_allow_diagonal: bool = False
    floor_static_weight: float = 1.0
    floor_density_weight: float = 1.2
    floor_dynamic_weight: float = 0.35
    floor_wall_weight: float = 0.6
    floor_inertia_weight: float = 0.25
    floor_group_weight: float = 0.8
    floor_randomness: float = 0.05
    dynamic_field_decay: float = 0.85
    dynamic_field_diffusion: float = 0.10
    max_movement_ticks_per_minute: int = 12
    queue_spacing_cells: int = 1
    personal_space_radius_cells: int = 1
    congestion_density_threshold: int = 3
    advanced_movement_coupling: bool = True
    entry_spawn_radius_cells: int = 3

    # 基于当前不可变配置生成字段替换后的新配置，推荐模块用于构造候选方案。
    def with_updates(self, **updates: Any) -> "SimulationConfigData":
        return replace(self, **updates)


def apply_movement_quality_preset(
    config: SimulationConfigData,
    explicit_fields: set[str] | None = None,
) -> SimulationConfigData:
    preset_id = config.movement_quality_preset
    if not preset_id or preset_id not in MOVEMENT_QUALITY_PRESETS:
        return config
    explicit = explicit_fields or set()
    updates = {
        key: value
        for key, value in MOVEMENT_QUALITY_PRESETS[preset_id]["settings"].items()
        if key not in explicit
    }
    return replace(config, **updates) if updates else config


def movement_quality_preset_metadata(preset_id: str | None) -> dict[str, Any]:
    if not preset_id or preset_id not in MOVEMENT_QUALITY_PRESETS:
        return {
            "quality_preset": preset_id or "",
            "preset_label": "",
            "preset_role": "",
            "expected_use_case": "",
        }
    preset = MOVEMENT_QUALITY_PRESETS[preset_id]
    return {
        "quality_preset": preset_id,
        "preset_label": preset["label"],
        "preset_role": preset["role"],
        "expected_use_case": preset["expected_use_case"],
    }


# Student 表示单个学生，从到达、排队、服务、入座到离开都会记录时间点。
@dataclass
# 单个学生的生命周期记录，保存到达、排队、服务、入座和离开时间。
class Student:
    student_id: int
    party_id: int
    arrival_time: int
    queue_enter_time: int
    door_index: int = 0
    service_start_time: int | None = None
    service_end_time: int | None = None
    service_start_time_sec: int | None = None
    service_end_time_sec: int | None = None
    seat_time: int | None = None
    leave_time: int | None = None
    window_index: int | None = None


# DiningParty 表示结伴就餐小组；同组成员都取餐完成后才进入等座队列。
@dataclass
# 结伴就餐小组，组内成员都取餐完成后才会作为整体等座。
class DiningParty:
    party_id: int
    arrival_time: int
    door_index: int
    student_ids: list[int]
    ready_time: int | None = None
    seat_assignment_time: int | None = None
    seat_time: int | None = None
    table_index: int | None = None
    reserved_table_index: int | None = None

    @property
    # 小组人数直接由成员列表长度决定。
    def size(self) -> int:
        return len(self.student_ids)


@dataclass
# 窗口当前服务中的学生和剩余服务分钟数，支持小数分钟以表达秒级服务。
class WindowService:
    student: Student
    remaining: float


@dataclass
# 已入座学生对应的餐桌位置和剩余就餐分钟数。
class DiningSeat:
    student: Student
    remaining: int
    table_index: int | None = None


@dataclass
# 小组从取餐窗口走向餐桌的后端时间线状态。
class WalkingSeatTransfer:
    party: DiningParty
    table_index: int
    window_index: int
    dining_remaining: int
    start_time_sec: int
    arrive_time_sec: int
    path: list[dict[str, float]]


# StepRecord 是每推进一分钟返回给前端和数据库保存的过程记录。
@dataclass(frozen=True)
# 每分钟 StepRecord 保存前端实时展示和 SQLite 持久化所需的过程状态。
class StepRecord:
    run_id: str
    t: int
    clock_minute: int
    arrived_count: int
    queue_lengths: list[int]
    served_count: int
    seated_count: int
    left_count: int
    empty_seats: int
    reserved_seats: int
    available_seats: int
    waiting_for_seat_count: int
    total_arrived: int
    total_served: int
    total_seated: int
    total_left: int
    avg_wait_so_far: float
    snapshot: dict[str, Any] = field(default_factory=dict)


# MetricsSummary 是仿真结束后的指标汇总，结果分析页和推荐模块都读取这些字段。
@dataclass(frozen=True)
# 仿真结束后的指标汇总，覆盖等待、吞吐、利用率和瓶颈分类。
class MetricsSummary:
    run_id: str
    avg_wait: float
    avg_queue_wait: float
    avg_seat_wait: float
    peak_queue: int
    peak_waiting_for_seat: int
    throughput: int
    total_arrived: int
    total_left: int
    seat_utilization: float
    window_utilization: float
    bottleneck_type: str
    chart_data: dict[str, list[Any]]
    active_window_utilization: float = 0.0
    avg_party_gather_wait: float = 0.0
    avg_party_seat_wait: float = 0.0
    avg_post_service_to_seat_time: float = 0.0
    party_window_split_count: int = 0
    party_split_count: int = 0
    shared_table_count: int = 0
    blocked_party_count: int = 0
    fragmented_seats: int = 0
    table_utilization_by_type: dict[str, float] = field(default_factory=dict)
    avg_walking_time: float = 0.0
    movement_conflict_count: int = 0
    avg_stuck_ticks: float = 0.0
    max_density: int = 0


@dataclass(frozen=True)
# 一次完整仿真的返回对象，包含过程记录、最终指标和最终快照。
class SimulationResult:
    run_id: str
    config: SimulationConfigData
    records: list[StepRecord]
    metrics: MetricsSummary
    final_state: dict[str, Any]


# validate_config() 校验输入参数并返回错误或提示。
def validate_config(config: SimulationConfigData) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if config.movement_quality_preset and config.movement_quality_preset not in MOVEMENT_QUALITY_PRESETS:
        errors.append("movement_quality_preset 必须是 fast、balanced 或 quality。")
    config = apply_movement_quality_preset(config)
    layout = _effective_layout(config)
    if config.num_windows < 1 or config.num_windows > 30:
        errors.append("开放窗口数应在 1 到 30 之间。")
    if config.num_seats < 1 or config.num_seats > 2000:
        errors.append("座位数应在 1 到 2000 之间。")
    if config.layout is not None:
        if not config.layout.doors:
            errors.append("布局至少需要 1 个入口。")
        if not config.layout.windows:
            errors.append("布局至少需要 1 个取餐窗口。")
        if not config.layout.tables:
            errors.append("布局至少需要 1 张餐桌。")
        if any(window.service_rate_factor <= 0 for window in config.layout.windows):
            errors.append("窗口服务能力系数必须大于 0。")
        if any(table.capacity < 1 for table in config.layout.tables):
            errors.append("餐桌容量必须大于 0。")
        layout_seats = sum(table.capacity for table in config.layout.tables)
        if layout_seats != config.num_seats:
            warnings.append(f"布局座位容量为 {layout_seats}，仿真将按布局容量运行。")
        if len(config.layout.windows) != config.num_windows:
            warnings.append(f"布局开放窗口为 {len(config.layout.windows)} 个，仿真将按布局窗口运行。")
    if config.simulation_start_minute < 0 or config.simulation_start_minute >= 24 * 60:
        errors.append("simulation_start_minute 必须是 0 到 1439 之间的分钟数。")
    if config.meal_period not in {"breakfast", "lunch", "dinner", "weekend"}:
        errors.append("meal_period 必须是 breakfast、lunch、dinner 或 weekend。")
    if config.arrival_rate <= 0:
        errors.append("平均每分钟到达人数必须大于 0。")
    if config.service_time_mean <= 0:
        errors.append("平均打饭时长必须大于 0。")
    if config.dining_time_mean <= 0:
        errors.append("平均就餐时长必须大于 0。")
    if config.window_choice_temperature < 0:
        errors.append("窗口选择温度不能为负数。")
    if config.window_switch_cooldown_min < 0:
        errors.append("窗口换队冷却分钟不能为负数。")
    if config.window_switch_threshold_min < 0:
        errors.append("窗口换队阈值不能为负数。")
    if config.window_switch_penalty_min < 0:
        errors.append("窗口换队惩罚不能为负数。")
    if config.entry_spawn_radius_cells < 1:
        errors.append("入口注入半径必须至少为 1 个网格。")
    if config.table_choice_temperature < 0:
        errors.append("餐桌选择温度不能为负数。")
    if config.preempt_seat_probability < 0 or config.preempt_seat_probability > 1:
        errors.append("预占座概率应在 0 到 1 之间。")
    if config.seat_holder_min_party_size < 1:
        errors.append("预占座最小小组人数必须大于等于 1。")
    if config.movement_model not in {"path", "static_floor_field", "advanced_floor_field"}:
        errors.append("movement_model 必须是 path、static_floor_field 或 advanced_floor_field。")
    if config.movement_tick_seconds <= 0 or config.movement_tick_seconds > 15:
        errors.append("movement_tick_seconds 必须大于 0 且不超过 15。")
    if config.floor_cell_size <= 0:
        errors.append("floor_cell_size 必须大于 0。")
    movement_weights = {
        "floor_static_weight": config.floor_static_weight,
        "floor_density_weight": config.floor_density_weight,
        "floor_dynamic_weight": config.floor_dynamic_weight,
        "floor_wall_weight": config.floor_wall_weight,
        "floor_inertia_weight": config.floor_inertia_weight,
        "floor_group_weight": config.floor_group_weight,
        "floor_randomness": config.floor_randomness,
    }
    for name, value in movement_weights.items():
        if value < 0:
            errors.append(f"{name} 必须大于等于 0。")
    if config.dynamic_field_decay < 0 or config.dynamic_field_decay > 1:
        errors.append("dynamic_field_decay 必须在 0 到 1 之间。")
    if config.dynamic_field_diffusion < 0 or config.dynamic_field_diffusion > 1:
        errors.append("dynamic_field_diffusion 必须在 0 到 1 之间。")
    if config.duration_min < 5 or config.duration_min > 360:
        errors.append("手动到达持续时间应在 5 到 360 分钟之间。")
    if config.peak_start_min >= config.peak_end_min:
        warnings.append("高峰开始时间不早于结束时间，将按普通到达人数运行。")
    if config.num_seats < config.num_windows * 6:
        warnings.append("座位数相对窗口数偏少，可能出现入座瓶颈。")
    if config.arrival_rate * config.service_time_mean > config.num_windows * 1.2:
        warnings.append("到达强度高于窗口服务能力，可能形成长队。")
    if config.campus_demand and config.campus_demand.enabled:
        campus = config.campus_demand
        if campus.cafeteria_id not in known_cafeteria_ids():
            errors.append("校园到达模式需要选择有效食堂。")
        if campus.source_mode not in {"live", "random", "manual"}:
            errors.append("校园人数来源必须是 live、random 或 manual。")
        residential_enabled = bool(
            campus.residential_sources
            or (campus.population_pool is not None and campus.population_pool.enabled)
        )
        if not campus.buildings and not residential_enabled:
            errors.append("校园到达模式至少需要一栋教学楼或宿舍来源。")
        valid_buildings = known_building_ids()
        total_people = 0
        for building in campus.buildings:
            if building.building_id not in valid_buildings:
                errors.append(f"未知教学楼：{building.building_id}。")
            if building.release_ratio < 0 or building.release_ratio > 1:
                errors.append("下课释放比例应在 0 到 1 之间。")
            if building.dismissal_minute < 0:
                errors.append("下课时间不能为负数。")
            if not building.floors:
                warnings.append(f"{building.building_id} 没有楼层人数。")
            for floor in building.floors:
                if floor.floor < 1:
                    errors.append("楼层编号必须大于等于 1。")
                if floor.count < 0:
                    errors.append("楼层人数不能为负数。")
                total_people += max(0, floor.count)
        if total_people == 0:
            warnings.append("校园到达模式当前楼层人数为 0，仿真可能没有到达学生。")
    party_distribution = _normalized_party_distribution(config.party_size_distribution)
    if not party_distribution:
        errors.append("结伴人数分布至少需要一个正权重。")
    elif layout.tables and max(size for size, _weight in party_distribution) > max(table.capacity for table in layout.tables):
        errors.append("结伴人数不能超过最大单桌容量。")
    if sum(table.capacity for table in layout.tables) < len(layout.windows):
        warnings.append("布局座位容量相对窗口数偏少，可能出现入座瓶颈。")
    return errors, warnings


def normalize_arrival_schedule_to_simulation_start(
    schedule: dict[int, int] | dict[int, float],
    simulation_start_minute: int,
) -> dict[int, int] | dict[int, float]:
    """把真实钟点分钟转换成 runner 内部从 0 开始的相对分钟。"""
    start_minute = max(0, int(simulation_start_minute))
    normalized: dict[int, int | float] = {}
    for absolute_minute, count in schedule.items():
        relative_minute = int(absolute_minute) - start_minute
        if relative_minute < 0:
            continue
        normalized[relative_minute] = normalized.get(relative_minute, 0) + count
    return dict(sorted(normalized.items()))


# 完整仿真只是循环调用 runner.step()，因此与实时单步接口使用同一套核心逻辑。
# run_simulation() 循环调用 step 直到仿真结束。
def run_simulation(config: SimulationConfigData, run_id: str | None = None) -> SimulationResult:
    runner = DiningSimulationRunner(config, run_id=run_id)
    while not runner.done:
        runner.step()
    return runner.result()


def run_layout_ablation_snapshot(
    config: SimulationConfigData,
    *,
    baseline_layout: DiningLayoutData,
    optimized_layout: DiningLayoutData,
    steps: int,
) -> dict[str, Any]:
    def run_snapshot(layout: DiningLayoutData) -> dict[str, Any]:
        layout_config = config.with_updates(
            layout=layout,
            num_windows=len(layout.windows),
            num_seats=sum(table.capacity for table in layout.tables),
        )
        runner = DiningSimulationRunner(layout_config)
        record: StepRecord | None = None
        for _ in range(max(1, int(steps))):
            if runner.done:
                break
            record = runner.step()
        snapshot = record.snapshot if record is not None else {}
        totals = snapshot.get("totals", {})
        queue_lengths = snapshot.get("queue_lengths", [])
        movement = snapshot.get("movement_metrics", {})
        return {
            "entry_waiting_count": int(snapshot.get("entry_waiting_count", 0) or 0),
            "indoor_agents": len(snapshot.get("pedestrian_agents", []) or []),
            "queue_total": int(sum(queue_lengths)),
            "served": int(totals.get("served", 0) or 0),
            "seated": int(totals.get("seated", 0) or 0),
            "total_arrived": int(totals.get("arrived", 0) or 0),
            "movement_conflict_count": int(movement.get("movement_conflict_count", 0) or 0),
            "avg_stuck_ticks": float(movement.get("avg_stuck_ticks", 0.0) or 0.0),
            "max_density": int(movement.get("max_density", 0) or 0),
        }

    baseline = run_snapshot(baseline_layout)
    optimized = run_snapshot(optimized_layout)
    delta = {
        key: optimized[key] - baseline[key]
        for key in baseline
        if isinstance(baseline[key], (int, float)) and isinstance(optimized.get(key), (int, float))
    }
    return {"baseline": baseline, "optimized": optimized, "delta": delta}


# DiningSimulationRunner 保存一次仿真的全部动态状态：队列、窗口、等座、行走、入座和记录。
# 每次 step() 都在这个对象内原地推进状态。
class DiningSimulationRunner:
    # 校验配置并初始化随机数、队列、窗口、餐桌占用和统计计数器。
    def __init__(self, config: SimulationConfigData, run_id: str | None = None):
        errors, _ = validate_config(config)
        if errors:
            raise ValueError("; ".join(errors))
        self.config = config
        self.layout = _effective_layout(config)
        self.total_seat_capacity = sum(table.capacity for table in self.layout.tables)
        self.run_id = run_id or uuid.uuid4().hex
        self.arrival_rng = random.Random(config.seed + 1009)
        self.duration_rng = random.Random(config.seed + 2003)
        self.choice_rng = random.Random(config.seed + 3001)
        self.movement_rng = random.Random(config.seed + 4001)
        self.entry_rng = random.Random(config.seed + 5003)
        self.current_minute = 0
        self.next_student_id = 1
        self.next_party_id = 1
        # 校园模式在初始化时一次性生成到达表，后续每分钟只查 schedule。
        self.campus_arrival_schedule = self._build_campus_arrival_schedule()
        if config.campus_demand and config.campus_demand.enabled:
            self.campus_arrival_schedule = normalize_arrival_schedule_to_simulation_start(
                self.campus_arrival_schedule,
                config.simulation_start_minute,
            )
        self.arrival_horizon_minute = self._arrival_horizon_minute()
        # 下面这些列表就是仿真“现场”：每分钟都会原地更新。
        self.queues: list[list[Student]] = [[] for _ in range(len(self.layout.windows))]
        self.windows: list[WindowService | None] = [None for _ in range(len(self.layout.windows))]
        self.waiting_for_seat: list[DiningParty] = []
        self.walking_to_seat: list[WalkingSeatTransfer] = []
        self.seated: list[DiningSeat] = []
        self.waiting_to_queue_student_ids: set[int] = set()
        self.pending_entry_students: list[tuple[int, int, Student]] = []
        self.next_entry_sequence = 0
        self.entered_this_minute = 0
        self.table_occupied_seats: list[int] = [0 for _ in self.layout.tables]
        self.table_reserved_seats: list[int] = [0 for _ in self.layout.tables]
        self.table_party_ids: list[set[int]] = [set() for _ in self.layout.tables]
        # students/parties 是全局索引，快照、指标和结伴逻辑都从这里回查。
        self.records: list[StepRecord] = []
        self.students: dict[int, Student] = {}
        self.parties: dict[int, DiningParty] = {}
        self.total_served = 0
        self.total_seated = 0
        self.total_left = 0
        self.window_busy_minutes = 0
        self.seat_occupied_minutes = 0
        self.metrics_counters: dict[str, int] = {
            "party_split_count": 0,
            "party_window_split_count": 0,
            "shared_table_count": 0,
            "blocked_party_count": 0,
        }
        self.blocked_party_ids: set[int] = set()
        self.party_window_split_party_ids: set[int] = set()
        self.window_switch_minutes: dict[int, int] = {}
        self.peak_fragmented_seats = 0
        self.pedestrian_engine = (
            PedestrianEngine(self.layout, config, self.movement_rng)
            if config.movement_model == "advanced_floor_field"
            else None
        )

    @property
    # 到达期结束且系统内没有排队、服务、等座、行走或就餐学生时结束。
    def done(self) -> bool:
        return self.current_minute >= self.arrival_horizon_minute and not self._has_active_students()

    # step() 推进一分钟仿真，是实时运行最核心的单步方法。
    def step(self) -> StepRecord:
        # 单步顺序用于展示说明：
        # 1. 吃完离开；2. 推进窗口服务；3. 完成取餐的小组进入等座；
        # 4. 分配餐桌；5. 生成新到达；6. 选择窗口排队；
        # 7. 空闲窗口开始服务；8. 推进入座行走；9. 生成 StepRecord。
        if self.done:
            raise RuntimeError("仿真已经结束。")

        minute = self.current_minute
        step_start_sec = minute * 60
        step_end_sec = (minute + 1) * 60
        timeline_events: list[dict[str, Any]] = []
        # 先处理旧状态，再生成新到达，避免同一分钟新来的学生立即“吃完”或越级入座。
        left_count = self._advance_dining(minute)
        window_elapsed: dict[int, float] = {}
        served_students = self._advance_windows(minute, elapsed_by_window=window_elapsed)
        self._move_ready_parties_to_seat_wait(served_students, minute)
        self._seat_waiting_students(minute, timeline_events=timeline_events)
        self.entered_this_minute = 0
        arrivals = self._generate_arrivals(minute)
        self._enqueue_arrivals(arrivals)
        started_windows = self._start_window_services(minute, start_offsets=window_elapsed)
        post_arrival_served = self._advance_windows(
            minute,
            window_indices=started_windows,
            start_offsets=window_elapsed,
            elapsed_by_window=window_elapsed,
        )
        if post_arrival_served:
            served_students.extend(post_arrival_served)
            self._move_ready_parties_to_seat_wait(post_arrival_served, minute)
        pedestrian_timeline: dict[str, Any] | None = None
        if self.pedestrian_engine is not None:
            pedestrian_result = self.pedestrian_engine.run_for_minute(
                step_start_sec,
                step_end_sec,
                before_tick=(self._admit_due_entry_students if self._uses_advanced_movement_coupling() else None),
            )
            pedestrian_timeline = pedestrian_result.get("timeline")
        if self._uses_advanced_movement_coupling():
            self._admit_students_who_reached_window_queue(minute)
            started_windows = self._start_window_services(minute, start_offsets=window_elapsed)
            post_movement_served = self._advance_windows(
                minute,
                window_indices=started_windows,
                start_offsets=window_elapsed,
                elapsed_by_window=window_elapsed,
            )
            if post_movement_served:
                served_students.extend(post_movement_served)
                self._move_ready_parties_to_seat_wait(post_movement_served, minute)
        seated_count = self._advance_walking_to_seats(step_end_sec)
        self.peak_fragmented_seats = max(self.peak_fragmented_seats, self._fragmented_seats())

        self.seat_occupied_minutes += len(self.seated)

        self.current_minute += 1
        # 记录中的 t 是推进完成后的分钟数，方便前端把第 1 条记录显示为第 1 分钟。
        record = self._build_record(
            t=self.current_minute,
            arrived_count=len(arrivals),
            served_count=len(served_students),
            seated_count=seated_count,
            left_count=left_count,
            timeline=merge_timelines(
                self._build_step_timeline(step_start_sec, step_end_sec, timeline_events),
                pedestrian_timeline,
            ),
        )
        self.records.append(record)
        return record

    # result() 在仿真结束后汇总指标并生成最终返回对象。
    def result(self) -> SimulationResult:
        metrics = self._build_metrics()
        return SimulationResult(
            run_id=self.run_id,
            config=self.config,
            records=list(self.records),
            metrics=metrics,
            final_state=self._snapshot(),
        )

    # 推进入座学生的就餐剩余时间，并释放已吃完学生占用的餐桌座位。
    def _advance_dining(self, minute: int) -> int:
        still_seated: list[DiningSeat] = []
        left_count = 0
        for seat in self.seated:
            seat.remaining -= 1
            if seat.remaining <= 0:
                seat.student.leave_time = minute
                if seat.table_index is not None:
                    self.table_occupied_seats[seat.table_index] = max(0, self.table_occupied_seats[seat.table_index] - 1)
                    party_id = seat.student.party_id
                    # 同组最后一个人离开该桌后，才能从桌面 party 集合中移除这个小组。
                    if not any(
                        other.student.party_id == party_id and other.table_index == seat.table_index and other.remaining > 0
                        for other in self.seated
                    ):
                        self.table_party_ids[seat.table_index].discard(party_id)
                self.total_left += 1
                left_count += 1
                if self.pedestrian_engine is not None:
                    self.pedestrian_engine.set_agent_exited(seat.student.student_id)
            else:
                still_seated.append(seat)
        self.seated = still_seated
        return left_count

    # 按秒级服务时长推进窗口；同一分钟内窗口可以连续服务多名学生。
    def _advance_windows(
        self,
        minute: int,
        window_indices: list[int] | None = None,
        start_offsets: dict[int, float] | None = None,
        elapsed_by_window: dict[int, float] | None = None,
    ) -> list[Student]:
        served: list[Student] = []
        indices = range(len(self.windows)) if window_indices is None else window_indices
        for idx in indices:
            elapsed = max(0.0, min(1.0, (start_offsets or {}).get(idx, 0.0)))
            busy_elapsed = 0.0
            while elapsed < 1.0:
                service = self.windows[idx]
                if service is None:
                    if not self.queues[idx]:
                        break
                    self._start_single_window_service(idx, start_time_minute=minute + elapsed)
                    service = self.windows[idx]
                    if service is None:
                        break
                available = 1.0 - elapsed
                consumed = min(max(0.0, service.remaining), available)
                service.remaining -= consumed
                elapsed += consumed
                busy_elapsed += consumed
                if service.remaining > 1e-9:
                    break
                end_time_sec = int(round((minute + elapsed) * 60))
                service.student.service_end_time_sec = end_time_sec
                service.student.service_end_time = math.ceil(end_time_sec / 60)
                served.append(service.student)
                self.windows[idx] = None
                self.total_served += 1
                if self.pedestrian_engine is not None:
                    self.pedestrian_engine.set_agent_waiting_group(service.student.student_id)
            self.window_busy_minutes += busy_elapsed
            if elapsed_by_window is not None:
                elapsed_by_window[idx] = elapsed
        return served

    # 查看完成取餐的学生所属小组；全员完成后把小组放入等座队列。
    def _move_ready_parties_to_seat_wait(self, served_students: list[Student], minute: int) -> None:
        for student in served_students:
            party = self.parties[student.party_id]
            if party.ready_time is not None:
                continue
            members = [self.students[student_id] for student_id in party.student_ids]
            # 结伴小组必须等所有成员都取餐结束后，才整体进入等座队列。
            if all(member.service_end_time is not None for member in members):
                party.ready_time = minute
                self.waiting_for_seat.append(party)
                if self.pedestrian_engine is not None:
                    for student_id in party.student_ids:
                        self.pedestrian_engine.set_agent_waiting_group(student_id)

    # 为等座小组尝试锁定餐桌；锁定成功后生成走向餐桌的时间线事件。
    def _seat_waiting_students(self, minute: int, timeline_events: list[dict[str, Any]] | None = None) -> int:
        walking_count = 0
        still_waiting: list[DiningParty] = []
        for party in self.waiting_for_seat:
            table_index = self._reserved_table_for_party(party)
            uses_preemptive_reservation = table_index is not None
            if table_index is None:
                table_index = self._choose_table_for_party(party)
            if table_index is None:
                # 找不到能容纳整组的餐桌时继续等待，并记录 blocked_party_count 指标。
                still_waiting.append(party)
                self.blocked_party_ids.add(party.party_id)
                self.metrics_counters["blocked_party_count"] = len(self.blocked_party_ids)
                continue
            own_reserved = party.size if uses_preemptive_reservation else 0
            occupied_before = self.table_occupied_seats[table_index] + max(
                0,
                self.table_reserved_seats[table_index] - own_reserved,
            )
            if occupied_before > 0:
                self.metrics_counters["shared_table_count"] += 1
            remaining = self._sample_duration(self.config.dining_time_mean)
            transfer = self._start_walking_to_seat(party, table_index, remaining, minute)
            self.walking_to_seat.append(transfer)
            if self.pedestrian_engine is not None:
                self.pedestrian_engine.set_party_target_table(party, table_index)
            # 先预留座位，避免同一分钟后面的等座小组抢到同一张桌子的同一批座位。
            if not uses_preemptive_reservation:
                self.table_reserved_seats[table_index] += party.size
            party.table_index = table_index
            party.seat_assignment_time = minute
            walking_count += party.size
            if timeline_events is not None and not self._uses_advanced_movement_coupling():
                timeline_events.append(self._walking_event_snapshot(transfer, step_start_sec=minute * 60))
        self.waiting_for_seat = still_waiting
        return walking_count

    # 默认关闭的预占座实验：满足人数和概率条件时，为整个小组预留同一张桌的容量。
    def _maybe_preempt_seat_for_party(self, party: DiningParty) -> None:
        if self.config.preempt_seat_probability <= 0:
            return
        if party.size < self.config.seat_holder_min_party_size:
            return
        if self.choice_rng.random() >= self.config.preempt_seat_probability:
            return
        table_index = self._choose_table_for_party(party)
        if table_index is None:
            return
        table = self.layout.tables[table_index]
        occupied = self.table_occupied_seats[table_index] + self.table_reserved_seats[table_index]
        if table.capacity - occupied < party.size:
            return
        self.table_reserved_seats[table_index] += party.size
        party.reserved_table_index = table_index

    # 若小组已提前预留餐桌，等取餐完成后优先使用该桌，不再次增加 reserved seats。
    def _reserved_table_for_party(self, party: DiningParty) -> int | None:
        if party.reserved_table_index is None:
            return None
        if party.reserved_table_index < 0 or party.reserved_table_index >= len(self.layout.tables):
            return None
        if not self._table_has_movement_target(party.reserved_table_index):
            return None
        table = self.layout.tables[party.reserved_table_index]
        if self.table_reserved_seats[party.reserved_table_index] < party.size:
            return None
        if self.table_occupied_seats[party.reserved_table_index] + self.table_reserved_seats[party.reserved_table_index] > table.capacity:
            return None
        return party.reserved_table_index

    # 根据最后完成取餐的窗口和目标餐桌生成行走路径与到达时间。
    def _start_walking_to_seat(
        self,
        party: DiningParty,
        table_index: int,
        dining_remaining: int,
        minute: int,
    ) -> WalkingSeatTransfer:
        window_index = self._party_reference_window_index(party)
        start = self._window_service_point(self.layout.windows[window_index])
        table = self.layout.tables[table_index]
        end = {"x": round(float(table.x), 1), "y": round(float(table.y), 1)}
        # 路径排除目标餐桌本身，否则终点在桌面附近会被误判为撞到目标桌。
        path = self._walking_path(start, end, table_index)
        duration = self._walking_duration_sec(path)
        start_time_sec = minute * 60
        return WalkingSeatTransfer(
            party=party,
            table_index=table_index,
            window_index=window_index,
            dining_remaining=dining_remaining,
            start_time_sec=start_time_sec,
            arrive_time_sec=start_time_sec + duration,
            path=path,
        )

    # 推进正在走向餐桌的小组；到达后把成员转成正式入座状态。
    def _advance_walking_to_seats(self, end_time_sec: int) -> int:
        arrived_count = 0
        still_walking: list[WalkingSeatTransfer] = []
        for transfer in self.walking_to_seat:
            if self._uses_advanced_movement_coupling():
                if not self._advanced_transfer_ready_to_seat(transfer, end_time_sec):
                    still_walking.append(transfer)
                    continue
                seat_minute = math.ceil(end_time_sec / 60)
            elif transfer.arrive_time_sec > end_time_sec:
                still_walking.append(transfer)
                continue
            else:
                # 到达秒数可能落在分钟中间，seat_time 向上取整代表学生在下一分钟开始占座。
                seat_minute = math.ceil(transfer.arrive_time_sec / 60)
            party = transfer.party
            for student_id in party.student_ids:
                student = self.students[student_id]
                student.seat_time = seat_minute
                if self.pedestrian_engine is not None:
                    self.pedestrian_engine.set_agent_seated(
                        student_id,
                        transfer.table_index,
                        preserve_cell=self._uses_advanced_movement_coupling(),
                    )
                self.seated.append(
                    DiningSeat(
                        student=student,
                        remaining=transfer.dining_remaining,
                        table_index=transfer.table_index,
                    )
                )
            self.table_reserved_seats[transfer.table_index] = max(
                0,
                self.table_reserved_seats[transfer.table_index] - party.size,
            )
            # 行走完成后，预留座位转为实际占用座位。
            self.table_occupied_seats[transfer.table_index] += party.size
            self.table_party_ids[transfer.table_index].add(party.party_id)
            party.seat_time = seat_minute
            party.table_index = transfer.table_index
            self.total_seated += party.size
            arrived_count += party.size
        self.walking_to_seat = still_walking
        return arrived_count

    def _advanced_transfer_ready_to_seat(self, transfer: WalkingSeatTransfer, end_time_sec: int) -> bool:
        return self._party_reached_table(transfer.party)

    # 按校园到达表或手动泊松到达生成本分钟新学生。
    def _generate_arrivals(self, minute: int) -> list[Student]:
        # 到达有两种模式：校园到达使用预先生成的下课到达表，手动模式按泊松分布采样。
        if self.config.campus_demand and self.config.campus_demand.enabled:
            count = self.campus_arrival_schedule.get(minute, 0)
            return self._create_party_students(minute=minute, person_count=count)
        if minute >= self.config.duration_min:
            return []
        count = self._poisson(self._arrival_rate_for_minute(minute))
        return self._create_party_students(minute=minute, person_count=count)

    # 校园模式下把教学楼人数和步行时间展开成分钟级到达表。
    def _build_campus_arrival_schedule(self) -> dict[int, int]:
        campus = self.config.campus_demand
        if campus is None or not campus.enabled or campus.cafeteria_id is None:
            return {}
        if campus.residential_sources or (campus.population_pool is not None and campus.population_pool.enabled):
            return build_mixed_campus_arrival_schedule(
                cafeteria_id=campus.cafeteria_id,
                buildings=campus.buildings,
                residential_sources=campus.residential_sources,
                population_pool=campus.population_pool,
                meal_period=campus.meal_period,
                seed=self.config.seed,
                residential_release_profile=campus.residential_release_profile,
            )["schedule"]
        return build_campus_arrival_schedule(
            cafeteria_id=campus.cafeteria_id,
            buildings=campus.buildings,
            seed=self.config.seed,
        )

    # 计算最后一批学生到达后的仿真到达期边界。
    def _arrival_horizon_minute(self) -> int:
        if self.config.campus_demand and self.config.campus_demand.enabled:
            if not self.campus_arrival_schedule:
                return 1
            return max(self.campus_arrival_schedule) + 1
        if not self.campus_arrival_schedule:
            return self.config.duration_min
        return max(self.config.duration_min, max(self.campus_arrival_schedule) + 1)

    # 按结伴人数分布拆分本分钟到达人数，并创建学生和小组对象。
    def _create_party_students(self, minute: int, person_count: int) -> list[Student]:
        arrivals = []
        remaining = max(0, person_count)
        while remaining > 0:
            # 最后一组人数不能超过本分钟剩余到达人数。
            party_size = min(self._sample_party_size(), remaining)
            party_id = self.next_party_id
            self.next_party_id += 1
            door_index = self._sample_door_index()
            student_ids: list[int] = []
            for _ in range(party_size):
                student = Student(
                    student_id=self.next_student_id,
                    party_id=party_id,
                    arrival_time=minute,
                    queue_enter_time=minute,
                    door_index=door_index,
                )
                self.students[student.student_id] = student
                self.next_student_id += 1
                student_ids.append(student.student_id)
                arrivals.append(student)
            party = DiningParty(
                party_id=party_id,
                arrival_time=minute,
                door_index=door_index,
                student_ids=student_ids,
            )
            self.parties[party_id] = party
            self._maybe_preempt_seat_for_party(party)
            # 同组成员共享 party_id，但后续仍会各自选择窗口排队。
            remaining -= party_size
        return arrivals

    # 为新到达学生选择窗口并加入对应排队队列。
    def _enqueue_arrivals(self, arrivals: list[Student]) -> None:
        if self._uses_advanced_movement_coupling():
            for student in arrivals:
                heapq.heappush(
                    self.pending_entry_students,
                    (self._sample_entry_time_sec(student.arrival_time), self.next_entry_sequence, student),
                )
                self.next_entry_sequence += 1
            return
        if self.pedestrian_engine is not None:
            by_door: dict[int, list[Student]] = {}
            for student in arrivals:
                by_door.setdefault(self._bounded_door_index(student.door_index), []).append(student)
            for door_index, students in by_door.items():
                self.pedestrian_engine.spawn_arrivals(students, door_index=door_index)
        for student in arrivals:
            idx = self._choose_window_for_student(student)
            student.window_index = idx
            if self.pedestrian_engine is not None:
                self.pedestrian_engine.set_agent_target_window(student.student_id, idx)
            if self._uses_advanced_movement_coupling():
                self.waiting_to_queue_student_ids.add(student.student_id)
            else:
                self.queues[idx].append(student)
            self._update_party_window_split_metric(student.party_id)

    def _sample_entry_time_sec(self, minute: int) -> int:
        return int(minute) * 60 + self.entry_rng.randrange(60)

    # advanced 模式下，到达者按秒级边界事件进入 CA；是否延迟由入口格占用自然决定。
    def _admit_due_entry_students(self, current_time_sec: int) -> int:
        if self.pedestrian_engine is None:
            return 0
        admitted_total = 0
        due_by_door: dict[int, list[tuple[int, int, Student]]] = {}
        while self.pending_entry_students and self.pending_entry_students[0][0] <= current_time_sec:
            entry = heapq.heappop(self.pending_entry_students)
            due_by_door.setdefault(self._bounded_door_index(entry[2].door_index), []).append(entry)
        if not due_by_door:
            return 0

        retry_time_sec = current_time_sec + max(1, int(getattr(self.pedestrian_engine, "tick_seconds", 5)))
        for door_index, entries in due_by_door.items():
            available_cells = self.pedestrian_engine.available_entry_cells(door_index, limit=len(entries))
            allowed = min(len(entries), len(available_cells))
            if allowed <= 0:
                for _entry_time, sequence, student in entries:
                    heapq.heappush(self.pending_entry_students, (retry_time_sec, sequence, student))
                continue
            students = [entry[2] for entry in entries[:allowed]]
            self.pedestrian_engine.spawn_arrivals(students, door_index=door_index)
            for student in students:
                idx = self._choose_window_for_student(student)
                self._assign_student_to_window_queue(
                    student,
                    idx,
                    queue_enter_time=math.floor(current_time_sec / 60),
                )
            admitted_total += len(students)
            for _entry_time, sequence, student in entries[allowed:]:
                heapq.heappush(self.pending_entry_students, (retry_time_sec, sequence, student))
        self.entered_this_minute += admitted_total
        return admitted_total

    def _bounded_door_index(self, door_index: int) -> int:
        if not self.layout.doors:
            return 0
        return min(max(0, int(door_index)), len(self.layout.doors) - 1)

    # 高级移动耦合下，学生必须实际走到窗口排队点后才进入 DES 窗口队列。
    def _admit_students_who_reached_window_queue(self, minute: int) -> int:
        if self.pedestrian_engine is None or not self.waiting_to_queue_student_ids:
            return 0
        self._retarget_stuck_window_agents()
        ready_ids = self.pedestrian_engine.ready_to_queue_student_ids(self.waiting_to_queue_student_ids)
        admitted = 0
        for student_id in ready_ids:
            student = self.students.get(student_id)
            if student is None or student.window_index is None or student.service_start_time is not None:
                self.waiting_to_queue_student_ids.discard(student_id)
                continue
            if not self._student_is_in_any_window_queue(student):
                student.queue_enter_time = minute
                self.queues[student.window_index].append(student)
            self.waiting_to_queue_student_ids.discard(student_id)
            admitted += 1
        return admitted

    def _retarget_stuck_window_agents(self) -> None:
        if self.pedestrian_engine is None:
            return
        wait_threshold = max(60, int(180))
        for student_id in sorted(self.waiting_to_queue_student_ids):
            student = self.students.get(student_id)
            agent = self.pedestrian_engine.agents.get(student_id)
            if student is None or agent is None or student.window_index is None:
                continue
            if agent.state is not AgentState.TO_WINDOW:
                continue
            if self._maybe_switch_window_by_cost(student, agent):
                continue
            if agent.wait_ticks < wait_threshold:
                continue
            nearest_window, nearest_distance = self._nearest_window_service_distance(agent.cell)
            if nearest_window is None or nearest_window == student.window_index:
                continue
            current_distance = self._window_service_distance(agent.cell, student.window_index)
            if nearest_distance > 2 or current_distance <= nearest_distance + 1:
                continue
            self._move_student_to_window_queue(student, nearest_window)
            self.window_switch_minutes[student_id] = self.current_minute
            self._update_party_window_split_metric(student.party_id)

    def _maybe_switch_window_by_cost(self, student: Student, agent: Any) -> bool:
        cooldown = int(self.config.window_switch_cooldown_min)
        if cooldown <= 0:
            return False
        last_switch = self.window_switch_minutes.get(student.student_id)
        if last_switch is not None and self.current_minute - last_switch < cooldown:
            return False
        current_window = student.window_index
        if current_window is None or current_window < 0 or current_window >= len(self.layout.windows):
            return False
        current_cost = self._window_choice_cost_from_cell(
            agent.cell,
            current_window,
            excluded_student_id=student.student_id,
            switching=False,
        )
        candidates = [
            (
                self._window_choice_cost_from_cell(
                    agent.cell,
                    window_index,
                    excluded_student_id=student.student_id,
                    switching=True,
                ),
                window_index,
            )
            for window_index in range(len(self.layout.windows))
            if window_index != current_window
        ]
        if not candidates:
            return False
        best_cost, best_window = min(candidates, key=lambda item: (item[0], item[1]))
        threshold = float(self.config.window_switch_threshold_min)
        if current_cost - best_cost < threshold:
            return False
        self._move_student_to_window_queue(student, best_window)
        self.window_switch_minutes[student.student_id] = self.current_minute
        self._update_party_window_split_metric(student.party_id)
        return True

    def _nearest_window_service_distance(self, cell: tuple[int, int]) -> tuple[int | None, int]:
        if self.pedestrian_engine is None:
            return None, 0
        best_window: int | None = None
        best_distance: int | None = None
        for window_index, service_cell in self.pedestrian_engine.grid.service_cells.items():
            distance = abs(cell[0] - service_cell[0]) + abs(cell[1] - service_cell[1])
            if best_distance is None or distance < best_distance:
                best_window = window_index
                best_distance = distance
        return best_window, best_distance if best_distance is not None else 0

    def _window_service_distance(self, cell: tuple[int, int], window_index: int) -> int:
        if self.pedestrian_engine is None:
            return 0
        service_cell = self.pedestrian_engine.grid.service_cells.get(window_index)
        if service_cell is None:
            return 0
        return abs(cell[0] - service_cell[0]) + abs(cell[1] - service_cell[1])

    def _distance_to_window_queue(self, cell: tuple[int, int], window_index: int) -> int:
        if self.pedestrian_engine is None:
            return 0
        queue_cells = self.pedestrian_engine.grid.queue_cells_by_window.get(window_index, [])
        if not queue_cells:
            return 0
        return min(abs(cell[0] - target[0]) + abs(cell[1] - target[1]) for target in queue_cells)

    # 记录同行小队是否被分配到多个窗口；同一小队只计一次。
    def _update_party_window_split_metric(self, party_id: int) -> None:
        party = self.parties.get(party_id)
        if party is None:
            return
        assigned_windows = {
            self.students[student_id].window_index
            for student_id in party.student_ids
            if self.students[student_id].window_index is not None
        }
        if len(assigned_windows) > 1:
            self.party_window_split_party_ids.add(party_id)
        split_count = len(self.party_window_split_party_ids)
        self.metrics_counters["party_window_split_count"] = split_count
        # party_split_count 是旧字段，保留为窗口分流次数的兼容别名。
        self.metrics_counters["party_split_count"] = split_count

    # 从当前学生索引重新计算窗口分流小队数，覆盖手动构造测试或后续状态修正。
    def _refresh_party_window_split_metrics(self) -> int:
        split_party_ids = {
            party.party_id
            for party in self.parties.values()
            if len({
                self.students[student_id].window_index
                for student_id in party.student_ids
                if self.students[student_id].window_index is not None
            }) > 1
        }
        self.party_window_split_party_ids.update(split_party_ids)
        split_count = len(self.party_window_split_party_ids)
        self.metrics_counters["party_window_split_count"] = split_count
        self.metrics_counters["party_split_count"] = split_count
        return split_count

    # 结合预计剩余服务、队伍长度、窗口服务速度和步行时间选择排队窗口。
    def _choose_window_for_student(self, student: Student) -> int:
        # 默认 temperature=0 时确定性选择最低预计完成成本；温度大于 0 时用 softmax 模拟有限理性。
        candidates = [
            (self._window_choice_cost(student, idx), idx)
            for idx in range(len(self.queues))
        ]
        return self._choose_by_softmax_cost(candidates, self.config.window_choice_temperature)

    # 预计完成排队成本：当前服务剩余时间 + 队列服务时间 + 从入口走到窗口的时间。
    def _window_choice_cost(self, student: Student, window_index: int) -> float:
        door = self.layout.doors[min(student.door_index, len(self.layout.doors) - 1)]
        return self._window_choice_cost_from_point(_clean_point(door), window_index)

    def _window_choice_cost_from_cell(
        self,
        cell: tuple[int, int],
        window_index: int,
        excluded_student_id: int | None = None,
        switching: bool = False,
    ) -> float:
        if self.pedestrian_engine is not None:
            point = self.pedestrian_engine.grid.cell_size
            current_point = {
                "x": round((cell[0] + 0.5) * point, 1),
                "y": round((cell[1] + 0.5) * point, 1),
            }
        else:
            current_point = {"x": 0.0, "y": 0.0}
        return self._window_choice_cost_from_point(
            current_point,
            window_index,
            excluded_student_id=excluded_student_id,
            switching=switching,
        )

    def _window_choice_cost_from_point(
        self,
        point: dict[str, float],
        window_index: int,
        excluded_student_id: int | None = None,
        switching: bool = False,
    ) -> float:
        window = self.layout.windows[window_index]
        current_remaining = self.windows[window_index].remaining if self.windows[window_index] is not None else 0.0
        average_service = self.config.service_time_mean / max(0.1, window.service_rate_factor)
        walking_minutes = _point_distance(point, _clean_point(window)) / WALKING_SPEED_UNITS_PER_SEC / 60
        queued_load = len(self.queues[window_index]) + self._pending_window_queue_count(
            window_index,
            excluded_student_id=excluded_student_id,
        )
        switching_penalty = float(self.config.window_switch_penalty_min) if switching else 0.0
        return current_remaining + queued_load * average_service + walking_minutes + switching_penalty

    def _pending_window_queue_count(self, window_index: int, excluded_student_id: int | None = None) -> int:
        if not self._uses_advanced_movement_coupling():
            return 0
        return sum(
            1
            for student_id in self.waiting_to_queue_student_ids
            if student_id != excluded_student_id
            if (student := self.students.get(student_id)) is not None
            and student.window_index == window_index
            and student.service_start_time is None
            and not self._student_is_in_any_window_queue(student)
        )

    # 空闲窗口从队首取学生开始服务，并按窗口速度系数采样服务时长。
    def _start_window_services(self, minute: int, start_offsets: dict[int, float] | None = None) -> list[int]:
        started: list[int] = []
        for idx in range(len(self.windows)):
            offset = max(0.0, min(1.0, (start_offsets or {}).get(idx, 0.0)))
            if self._start_single_window_service(idx, start_time_minute=float(minute) + offset):
                started.append(idx)
        return started

    def _start_single_window_service(self, idx: int, start_time_minute: float) -> bool:
        if self.windows[idx] is not None or not self.queues[idx]:
            return False
        if not self._window_head_ready_for_service(idx):
            return False
        student = self.queues[idx].pop(0)
        self.waiting_to_queue_student_ids.discard(student.student_id)
        start_time_sec = int(round(start_time_minute * 60))
        student.service_start_time = math.floor(start_time_sec / 60)
        student.service_start_time_sec = start_time_sec
        window = self.layout.windows[idx]
        self.windows[idx] = WindowService(
            student=student,
            remaining=self._sample_service_duration_minutes(
                self.config.service_time_mean / max(0.1, window.service_rate_factor)
            ),
        )
        if self.pedestrian_engine is not None:
            self.pedestrian_engine.set_agent_service(student.student_id, idx)
        return True

    def _assign_student_to_window_queue(
        self,
        student: Student,
        window_index: int,
        queue_enter_time: int | None = None,
    ) -> None:
        self._move_student_to_window_queue(student, window_index)
        if queue_enter_time is not None:
            student.queue_enter_time = queue_enter_time
        if self._uses_advanced_movement_coupling():
            self.waiting_to_queue_student_ids.add(student.student_id)
        self._update_party_window_split_metric(student.party_id)

    def _move_student_to_window_queue(self, student: Student, window_index: int) -> None:
        bounded_index = min(max(0, int(window_index)), max(0, len(self.queues) - 1))
        for queue in self.queues:
            if student in queue:
                queue.remove(student)
        student.window_index = bounded_index
        if student.service_start_time is None:
            self.queues[bounded_index].append(student)
        if self.pedestrian_engine is not None:
            self.pedestrian_engine.set_agent_target_window(student.student_id, bounded_index)

    def _student_is_in_any_window_queue(self, student: Student) -> bool:
        return any(student in queue for queue in self.queues)

    def _window_head_ready_for_service(self, window_index: int) -> bool:
        if not self._uses_advanced_movement_coupling() or self.pedestrian_engine is None:
            return True
        if not self.queues[window_index]:
            return False
        student = self.queues[window_index][0]
        agent = self.pedestrian_engine.agents.get(student.student_id)
        service_cell = self.pedestrian_engine.grid.service_cells.get(window_index)
        if agent is None or service_cell is None:
            return False
        queue_cells = self.pedestrian_engine.grid.queue_cells_by_window.get(window_index, [])
        service_front = [service_cell, *queue_cells[:16]]
        return min(abs(agent.cell[0] - cell[0]) + abs(agent.cell[1] - cell[1]) for cell in service_front) <= 1

    # 按可用容量、距离、拼桌惩罚、空座浪费和拥挤度为小组选择餐桌。
    def _choose_table_for_party(self, party: DiningParty) -> int | None:
        # 小组选择餐桌时考虑容量、距离、拼桌惩罚和空座浪费；没有合适桌子就继续等座。
        candidates: list[tuple[float, int]] = []
        for idx, table in enumerate(self.layout.tables):
            occupied = self.table_occupied_seats[idx] + self.table_reserved_seats[idx]
            available = table.capacity - occupied
            if available < party.size:
                continue
            if not self._table_has_movement_target(idx):
                continue
            candidates.append((self._table_choice_cost(party, idx), idx))
        if not candidates:
            return None
        return self._choose_by_softmax_cost(candidates, self.config.table_choice_temperature)

    # advanced 模式下餐桌必须存在真实可达 approach cell；否则不能进入选桌候选。
    def _table_has_movement_target(self, table_index: int) -> bool:
        if not self._uses_advanced_movement_coupling() or self.pedestrian_engine is None:
            return True
        return bool(self.pedestrian_engine.grid.table_approach_cells.get(table_index))

    # 随机效用模型中的餐桌成本项，保留原有距离、拼桌、浪费和单人空桌偏好。
    def _table_choice_cost(self, party: DiningParty, table_index: int) -> float:
        party_window = self._party_reference_window(party)
        table = self.layout.tables[table_index]
        occupied = self.table_occupied_seats[table_index] + self.table_reserved_seats[table_index]
        available = max(0, table.capacity - occupied)
        is_empty = occupied == 0
        distance_cost = _distance(party_window, table) * 0.015
        sharing_penalty = 0.0 if is_empty else (6.0 if party.size == 1 else 3.0)
        seat_waste = max(0, available - party.size)
        waste_penalty = seat_waste * (0.7 if party.size == 1 else 0.35)
        empty_table_bonus = 2.0 if party.size == 1 and is_empty else 0.0
        crowd_penalty = (occupied / max(1, table.capacity)) * (0.5 if party.size == 1 else 0.25)
        return distance_cost + sharing_penalty + waste_penalty - empty_table_bonus + crowd_penalty

    # 对成本越低越优的候选集合做选择；温度为 0 时完全确定，温度大于 0 时按 softmax 概率抽样。
    def _choose_by_softmax_cost(self, candidates: list[tuple[float, int]], temperature: float) -> int:
        if not candidates:
            raise ValueError("候选集合不能为空。")
        ordered = sorted(candidates, key=lambda item: item[1])
        if temperature <= 0:
            return min(ordered, key=lambda item: (item[0], item[1]))[1]
        min_cost = min(cost for cost, _idx in ordered)
        scale = max(1e-9, temperature)
        weights = [math.exp(-(cost - min_cost) / scale) for cost, _idx in ordered]
        total = sum(weights)
        if total <= 0:
            return min(ordered, key=lambda item: (item[0], item[1]))[1]
        threshold = self.choice_rng.random() * total
        cumulative = 0.0
        for (_cost, idx), weight in zip(ordered, weights):
            cumulative += weight
            if threshold <= cumulative:
                return idx
        return ordered[-1][1]

    # 返回该小组取餐完成位置对应的窗口对象。
    def _party_reference_window(self, party: DiningParty) -> LayoutWindowData:
        return self.layout.windows[self._party_reference_window_index(party)]

    # 用组内最晚完成取餐的成员确定小组走向餐桌的起点窗口。
    def _party_reference_window_index(self, party: DiningParty) -> int:
        if not self.layout.windows:
            return 0
        members = [
            self.students[student_id]
            for student_id in party.student_ids
            if self.students[student_id].window_index is not None
        ]
        if not members:
            return 0
        latest = max(
            members,
            key=lambda student: (
                # service_end_time 越晚，越能代表小组最后汇合的位置。
                student.service_end_time if student.service_end_time is not None else -1,
                -student.student_id,
            ),
        )
        return min(max(0, int(latest.window_index or 0)), len(self.layout.windows) - 1)

    # 取窗口朝向内侧的一点作为学生离开窗口后的行走起点。
    def _window_service_point(self, window: LayoutWindowData) -> dict[str, float]:
        normal = self._wall_normal(window.wall_side)
        footprint = self._opening_footprint("window", window.wall_side)
        half = footprint["width"] / 2 if window.wall_side in {"left", "right"} else footprint["height"] / 2
        return _clean_point({
            "x": window.x + normal["x"] * (half + 6),
            "y": window.y + normal["y"] * (half + 6),
        })

    # _walking_path() 处理行走路径或路径采样。
    def _walking_path(
        self,
        start: dict[str, float],
        end: dict[str, float],
        target_table_index: int,
    ) -> list[dict[str, float]]:
        if self.config.movement_model == "static_floor_field":
            path = static_floor_field_path(self.layout, self.config, start, end)
            if len(path) > 1:
                return path
        boxes = self._table_obstacle_boxes(exclude_index=target_table_index)
        direct = _dedupe_path([start, end])
        if self._path_is_clear(direct, boxes):
            return direct

        # 先尝试两条简单 L 型路径；如果仍被餐桌挡住，再围绕阻挡餐桌生成绕行点。
        candidates = [
            _dedupe_path([start, {"x": start["x"], "y": end["y"]}, end]),
            _dedupe_path([start, {"x": end["x"], "y": start["y"]}, end]),
        ]
        blocking_boxes = [
            box for box in boxes if _segment_intersects_box(start, end, box)
        ] or boxes
        for box in blocking_boxes:
            for x in (box["left"] - 10, box["right"] + 10):
                candidates.append(_dedupe_path([
                    start,
                    {"x": x, "y": start["y"]},
                    {"x": x, "y": end["y"]},
                    end,
                ]))
            for y in (box["top"] - 10, box["bottom"] + 10):
                candidates.append(_dedupe_path([
                    start,
                    {"x": start["x"], "y": y},
                    {"x": end["x"], "y": y},
                    end,
                ]))

        for path in sorted(candidates, key=_path_length):
            if self._path_is_clear(path, boxes):
                return path
        # 如果所有绕行候选都失败，保留直线路径，保证前端仍有可播放轨迹。
        return direct

    # _path_is_clear() 处理行走路径或路径采样。
    def _path_is_clear(self, path: list[dict[str, float]], boxes: list[dict[str, float]]) -> bool:
        points = _dedupe_path(path)
        return all(
            not any(_segment_intersects_box(points[index - 1], points[index], box) for box in boxes)
            for index in range(1, len(points))
        )

    # 把路径长度换算成前端播放用的行走秒数，并限制最短和最长时长。
    def _walking_duration_sec(self, path: list[dict[str, float]]) -> int:
        distance = _path_length(path)
        if distance <= 0:
            return MIN_WALKING_DURATION_SEC
        return max(
            MIN_WALKING_DURATION_SEC,
            min(MAX_WALKING_DURATION_SEC, int(round(distance / WALKING_SPEED_UNITS_PER_SEC))),
        )

    # 把除目标餐桌外的桌面 footprint 转成行走避障矩形。
    def _table_obstacle_boxes(self, exclude_index: int | None = None) -> list[dict[str, float]]:
        boxes: list[dict[str, float]] = []
        for idx, table in enumerate(self.layout.tables):
            if exclude_index is not None and idx == exclude_index:
                continue
            footprint = self._table_footprint(table)
            boxes.append(_box(
                table.x - footprint["width"] / 2,
                table.y - footprint["height"] / 2,
                table.x + footprint["width"] / 2,
                table.y + footprint["height"] / 2,
                padding=PATH_OBSTACLE_PADDING,
            ))
        return boxes

    # 根据桌型容量和旋转角估算碰撞检测所需的桌面尺寸。
    def _table_footprint(self, table: LayoutTableData) -> dict[str, float]:
        capacity = max(1, int(table.capacity or 1))
        if capacity <= 2:
            footprint = {"width": 52.0, "height": 26.0}
        elif capacity <= 4:
            footprint = {"width": 64.0, "height": 50.0}
        else:
            footprint = {"width": 76.0, "height": 50.0}
        rotation = ((round(float(table.rotation or 0)) % 180) + 180) % 180
        if 45 <= rotation < 135:
            return {"width": footprint["height"], "height": footprint["width"]}
        return footprint

    # 根据门/窗口类型和所在墙面给出墙面开口的占位尺寸。
    def _opening_footprint(self, kind: str, wall_side: str) -> dict[str, float]:
        if kind == "door":
            horizontal = {"width": 52.0, "height": 32.0}
            vertical = {"width": 32.0, "height": 52.0}
        else:
            horizontal = {"width": 36.0, "height": 32.0}
            vertical = {"width": 32.0, "height": 36.0}
        return horizontal if wall_side in {"top", "bottom"} else vertical

    # 返回从墙面指向食堂内部的单位方向，用于放置服务点。
    def _wall_normal(self, wall_side: str) -> dict[str, float]:
        if wall_side == "right":
            return {"x": -1.0, "y": 0.0}
        if wall_side == "bottom":
            return {"x": 0.0, "y": -1.0}
        if wall_side == "left":
            return {"x": 1.0, "y": 0.0}
        return {"x": 0.0, "y": 1.0}

    # 手动模式下按高峰区间和错峰分钟数计算本分钟泊松到达率。
    def _arrival_rate_for_minute(self, minute: int) -> float:
        rate = self.config.arrival_rate
        in_peak = self.config.peak_start_min <= minute < self.config.peak_end_min
        if not in_peak:
            shoulder_end = self.config.peak_end_min + max(0, self.config.stagger_minutes)
            if self.config.stagger_minutes and self.config.peak_end_min <= minute < shoulder_end:
                # 错峰不会凭空减少总需求，而是把一部分高峰需求推到高峰后的肩部时段。
                return rate * (1.0 + min(0.35, self.config.stagger_minutes / 60))
            return rate

        # 错峰分钟越长，高峰强度越低，但用 0.55 设置下限，避免高峰被完全削平。
        stagger_factor = max(0.55, 1.0 - self.config.stagger_minutes / 45)
        return rate * self.config.peak_multiplier * stagger_factor

    # 使用 Knuth 算法采样普通到达人数，大均值时改用正态近似。
    def _poisson(self, lam: float) -> int:
        if lam <= 0:
            return 0
        if lam > 50:
            # 大均值下 Knuth 循环太长，使用同均值方差的正态近似提升速度。
            return max(0, int(round(self.arrival_rng.gauss(lam, math.sqrt(lam)))))
        threshold = math.exp(-lam)
        count = 0
        product = 1.0
        while product > threshold:
            count += 1
            product *= self.arrival_rng.random()
        return count - 1

    # 围绕均值采样服务或就餐时长，并保证至少持续一分钟。
    def _sample_duration(self, mean: float) -> int:
        if mean <= 1:
            return 1
        spread = max(0.35, mean * 0.22)
        return max(1, int(round(self.duration_rng.gauss(mean, spread))))

    # 服务窗口按秒采样，再折算成小数分钟供窗口推进使用。
    def _sample_service_duration_minutes(self, mean_minutes: float) -> float:
        mean_seconds = max(1.0, float(mean_minutes) * 60.0)
        spread_seconds = max(5.0, mean_seconds * 0.22)
        duration_seconds = max(1, int(round(self.duration_rng.gauss(mean_seconds, spread_seconds))))
        return duration_seconds / 60.0

    # 按归一化后的结伴人数分布随机抽取小组人数。
    def _sample_party_size(self) -> int:
        distribution = _normalized_party_distribution(self.config.party_size_distribution)
        threshold = self.arrival_rng.random()
        cumulative = 0.0
        for size, weight in distribution:
            cumulative += weight
            # 累积概率第一次越过随机阈值时，即抽中该小组人数。
            if threshold <= cumulative:
                return size
        return distribution[-1][0] if distribution else 1

    # 按入口 arrival_share 权重抽取本批学生进入食堂的入口。
    def _sample_door_index(self) -> int:
        shares = [max(0.0, door.arrival_share) for door in self.layout.doors]
        total = sum(shares)
        if total <= 0:
            return 0
        threshold = self.arrival_rng.random() * total
        cumulative = 0.0
        for idx, share in enumerate(shares):
            cumulative += share
            # arrival_share 是权重而不是百分比，按累计权重抽样即可。
            if threshold <= cumulative:
                return idx
        return len(shares) - 1

    # 统计当前等座队列中的总人数，而不是只统计小组数。
    def _waiting_for_seat_people(self) -> int:
        return sum(party.size for party in self.waiting_for_seat)

    # 统计已被部分占用餐桌上的剩余空位，用来衡量拼桌碎片化。
    def _fragmented_seats(self) -> int:
        available_by_table: list[int] = []
        partial_empty = 0
        for idx, table in enumerate(self.layout.tables):
            used = self.table_occupied_seats[idx] + self.table_reserved_seats[idx]
            available = max(0, table.capacity - used)
            available_by_table.append(available)
            if 0 < used < table.capacity:
                partial_empty += available

        blocked_by_fragmentation = 0
        total_available = sum(available_by_table)
        for party in self.waiting_for_seat:
            if total_available < party.size:
                continue
            if any(available >= party.size for available in available_by_table):
                continue
            blocked_by_fragmentation = max(blocked_by_fragmentation, total_available)
        return max(partial_empty, blocked_by_fragmentation)

    # 统计所有已预留但尚未正式入座的座位数。
    def _reserved_seats(self) -> int:
        return sum(self.table_reserved_seats)

    # 统计当前仍可分配给新等座小组的座位数，扣除已入座和已预留容量。
    def _available_seats(self) -> int:
        return max(0, self.total_seat_capacity - len(self.seated) - self._reserved_seats())

    # 判断系统内是否还有处于排队、服务、等座、行走或就餐阶段的学生。
    def _has_active_students(self) -> bool:
        return (
            any(self.queues)
            or any(window is not None for window in self.windows)
            or bool(self.waiting_for_seat)
            or bool(self.walking_to_seat)
            or bool(self.seated)
            or bool(self.waiting_to_queue_student_ids)
            or bool(self.pending_entry_students)
        )

    def _uses_advanced_movement_coupling(self) -> bool:
        return (
            self.config.movement_model == "advanced_floor_field"
            and self.pedestrian_engine is not None
            and bool(self.config.advanced_movement_coupling)
        )

    def _party_reached_table(self, party: DiningParty) -> bool:
        return bool(self.pedestrian_engine and self.pedestrian_engine.party_ready_to_seat(party))

    # 把当前 runner 状态整理成本分钟 StepRecord。
    def _build_record(
        self,
        t: int,
        arrived_count: int,
        served_count: int,
        seated_count: int,
        left_count: int,
        timeline: dict[str, Any] | None = None,
    ) -> StepRecord:
        snapshot = self._snapshot()
        if timeline is not None:
            snapshot["timeline"] = timeline
        return StepRecord(
            run_id=self.run_id,
            t=t,
            clock_minute=self.config.simulation_start_minute + t,
            arrived_count=arrived_count,
            queue_lengths=[len(queue) for queue in self.queues],
            served_count=served_count,
            seated_count=seated_count,
            left_count=left_count,
            empty_seats=self.total_seat_capacity - len(self.seated),
            reserved_seats=self._reserved_seats(),
            available_seats=self._available_seats(),
            waiting_for_seat_count=self._waiting_for_seat_people(),
            total_arrived=len(self.students),
            total_served=self.total_served,
            total_seated=self.total_seated,
            total_left=self.total_left,
            avg_wait_so_far=self._avg_wait_so_far(),
            snapshot=snapshot,
        )

    # 只用已经入座的学生计算截至当前分钟的平均等待时间。
    def _avg_wait_so_far(self) -> float:
        waits = [
            student.seat_time - student.arrival_time
            for student in self.students.values()
            if student.seat_time is not None
        ]
        return round(sum(waits) / len(waits), 2) if waits else 0.0

    # 生成前端实时地图需要的当前队列、窗口、餐桌和小组状态快照。
    def _snapshot(self) -> dict[str, Any]:
        occupied = len(self.seated)
        reserved = self._reserved_seats()
        snapshot = {
            "minute": self.current_minute,
            "clock_minute": self.config.simulation_start_minute + self.current_minute,
            # 队列长度用于指标卡和队列图；queue_groups 用于地图按小组展示。
            "queue_lengths": [len(queue) for queue in self.queues],
            "queue_groups": self._queue_groups_snapshot(),
            "busy_windows": [window is not None for window in self.windows],
            "window_services": self._window_services_snapshot(),
            "occupied_seats": occupied,
            "empty_seats": self.total_seat_capacity - occupied,
            "reserved_seats": reserved,
            "available_seats": max(0, self.total_seat_capacity - occupied - reserved),
            "waiting_for_seat_count": self._waiting_for_seat_people(),
            "waiting_party_count": len(self.waiting_for_seat),
            "waiting_parties": self._waiting_parties_snapshot(),
            "entry_queue_lengths": self._pending_entry_counts_by_door(),
            "entry_waiting_count": len(self.pending_entry_students),
            "entered_count": self.entered_this_minute,
            # walking_parties 是跨分钟仍在走的人；timeline 只记录本分钟新发生的走路事件。
            "walking_to_seat_count": sum(transfer.party.size for transfer in self.walking_to_seat),
            "walking_parties": self._walking_parties_snapshot(),
            "seated_parties": self._seated_parties_snapshot(),
            "table_occupancy": [
                {
                    "id": table.id,
                    "type": table.table_type,
                    "capacity": table.capacity,
                    "occupied": self.table_occupied_seats[idx],
                    "reserved": self.table_reserved_seats[idx],
                    "party_count": len(self.table_party_ids[idx]),
                    "party_ids": sorted(self.table_party_ids[idx]),
                }
                for idx, table in enumerate(self.layout.tables)
            ],
            "totals": {
                "arrived": len(self.students),
                "served": self.total_served,
                "seated": self.total_seated,
                "left": self.total_left,
            },
        }
        if self.pedestrian_engine is not None:
            snapshot["pedestrian_agents"] = self.pedestrian_engine.agent_snapshots()
            snapshot["density_hotspots"] = self.pedestrian_engine.density_hotspots()
            snapshot["movement_metrics"] = self.pedestrian_engine.metrics_snapshot()
        return snapshot

    def _pending_entry_counts_by_door(self) -> list[int]:
        counts = [0 for _ in self.layout.doors]
        for _entry_time_sec, _sequence, student in self.pending_entry_students:
            if counts:
                counts[self._bounded_door_index(student.door_index)] += 1
        return counts

    # 把窗口队列里的学生按小组聚合，保留队列位置和来源入口。
    def _queue_groups_snapshot(self) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for window_index, queue in enumerate(self.queues):
            grouped: dict[int, dict[str, Any]] = {}
            for position, student in enumerate(queue):
                party = self.parties[student.party_id]
                # 队列按学生排，但前端地图按小组画，所以同 party_id 的成员需要合并。
                item = grouped.setdefault(
                    party.party_id,
                    {
                        "party_id": party.party_id,
                        "size": party.size,
                        "member_count": 0,
                        "window_index": window_index,
                        "door_index": party.door_index,
                        "arrival_time": party.arrival_time,
                        "queue_position": position,
                    },
                )
                item["member_count"] += 1
            groups.extend(sorted(grouped.values(), key=lambda item: item["queue_position"]))
        return groups

    # 输出每个忙碌窗口正在服务的小组、入口和剩余服务时间。
    def _window_services_snapshot(self) -> list[dict[str, Any]]:
        services: list[dict[str, Any]] = []
        for window_index, service in enumerate(self.windows):
            if service is None:
                continue
            party = self.parties[service.student.party_id]
            services.append(
                {
                    "party_id": party.party_id,
                    "size": party.size,
                    "member_count": 1,
                    "window_index": window_index,
                    "door_index": party.door_index,
                    "arrival_time": party.arrival_time,
                    "remaining": service.remaining,
                }
            )
        return services

    # 输出正在等座的小组顺序、就绪时间和参考窗口。
    def _waiting_parties_snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "party_id": party.party_id,
                "size": party.size,
                "member_count": party.size,
                "door_index": party.door_index,
                "window_index": self._party_reference_window_index(party),
                "arrival_time": party.arrival_time,
                "ready_time": party.ready_time,
                "wait_position": position,
            }
            for position, party in enumerate(self.waiting_for_seat)
        ]

    # 按指定秒数采样正在走向餐桌的小组位置。
    def _walking_parties_snapshot(self, time_sec: int | None = None) -> list[dict[str, Any]]:
        now_sec = self.current_minute * 60 if time_sec is None else time_sec
        return [
            self._walking_transfer_snapshot(transfer, now_sec)
            for transfer in self.walking_to_seat
        ]

    # 把一个行走转移对象转换成前端可绘制的进度、坐标和路径信息。
    def _walking_transfer_snapshot(self, transfer: WalkingSeatTransfer, time_sec: int) -> dict[str, Any]:
        duration = max(1, transfer.arrive_time_sec - transfer.start_time_sec)
        progress = max(0.0, min(1.0, (time_sec - transfer.start_time_sec) / duration))
        point = _sample_path(transfer.path, progress)
        party = transfer.party
        table = self.layout.tables[transfer.table_index]
        return {
            "type": "walk_to_seat",
            "party_id": party.party_id,
            "size": party.size,
            "member_count": party.size,
            "door_index": party.door_index,
            "window_index": transfer.window_index,
            "table_index": transfer.table_index,
            "table_id": table.id,
            "arrival_time": party.arrival_time,
            "ready_time": party.ready_time,
            "start_time_sec": transfer.start_time_sec,
            "arrive_time_sec": transfer.arrive_time_sec,
            "duration_sec": duration,
            "progress": round(progress, 3),
            "x": point["x"],
            "y": point["y"],
            "from": transfer.path[0],
            "to": transfer.path[-1],
            "path": transfer.path,
        }

    # 为本分钟新发生的入座行走生成播放起止时间和逐秒帧。
    def _walking_event_snapshot(self, transfer: WalkingSeatTransfer, step_start_sec: int) -> dict[str, Any]:
        payload = self._walking_transfer_snapshot(transfer, transfer.start_time_sec)
        duration_sec = max(1, transfer.arrive_time_sec - transfer.start_time_sec)
        # playback_start_ms 把仿真秒映射到前端本 step 的播放时间轴。
        playback_start_ms = max(
            0,
            round((transfer.start_time_sec - step_start_sec) / 60 * TIMELINE_BASE_PLAYBACK_MS),
        )
        # 播放时长按真实路径秒数缩放，同时限制上下界，避免动画过快或过慢。
        playback_duration_ms = max(
            MIN_WALKING_PLAYBACK_MS,
            min(MAX_WALKING_PLAYBACK_MS, round(duration_sec * WALKING_PLAYBACK_MS_PER_SEC)),
        )
        payload.update({
            "playback_start_ms": playback_start_ms,
            "playback_duration_ms": playback_duration_ms,
            "playback_end_ms": playback_start_ms + playback_duration_ms,
            "frames": self._walking_frames(transfer),
        })
        return payload

    # 沿后端路径逐秒采样坐标，供前端在一个 step 内平滑播放。
    def _walking_frames(self, transfer: WalkingSeatTransfer) -> list[dict[str, Any]]:
        duration = max(1, transfer.arrive_time_sec - transfer.start_time_sec)
        frames = []
        for time_sec in range(transfer.start_time_sec, transfer.arrive_time_sec + 1):
            progress = max(0.0, min(1.0, (time_sec - transfer.start_time_sec) / duration))
            point = _sample_path(transfer.path, progress)
            frames.append({
                "time_sec": time_sec,
                "x": point["x"],
                "y": point["y"],
                "progress": round(progress, 3),
            })
        return frames

    # 把本分钟发生的行走事件包装成 snapshot.timeline。
    def _build_step_timeline(
        self,
        start_time_sec: int,
        end_time_sec: int,
        events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not events:
            return None
        playback_ms = max(
            TIMELINE_BASE_PLAYBACK_MS,
            max(int(event.get("playback_end_ms", 0)) for event in events),
        )
        return {
            "start_time_sec": start_time_sec,
            "end_time_sec": end_time_sec,
            "playback_ms": playback_ms,
            "events": events,
        }

    # 按小组和餐桌聚合已入座成员，便于前端显示桌面占用。
    def _seated_parties_snapshot(self) -> list[dict[str, Any]]:
        seated: dict[tuple[int, int], dict[str, Any]] = {}
        for seat in self.seated:
            if seat.table_index is None:
                continue
            party = self.parties[seat.student.party_id]
            table = self.layout.tables[seat.table_index]
            key = (party.party_id, seat.table_index)
            # 一张桌上同一个小组可能有多名成员，聚合后前端只画一个小组簇。
            item = seated.setdefault(
                key,
                {
                    "party_id": party.party_id,
                    "size": party.size,
                    "member_count": 0,
                    "table_index": seat.table_index,
                    "table_id": table.id,
                    "door_index": party.door_index,
                    "arrival_time": party.arrival_time,
                    "seat_time": party.seat_time,
                    "remaining": seat.remaining,
                },
            )
            item["member_count"] += 1
            item["remaining"] = max(item["remaining"], seat.remaining)
        return sorted(seated.values(), key=lambda item: (item["table_index"], item["party_id"]))

    # 从学生时间戳、分钟记录和资源占用累计值计算最终指标。
    def _build_metrics(self) -> MetricsSummary:
        # 指标汇总从所有学生、所有分钟记录和资源占用累计值中计算。
        seated_students = [student for student in self.students.values() if student.seat_time is not None]
        served_students = [student for student in self.students.values() if student.service_start_time is not None]
        seated_parties = [party for party in self.parties.values() if party.seat_time is not None]
        seat_wait_students = [
            student
            for student in seated_students
            if student.service_end_time is not None and student.seat_time is not None
        ]
        assigned_parties = [
            party
            for party in seated_parties
            if party.ready_time is not None and party.seat_assignment_time is not None
        ]
        avg_wait = _average(student.seat_time - student.arrival_time for student in seated_students)
        avg_queue_wait = _average(student.service_start_time - student.arrival_time for student in served_students)
        avg_post_service_to_seat_time = _average(student.seat_time - student.service_end_time for student in seat_wait_students)
        avg_seat_wait = _average(party.seat_assignment_time - party.ready_time for party in assigned_parties)
        # 峰值类指标从每分钟记录中取最大值，反映整个运行过程中的最拥堵时刻。
        peak_queue = max((sum(record.queue_lengths) for record in self.records), default=0)
        peak_waiting_for_seat = max((record.waiting_for_seat_count for record in self.records), default=0)
        elapsed_minutes = max(1, len(self.records))
        denominator_windows = max(1, elapsed_minutes * len(self.windows))
        denominator_seats = max(1, elapsed_minutes * self.total_seat_capacity)
        # 利用率 = 资源被占用的分钟数 / 资源总分钟数。
        window_utilization = self.window_busy_minutes / denominator_windows
        seat_utilization = self.seat_occupied_minutes / denominator_seats
        active_window_minutes = sum(
            1
            for record in self.records
            if sum(record.queue_lengths) > 0
            or record.served_count > 0
            or any(record.snapshot.get("busy_windows", []))
        )
        active_window_utilization = (
            self.window_busy_minutes / max(1, active_window_minutes * len(self.windows))
            if active_window_minutes
            else 0.0
        )
        party_window_split_count = self._refresh_party_window_split_metrics()
        avg_party_gather_wait = _average(self._party_gather_wait(party) for party in seated_parties)
        avg_party_seat_wait = _average(
            party.seat_assignment_time - party.ready_time
            for party in assigned_parties
        )
        table_utilization_by_type = self._table_utilization_by_type()
        movement = self._movement_metrics()
        bottleneck = self._classify_bottleneck(
            peak_queue=peak_queue,
            peak_waiting_for_seat=peak_waiting_for_seat,
            avg_seat_wait=avg_seat_wait,
            seat_utilization=seat_utilization,
            window_utilization=window_utilization,
            movement=movement,
        )
        chart_data = {
            # chart_data 直接服务前端 ECharts，避免前端重新理解完整记录结构。
            "times": [record.t for record in self.records],
            "queue_totals": [sum(record.queue_lengths) for record in self.records],
            "empty_seats": [record.empty_seats for record in self.records],
            "throughput": [record.total_seated for record in self.records],
            "avg_wait": [record.avg_wait_so_far for record in self.records],
            "waiting_for_seat": [record.waiting_for_seat_count for record in self.records],
        }
        return MetricsSummary(
            run_id=self.run_id,
            avg_wait=round(avg_wait, 2),
            avg_queue_wait=round(avg_queue_wait, 2),
            avg_seat_wait=round(avg_seat_wait, 2),
            peak_queue=peak_queue,
            peak_waiting_for_seat=peak_waiting_for_seat,
            throughput=self.total_seated,
            total_arrived=len(self.students),
            total_left=self.total_left,
            seat_utilization=round(seat_utilization, 4),
            window_utilization=round(window_utilization, 4),
            bottleneck_type=bottleneck,
            chart_data=chart_data,
            active_window_utilization=round(active_window_utilization, 4),
            avg_party_gather_wait=round(avg_party_gather_wait, 2),
            avg_party_seat_wait=round(avg_party_seat_wait, 2),
            avg_post_service_to_seat_time=round(avg_post_service_to_seat_time, 2),
            party_window_split_count=party_window_split_count,
            party_split_count=self.metrics_counters["party_split_count"],
            shared_table_count=self.metrics_counters["shared_table_count"],
            blocked_party_count=self.metrics_counters["blocked_party_count"],
            fragmented_seats=self.peak_fragmented_seats,
            table_utilization_by_type=table_utilization_by_type,
            avg_walking_time=round(float(movement.get("avg_walking_time", 0.0)), 2),
            movement_conflict_count=int(movement.get("movement_conflict_count", 0)),
            avg_stuck_ticks=round(float(movement.get("avg_stuck_ticks", 0.0)), 2),
            max_density=int(movement.get("max_density", 0)),
        )

    def _movement_metrics(self) -> dict[str, float | int]:
        if self.pedestrian_engine is None:
            return {
                "avg_walking_time": 0.0,
                "movement_conflict_count": 0,
                "avg_stuck_ticks": 0.0,
                "max_density": 0,
            }
        return self.pedestrian_engine.metrics_snapshot()

    # 计算同组最早和最晚取餐完成时间差，用于衡量结伴等待。
    def _party_gather_wait(self, party: DiningParty) -> float:
        service_end_times = [
            self.students[student_id].service_end_time
            for student_id in party.student_ids
            if self.students[student_id].service_end_time is not None
        ]
        if len(service_end_times) < 2:
            return 0.0
        return max(service_end_times) - min(service_end_times)

    # 按餐桌类型汇总每分钟占用座位数，得到各类型利用率。
    def _table_utilization_by_type(self) -> dict[str, float]:
        capacity_by_type: dict[str, int] = {}
        occupied_minutes_by_type: dict[str, int] = {}
        elapsed_minutes = max(1, len(self.records))
        for table in self.layout.tables:
            capacity_by_type[table.table_type] = capacity_by_type.get(table.table_type, 0) + table.capacity
            occupied_minutes_by_type.setdefault(table.table_type, 0)
        for record in self.records:
            for table in record.snapshot.get("table_occupancy", []):
                table_type = table.get("type", "unknown")
                # 每分钟 occupied 座位数累加起来，就是该桌型的占用座位分钟数。
                occupied_minutes_by_type[table_type] = occupied_minutes_by_type.get(table_type, 0) + int(table.get("occupied", 0))
        return {
            table_type: round(occupied_minutes_by_type.get(table_type, 0) / max(1, elapsed_minutes * capacity), 4)
            for table_type, capacity in capacity_by_type.items()
        }

    # 按排队峰值、等座峰值和资源利用率给出可解释的瓶颈标签。
    def _classify_bottleneck(
        self,
        peak_queue: int,
        peak_waiting_for_seat: int,
        avg_seat_wait: float,
        seat_utilization: float,
        window_utilization: float,
        movement: dict[str, float | int] | None = None,
    ) -> str:
        # 瓶颈分类用于结果分析和规则化解释：座位容量、窗口服务、到达高峰或运行平衡。
        if peak_waiting_for_seat > 0 and (seat_utilization >= 0.72 or avg_seat_wait >= 1.0):
            return "座位容量"
        movement = movement or {}
        if (
            float(movement.get("avg_walking_time", 0.0) or 0.0) >= 120.0
            or float(movement.get("avg_stuck_ticks", 0.0) or 0.0) >= 2.0
            or int(movement.get("movement_conflict_count", 0) or 0) >= max(50, peak_queue * 4)
        ):
            return "动线拥堵"
        window_count = max(1, len(self.windows))
        if peak_queue >= max(8, window_count * 8) and window_utilization >= 0.72:
            return "窗口服务"
        if self.config.peak_multiplier > 1.2 and peak_queue >= max(4, window_count * 3):
            return "到达高峰"
        return "运行平衡"


# 优先使用前端传入布局；没有布局时回退到后端默认平面。
def _effective_layout(config: SimulationConfigData) -> DiningLayoutData:
    if config.layout is not None:
        return config.layout
    return _default_layout(config)


# 根据窗口数和座位数生成一份可运行的默认食堂布局。
def _default_layout(config: SimulationConfigData) -> DiningLayoutData:
    table_capacities = _default_table_capacities(config.num_seats)
    table_count = max(1, len(table_capacities))
    table_columns = max(4, min(12, math.ceil(math.sqrt(table_count * 1.35))))
    table_rows = max(1, math.ceil(table_count / table_columns))
    table_x_step = 96.0
    table_y_step = 84.0
    table_origin_x = 110.0
    table_origin_y = 260.0
    floor_width = max(360.0, table_origin_x + (table_columns - 1) * table_x_step + 140.0)
    floor_height = max(640.0, table_origin_y + (table_rows - 1) * table_y_step + 140.0)
    floor = LayoutFloorData(width=floor_width, height=floor_height)
    doors = [
        LayoutDoorData(
            id="D1",
            x=18,
            y=min(max(145.0, floor_height * 0.5), floor_height - 80.0),
            arrival_share=1.0,
        )
    ]
    window_count = max(0, config.num_windows)
    windows_per_row = max(1, min(max(1, window_count), max(1, int((floor_width - 150.0) // 64.0))))
    windows = [
        LayoutWindowData(
            id=f"W{index + 1}",
            x=96 + (index % windows_per_row) * 64,
            y=82 + (index // windows_per_row) * 44,
            service_rate_factor=1.0,
        )
        for index in range(window_count)
    ]
    tables = [
        LayoutTableData(
            id=f"T{index + 1}",
            x=table_origin_x + (index % table_columns) * table_x_step,
            y=table_origin_y + (index // table_columns) * table_y_step,
            table_type=_table_type_for_capacity(capacity),
            capacity=capacity,
        )
        for index, capacity in enumerate(table_capacities)
    ]
    return DiningLayoutData(floor=floor, doors=doors, windows=windows, tables=tables)


# 用 2/4/4/6 的容量模式拆分默认餐桌，直到覆盖目标座位数。
def _default_table_capacities(num_seats: int) -> list[int]:
    remaining = max(0, num_seats)
    capacities: list[int] = []
    pattern = [2, 4, 4, 6]
    index = 0
    while remaining > 0:
        capacity = min(pattern[index % len(pattern)], remaining)
        capacities.append(capacity)
        remaining -= capacity
        index += 1
    return capacities


# 把餐桌容量映射为前端和指标汇总使用的桌型名称。
def _table_type_for_capacity(capacity: int) -> str:
    if capacity <= 1:
        return "single_seat"
    if capacity <= 2:
        return "two_seat"
    if capacity <= 4:
        return "four_seat"
    return "six_seat"


# 清洗结伴人数权重并归一化，供随机抽样使用。
def _normalized_party_distribution(distribution: dict[int, float]) -> list[tuple[int, float]]:
    weighted_sizes: list[tuple[int, float]] = []
    for raw_size, raw_weight in distribution.items():
        try:
            size = int(raw_size)
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        if size > 0 and weight > 0:
            weighted_sizes.append((size, weight))
    total = sum(weight for _size, weight in weighted_sizes)
    if total <= 0:
        return []
    return [(size, weight / total) for size, weight in sorted(weighted_sizes)]


# 计算两个带 x/y 属性布局元素之间的欧氏距离。
def _distance(a: Any, b: Any) -> float:
    return math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))


# 计算两个字典坐标点之间的欧氏距离。
def _point_distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


# 将 dict 或布局对象坐标规范成保留一位小数的点。
def _clean_point(point: dict[str, float] | Any) -> dict[str, float]:
    if isinstance(point, dict):
        x = point.get("x", 0)
        y = point.get("y", 0)
    else:
        x = getattr(point, "x", 0)
        y = getattr(point, "y", 0)
    return {"x": round(float(x), 1), "y": round(float(y), 1)}


# _dedupe_path() 处理行走路径或路径采样。
def _dedupe_path(path: list[dict[str, float]]) -> list[dict[str, float]]:
    cleaned: list[dict[str, float]] = []
    for point in path:
        item = _clean_point(point)
        if cleaned and _point_distance(cleaned[-1], item) < 0.1:
            continue
        cleaned.append(item)
    return cleaned


# _path_length() 处理行走路径或路径采样。
def _path_length(path: list[dict[str, float]]) -> float:
    points = _dedupe_path(path)
    return sum(_point_distance(points[index - 1], points[index]) for index in range(1, len(points)))


# _sample_path() 处理行走路径或路径采样。
def _sample_path(path: list[dict[str, float]], progress: float) -> dict[str, float]:
    points = _dedupe_path(path)
    if not points:
        return {"x": 0.0, "y": 0.0}
    if len(points) == 1:
        return points[0]
    amount = max(0.0, min(1.0, float(progress)))
    if amount <= 0:
        return points[0]
    if amount >= 1:
        return points[-1]

    total = _path_length(points)
    if total <= 0:
        return points[-1]
    remaining = total * amount
    for index in range(1, len(points)):
        start = points[index - 1]
        end = points[index]
        length = _point_distance(start, end)
        if length <= 0:
            continue
        if remaining <= length:
            local = remaining / length
            return _clean_point({
                "x": start["x"] + (end["x"] - start["x"]) * local,
                "y": start["y"] + (end["y"] - start["y"]) * local,
            })
        remaining -= length
    return points[-1]


# 判断一个点是否落在指定矩形盒内。
def _point_inside_box(point: dict[str, float], box: dict[str, float]) -> bool:
    return box["left"] <= point["x"] <= box["right"] and box["top"] <= point["y"] <= box["bottom"]


# 判断两条线段是否相交，包含共线重叠的边界情况。
def _segments_intersect(a: dict[str, float], b: dict[str, float], c: dict[str, float], d: dict[str, float]) -> bool:
    # 用三点叉积符号判断转向关系。
    def orientation(left: dict[str, float], mid: dict[str, float], right: dict[str, float]) -> float:
        return (mid["y"] - left["y"]) * (right["x"] - mid["x"]) - (mid["x"] - left["x"]) * (right["y"] - mid["y"])

    # 在线段端点包围盒内时，共线点视为落在线段上。
    def on_segment(left: dict[str, float], mid: dict[str, float], right: dict[str, float]) -> bool:
        return (
            min(left["x"], right["x"]) <= mid["x"] <= max(left["x"], right["x"])
            and min(left["y"], right["y"]) <= mid["y"] <= max(left["y"], right["y"])
        )

    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    epsilon = 1e-9
    if abs(o1) < epsilon and on_segment(a, c, b):
        return True
    if abs(o2) < epsilon and on_segment(a, d, b):
        return True
    if abs(o3) < epsilon and on_segment(c, a, d):
        return True
    if abs(o4) < epsilon and on_segment(c, b, d):
        return True
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


# 判断一段行走路径是否穿过餐桌避障矩形。
def _segment_intersects_box(start: dict[str, float], end: dict[str, float], box: dict[str, float]) -> bool:
    if _point_inside_box(start, box) or _point_inside_box(end, box):
        return True
    corners = [
        {"x": box["left"], "y": box["top"]},
        {"x": box["right"], "y": box["top"]},
        {"x": box["right"], "y": box["bottom"]},
        {"x": box["left"], "y": box["bottom"]},
    ]
    return any(
        _segments_intersect(start, end, corners[index], corners[(index + 1) % len(corners)])
        for index in range(len(corners))
    )


# 生成带可选 padding 的矩形盒，用于行走路径碰撞检测。
def _box(left: float, top: float, right: float, bottom: float, padding: float = 0.0) -> dict[str, float]:
    return {
        "left": left - padding,
        "top": top - padding,
        "right": right + padding,
        "bottom": bottom + padding,
    }


# 对可能为空的数值序列求平均，空序列返回 0。
def _average(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


# 将仿真 dataclass 结果递归转换成可序列化字典。
def dataclass_to_dict(value: Any) -> Any:
    return asdict(value)
