from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .campus import (
    CampusBuildingDemandData,
    CampusDemandConfigData,
    build_campus_arrival_schedule,
    cafeteria_choice_probabilities,
)
from .simulation import (
    DiningLayoutData,
    LayoutTableData,
    MetricsSummary,
    SimulationConfigData,
    _default_layout,
    run_simulation,
)


@dataclass(frozen=True)
class RecommendationRequestData:
    base_config: SimulationConfigData
    window_options: list[int]
    seat_options: list[int]
    stagger_options: list[int]
    peak_count_options: list[int] = field(default_factory=lambda: [1])
    top_k: int = 5


@dataclass(frozen=True)
class CandidateResultData:
    config: SimulationConfigData
    metrics: MetricsSummary
    score: float
    strategy: str


@dataclass(frozen=True)
class RecommendationResultData:
    baseline_metrics: MetricsSummary
    best: CandidateResultData
    ranking: list[CandidateResultData]
    explanation_summary: str
    alternatives: list[str]


def recommend_config(request: RecommendationRequestData) -> RecommendationResultData:
    campus_mode = _uses_campus_peak_search(request.base_config)
    baseline_metrics = _estimate_recommendation_metrics(request.base_config)
    candidates: list[CandidateResultData] = []
    candidate_keys = _candidate_keys(request, campus_mode)
    for windows, seats, stagger, peak_count in candidate_keys:
        config = _candidate_config(request.base_config, windows, seats, stagger, peak_count)
        metrics = baseline_metrics if _is_baseline_candidate_key(request.base_config, windows, seats, stagger, peak_count, campus_mode) else _estimate_recommendation_metrics(config)
        candidates.append(
            CandidateResultData(
                config=config,
                metrics=metrics,
                score=_score_candidate(metrics, config, request.base_config),
                strategy=_strategy_label(config, request.base_config),
            )
        )
    if not candidates:
        raise ValueError("至少需要提供一组候选方案。")

    ranking = sorted(candidates, key=lambda item: (item.score, item.metrics.avg_wait, item.metrics.peak_queue))
    top_k = max(1, request.top_k)
    best = ranking[0]
    return RecommendationResultData(
        baseline_metrics=baseline_metrics,
        best=best,
        ranking=ranking[:top_k],
        explanation_summary=_build_summary(best, baseline_metrics),
        alternatives=[candidate.strategy for candidate in ranking[1:top_k]],
    )


