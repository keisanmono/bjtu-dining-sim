#!/usr/bin/env python3
"""Run repeatable quality-mode stress scenarios with deadlock diagnostics."""

from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.pedestrian.agents import AgentState  # noqa: E402
from app.simulation import (  # noqa: E402
    DiningLayoutData,
    DiningSimulationRunner,
    LayoutDoorData,
    LayoutFloorData,
    LayoutTableData,
    LayoutWindowData,
    SimulationConfigData,
    apply_movement_quality_preset,
)


DEFAULT_ARRIVAL_RATES = [8.0, 12.0, 16.0]
DEFAULT_SEEDS = [20, 42, 20260613, 20260614, 20260615]
DEFAULT_DURATION_MIN = 20
DEFAULT_SCENARIO_TIMEOUT_SEC = 300.0
DEFAULT_MAX_STEPS = 360
DEFAULT_FREEZE_MINUTES = 5
OUTPUT_JSON = ROOT / "data" / "benchmarks" / "quality_stress_summary.json"
OUTPUT_CSV = ROOT / "data" / "benchmarks" / "quality_stress_results.csv"

CSV_FIELDS = [
    "arrival_rate",
    "seed",
    "duration_min",
    "total_arrived",
    "total_served",
    "total_seated",
    "total_left",
    "peak_physical_queue",
    "max_total_waiting_pressure",
    "movement_conflict_count",
    "avg_stuck_ticks",
    "max_density",
    "incomplete_party_ids_count",
    "warnings_count",
    "static_fields_cache_size",
    "natural_done",
    "runtime_sec",
    "queue_total_by_minute_json",
]


class StressFailure(RuntimeError):
    def __init__(self, message: str, diagnostics: dict[str, Any]):
        super().__init__(message)
        self.diagnostics = diagnostics


class ScenarioWallClockTimeout(TimeoutError):
    pass


def _raise_scenario_timeout(_signum: int, _frame: Any) -> None:
    raise ScenarioWallClockTimeout


@dataclass(frozen=True)
class Scenario:
    arrival_rate: float
    seed: int
    duration_min: int


def main() -> int:
    parser = argparse.ArgumentParser(description="Run quality advanced-floor-field stress scenarios.")
    parser.add_argument("--arrival-rate", action="append", type=float, dest="arrival_rates")
    parser.add_argument("--seed", action="append", type=int, dest="seeds")
    parser.add_argument("--duration-min", type=int, default=DEFAULT_DURATION_MIN)
    parser.add_argument("--scenario-timeout-sec", type=float, default=DEFAULT_SCENARIO_TIMEOUT_SEC)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--freeze-minutes", type=int, default=DEFAULT_FREEZE_MINUTES)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    args = parser.parse_args()

    scenarios = [
        Scenario(arrival_rate=rate, seed=seed, duration_min=args.duration_min)
        for rate in (args.arrival_rates or DEFAULT_ARRIVAL_RATES)
        for seed in (args.seeds or DEFAULT_SEEDS)
    ]
    rows: list[dict[str, Any]] = []
    try:
        for scenario in scenarios:
            row = run_scenario(
                scenario,
                scenario_timeout_sec=args.scenario_timeout_sec,
                max_steps=args.max_steps,
                freeze_minutes=args.freeze_minutes,
            )
            rows.append(row)
            print(_format_row(row), flush=True)
    except StressFailure as exc:
        payload = {"error": str(exc), "diagnostics": exc.diagnostics, "completed_rows": rows}
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    _write_outputs(rows, args.output_json, args.output_csv)
    print(_markdown_table(rows))
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_csv}")
    return 0


