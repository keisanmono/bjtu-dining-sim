from __future__ import annotations

import math
import random
import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import Any

WALKING_SPEED_UNITS_PER_SEC = 38.0
MIN_WALKING_DURATION_SEC = 3
MAX_WALKING_DURATION_SEC = 45
TIMELINE_BASE_PLAYBACK_MS = 720
WALKING_PLAYBACK_MS_PER_SEC = 90
MIN_WALKING_PLAYBACK_MS = 320
MAX_WALKING_PLAYBACK_MS = 900
PATH_OBSTACLE_PADDING = 7


@dataclass(frozen=True)
class LayoutDoorData:
    id: str
    x: float
    y: float
    wall_side: str = "left"
    arrival_share: float = 1.0


@dataclass(frozen=True)
class LayoutWindowData:
    id: str
    x: float
    y: float
    wall_side: str = "top"
    service_rate_factor: float = 1.0


@dataclass(frozen=True)
class LayoutTableData:
    id: str
    x: float
    y: float
    table_type: str = "four_seat"
    capacity: int = 4
    rotation: int = 0


@dataclass(frozen=True)
class DiningLayoutData:
    doors: list[LayoutDoorData] = field(default_factory=list)
    windows: list[LayoutWindowData] = field(default_factory=list)
    tables: list[LayoutTableData] = field(default_factory=list)


@dataclass(frozen=True)
class SimulationConfigData:
    num_windows: int = 4
    num_seats: int = 120
    arrival_rate: float = 8.0
    service_time_mean: float = 3.0
    dining_time_mean: float = 20.0
    duration_min: int = 60
    seed: int = 20
    peak_start_min: int = 15
    peak_end_min: int = 40
    peak_multiplier: float = 1.4
    stagger_minutes: int = 0
    seat_columns: int = 12
    layout: DiningLayoutData | None = None
    party_size_distribution: dict[int, float] = field(default_factory=lambda: {1: 1.0})

    def with_updates(self, **updates: Any) -> "SimulationConfigData":
        return replace(self, **updates)


@dataclass
class Student:
    student_id: int
    party_id: int
    arrival_time: int
    queue_enter_time: int
    door_index: int = 0
    service_start_time: int | None = None
    service_end_time: int | None = None
    seat_time: int | None = None
    leave_time: int | None = None
    window_index: int | None = None


@dataclass
class DiningParty:
    party_id: int
    arrival_time: int
    door_index: int
    student_ids: list[int]
    ready_time: int | None = None
    seat_time: int | None = None
    table_index: int | None = None

    @property
    def size(self) -> int:
        return len(self.student_ids)


@dataclass
class WindowService:
    student: Student
    remaining: int


@dataclass
class DiningSeat:
    student: Student
    remaining: int
    table_index: int | None = None


@dataclass
class WalkingSeatTransfer:
    party: DiningParty
    table_index: int
    window_index: int
    dining_remaining: int
    start_time_sec: int
    arrive_time_sec: int
    path: list[dict[str, float]]


@dataclass(frozen=True)
class StepRecord:
    run_id: str
    t: int
    arrived_count: int
    queue_lengths: list[int]
    served_count: int
    seated_count: int
    left_count: int
    empty_seats: int
    waiting_for_seat_count: int
    total_arrived: int
    total_served: int
    total_seated: int
    total_left: int
    avg_wait_so_far: float
    snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
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
    avg_party_gather_wait: float = 0.0
    party_split_count: int = 0
    shared_table_count: int = 0
    blocked_party_count: int = 0
    fragmented_seats: int = 0
    table_utilization_by_type: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SimulationResult:
    run_id: str
    config: SimulationConfigData
    records: list[StepRecord]
    metrics: MetricsSummary
    final_state: dict[str, Any]


