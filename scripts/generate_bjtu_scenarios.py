#!/usr/bin/env python3
"""Generate BJTU main-campus residential dining scenarios."""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.campus import (  # noqa: E402
    CampusBuildingDemandData,
    CampusDemandConfigData,
    CampusFloorDemandData,
    CampusPopulationPoolData,
    build_mixed_campus_arrival_schedule,
    default_residential_release_profile,
    load_campus_walk_times,
)
from app.simulation import SimulationConfigData, run_simulation  # noqa: E402


OUTPUT_PATH = ROOT / "data" / "experiments" / "bjtu_residential_scenarios.csv"
SUMMARY_PATH = ROOT / "docs" / "bjtu_residential_scenarios_summary.md"
DEFAULT_SIMULATION_POPULATION_SCALE = 0.05

RESIDENTIAL_SCENARIO_FIELDS = [
    "scenario",
    "meal_period",
    "cafeteria_id",
    "cafeteria_name",
    "source_mix",
    "teaching_release_mode",
    "residential_release_mode",
    "residential_release_start_minute",
    "residential_release_end_minute",
    "residential_release_peak_minute",
    "residential_release_distribution",
    "residential_participation_rate",
    "total_population_pool",
    "meal_participation_rate",
    "effective_meal_population",
    "teaching_population",
    "other_known_population",
    "residential_population",
    "residential_source_count",
    "residential_by_source_json",
    "residential_by_area_json",
    "residential_allocation_mode",
    "population_estimation_method",
    "simulation_population_scale",
    "teaching_arrived",
    "residential_arrived",
    "total_arrived",
    "num_windows",
    "num_seats",
    "movement_model",
    "avg_wait",
    "avg_queue_wait",
    "avg_seat_wait",
    "peak_queue",
    "peak_waiting_for_seat",
    "window_utilization",
    "seat_utilization",
    "bottleneck_type",
    "fragmented_seats",
    "avg_walking_time",
    "movement_conflict_count",
    "avg_stuck_ticks",
    "max_density",
]


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    cafeterias = {item["id"]: item for item in load_campus_walk_times()["locations"]["cafeterias"]}
    models = ["path", "advanced_floor_field"]
    simulation_scale = _simulation_scale()

    for scenario in _scenario_configs():
        for cafeteria_id, cafeteria in cafeterias.items():
            for movement_model in models:
                rows.append(_run_row(scenario, cafeteria_id, cafeteria["name"], movement_model, simulation_scale))
                print(
                    f"finished {scenario['scenario']} {cafeteria_id} {movement_model}",
                    flush=True,
                )

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESIDENTIAL_SCENARIO_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    _write_summary(rows)
    print(f"wrote {OUTPUT_PATH} ({len(rows)} rows)")
    print(f"wrote {SUMMARY_PATH}")
    return 0


def _scenario_configs() -> list[dict[str, Any]]:
    return [
        {
            "scenario": "breakfast_residential_window",
            "meal_period": "breakfast",
            "source_mix": "residential_window_dominant",
            "population_pool": CampusPopulationPoolData(
                enabled=True,
                meal_period="breakfast",
                total_population_pool=12000,
                meal_participation_rate=0.55,
                other_known_population=0,
            ),
            "buildings": [],
            "num_windows": 5,
            "num_seats": 180,
            "seed": 1201,
        },
        {
            "scenario": "lunch_teaching_event_plus_residential_window",
            "meal_period": "lunch",
            "source_mix": "teaching_event_plus_residential_window",
            "population_pool": CampusPopulationPoolData(
                enabled=True,
                meal_period="lunch",
                total_population_pool=15000,
                meal_participation_rate=0.75,
                other_known_population=400,
            ),
            "buildings": [
                _building("no9", 700, [900, 760, 620]),
                _building("no8", 705, [720, 640, 520]),
                _building("siyuan", 710, [620, 560, 440]),
                _building("yifu", 710, [620, 560, 440]),
            ],
            "num_windows": 8,
            "num_seats": 300,
            "seed": 1501,
        },
        {
            "scenario": "dinner_mixed_window",
            "meal_period": "dinner",
            "source_mix": "teaching_event_and_residential_window",
            "population_pool": CampusPopulationPoolData(
                enabled=True,
                meal_period="dinner",
                total_population_pool=15000,
                meal_participation_rate=0.70,
                other_known_population=500,
            ),
            "buildings": [
                _building("no9", 1035, [520, 460, 420]),
                _building("no5", 1040, [460, 420, 360]),
                _building("mechanical", 1045, [380, 340, 300]),
                _building("siyuan_east", 1050, [340, 300, 260]),
            ],
            "num_windows": 8,
            "num_seats": 320,
            "seed": 1801,
        },
        {
            "scenario": "weekend_residential_window",
            "meal_period": "weekend",
            "source_mix": "residential_window_dominant",
            "population_pool": CampusPopulationPoolData(
                enabled=True,
                meal_period="weekend",
                total_population_pool=10000,
                meal_participation_rate=0.50,
                other_known_population=200,
            ),
            "buildings": [
                _building("no17", 660, [120, 80]),
            ],
            "num_windows": 6,
            "num_seats": 240,
            "seed": 2001,
        },
    ]