def run_scenario(
    scenario: Scenario,
    *,
    scenario_timeout_sec: float,
    max_steps: int,
    freeze_minutes: int,
) -> dict[str, Any]:
    config = apply_movement_quality_preset(
        SimulationConfigData(
            movement_quality_preset="quality",
            layout=_quality_stress_layout(),
            num_windows=6,
            num_seats=160,
            arrival_rate=scenario.arrival_rate,
            service_time_mean=0.30,
            dining_time_mean=2.0,
            duration_min=scenario.duration_min,
            seed=scenario.seed,
            peak_multiplier=1.0,
            party_size_distribution={1: 1.0},
        )
    )
    if config.movement_model != "advanced_floor_field" or not config.advanced_movement_coupling:
        raise StressFailure(
            "quality preset did not enable advanced coupled movement",
            {"config": {"movement_model": config.movement_model, "advanced_movement_coupling": config.advanced_movement_coupling}},
        )

    runner = DiningSimulationRunner(config)
    start = time.perf_counter()
    history: list[dict[str, Any]] = []
    old_alarm_handler = None
    alarm_enabled = hasattr(signal, "SIGALRM") and scenario_timeout_sec > 0
    if alarm_enabled:
        old_alarm_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _raise_scenario_timeout)
        signal.setitimer(signal.ITIMER_REAL, scenario_timeout_sec)
    try:
        while not runner.done:
            elapsed = time.perf_counter() - start
            if elapsed > scenario_timeout_sec:
                raise StressFailure(
                    "scenario wall-clock timeout",
                    _failure_diagnostics(runner, history, scenario, elapsed, reason="timeout"),
                )
            if len(history) >= max_steps:
                raise StressFailure(
                    "scenario exceeded max test steps",
                    _failure_diagnostics(runner, history, scenario, elapsed, reason="max_steps"),
                )
            record = runner.step()
            snapshot = _snapshot_summary(runner, record.snapshot)
            history.append(snapshot)
            freeze = _detect_queue_freeze(history, runner.arrival_horizon_minute, freeze_minutes)
            if freeze is not None:
                raise StressFailure(
                    "possible queue deadlock detected",
                    _failure_diagnostics(runner, history, scenario, time.perf_counter() - start, reason="possible_deadlock", freeze=freeze),
                )
    except ScenarioWallClockTimeout as exc:
        raise StressFailure(
            "scenario wall-clock timeout",
            _failure_diagnostics(runner, history, scenario, time.perf_counter() - start, reason="timeout"),
        ) from exc
    finally:
        if alarm_enabled:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, old_alarm_handler)

    result = runner.result()
    final_snapshot = result.final_state
    incomplete_party_ids = list(final_snapshot.get("incomplete_party_ids", []) or [])
    warnings = list(final_snapshot.get("warnings", []) or [])
    physical_queue_lengths = list(final_snapshot.get("physical_queue_lengths", []) or [])
    walking_to_window_count = int(final_snapshot.get("walking_to_window_count", 0) or 0)
    entry_waiting_count = int(final_snapshot.get("entry_waiting_count", 0) or 0)
    if incomplete_party_ids or warnings:
        raise StressFailure(
            "quality stress scenario ended with incomplete parties or warnings",
            _failure_diagnostics(
                runner,
                history,
                scenario,
                time.perf_counter() - start,
                reason="incomplete_or_warning",
            ),
        )
    if result.metrics.total_arrived != runner.total_served:
        raise StressFailure(
            "natural completion ended with unserved arrivals",
            _failure_diagnostics(runner, history, scenario, time.perf_counter() - start, reason="unserved_arrivals"),
        )
    if sum(physical_queue_lengths) or walking_to_window_count or entry_waiting_count:
        raise StressFailure(
            "natural completion ended with residual movement queues",
            _failure_diagnostics(runner, history, scenario, time.perf_counter() - start, reason="residual_movement_queues"),
        )

    movement = final_snapshot.get("movement_metrics", {}) or {}
    queue_total_by_minute = [
        {"minute": item["minute"], "queue_total": sum(item["physical_queue_lengths"])}
        for item in history
    ]
    return {
        "arrival_rate": scenario.arrival_rate,
        "seed": scenario.seed,
        "duration_min": scenario.duration_min,
        "total_arrived": result.metrics.total_arrived,
        "total_served": runner.total_served,
        "total_seated": result.metrics.throughput,
        "total_left": result.metrics.total_left,
        "physical_queue_lengths": physical_queue_lengths,
        "walking_to_window_count": walking_to_window_count,
        "entry_waiting_count": entry_waiting_count,
        "total_waiting_pressure": int(final_snapshot.get("total_waiting_pressure", 0) or 0),
        "peak_physical_queue": max((sum(item["physical_queue_lengths"]) for item in history), default=0),
        "max_total_waiting_pressure": max((int(item["total_waiting_pressure"]) for item in history), default=0),
        "movement_conflict_count": int(movement.get("movement_conflict_count", 0) or 0),
        "avg_stuck_ticks": float(movement.get("avg_stuck_ticks", 0.0) or 0.0),
        "max_density": int(movement.get("max_density", 0) or 0),
        "incomplete_party_ids": incomplete_party_ids,
        "warnings": warnings,
        "static_fields_cache_size": len(runner.pedestrian_engine.static_fields) if runner.pedestrian_engine else 0,
        "queue_total_by_minute": queue_total_by_minute,
        "natural_done": bool(runner.done),
        "runtime_sec": round(time.perf_counter() - start, 4),
    }