def validate_config(config: SimulationConfigData) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
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
    if config.arrival_rate <= 0:
        errors.append("平均每分钟到达人数必须大于 0。")
    if config.service_time_mean <= 0:
        errors.append("平均打饭时长必须大于 0。")
    if config.dining_time_mean <= 0:
        errors.append("平均就餐时长必须大于 0。")
    if config.duration_min < 5 or config.duration_min > 360:
        errors.append("到达时段应在 5 到 360 分钟之间。")
    if config.peak_start_min >= config.peak_end_min:
        warnings.append("高峰开始时间不早于结束时间，将按普通到达人数运行。")
    if config.num_seats < config.num_windows * 6:
        warnings.append("座位数相对窗口数偏少，可能出现入座瓶颈。")
    if config.arrival_rate * config.service_time_mean > config.num_windows * 1.2:
        warnings.append("到达强度高于窗口服务能力，可能形成长队。")
    party_distribution = _normalized_party_distribution(config.party_size_distribution)
    if not party_distribution:
        errors.append("结伴人数分布至少需要一个正权重。")
    elif layout.tables and max(size for size, _weight in party_distribution) > max(table.capacity for table in layout.tables):
        errors.append("结伴人数不能超过最大单桌容量。")
    if sum(table.capacity for table in layout.tables) < len(layout.windows):
        warnings.append("布局座位容量相对窗口数偏少，可能出现入座瓶颈。")
    return errors, warnings


def run_simulation(config: SimulationConfigData, run_id: str | None = None) -> SimulationResult:
    runner = DiningSimulationRunner(config, run_id=run_id)
    while not runner.done:
        runner.step()
    return runner.result()


