from __future__ import annotations

import math
import random
import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import Any


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

    def with_updates(self, **updates: Any) -> "SimulationConfigData":
        return replace(self, **updates)


@dataclass
class Student:
    student_id: int
    arrival_time: int
    queue_enter_time: int
    service_start_time: int | None = None
    service_end_time: int | None = None
    seat_time: int | None = None
    leave_time: int | None = None
    window_index: int | None = None


@dataclass
class WindowService:
    student: Student
    remaining: int


@dataclass
class DiningSeat:
    student: Student
    remaining: int


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
    if config.num_windows < 1 or config.num_windows > 30:
        errors.append("开放窗口数应在 1 到 30 之间。")
    if config.num_seats < 1 or config.num_seats > 2000:
        errors.append("座位数应在 1 到 2000 之间。")
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
        self.run_id = run_id or uuid.uuid4().hex
        self.rng = random.Random(config.seed)
        self.current_minute = 0
        self.next_student_id = 1
        self.queues: list[list[Student]] = [[] for _ in range(config.num_windows)]
        self.windows: list[WindowService | None] = [None for _ in range(config.num_windows)]
        self.waiting_for_seat: list[Student] = []
        self.seated: list[DiningSeat] = []
        self.records: list[StepRecord] = []
        self.students: dict[int, Student] = {}
        self.total_served = 0
        self.total_seated = 0
        self.total_left = 0
        self.window_busy_minutes = 0
        self.seat_occupied_minutes = 0

    @property
    def done(self) -> bool:
        return self.current_minute >= self.config.duration_min and not self._has_active_students()

    def step(self) -> StepRecord:
        if self.done:
            raise RuntimeError("仿真已经结束。")

        minute = self.current_minute
        left_count = self._advance_dining(minute)
        served_students = self._advance_windows(minute)
        self.waiting_for_seat.extend(served_students)
        seated_count = self._seat_waiting_students(minute)
        arrivals = self._generate_arrivals(minute)
        self._enqueue_arrivals(arrivals)
        self._start_window_services(minute)

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

    def _seat_waiting_students(self, minute: int) -> int:
        seated_count = 0
        while self.waiting_for_seat and len(self.seated) < self.config.num_seats:
            student = self.waiting_for_seat.pop(0)
            student.seat_time = minute
            self.seated.append(DiningSeat(student=student, remaining=self._sample_duration(self.config.dining_time_mean)))
            self.total_seated += 1
            seated_count += 1
        return seated_count

    def _generate_arrivals(self, minute: int) -> list[Student]:
        if minute >= self.config.duration_min:
            return []
        count = self._poisson(self._arrival_rate_for_minute(minute))
        arrivals = []
        for _ in range(count):
            student = Student(
                student_id=self.next_student_id,
                arrival_time=minute,
                queue_enter_time=minute,
            )
            self.students[student.student_id] = student
            self.next_student_id += 1
            arrivals.append(student)
        return arrivals

    def _enqueue_arrivals(self, arrivals: list[Student]) -> None:
        for student in arrivals:
            idx = min(range(len(self.queues)), key=lambda i: (len(self.queues[i]), i))
            student.window_index = idx
            self.queues[idx].append(student)

    def _start_window_services(self, minute: int) -> None:
        for idx, service in enumerate(self.windows):
            if service is not None or not self.queues[idx]:
                continue
            student = self.queues[idx].pop(0)
            student.service_start_time = minute
            self.windows[idx] = WindowService(
                student=student,
                remaining=self._sample_duration(self.config.service_time_mean),
            )

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

    def _has_active_students(self) -> bool:
        return (
            any(self.queues)
            or any(window is not None for window in self.windows)
            or bool(self.waiting_for_seat)
            or bool(self.seated)
        )

    def _build_record(
        self,
        t: int,
        arrived_count: int,
        served_count: int,
        seated_count: int,
        left_count: int,
    ) -> StepRecord:
        return StepRecord(
            run_id=self.run_id,
            t=t,
            arrived_count=arrived_count,
            queue_lengths=[len(queue) for queue in self.queues],
            served_count=served_count,
            seated_count=seated_count,
            left_count=left_count,
            empty_seats=self.config.num_seats - len(self.seated),
            waiting_for_seat_count=len(self.waiting_for_seat),
            total_arrived=len(self.students),
            total_served=self.total_served,
            total_seated=self.total_seated,
            total_left=self.total_left,
            avg_wait_so_far=self._avg_wait_so_far(),
            snapshot=self._snapshot(),
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
            "busy_windows": [window is not None for window in self.windows],
            "occupied_seats": occupied,
            "empty_seats": self.config.num_seats - occupied,
            "waiting_for_seat_count": len(self.waiting_for_seat),
            "seat_matrix": [idx < occupied for idx in range(self.config.num_seats)],
            "totals": {
                "arrived": len(self.students),
                "served": self.total_served,
                "seated": self.total_seated,
                "left": self.total_left,
            },
        }

    def _build_metrics(self) -> MetricsSummary:
        seated_students = [student for student in self.students.values() if student.seat_time is not None]
        served_students = [student for student in self.students.values() if student.service_start_time is not None]
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
        denominator_windows = max(1, elapsed_minutes * self.config.num_windows)
        denominator_seats = max(1, elapsed_minutes * self.config.num_seats)
        window_utilization = self.window_busy_minutes / denominator_windows
        seat_utilization = self.seat_occupied_minutes / denominator_seats
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
        )

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
        if peak_queue >= max(8, self.config.num_windows * 8) and window_utilization >= 0.72:
            return "窗口服务"
        if self.config.peak_multiplier > 1.2 and peak_queue >= max(4, self.config.num_windows * 3):
            return "到达高峰"
        return "运行平衡"


def _average(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def dataclass_to_dict(value: Any) -> Any:
    return asdict(value)