def _building(building_id: str, dismissal_minute: int, counts: list[int]) -> CampusBuildingDemandData:
    return CampusBuildingDemandData(
        building_id=building_id,
        dismissal_minute=dismissal_minute,
        release_ratio=1.0,
        floors=[
            CampusFloorDemandData(floor=index + 1, count=count)
            for index, count in enumerate(counts)
        ],
    )


def _run_row(
    scenario: dict[str, Any],
    cafeteria_id: str,
    cafeteria_name: str,
    movement_model: str,
    simulation_scale: float,
) -> dict[str, Any]:
    seed = int(scenario["seed"]) + _stable_seed(cafeteria_id) + (10000 if movement_model == "advanced_floor_field" else 0)
    campus = CampusDemandConfigData(
        enabled=True,
        cafeteria_id=cafeteria_id,
        source_mode="manual",
        buildings=scenario["buildings"],
        residential_sources=[],
        population_pool=scenario["population_pool"],
        meal_period=scenario["meal_period"],
    )
    model_schedule_result = build_mixed_campus_arrival_schedule(
        cafeteria_id=cafeteria_id,
        buildings=campus.buildings,
        residential_sources=campus.residential_sources,
        population_pool=campus.population_pool,
        meal_period=campus.meal_period,
        seed=seed,
    )
    model_breakdown = model_schedule_result["breakdown"]
    simulation_scenario = _scaled_scenario(scenario, simulation_scale)
    simulation_campus = replace(
        campus,
        buildings=simulation_scenario["buildings"],
        population_pool=simulation_scenario["population_pool"],
    )
    simulation_schedule_result = build_mixed_campus_arrival_schedule(
        cafeteria_id=cafeteria_id,
        buildings=simulation_campus.buildings,
        residential_sources=simulation_campus.residential_sources,
        population_pool=simulation_campus.population_pool,
        meal_period=simulation_campus.meal_period,
        seed=seed,
    )
    simulation_breakdown = simulation_schedule_result["breakdown"]
    profile = default_residential_release_profile(scenario["meal_period"])
    config = SimulationConfigData(
        num_windows=scenario["num_windows"],
        num_seats=scenario["num_seats"],
        service_time_mean=2.4,
        dining_time_mean=18.0,
        duration_min=120,
        simulation_start_minute=profile.start_minute,
        seed=seed,
        campus_demand=simulation_campus,
        party_size_distribution={1: 0.72, 2: 0.20, 3: 0.06, 4: 0.02},
        movement_model=movement_model,
        max_movement_ticks_per_minute=1,
        floor_cell_size=18.0,
    )
    result = run_simulation(config)
    metrics = result.metrics
    return {
        "scenario": scenario["scenario"],
        "meal_period": scenario["meal_period"],
        "cafeteria_id": cafeteria_id,
        "cafeteria_name": cafeteria_name,
        "source_mix": scenario["source_mix"],
        "teaching_release_mode": model_breakdown["teaching_release_mode"],
        "residential_release_mode": model_breakdown["residential_release_mode"],
        "residential_release_start_minute": profile.start_minute,
        "residential_release_end_minute": profile.end_minute,
        "residential_release_peak_minute": profile.peak_minute if profile.peak_minute is not None else "",
        "residential_release_distribution": profile.distribution,
        "residential_participation_rate": profile.residential_participation_rate,
        "total_population_pool": model_breakdown["total_population_pool"],
        "meal_participation_rate": model_breakdown["meal_participation_rate"],
        "effective_meal_population": model_breakdown["effective_meal_population"],
        "teaching_population": model_breakdown["teaching_population"],
        "other_known_population": model_breakdown["other_known_population"],
        "residential_population": model_breakdown["residential_population"],
        "residential_source_count": model_breakdown["residential_source_count"],
        "residential_by_source_json": json.dumps(model_breakdown["residential_by_source"], ensure_ascii=False, sort_keys=True),
        "residential_by_area_json": json.dumps(model_breakdown["residential_by_area"], ensure_ascii=False, sort_keys=True),
        "residential_allocation_mode": model_breakdown["residential_allocation_mode"],
        "population_estimation_method": "residual_population_capacity_weight_not_real_occupancy",
        "simulation_population_scale": simulation_scale,
        "teaching_arrived": simulation_breakdown["teaching_arrived"],
        "residential_arrived": simulation_breakdown["residential_arrived"],
        "total_arrived": simulation_breakdown["total_arrived"],
        "num_windows": scenario["num_windows"],
        "num_seats": scenario["num_seats"],
        "movement_model": movement_model,
        "avg_wait": metrics.avg_wait,
        "avg_queue_wait": metrics.avg_queue_wait,
        "avg_seat_wait": metrics.avg_seat_wait,
        "peak_queue": metrics.peak_queue,
        "peak_waiting_for_seat": metrics.peak_waiting_for_seat,
        "window_utilization": metrics.window_utilization,
        "seat_utilization": metrics.seat_utilization,
        "bottleneck_type": metrics.bottleneck_type,
        "fragmented_seats": metrics.fragmented_seats,
        "avg_walking_time": metrics.avg_walking_time,
        "movement_conflict_count": metrics.movement_conflict_count,
        "avg_stuck_ticks": metrics.avg_stuck_ticks,
        "max_density": metrics.max_density,
    }