class DiningSimulationRunner:
    def __init__(self, config: SimulationConfigData, run_id: str | None = None):
        errors, _ = validate_config(config)
        if errors:
            raise ValueError("; ".join(errors))
        self.config = config
        self.layout = _effective_layout(config)
        self.total_seat_capacity = sum(table.capacity for table in self.layout.tables)
        self.run_id = run_id or uuid.uuid4().hex
        self.rng = random.Random(config.seed)
        self.current_minute = 0
        self.next_student_id = 1
        self.next_party_id = 1
        self.queues: list[list[Student]] = [[] for _ in range(len(self.layout.windows))]
        self.windows: list[WindowService | None] = [None for _ in range(len(self.layout.windows))]
        self.waiting_for_seat: list[DiningParty] = []
        self.walking_to_seat: list[WalkingSeatTransfer] = []
        self.seated: list[DiningSeat] = []
        self.table_occupied_seats: list[int] = [0 for _ in self.layout.tables]
        self.table_reserved_seats: list[int] = [0 for _ in self.layout.tables]
        self.table_party_ids: list[set[int]] = [set() for _ in self.layout.tables]
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
            "shared_table_count": 0,
            "blocked_party_count": 0,
        }
        self.blocked_party_ids: set[int] = set()
        self.peak_fragmented_seats = 0

    @property
    def done(self) -> bool:
        return self.current_minute >= self.config.duration_min and not self._has_active_students()

    def step(self) -> StepRecord:
        if self.done:
            raise RuntimeError("仿真已经结束。")

        minute = self.current_minute
        step_start_sec = minute * 60
        step_end_sec = (minute + 1) * 60
        timeline_events: list[dict[str, Any]] = []
        left_count = self._advance_dining(minute)
        served_students = self._advance_windows(minute)
        self._move_ready_parties_to_seat_wait(served_students, minute)
        self._seat_waiting_students(minute, timeline_events=timeline_events)
        arrivals = self._generate_arrivals(minute)
        self._enqueue_arrivals(arrivals)
        self._start_window_services(minute)
        seated_count = self._advance_walking_to_seats(step_end_sec)
        self.peak_fragmented_seats = max(self.peak_fragmented_seats, self._fragmented_seats())

        busy_windows = sum(1 for window in self.windows if window is not None)
        self.window_busy_minutes += busy_windows
        self.seat_occupied_minutes += len(self.seated)

        self.current_minute += 1
        record = self._build_record(
            t=self.current_minute,
            arrived_count=len(arrivals),
            served_count=len(served_students),
            seated_count=seated_count,
            left_count=left_count,
            timeline=self._build_step_timeline(step_start_sec, step_end_sec, timeline_events),
        )
        self.records.append(record)
        return record

    def result(self) -> SimulationResult:
        metrics = self._build_metrics()
        return SimulationResult(
            run_id=self.run_id,
            config=self.config,
            records=list(self.records),
            metrics=metrics,
            final_state=self._snapshot(),
        )

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
                    if not any(
                        other.student.party_id == party_id and other.table_index == seat.table_index and other.remaining > 0
                        for other in self.seated
                    ):
                        self.table_party_ids[seat.table_index].discard(party_id)
                self.total_left += 1
                left_count += 1
            else:
                still_seated.append(seat)
        self.seated = still_seated
        return left_count

    def _advance_windows(self, minute: int) -> list[Student]:
        served: list[Student] = []
        for idx, service in enumerate(self.windows):
            if service is None:
                continue
            service.remaining -= 1
            if service.remaining <= 0:
                service.student.service_end_time = minute
                served.append(service.student)
                self.windows[idx] = None
                self.total_served += 1
        return served

    def _move_ready_parties_to_seat_wait(self, served_students: list[Student], minute: int) -> None:
        for student in served_students:
            party = self.parties[student.party_id]
            if party.ready_time is not None:
                continue
            members = [self.students[student_id] for student_id in party.student_ids]
            if all(member.service_end_time is not None for member in members):
                party.ready_time = minute
                self.waiting_for_seat.append(party)

    def _seat_waiting_students(self, minute: int, timeline_events: list[dict[str, Any]] | None = None) -> int:
        walking_count = 0
        still_waiting: list[DiningParty] = []
        for party in self.waiting_for_seat:
            table_index = self._choose_table_for_party(party)
            if table_index is None:
                still_waiting.append(party)
                self.blocked_party_ids.add(party.party_id)
                self.metrics_counters["blocked_party_count"] = len(self.blocked_party_ids)
                continue
            occupied_before = self.table_occupied_seats[table_index] + self.table_reserved_seats[table_index]
            if occupied_before > 0:
                self.metrics_counters["shared_table_count"] += 1
            remaining = self._sample_duration(self.config.dining_time_mean)
            transfer = self._start_walking_to_seat(party, table_index, remaining, minute)
            self.walking_to_seat.append(transfer)
            self.table_reserved_seats[table_index] += party.size
            party.table_index = table_index
            walking_count += party.size
            if timeline_events is not None:
                timeline_events.append(self._walking_event_snapshot(transfer, step_start_sec=minute * 60))
        self.waiting_for_seat = still_waiting
        return walking_count

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

    def _advance_walking_to_seats(self, end_time_sec: int) -> int:
        arrived_count = 0
        still_walking: list[WalkingSeatTransfer] = []
        for transfer in self.walking_to_seat:
            if transfer.arrive_time_sec > end_time_sec:
                still_walking.append(transfer)
                continue
            party = transfer.party
            seat_minute = math.ceil(transfer.arrive_time_sec / 60)
            for student_id in party.student_ids:
                student = self.students[student_id]
                student.seat_time = seat_minute
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
            self.table_occupied_seats[transfer.table_index] += party.size
            self.table_party_ids[transfer.table_index].add(party.party_id)
            party.seat_time = seat_minute
            party.table_index = transfer.table_index
            self.total_seated += party.size
            arrived_count += party.size
        self.walking_to_seat = still_walking
        return arrived_count

    def _generate_arrivals(self, minute: int) -> list[Student]:
        if minute >= self.config.duration_min:
            return []
        count = self._poisson(self._arrival_rate_for_minute(minute))
        return self._create_party_students(minute=minute, person_count=count)

    def _create_party_students(self, minute: int, person_count: int) -> list[Student]:
        arrivals = []
        remaining = max(0, person_count)
        while remaining > 0:
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
            self.parties[party_id] = DiningParty(
                party_id=party_id,
                arrival_time=minute,
                door_index=door_index,
                student_ids=student_ids,
            )
            remaining -= party_size
        return arrivals

    def _enqueue_arrivals(self, arrivals: list[Student]) -> None:
        for student in arrivals:
            idx = self._choose_window_for_student(student)
            student.window_index = idx
            self.queues[idx].append(student)

    def _choose_window_for_student(self, student: Student) -> int:
        door = self.layout.doors[min(student.door_index, len(self.layout.doors) - 1)]
        return min(
            range(len(self.queues)),
            key=lambda idx: (
                len(self.queues[idx]) * 5.0 + _distance(door, self.layout.windows[idx]) * 0.02,
                idx,
            ),
        )

    def _start_window_services(self, minute: int) -> None:
        for idx, service in enumerate(self.windows):
            if service is not None or not self.queues[idx]:
                continue
            student = self.queues[idx].pop(0)
            student.service_start_time = minute
            window = self.layout.windows[idx]
            self.windows[idx] = WindowService(
                student=student,
                remaining=self._sample_duration(self.config.service_time_mean / max(0.1, window.service_rate_factor)),
            )

    def _choose_table_for_party(self, party: DiningParty) -> int | None:
        candidates: list[tuple[float, int]] = []
        party_window = self._party_reference_window(party)
        for idx, table in enumerate(self.layout.tables):
            occupied = self.table_occupied_seats[idx] + self.table_reserved_seats[idx]
            available = table.capacity - occupied
            if available < party.size:
                continue
            is_empty = occupied == 0
            distance_cost = _distance(party_window, table) * 0.015
            share_penalty = 0.0 if is_empty else (6.0 if party.size == 1 else 3.0)
            waste_penalty = max(0, available - party.size) * (0.7 if party.size == 1 else 0.35)
            single_empty_bonus = -2.0 if party.size == 1 and is_empty else 0.0
            candidates.append((distance_cost + share_penalty + waste_penalty + single_empty_bonus, idx))
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[0], item[1]))[1]

    def _party_reference_window(self, party: DiningParty) -> LayoutWindowData:
        return self.layout.windows[self._party_reference_window_index(party)]

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
                student.service_end_time if student.service_end_time is not None else -1,
                -student.student_id,
            ),
        )
        return min(max(0, int(latest.window_index or 0)), len(self.layout.windows) - 1)

    def _window_service_point(self, window: LayoutWindowData) -> dict[str, float]:
        normal = self._wall_normal(window.wall_side)
        footprint = self._opening_footprint("window", window.wall_side)
        half = footprint["width"] / 2 if window.wall_side in {"left", "right"} else footprint["height"] / 2
        return _clean_point({
            "x": window.x + normal["x"] * (half + 6),
            "y": window.y + normal["y"] * (half + 6),
        })

    def _walking_path(
        self,
        start: dict[str, float],
        end: dict[str, float],
        target_table_index: int,
    ) -> list[dict[str, float]]:
        boxes = self._table_obstacle_boxes(exclude_index=target_table_index)
        direct = _dedupe_path([start, end])
        if self._path_is_clear(direct, boxes):
            return direct

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
        return direct

    def _path_is_clear(self, path: list[dict[str, float]], boxes: list[dict[str, float]]) -> bool:
        points = _dedupe_path(path)
        return all(
            not any(_segment_intersects_box(points[index - 1], points[index], box) for box in boxes)
            for index in range(1, len(points))
        )

    def _walking_duration_sec(self, path: list[dict[str, float]]) -> int:
        distance = _path_length(path)
        if distance <= 0:
            return MIN_WALKING_DURATION_SEC
        return max(
            MIN_WALKING_DURATION_SEC,
            min(MAX_WALKING_DURATION_SEC, int(round(distance / WALKING_SPEED_UNITS_PER_SEC))),
        )

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

    def _opening_footprint(self, kind: str, wall_side: str) -> dict[str, float]:
        if kind == "door":
            horizontal = {"width": 52.0, "height": 32.0}
            vertical = {"width": 32.0, "height": 52.0}
        else:
            horizontal = {"width": 36.0, "height": 32.0}
            vertical = {"width": 32.0, "height": 36.0}
        return horizontal if wall_side in {"top", "bottom"} else vertical

    def _wall_normal(self, wall_side: str) -> dict[str, float]:
        if wall_side == "right":
            return {"x": -1.0, "y": 0.0}
        if wall_side == "bottom":
            return {"x": 0.0, "y": -1.0}
        if wall_side == "left":
            return {"x": 1.0, "y": 0.0}
        return {"x": 0.0, "y": 1.0}

    def _arrival_rate_for_minute(self, minute: int) -> float:
        rate = self.config.arrival_rate
        in_peak = self.config.peak_start_min <= minute < self.config.peak_end_min
        if not in_peak:
            shoulder_end = self.config.peak_end_min + max(0, self.config.stagger_minutes)
            if self.config.stagger_minutes and self.config.peak_end_min <= minute < shoulder_end:
                return rate * (1.0 + min(0.35, self.config.stagger_minutes / 60))
            return rate

        stagger_factor = max(0.55, 1.0 - self.config.stagger_minutes / 45)
        return rate * self.config.peak_multiplier * stagger_factor

    def _poisson(self, lam: float) -> int:
        if lam <= 0:
            return 0
        if lam > 50:
            return max(0, int(round(self.rng.gauss(lam, math.sqrt(lam)))))
        threshold = math.exp(-lam)
        count = 0
        product = 1.0
        while product > threshold:
            count += 1
            product *= self.rng.random()
        return count - 1

    def _sample_duration(self, mean: float) -> int:
        if mean <= 1:
            return 1
        spread = max(0.35, mean * 0.22)
        return max(1, int(round(self.rng.gauss(mean, spread))))

    def _sample_party_size(self) -> int:
        distribution = _normalized_party_distribution(self.config.party_size_distribution)
        threshold = self.rng.random()
        cumulative = 0.0
        for size, weight in distribution:
            cumulative += weight
            if threshold <= cumulative:
                return size
        return distribution[-1][0] if distribution else 1

    def _sample_door_index(self) -> int:
        shares = [max(0.0, door.arrival_share) for door in self.layout.doors]
        total = sum(shares)
        if total <= 0:
            return 0
        threshold = self.rng.random() * total
        cumulative = 0.0
        for idx, share in enumerate(shares):
            cumulative += share
            if threshold <= cumulative:
                return idx
        return len(shares) - 1

    def _waiting_for_seat_people(self) -> int:
        return sum(party.size for party in self.waiting_for_seat)

    def _fragmented_seats(self) -> int:
        return sum(
            table.capacity - occupied
            for table, occupied in zip(self.layout.tables, self.table_occupied_seats)
            if 0 < occupied < table.capacity
        )

    def _has_active_students(self) -> bool:
        return (
            any(self.queues)
            or any(window is not None for window in self.windows)
            or bool(self.waiting_for_seat)
            or bool(self.walking_to_seat)
            or bool(self.seated)
        )

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
            arrived_count=arrived_count,
            queue_lengths=[len(queue) for queue in self.queues],
            served_count=served_count,
            seated_count=seated_count,
            left_count=left_count,
            empty_seats=self.total_seat_capacity - len(self.seated),
            waiting_for_seat_count=self._waiting_for_seat_people(),
            total_arrived=len(self.students),
            total_served=self.total_served,
            total_seated=self.total_seated,
            total_left=self.total_left,
            avg_wait_so_far=self._avg_wait_so_far(),
            snapshot=snapshot,
        )

    def _avg_wait_so_far(self) -> float:
        waits = [
            student.seat_time - student.arrival_time
            for student in self.students.values()
            if student.seat_time is not None
        ]
        return round(sum(waits) / len(waits), 2) if waits else 0.0

    def _snapshot(self) -> dict[str, Any]:
        occupied = len(self.seated)
        return {
            "minute": self.current_minute,
            "queue_lengths": [len(queue) for queue in self.queues],
            "queue_groups": self._queue_groups_snapshot(),
            "busy_windows": [window is not None for window in self.windows],
            "window_services": self._window_services_snapshot(),
            "occupied_seats": occupied,
            "empty_seats": self.total_seat_capacity - occupied,
            "waiting_for_seat_count": self._waiting_for_seat_people(),
            "waiting_party_count": len(self.waiting_for_seat),
            "waiting_parties": self._waiting_parties_snapshot(),
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

    def _queue_groups_snapshot(self) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for window_index, queue in enumerate(self.queues):
            grouped: dict[int, dict[str, Any]] = {}
            for position, student in enumerate(queue):
                party = self.parties[student.party_id]
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

    def _walking_parties_snapshot(self, time_sec: int | None = None) -> list[dict[str, Any]]:
        now_sec = self.current_minute * 60 if time_sec is None else time_sec
        return [
            self._walking_transfer_snapshot(transfer, now_sec)
            for transfer in self.walking_to_seat
        ]

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

    def _walking_event_snapshot(self, transfer: WalkingSeatTransfer, step_start_sec: int) -> dict[str, Any]:
        payload = self._walking_transfer_snapshot(transfer, transfer.start_time_sec)
        duration_sec = max(1, transfer.arrive_time_sec - transfer.start_time_sec)
        playback_start_ms = max(
            0,
            round((transfer.start_time_sec - step_start_sec) / 60 * TIMELINE_BASE_PLAYBACK_MS),
        )
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

    def _seated_parties_snapshot(self) -> list[dict[str, Any]]:
        seated: dict[tuple[int, int], dict[str, Any]] = {}
        for seat in self.seated:
            if seat.table_index is None:
                continue
            party = self.parties[seat.student.party_id]
            table = self.layout.tables[seat.table_index]
            key = (party.party_id, seat.table_index)
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

    def _build_metrics(self) -> MetricsSummary:
        seated_students = [student for student in self.students.values() if student.seat_time is not None]
        served_students = [student for student in self.students.values() if student.service_start_time is not None]
        seated_parties = [party for party in self.parties.values() if party.seat_time is not None]
        seat_wait_students = [
            student
            for student in seated_students
            if student.service_end_time is not None and student.seat_time is not None
        ]
        avg_wait = _average(student.seat_time - student.arrival_time for student in seated_students)
        avg_queue_wait = _average(student.service_start_time - student.arrival_time for student in served_students)
        avg_seat_wait = _average(student.seat_time - student.service_end_time for student in seat_wait_students)
        peak_queue = max((sum(record.queue_lengths) for record in self.records), default=0)
        peak_waiting_for_seat = max((record.waiting_for_seat_count for record in self.records), default=0)
        elapsed_minutes = max(1, len(self.records))
        denominator_windows = max(1, elapsed_minutes * len(self.windows))
        denominator_seats = max(1, elapsed_minutes * self.total_seat_capacity)
        window_utilization = self.window_busy_minutes / denominator_windows
        seat_utilization = self.seat_occupied_minutes / denominator_seats
        avg_party_gather_wait = _average(self._party_gather_wait(party) for party in seated_parties)
        table_utilization_by_type = self._table_utilization_by_type()
        bottleneck = self._classify_bottleneck(
            peak_queue=peak_queue,
            peak_waiting_for_seat=peak_waiting_for_seat,
            avg_seat_wait=avg_seat_wait,
            seat_utilization=seat_utilization,
            window_utilization=window_utilization,
        )
        chart_data = {
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
            avg_party_gather_wait=round(avg_party_gather_wait, 2),
            party_split_count=self.metrics_counters["party_split_count"],
            shared_table_count=self.metrics_counters["shared_table_count"],
            blocked_party_count=self.metrics_counters["blocked_party_count"],
            fragmented_seats=self.peak_fragmented_seats,
            table_utilization_by_type=table_utilization_by_type,
        )

    def _party_gather_wait(self, party: DiningParty) -> float:
        service_end_times = [
            self.students[student_id].service_end_time
            for student_id in party.student_ids
            if self.students[student_id].service_end_time is not None
        ]
        if len(service_end_times) < 2:
            return 0.0
        return max(service_end_times) - min(service_end_times)

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
                occupied_minutes_by_type[table_type] = occupied_minutes_by_type.get(table_type, 0) + int(table.get("occupied", 0))
        return {
            table_type: round(occupied_minutes_by_type.get(table_type, 0) / max(1, elapsed_minutes * capacity), 4)
            for table_type, capacity in capacity_by_type.items()
        }

    def _classify_bottleneck(
        self,
        peak_queue: int,
        peak_waiting_for_seat: int,
        avg_seat_wait: float,
        seat_utilization: float,
        window_utilization: float,
    ) -> str:
        if peak_waiting_for_seat > 0 and (seat_utilization >= 0.72 or avg_seat_wait >= 1.0):
            return "座位容量"
        window_count = max(1, len(self.windows))
        if peak_queue >= max(8, window_count * 8) and window_utilization >= 0.72:
            return "窗口服务"
        if self.config.peak_multiplier > 1.2 and peak_queue >= max(4, window_count * 3):
            return "到达高峰"
        return "运行平衡"


def _effective_layout(config: SimulationConfigData) -> DiningLayoutData:
    if config.layout is not None:
        return config.layout
    return _default_layout(config)


def _default_layout(config: SimulationConfigData) -> DiningLayoutData:
    doors = [LayoutDoorData(id="D1", x=18, y=145, arrival_share=1.0)]
    windows = [
        LayoutWindowData(
            id=f"W{index + 1}",
            x=126 + (index % 4) * 54,
            y=82 + (index // 4) * 42,
            service_rate_factor=1.0,
        )
        for index in range(max(0, config.num_windows))
    ]
    tables = [
        LayoutTableData(
            id=f"T{index + 1}",
            x=126 + (index % 4) * 62,
            y=232 + (index // 4) * 54,
            table_type=_table_type_for_capacity(capacity),
            capacity=capacity,
        )
        for index, capacity in enumerate(_default_table_capacities(config.num_seats))
    ]
    return DiningLayoutData(doors=doors, windows=windows, tables=tables)


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


def _table_type_for_capacity(capacity: int) -> str:
    if capacity <= 1:
        return "single_seat"
    if capacity <= 2:
        return "two_seat"
    if capacity <= 4:
        return "four_seat"
    return "six_seat"


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


def _distance(a: Any, b: Any) -> float:
    return math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))


def _point_distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def _clean_point(point: dict[str, float] | Any) -> dict[str, float]:
    if isinstance(point, dict):
        x = point.get("x", 0)
        y = point.get("y", 0)
    else:
        x = getattr(point, "x", 0)
        y = getattr(point, "y", 0)
    return {"x": round(float(x), 1), "y": round(float(y), 1)}


def _dedupe_path(path: list[dict[str, float]]) -> list[dict[str, float]]:
    cleaned: list[dict[str, float]] = []
    for point in path:
        item = _clean_point(point)
        if cleaned and _point_distance(cleaned[-1], item) < 0.1:
            continue
        cleaned.append(item)
    return cleaned


def _path_length(path: list[dict[str, float]]) -> float:
    points = _dedupe_path(path)
    return sum(_point_distance(points[index - 1], points[index]) for index in range(1, len(points)))


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


def _point_inside_box(point: dict[str, float], box: dict[str, float]) -> bool:
    return box["left"] <= point["x"] <= box["right"] and box["top"] <= point["y"] <= box["bottom"]


def _segments_intersect(a: dict[str, float], b: dict[str, float], c: dict[str, float], d: dict[str, float]) -> bool:
    def orientation(left: dict[str, float], mid: dict[str, float], right: dict[str, float]) -> float:
        return (mid["y"] - left["y"]) * (right["x"] - mid["x"]) - (mid["x"] - left["x"]) * (right["y"] - mid["y"])

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


def _box(left: float, top: float, right: float, bottom: float, padding: float = 0.0) -> dict[str, float]:
    return {
        "left": left - padding,
        "top": top - padding,
        "right": right + padding,
        "bottom": bottom + padding,
    }


def _average(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def dataclass_to_dict(value: Any) -> Any:
    return asdict(value)