def _quality_stress_layout() -> DiningLayoutData:
    windows = [
        LayoutWindowData(id=f"W{index + 1}", x=150.0 + index * 132.0, y=82.0, wall_side="top")
        for index in range(6)
    ]
    tables = [
        LayoutTableData(
            id=f"T{index + 1}",
            x=120.0 + (index % 8) * 105.0,
            y=320.0 + (index // 8) * 90.0,
            table_type="four_seat",
            capacity=4,
        )
        for index in range(40)
    ]
    return DiningLayoutData(
        floor=LayoutFloorData(width=960.0, height=780.0),
        doors=[
            LayoutDoorData(id="D-bottom-left", x=160.0, y=762.0, wall_side="bottom", arrival_share=0.34),
            LayoutDoorData(id="D-bottom-center", x=480.0, y=762.0, wall_side="bottom", arrival_share=0.33),
            LayoutDoorData(id="D-bottom-right", x=800.0, y=762.0, wall_side="bottom", arrival_share=0.33),
        ],
        windows=windows,
        tables=tables,
    )


def _snapshot_summary(runner: DiningSimulationRunner, snapshot: dict[str, Any]) -> dict[str, Any]:
    movement = snapshot.get("movement_metrics", {}) or {}
    totals = snapshot.get("totals", {}) or {}
    return {
        "minute": int(snapshot.get("minute", runner.current_minute) or 0),
        "total_arrived": int(totals.get("arrived", 0) or 0),
        "total_served": int(totals.get("served", 0) or 0),
        "total_seated": int(totals.get("seated", 0) or 0),
        "total_left": int(totals.get("left", 0) or 0),
        "physical_queue_lengths": list(snapshot.get("physical_queue_lengths", []) or []),
        "walking_to_window_count": int(snapshot.get("walking_to_window_count", 0) or 0),
        "entry_waiting_count": int(snapshot.get("entry_waiting_count", 0) or 0),
        "total_waiting_pressure": int(snapshot.get("total_waiting_pressure", 0) or 0),
        "busy_windows": list(snapshot.get("busy_windows", []) or []),
        "movement_conflict_count": int(movement.get("movement_conflict_count", 0) or 0),
        "avg_stuck_ticks": float(movement.get("avg_stuck_ticks", 0.0) or 0.0),
        "max_density": int(movement.get("max_density", 0) or 0),
        "incomplete_party_ids": list(snapshot.get("incomplete_party_ids", []) or []),
        "warnings": list(snapshot.get("warnings", []) or []),
        "static_fields_cache_size": len(runner.pedestrian_engine.static_fields) if runner.pedestrian_engine else 0,
        "window_heads": _window_head_diagnostics(runner),
    }


def _detect_queue_freeze(
    history: list[dict[str, Any]],
    arrival_horizon: int,
    freeze_minutes: int,
) -> dict[str, Any] | None:
    window = history[-max(2, freeze_minutes):]
    if len(window) < max(2, freeze_minutes):
        return None
    if not all(item["minute"] > arrival_horizon for item in window):
        return None
    first = window[0]
    last = window[-1]
    first_queue_total = sum(first["physical_queue_lengths"])
    last_queue_total = sum(last["physical_queue_lengths"])
    if first_queue_total <= 0 and last_queue_total <= 0:
        return None
    stalled_idle_head = _has_stalled_idle_head(first, last)
    if not stalled_idle_head:
        return None
    served_static = last["total_served"] == first["total_served"]
    queue_not_decreasing = last_queue_total >= first_queue_total
    walkers_static = last["walking_to_window_count"] == first["walking_to_window_count"]
    entry_static = last["entry_waiting_count"] == first["entry_waiting_count"]
    if served_static and queue_not_decreasing and walkers_static and entry_static:
        return {"arrival_horizon": arrival_horizon, "window": window}
    return None


def _has_stalled_idle_head(first: dict[str, Any], last: dict[str, Any]) -> bool:
    first_heads = {item["window_index"]: item for item in first.get("window_heads", [])}
    for head in last.get("window_heads", []):
        window_index = head["window_index"]
        if head.get("busy"):
            continue
        if window_index >= len(last["physical_queue_lengths"]):
            continue
        if last["physical_queue_lengths"][window_index] <= 0:
            continue
        first_head = first_heads.get(window_index, {})
        first_distance = first_head.get("head_distance_to_service")
        last_distance = head.get("head_distance_to_service")
        stuck_ticks = int(head.get("head_stuck_ticks") or 0)
        if first_distance is None or last_distance is None:
            continue
        if last_distance >= first_distance and stuck_ticks >= 12:
            return True
    return False


def _failure_diagnostics(
    runner: DiningSimulationRunner,
    history: list[dict[str, Any]],
    scenario: Scenario,
    elapsed: float,
    *,
    reason: str,
    freeze: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = runner._snapshot()
    return {
        "reason": reason,
        "scenario": {
            "arrival_rate": scenario.arrival_rate,
            "seed": scenario.seed,
            "duration_min": scenario.duration_min,
        },
        "elapsed_sec": round(elapsed, 4),
        "runner_done": runner.done,
        "arrival_horizon": runner.arrival_horizon_minute,
        "current_minute": runner.current_minute,
        "last_snapshots": history[-8:],
        "window_heads": _window_head_diagnostics(runner),
        "top_stuck_agents": _top_stuck_agents(runner),
        "incomplete_party_ids": list(snapshot.get("incomplete_party_ids", []) or []),
        "warnings": list(snapshot.get("warnings", []) or []),
        "static_fields_cache_size": len(runner.pedestrian_engine.static_fields) if runner.pedestrian_engine else 0,
        "freeze": freeze,
    }


def _window_head_diagnostics(runner: DiningSimulationRunner) -> list[dict[str, Any]]:
    engine = runner.pedestrian_engine
    if engine is None:
        return []
    diagnostics: list[dict[str, Any]] = []
    for window_index, queue in enumerate(runner.queues):
        service_cell = engine.grid.service_cells.get(window_index)
        head_student_id = queue[0].student_id if queue else None
        head_agent = engine.agents.get(head_student_id) if head_student_id is not None else None
        head_cell = head_agent.cell if head_agent is not None else None
        head_slot = (engine.grid.queue_cells_by_window.get(window_index) or [None])[0]
        diagnostics.append(
            {
                "window_index": window_index,
                "queue_length": len(queue),
                "busy": runner.windows[window_index] is not None,
                "head_student_id": head_student_id,
                "head_cell": list(head_cell) if head_cell is not None else None,
                "head_slot": list(head_slot) if head_slot is not None else None,
                "service_cell": list(service_cell) if service_cell is not None else None,
                "head_distance_to_service": _distance(head_cell, service_cell),
                "head_stuck_ticks": head_agent.stuck_ticks if head_agent is not None else None,
                "service_occupant": _occupant_at(engine, service_cell),
                "head_slot_occupant": _occupant_at(engine, head_slot),
            }
        )
    return diagnostics


def _top_stuck_agents(runner: DiningSimulationRunner) -> list[dict[str, Any]]:
    engine = runner.pedestrian_engine
    if engine is None:
        return []
    active_states = {AgentState.ENTERING, AgentState.TO_WINDOW, AgentState.QUEUEING, AgentState.WAITING_GROUP, AgentState.TO_TABLE, AgentState.TO_EXIT}
    agents = [agent for agent in engine.agents.values() if agent.state in active_states]
    top = sorted(agents, key=lambda agent: (-agent.stuck_ticks, agent.student_id))[:10]
    return [
        {
            "student_id": agent.student_id,
            "state": agent.state.value,
            "cell": list(agent.cell),
            "target_cells": [list(cell) for cell in sorted(agent.target_cells)],
            "stuck_ticks": agent.stuck_ticks,
            "desired_window_index": agent.desired_window_index,
            "assigned_queue_slot_index": agent.assigned_queue_slot_index,
            "assigned_table_approach_cell": list(agent.assigned_table_approach_cell) if agent.assigned_table_approach_cell else None,
        }
        for agent in top
    ]


def _occupant_at(engine: Any, cell: tuple[int, int] | None) -> int | None:
    if cell is None:
        return None
    for agent in engine.agents.values():
        if agent.cell == cell and agent.state not in {AgentState.SEATED, AgentState.EXITED}:
            return agent.student_id
    return None


def _distance(first: tuple[int, int] | None, second: tuple[int, int] | None) -> int | None:
    if first is None or second is None:
        return None
    return abs(first[0] - second[0]) + abs(first[1] - second[1])


def _write_outputs(rows: list[dict[str, Any]], output_json: Path, output_csv: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            csv_row = {field: row.get(field, "") for field in CSV_FIELDS}
            csv_row["queue_total_by_minute_json"] = json.dumps(row["queue_total_by_minute"], ensure_ascii=False, separators=(",", ":"))
            csv_row["incomplete_party_ids_count"] = len(row.get("incomplete_party_ids", []))
            csv_row["warnings_count"] = len(row.get("warnings", []))
            writer.writerow(csv_row)


def _format_row(row: dict[str, Any]) -> str:
    return (
        f"rate={row['arrival_rate']:g} seed={row['seed']} "
        f"arrived={row['total_arrived']} served={row['total_served']} seated={row['total_seated']} "
        f"peak_queue={row['peak_physical_queue']} pressure={row['max_total_waiting_pressure']} "
        f"conflicts={row['movement_conflict_count']} avg_stuck={row['avg_stuck_ticks']} "
        f"done={row['natural_done']} runtime={row['runtime_sec']}s"
    )


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| seed | arrival_rate | total_arrived | total_served | total_seated | peak physical queue | max pressure | avg_stuck_ticks | movement_conflict_count | incomplete_party_ids | natural done |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['seed']} | {row['arrival_rate']:g} | {row['total_arrived']} | {row['total_served']} | "
            f"{row['total_seated']} | {row['peak_physical_queue']} | {row['max_total_waiting_pressure']} | "
            f"{row['avg_stuck_ticks']} | {row['movement_conflict_count']} | {len(row['incomplete_party_ids'])} | "
            f"{'yes' if row['natural_done'] else 'no'} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