def _candidate_keys(request: RecommendationRequestData, campus_mode: bool) -> list[tuple[int, int, int, int]]:
    keys: list[tuple[int, int, int, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    peak_counts = _peak_count_options(request.peak_count_options if campus_mode else [1])
    for windows in request.window_options:
        for seats in request.seat_options:
            for peak_count in peak_counts:
                for stagger in _stagger_options_for_peak(request.stagger_options, peak_count, campus_mode):
                    key = (windows, seats, stagger, peak_count)
                    if key in seen:
                        continue
                    seen.add(key)
                    keys.append(key)
    keys.sort(key=lambda key: _candidate_key_priority(key, request.base_config, campus_mode))
    return keys


def _candidate_key_priority(
    key: tuple[int, int, int, int],
    base: SimulationConfigData,
    campus_mode: bool,
) -> tuple[float, int, int, int, int]:
    windows, seats, stagger, peak_count = key
    resource_cost = abs(windows - base.num_windows) * 4.0 + abs(seats - base.num_seats) / 20.0
    if campus_mode:
        peak_cost = 0.0 if peak_count <= 1 else (peak_count - 1) * 0.7 + max(0, stagger) / 20.0
    else:
        peak_cost = max(0, stagger) / 10.0
    return (resource_cost + peak_cost, windows, seats, peak_count, stagger)


def _is_baseline_candidate_key(
    base: SimulationConfigData,
    windows: int,
    seats: int,
    stagger: int,
    peak_count: int,
    campus_mode: bool,
) -> bool:
    if windows != base.num_windows or seats != base.num_seats:
        return False
    if campus_mode:
        return peak_count <= 1 and stagger == 0
    return stagger == base.stagger_minutes


def _score_candidate(metrics: MetricsSummary, config: SimulationConfigData, base: SimulationConfigData) -> float:
    added_window_cost = max(0, config.num_windows - base.num_windows) * 3.0
    added_seat_cost = max(0, config.num_seats - base.num_seats) * 0.05
    stagger_cost = _stagger_cost(config, base)
    overload_penalty = 0.0
    if metrics.window_utilization > 0.92:
        overload_penalty += (metrics.window_utilization - 0.92) * 80
    if metrics.seat_utilization > 0.92:
        overload_penalty += (metrics.seat_utilization - 0.92) * 60
    return round(
        metrics.avg_wait * 3.0
        + metrics.peak_queue * 0.35
        + metrics.peak_waiting_for_seat * 0.45
        + added_window_cost
        + added_seat_cost
        + stagger_cost
        + overload_penalty,
        4,
    )


def _estimate_recommendation_metrics(config: SimulationConfigData) -> MetricsSummary:
    schedule = _estimate_arrival_schedule(config)
    total_arrived = sum(schedule.values())
    if total_arrived <= 0:
        return MetricsSummary(
            run_id="estimate",
            avg_wait=0.0,
            avg_queue_wait=0.0,
            avg_seat_wait=0.0,
            peak_queue=0,
            peak_waiting_for_seat=0,
            throughput=0,
            total_arrived=0,
            total_left=0,
            seat_utilization=0.0,
            window_utilization=0.0,
            bottleneck_type="整体均衡",
            chart_data={},
        )

    service_capacity = max(0.05, config.num_windows / max(0.1, config.service_time_mean))
    dining_minutes = max(1, int(math.ceil(config.dining_time_mean)))
    last_arrival = max(schedule) if schedule else 0
    horizon = max(config.duration_min, last_arrival + dining_minutes + int(math.ceil(config.service_time_mean)) + 5)
    releases = [0.0 for _ in range(horizon + dining_minutes + 2)]
    queue_backlog = 0.0
    seat_waiting = 0.0
    occupied_seats = 0.0
    queue_wait_area = 0.0
    seat_wait_area = 0.0
    occupied_seat_area = 0.0
    served_total = 0.0
    left_total = 0.0
    peak_queue = 0.0
    peak_waiting_for_seat = 0.0

    for minute in range(horizon):
        occupied_seats = max(0.0, occupied_seats - releases[minute])
        left_total += releases[minute]

        arrivals = float(schedule.get(minute, 0))
        service_demand = queue_backlog + arrivals
        served = min(service_demand, service_capacity)
        queue_backlog = max(0.0, service_demand - served)
        served_total += served

        seat_demand = seat_waiting + served
        available_seats = max(0.0, config.num_seats - occupied_seats)
        newly_seated = min(seat_demand, available_seats)
        seat_waiting = max(0.0, seat_demand - newly_seated)
        occupied_seats += newly_seated
        release_minute = min(len(releases) - 1, minute + dining_minutes)
        releases[release_minute] += newly_seated

        queue_wait_area += queue_backlog
        seat_wait_area += seat_waiting
        occupied_seat_area += min(config.num_seats, occupied_seats)
        peak_queue = max(peak_queue, queue_backlog)
        peak_waiting_for_seat = max(peak_waiting_for_seat, seat_waiting)

    avg_queue_wait = queue_wait_area / total_arrived
    avg_seat_wait = seat_wait_area / total_arrived
    avg_wait = avg_queue_wait + avg_seat_wait
    window_capacity_total = service_capacity * max(1, horizon)
    seat_capacity_total = max(1, config.num_seats) * max(1, horizon)
    window_utilization = min(1.0, served_total / window_capacity_total)
    seat_utilization = min(1.0, occupied_seat_area / seat_capacity_total)
    peak_queue_int = int(math.ceil(peak_queue))
    peak_waiting_int = int(math.ceil(peak_waiting_for_seat))
    bottleneck = _estimated_bottleneck_type(peak_queue_int, peak_waiting_int, window_utilization, seat_utilization)

    return MetricsSummary(
        run_id="estimate",
        avg_wait=round(avg_wait, 2),
        avg_queue_wait=round(avg_queue_wait, 2),
        avg_seat_wait=round(avg_seat_wait, 2),
        peak_queue=peak_queue_int,
        peak_waiting_for_seat=peak_waiting_int,
        throughput=int(round(min(total_arrived, left_total))),
        total_arrived=int(total_arrived),
        total_left=int(round(min(total_arrived, left_total))),
        seat_utilization=round(seat_utilization, 4),
        window_utilization=round(window_utilization, 4),
        bottleneck_type=bottleneck,
        chart_data={},
    )


def _estimate_arrival_schedule(config: SimulationConfigData) -> dict[int, float]:
    campus = config.campus_demand
    if campus and campus.enabled and campus.cafeteria_id:
        return {
            minute: float(count)
            for minute, count in build_campus_arrival_schedule(campus.cafeteria_id, campus.buildings, seed=config.seed).items()
        }
    return {
        minute: _manual_arrival_rate_for_minute(config, minute)
        for minute in range(max(0, config.duration_min))
    }


def _manual_arrival_rate_for_minute(config: SimulationConfigData, minute: int) -> float:
    rate = max(0.0, float(config.arrival_rate))
    in_peak = config.peak_start_min <= minute < config.peak_end_min
    if not in_peak:
        shoulder_end = config.peak_end_min + max(0, config.stagger_minutes)
        if config.stagger_minutes and config.peak_end_min <= minute < shoulder_end:
            return rate * (1.0 + min(0.35, config.stagger_minutes / 60))
        return rate

    stagger_factor = max(0.55, 1.0 - config.stagger_minutes / 45)
    return rate * max(0.0, config.peak_multiplier) * stagger_factor


def _estimated_bottleneck_type(
    peak_queue: int,
    peak_waiting_for_seat: int,
    window_utilization: float,
    seat_utilization: float,
) -> str:
    if peak_waiting_for_seat > 0 and seat_utilization >= 0.85:
        return "座位容量"
    if peak_queue > 0 or window_utilization >= 0.85:
        return "窗口服务"
    return "整体均衡"


def _strategy_label(config: SimulationConfigData, base: SimulationConfigData) -> str:
    parts: list[str] = []
    if config.num_windows > base.num_windows:
        parts.append(f"窗口 +{config.num_windows - base.num_windows}")
    elif config.num_windows < base.num_windows:
        parts.append(f"窗口 {config.num_windows}")
    if config.num_seats > base.num_seats:
        parts.append(f"座位 +{config.num_seats - base.num_seats}")
    elif config.num_seats < base.num_seats:
        parts.append(f"座位 {config.num_seats}")
    peak_label = _campus_peak_strategy_label(config, base)
    if peak_label:
        parts.append(peak_label)
    elif config.stagger_minutes:
        parts.append(f"错峰 {config.stagger_minutes} 分钟")
    return "，".join(parts) if parts else "保持基准配置"


def _build_summary(best: CandidateResultData, baseline: MetricsSummary) -> str:
    wait_delta = round(baseline.avg_wait - best.metrics.avg_wait, 2)
    queue_delta = baseline.peak_queue - best.metrics.peak_queue
    if wait_delta > 0 or queue_delta > 0:
        return (
            f"推荐采用“{best.strategy}”。相较基准方案，平均等待时间减少约 {wait_delta} 分钟，"
            f"峰值排队长度减少 {queue_delta} 人，主要改善瓶颈为 {best.metrics.bottleneck_type}。"
        )
    return f"推荐采用“{best.strategy}”。该方案在资源成本和等待指标之间综合评分最低。"


def _candidate_layout(base: SimulationConfigData, windows: int, seats: int) -> DiningLayoutData | None:
    if base.layout is None:
        return None

    default = _default_layout(replace(base, num_windows=windows, num_seats=seats, layout=None))
    base_windows = list(base.layout.windows)
    candidate_windows = base_windows[:windows]
    if len(candidate_windows) < windows:
        candidate_windows.extend(default.windows[len(candidate_windows):windows])

    if sum(table.capacity for table in base.layout.tables) == seats:
        candidate_tables = list(base.layout.tables)
    else:
        candidate_tables = []
        for index, default_table in enumerate(default.tables):
            if index < len(base.layout.tables):
                existing = base.layout.tables[index]
                candidate_tables.append(
                    LayoutTableData(
                        id=existing.id,
                        x=existing.x,
                        y=existing.y,
                        table_type=default_table.table_type,
                        capacity=default_table.capacity,
                        rotation=existing.rotation,
                    )
                )
            else:
                candidate_tables.append(default_table)

    return DiningLayoutData(
        doors=list(base.layout.doors) or list(default.doors),
        windows=candidate_windows,
        tables=candidate_tables,
    )


def _candidate_config(base: SimulationConfigData, windows: int, seats: int, stagger: int, peak_count: int) -> SimulationConfigData:
    campus_mode = _uses_campus_peak_search(base)
    campus_demand = base.campus_demand
    stagger_minutes = stagger
    if campus_mode:
        campus_demand = _campus_demand_with_peaks(base.campus_demand, peak_count, stagger)
        stagger_minutes = 0
    return replace(
        base,
        num_windows=windows,
        num_seats=seats,
        stagger_minutes=stagger_minutes,
        campus_demand=campus_demand,
        layout=_candidate_layout(base, windows, seats),
    )


def _uses_campus_peak_search(config: SimulationConfigData) -> bool:
    campus = config.campus_demand
    return bool(campus and campus.enabled and campus.buildings)


def _peak_count_options(values: list[int]) -> list[int]:
    normalized = sorted({max(1, min(6, int(value))) for value in values if int(value) >= 1})
    return normalized or [1]


def _stagger_options_for_peak(stagger_options: list[int], peak_count: int, campus_mode: bool) -> list[int]:
    if not campus_mode:
        return stagger_options
    if peak_count <= 1:
        return [0]
    positive_options = [option for option in stagger_options if option > 0]
    return positive_options or [0]


def _campus_demand_with_peaks(
    campus: CampusDemandConfigData | None,
    peak_count: int,
    peak_gap_minutes: int,
) -> CampusDemandConfigData | None:
    if campus is None or peak_count <= 1 or peak_gap_minutes <= 0:
        return campus
    assignments = _assign_buildings_to_peaks(campus.buildings, campus.cafeteria_id, peak_count)
    buildings = [
        replace(
            building,
            dismissal_minute=max(0, building.dismissal_minute) + assignments.get(building.building_id, 0) * peak_gap_minutes,
        )
        for building in campus.buildings
    ]
    return replace(campus, buildings=buildings)


def _assign_buildings_to_peaks(
    buildings: list[CampusBuildingDemandData],
    cafeteria_id: str | None,
    peak_count: int,
) -> dict[str, int]:
    bucket_loads = [0.0 for _ in range(max(1, peak_count))]
    assignments: dict[str, int] = {}
    weighted = sorted(
        ((_estimated_building_demand(building, cafeteria_id), building) for building in buildings),
        key=lambda item: (-item[0], item[1].building_id),
    )
    for weight, building in weighted:
        bucket_index = min(range(len(bucket_loads)), key=lambda index: (bucket_loads[index], index))
        assignments[building.building_id] = bucket_index
        bucket_loads[bucket_index] += weight
    return assignments


def _estimated_building_demand(building: CampusBuildingDemandData, cafeteria_id: str | None) -> float:
    released = sum(max(0, floor.count) for floor in building.floors) * max(0.0, min(1.0, building.release_ratio))
    if not cafeteria_id:
        return released
    try:
        return released * cafeteria_choice_probabilities(building.building_id).get(cafeteria_id, 1.0)
    except ValueError:
        return released


def _stagger_cost(config: SimulationConfigData, base: SimulationConfigData) -> float:
    if _uses_campus_peak_search(config):
        return _campus_delay_cost(config.campus_demand, base.campus_demand)
    return max(0, config.stagger_minutes) * 0.08


def _campus_delay_cost(candidate: CampusDemandConfigData | None, base: CampusDemandConfigData | None) -> float:
    if not candidate or not base:
        return 0.0
    base_by_id = {building.building_id: building for building in base.buildings}
    weighted_delay = 0.0
    total_weight = 0.0
    peak_offsets: set[int] = set()
    for building in candidate.buildings:
        base_building = base_by_id.get(building.building_id)
        if not base_building:
            continue
        weight = _estimated_building_demand(building, candidate.cafeteria_id)
        delay = max(0, building.dismissal_minute - base_building.dismissal_minute)
        weighted_delay += weight * delay
        total_weight += weight
        peak_offsets.add(delay)
    average_delay = weighted_delay / total_weight if total_weight else 0.0
    peak_count_cost = max(0, len(peak_offsets) - 1) * 1.5
    return average_delay * 0.12 + peak_count_cost


def _campus_peak_strategy_label(config: SimulationConfigData, base: SimulationConfigData) -> str:
    candidate = config.campus_demand
    baseline = base.campus_demand
    if not candidate or not baseline or not _uses_campus_peak_search(config):
        return ""
    baseline_by_id = {building.building_id: building for building in baseline.buildings}
    offsets = sorted({
        max(0, building.dismissal_minute - baseline_by_id[building.building_id].dismissal_minute)
        for building in candidate.buildings
        if building.building_id in baseline_by_id
    })
    if len(offsets) <= 1:
        return ""
    gaps = [right - left for left, right in zip(offsets, offsets[1:]) if right > left]
    gap_label = min(gaps) if gaps else offsets[-1]
    return f"{len(offsets)} 峰下课，间隔 {gap_label} 分钟"