def _write_summary(rows: list[dict[str, Any]]) -> None:
    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_scenario.setdefault(str(row["scenario"]), []).append(row)
    busiest = max(rows, key=lambda row: (int(row["peak_queue"]), int(row["peak_waiting_for_seat"]))) if rows else None
    advanced_rows = [row for row in rows if row["movement_model"] == "advanced_floor_field"]
    avg_conflicts = sum(int(row["movement_conflict_count"]) for row in advanced_rows) / max(1, len(advanced_rows))
    max_density = max((int(row["max_density"]) for row in advanced_rows), default=0)

    lines = [
        "# BJTU Residential Scenarios Summary",
        "",
        "This summary is generated from `data/experiments/bjtu_residential_scenarios.csv`.",
        "All population pool, participation, and capacity-weight parameters are modeling assumptions, not school operation data.",
        f"Default runtime simulation scale in this CSV: {rows[0]['simulation_population_scale'] if rows else 'n/a'}.",
        "",
        "## Scenario Mix",
    ]
    for scenario, items in sorted(by_scenario.items()):
        teaching_arrived = sum(int(item["teaching_arrived"]) for item in items)
        residential_arrived = sum(int(item["residential_arrived"]) for item in items)
        total_arrived = sum(int(item["total_arrived"]) for item in items)
        residential_share = residential_arrived / total_arrived if total_arrived else 0.0
        lines.append(
            f"- `{scenario}`: total_arrived={total_arrived}, teaching_arrived={teaching_arrived}, "
            f"residential_arrived={residential_arrived}, residential_share={residential_share:.1%}."
        )
    lines.extend([
        "",
        "## Congestion",
    ])
    if busiest:
        lines.append(
            f"- Highest peak queue in this run: `{busiest['scenario']}` / `{busiest['cafeteria_id']}` "
            f"/ `{busiest['movement_model']}` with peak_queue={busiest['peak_queue']}."
        )
    lines.extend([
        f"- Advanced floor field average conflict count across rows: {avg_conflicts:.2f}.",
        f"- Advanced floor field max observed density across rows: {max_density}.",
        "",
        "## Interpretation Notes",
        "- `residential_by_source_json` is the calculation-level allocation by individual dormitory source.",
        "- `residential_by_area_json` is only a reporting summary; it is not used for pathing or schedule generation.",
        "- Residential time-window release spreads departures and avoids putting all dormitory students into one minute.",
        "- `simulation_population_scale` records the runtime scale used for DES/Floor Field execution; set `BJTU_SCENARIO_SIMULATION_SCALE=1.0` for a full-size run.",
    ])
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stable_seed(value: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(value))


def _simulation_scale() -> float:
    raw = os.environ.get("BJTU_SCENARIO_SIMULATION_SCALE")
    if raw is None:
        return DEFAULT_SIMULATION_POPULATION_SCALE
    try:
        return max(0.001, min(1.0, float(raw)))
    except ValueError:
        return DEFAULT_SIMULATION_POPULATION_SCALE


def _scaled_scenario(scenario: dict[str, Any], scale: float) -> dict[str, Any]:
    pool = scenario["population_pool"]
    scaled_pool = replace(
        pool,
        total_population_pool=max(0, int(round(pool.total_population_pool * scale))),
        other_known_population=max(0, int(round(pool.other_known_population * scale))),
    )
    scaled_buildings = [
        replace(
            building,
            floors=[
                replace(
                    floor,
                    count=_scaled_count(floor.count, scale),
                )
                for floor in building.floors
            ],
        )
        for building in scenario["buildings"]
    ]
    return {**scenario, "population_pool": scaled_pool, "buildings": scaled_buildings}


def _scaled_count(value: int, scale: float) -> int:
    if value <= 0:
        return 0
    return max(1, int(round(value * scale)))


if __name__ == "__main__":
    raise SystemExit(main())
