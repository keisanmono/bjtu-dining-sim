#!/usr/bin/env python3
"""Run movement-model baseline and benchmark comparisons."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.campus import (  # noqa: E402
    CampusBuildingDemandData,
    CampusDemandConfigData,
    CampusFloorDemandData,
    CampusPopulationPoolData,
)
from app.simulation import (  # noqa: E402
    DiningLayoutData,
    LayoutDoorData,
    LayoutTableData,
    LayoutWindowData,
    MOVEMENT_QUALITY_PRESET_ORDER,
    SimulationConfigData,
    apply_movement_quality_preset,
    movement_quality_preset_metadata,
    run_simulation,
)


OUTPUT_CSV = ROOT / "data" / "benchmarks" / "movement_baseline_benchmark.csv"
OUTPUT_SUMMARY = ROOT / "data" / "benchmarks" / "movement_baseline_summary.json"
OUTPUT_DOC = ROOT / "docs" / "movement_benchmark.md"
OUTPUT_STRESS_CSV = ROOT / "data" / "benchmarks" / "movement_stress_benchmark.csv"
OUTPUT_STRESS_SUMMARY = ROOT / "data" / "benchmarks" / "movement_stress_summary.json"
OUTPUT_STRESS_DOC = ROOT / "docs" / "movement_stress_benchmark.md"
BENCHMARK_VERSION = "2026-06-13-movement-baseline-v2"
DEFAULT_QUALITY_PRESETS = list(MOVEMENT_QUALITY_PRESET_ORDER)
DEFAULT_SEEDS = [6101, 6102, 6103]
DEFAULT_STRESS_SEEDS = [7201]
STRESS_TARGET_ARRIVALS = [300, 800, 1500, 3000]
DEFAULT_QUALITY_STRESS_TARGET_CAP = 300

BENCHMARK_FIELDS = [
    "benchmark_version",
    "benchmark_id",
    "category",
    "scenario",
    "seed",
    "quality_preset",
    "preset_label",
    "preset_role",
    "expected_use_case",
    "movement_model",
    "cafeteria_id",
    "source_mix",
    "simulation_population_scale",
    "target_arrivals",
    "stress_level",
    "num_windows",
    "num_seats",
    "duration_min",
    "total_arrived",
    "throughput",
    "total_left",
    "avg_wait",
    "avg_queue_wait",
    "avg_seat_wait",
    "peak_queue",
    "peak_waiting_for_seat",
    "window_utilization",
    "seat_utilization",
    "bottleneck_type",
    "avg_walking_time",
    "movement_conflict_count",
    "avg_stuck_ticks",
    "max_density",
    "realism_score",
    "spatial_signal_score",
    "behavior_coupling_score",
    "congestion_response_score",
    "arrival_fairness_score",
    "runtime_penalty_score",
    "runtime_sec",
    "runtime_per_arrival_ms",
    "arrival_stream_hash",
    "arrival_series_json",
]


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    category: str
    source_mix: str
    cafeteria_id: str
    config: SimulationConfigData
    simulation_population_scale: float = 1.0
    target_arrivals: int = 0
    stress_level: str = ""


@dataclass(frozen=True)
class BenchmarkFloorData:
    width: float
    height: float


@dataclass(frozen=True)
class BenchmarkDiningLayoutData:
    floor: BenchmarkFloorData
    doors: list[LayoutDoorData]
    windows: list[LayoutWindowData]
    tables: list[LayoutTableData]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run movement-model baseline benchmark.")
    parser.add_argument("--suite", choices=["baseline", "stress", "all"], default="baseline")
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--output-summary", type=Path, default=None)
    parser.add_argument("--output-doc", type=Path, default=None)
    parser.add_argument("--scenario", action="append", dest="scenarios", help="Scenario name to include. Repeatable.")
    parser.add_argument("--seed", action="append", type=int, dest="seeds", help="Seed to include. Repeatable.")
    parser.add_argument("--preset", action="append", dest="quality_presets", help="Quality preset to include. Repeatable.")
    args = parser.parse_args()
    output_csv, output_summary, output_doc = _default_outputs_for_suite(args.suite)

    rows, _summary = run_benchmark(
        output_csv=args.output_csv or output_csv,
        output_summary=args.output_summary or output_summary,
        output_doc=args.output_doc or output_doc,
        suite=args.suite,
        scenario_names=args.scenarios,
        seeds=args.seeds,
        quality_presets=args.quality_presets,
    )
    print(f"wrote {args.output_csv or output_csv} ({len(rows)} rows)")
    print(f"wrote {args.output_summary or output_summary}")
    print(f"wrote {args.output_doc or output_doc}")
    return 0


def run_benchmark(
    output_csv: Path = OUTPUT_CSV,
    output_summary: Path = OUTPUT_SUMMARY,
    output_doc: Path = OUTPUT_DOC,
    suite: str = "baseline",
    scenario_names: list[str] | None = None,
    seeds: list[int] | None = None,
    quality_presets: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    explicit_presets = quality_presets is not None
    selected_presets = list(quality_presets or DEFAULT_QUALITY_PRESETS)
    selected_seeds = list(seeds or _default_seeds(suite))
    scenarios = _selected_scenarios(scenario_names, suite=suite)
    rows: list[dict[str, Any]] = []

    for scenario in scenarios:
        for seed in selected_seeds:
            for preset in _presets_for_scenario(scenario, selected_presets, explicit_presets=explicit_presets):
                rows.append(_run_one(scenario, seed, preset))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BENCHMARK_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = _build_summary(rows, selected_presets, output_csv, output_summary, output_doc, suite=suite)
    output_summary.parent.mkdir(parents=True, exist_ok=True)
    output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_doc(rows, summary, output_doc)
    return rows, summary


def _run_one(scenario: BenchmarkScenario, seed: int, quality_preset: str) -> dict[str, Any]:
    config = apply_movement_quality_preset(
        replace(scenario.config, seed=seed, movement_quality_preset=quality_preset)
    )
    start = time.perf_counter()
    result = run_simulation(config)
    runtime_sec = time.perf_counter() - start
    metrics = result.metrics
    arrivals = _trim_trailing_zeros([int(record.arrived_count) for record in result.records])
    arrival_series_json = json.dumps(arrivals, ensure_ascii=False, separators=(",", ":"))
    arrival_hash = hashlib.sha256(arrival_series_json.encode("utf-8")).hexdigest()[:16]
    runtime_per_arrival = (runtime_sec * 1000 / metrics.total_arrived) if metrics.total_arrived else 0.0
    benchmark_id = f"{scenario.name}:{seed}"
    preset_meta = movement_quality_preset_metadata(quality_preset)
    score = _realism_score(
        quality_preset=quality_preset,
        avg_walking_time=float(metrics.avg_walking_time),
        movement_conflict_count=int(metrics.movement_conflict_count),
        avg_stuck_ticks=float(metrics.avg_stuck_ticks),
        max_density=int(metrics.max_density),
        avg_wait=float(metrics.avg_wait),
        peak_queue=int(metrics.peak_queue),
        runtime_per_arrival_ms=runtime_per_arrival,
    )
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_id": benchmark_id,
        "category": scenario.category,
        "scenario": scenario.name,
        "seed": seed,
        **preset_meta,
        "movement_model": config.movement_model,
        "cafeteria_id": scenario.cafeteria_id,
        "source_mix": scenario.source_mix,
        "simulation_population_scale": scenario.simulation_population_scale,
        "target_arrivals": scenario.target_arrivals,
        "stress_level": scenario.stress_level,
        "num_windows": config.num_windows,
        "num_seats": config.num_seats,
        "duration_min": config.duration_min,
        "total_arrived": metrics.total_arrived,
        "throughput": metrics.throughput,
        "total_left": metrics.total_left,
        "avg_wait": metrics.avg_wait,
        "avg_queue_wait": metrics.avg_queue_wait,
        "avg_seat_wait": metrics.avg_seat_wait,
        "peak_queue": metrics.peak_queue,
        "peak_waiting_for_seat": metrics.peak_waiting_for_seat,
        "window_utilization": metrics.window_utilization,
        "seat_utilization": metrics.seat_utilization,
        "bottleneck_type": metrics.bottleneck_type,
        "avg_walking_time": metrics.avg_walking_time,
        "movement_conflict_count": metrics.movement_conflict_count,
        "avg_stuck_ticks": metrics.avg_stuck_ticks,
        "max_density": metrics.max_density,
        **score,
        "runtime_sec": round(runtime_sec, 4),
        "runtime_per_arrival_ms": round(runtime_per_arrival, 2),
        "arrival_stream_hash": arrival_hash,
        "arrival_series_json": arrival_series_json,
    }


def _realism_score(
    quality_preset: str,
    avg_walking_time: float,
    movement_conflict_count: int,
    avg_stuck_ticks: float,
    max_density: int,
    avg_wait: float,
    peak_queue: int,
    runtime_per_arrival_ms: float,
) -> dict[str, float]:
    spatial_signal = min(
        35.0,
        (12.0 if avg_walking_time > 0 else 0.0)
        + min(8.0, max_density * 1.5)
        + min(8.0, movement_conflict_count / 8)
        + min(7.0, avg_stuck_ticks * 2),
    )
    behavior_coupling = {
        "fast": 0.0,
        "balanced": 12.0,
        "quality": 25.0,
    }.get(quality_preset, 0.0)
    congestion_response = min(20.0, max(0.0, avg_wait) * 0.4 + max(0.0, peak_queue) * 1.2)
    arrival_fairness = 10.0
    runtime_penalty = min(12.0, max(0.0, runtime_per_arrival_ms - 40.0) / 12.0)
    realism = max(0.0, min(100.0, spatial_signal + behavior_coupling + congestion_response + arrival_fairness - runtime_penalty))
    return {
        "realism_score": round(realism, 2),
        "spatial_signal_score": round(spatial_signal, 2),
        "behavior_coupling_score": round(behavior_coupling, 2),
        "congestion_response_score": round(congestion_response, 2),
        "arrival_fairness_score": round(arrival_fairness, 2),
        "runtime_penalty_score": round(runtime_penalty, 2),
    }


def _trim_trailing_zeros(values: list[int]) -> list[int]:
    last_nonzero = -1
    for index, value in enumerate(values):
        if value:
            last_nonzero = index
    if last_nonzero < 0:
        return []
    return values[: last_nonzero + 1]


def _default_outputs_for_suite(suite: str) -> tuple[Path, Path, Path]:
    if suite == "stress":
        return OUTPUT_STRESS_CSV, OUTPUT_STRESS_SUMMARY, OUTPUT_STRESS_DOC
    return OUTPUT_CSV, OUTPUT_SUMMARY, OUTPUT_DOC


def _presets_for_scenario(
    scenario: BenchmarkScenario,
    selected_presets: list[str],
    explicit_presets: bool,
) -> list[str]:
    if explicit_presets or scenario.category != "stress":
        return list(selected_presets)
    if scenario.target_arrivals <= DEFAULT_QUALITY_STRESS_TARGET_CAP:
        return list(selected_presets)
    return [preset for preset in selected_presets if preset != "quality"]


def _build_summary(
    rows: list[dict[str, Any]],
    quality_presets: list[str],
    output_csv: Path,
    output_summary: Path,
    output_doc: Path,
    suite: str,
) -> dict[str, Any]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["scenario"]), int(row["seed"])), []).append(row)
    mismatches = [
        {"scenario": scenario, "seed": seed}
        for (scenario, seed), items in sorted(groups.items())
        if len({str(item["arrival_stream_hash"]) for item in items}) > 1
    ]
    advanced_rows = [row for row in rows if row["quality_preset"] == "quality"]
    spatial_rows = [
        row
        for row in advanced_rows
        if float(row["avg_walking_time"]) > 0
        or int(row["movement_conflict_count"]) > 0
        or float(row["avg_stuck_ticks"]) > 0
        or int(row["max_density"]) > 0
    ]
    stress_rows = [row for row in rows if row["category"] == "stress"]
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "suite": suite,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "quality_presets": quality_presets,
        "models": sorted({str(row["movement_model"]) for row in rows}),
        "scenarios": sorted({str(row["scenario"]) for row in rows}),
        "outputs": {
            "csv": str(output_csv.relative_to(ROOT)) if output_csv.is_relative_to(ROOT) else str(output_csv),
            "summary": str(output_summary.relative_to(ROOT)) if output_summary.is_relative_to(ROOT) else str(output_summary),
            "doc": str(output_doc.relative_to(ROOT)) if output_doc.is_relative_to(ROOT) else str(output_doc),
        },
        "fairness": {
            "groups_checked": len(groups),
            "groups_with_mismatched_arrival_streams": len(mismatches),
            "mismatched_groups": mismatches,
        },
        "advanced_signal": {
            "advanced_rows": len(advanced_rows),
            "rows_with_spatial_signal": len(spatial_rows),
            "max_density": max((int(row["max_density"]) for row in advanced_rows), default=0),
            "movement_conflict_count_sum": sum(int(row["movement_conflict_count"]) for row in advanced_rows),
        },
        "mean_by_preset": _mean_by_preset(rows),
        "mean_by_model": _mean_by_model(rows),
        "confidence_by_preset": _confidence_by_preset(rows),
        "realism_score_by_preset": _realism_score_by_preset(rows),
        "stress": _stress_summary(stress_rows),
    }


def _mean_by_model(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for model in sorted({str(row["movement_model"]) for row in rows}):
        items = [row for row in rows if row["movement_model"] == model]
        result[model] = {
            "avg_wait": round(statistics.fmean(float(row["avg_wait"]) for row in items), 3),
            "peak_queue": round(statistics.fmean(int(row["peak_queue"]) for row in items), 3),
            "avg_walking_time": round(statistics.fmean(float(row["avg_walking_time"]) for row in items), 3),
            "movement_conflict_count": round(statistics.fmean(int(row["movement_conflict_count"]) for row in items), 3),
            "max_density": round(statistics.fmean(int(row["max_density"]) for row in items), 3),
            "runtime_sec": round(statistics.fmean(float(row["runtime_sec"]) for row in items), 4),
            "realism_score": round(statistics.fmean(float(row["realism_score"]) for row in items), 3),
        }
    return result


def _realism_score_by_preset(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for preset in DEFAULT_QUALITY_PRESETS:
        values = [float(row["realism_score"]) for row in rows if row["quality_preset"] == preset]
        if values:
            result[preset] = _distribution(values)
    return result


def _stress_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "rows": 0,
            "target_arrivals": [],
            "quality_target_arrivals": [],
            "default_quality_target_cap": DEFAULT_QUALITY_STRESS_TARGET_CAP,
            "max_total_arrived": 0,
            "max_runtime_sec": 0.0,
            "runtime_by_preset": {},
        }
    return {
        "rows": len(rows),
        "target_arrivals": sorted({int(row["target_arrivals"]) for row in rows if int(row["target_arrivals"]) > 0}),
        "quality_target_arrivals": sorted(
            {
                int(row["target_arrivals"])
                for row in rows
                if row["quality_preset"] == "quality" and int(row["target_arrivals"]) > 0
            }
        ),
        "default_quality_target_cap": DEFAULT_QUALITY_STRESS_TARGET_CAP,
        "max_total_arrived": max(int(row["total_arrived"]) for row in rows),
        "max_runtime_sec": max(float(row["runtime_sec"]) for row in rows),
        "runtime_by_preset": {
            preset: _distribution(float(row["runtime_sec"]) for row in rows if row["quality_preset"] == preset)
            for preset in DEFAULT_QUALITY_PRESETS
            if any(row["quality_preset"] == preset for row in rows)
        },
    }


def _confidence_by_preset(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics = ["avg_wait", "peak_queue", "runtime_sec", "realism_score"]
    result: dict[str, dict[str, Any]] = {}
    for preset in DEFAULT_QUALITY_PRESETS:
        items = [row for row in rows if row["quality_preset"] == preset]
        if not items:
            continue
        result[preset] = {"sample_count": len(items)}
        for metric in metrics:
            result[preset][metric] = _distribution(float(row[metric]) for row in items)
    return result


def _distribution(values_iter: Any) -> dict[str, float]:
    values = sorted(float(value) for value in values_iter)
    if not values:
        return {"mean": 0.0, "std": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0}
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "mean": round(statistics.fmean(values), 3),
        "std": round(std, 3),
        "p50": round(_percentile(values, 0.50), 3),
        "p90": round(_percentile(values, 0.90), 3),
        "p95": round(_percentile(values, 0.95), 3),
    }


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def _mean_by_preset(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for preset in DEFAULT_QUALITY_PRESETS:
        items = [row for row in rows if row["quality_preset"] == preset]
        if not items:
            continue
        result[preset] = {
            "avg_wait": round(statistics.fmean(float(row["avg_wait"]) for row in items), 3),
            "peak_queue": round(statistics.fmean(int(row["peak_queue"]) for row in items), 3),
            "avg_walking_time": round(statistics.fmean(float(row["avg_walking_time"]) for row in items), 3),
            "movement_conflict_count": round(statistics.fmean(int(row["movement_conflict_count"]) for row in items), 3),
            "max_density": round(statistics.fmean(int(row["max_density"]) for row in items), 3),
            "runtime_sec": round(statistics.fmean(float(row["runtime_sec"]) for row in items), 4),
            "realism_score": round(statistics.fmean(float(row["realism_score"]) for row in items), 3),
        }
    return result


def _write_doc(rows: list[dict[str, Any]], summary: dict[str, Any], output_doc: Path) -> None:
    output_doc.parent.mkdir(parents=True, exist_ok=True)
    mean_by_preset = summary["mean_by_preset"]
    is_stress = summary.get("suite") == "stress"
    lines = [
        "# Movement Stress Benchmark" if is_stress else "# Movement Model Baseline Benchmark",
        "",
        f"Generated from `{summary['outputs']['csv']}`.",
        "",
        "## Baseline Roles",
        "",
        "- `快速 Fast`: high-speed path baseline for batch experiments and parameter search.",
        "- `平衡 Balanced`: static floor-field baseline with geometry-aware walking paths.",
        "- `质量 Quality`: advanced CA/Floor Field model coupled to queue admission and seating.",
        "",
        "## Fairness Check",
        "",
        f"- Scenario/seed groups checked: {summary['fairness']['groups_checked']}.",
        f"- Groups with mismatched arrival streams: {summary['fairness']['groups_with_mismatched_arrival_streams']}.",
        "",
        "## Model Means",
        "",
        "| preset | avg_wait | peak_queue | avg_walking_time | movement_conflict_count | max_density | runtime_sec | realism_score |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for preset in DEFAULT_QUALITY_PRESETS:
        values = mean_by_preset.get(preset, {})
        label = movement_quality_preset_metadata(preset)["preset_label"]
        lines.append(
            f"| {label} | {values.get('avg_wait', 0)} | {values.get('peak_queue', 0)} | "
            f"{values.get('avg_walking_time', 0)} | {values.get('movement_conflict_count', 0)} | "
            f"{values.get('max_density', 0)} | {values.get('runtime_sec', 0)} | {values.get('realism_score', 0)} |"
        )
    lines.extend([
        "",
        "## Confidence Statistics",
        "",
        "| preset | n | avg_wait mean/std/p95 | runtime mean/std/p95 | realism mean/std/p95 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    confidence = summary["confidence_by_preset"]
    for preset in DEFAULT_QUALITY_PRESETS:
        label = movement_quality_preset_metadata(preset)["preset_label"]
        stats = confidence.get(preset, {})
        wait = stats.get("avg_wait", {})
        runtime = stats.get("runtime_sec", {})
        realism = stats.get("realism_score", {})
        lines.append(
            f"| {label} | {stats.get('sample_count', 0)} | "
            f"{wait.get('mean', 0)}/{wait.get('std', 0)}/{wait.get('p95', 0)} | "
            f"{runtime.get('mean', 0)}/{runtime.get('std', 0)}/{runtime.get('p95', 0)} | "
            f"{realism.get('mean', 0)}/{realism.get('std', 0)}/{realism.get('p95', 0)} |"
        )
    stress = summary.get("stress", {})
    if stress.get("rows", 0):
        lines.extend([
            "",
            "## Stress Scale",
            "",
            f"- Stress rows: {stress.get('rows', 0)}.",
            f"- Target arrivals: {stress.get('target_arrivals', [])}.",
            f"- Max actual arrivals: {stress.get('max_total_arrived', 0)}.",
            f"- Max runtime: {stress.get('max_runtime_sec', 0)} seconds.",
            f"- Default quality target cap: {stress.get('default_quality_target_cap', DEFAULT_QUALITY_STRESS_TARGET_CAP)}.",
            f"- Quality targets included by default: {stress.get('quality_target_arrivals', [])}.",
            "",
            "`quality` remains available for larger targets by explicitly passing `--preset quality`, but it is excluded by default above the cap because advanced CA/Floor Field is intended for high-fidelity analysis rather than bulk stress sweeps.",
        ])
    lines.extend([
        "",
        "## Interpretation",
        "",
        "This benchmark measures whether advanced movement adds spatial constraints, not whether it always reduces waits.",
        "A more realistic movement model can increase total wait because students must physically reach the window queue and table area.",
        "The CSV keeps `arrival_series_json` and `arrival_stream_hash` so model comparisons can verify identical demand streams.",
        "",
        "## Rows",
        "",
        f"- Total rows: {len(rows)}.",
        f"- Advanced rows with spatial signal: {summary['advanced_signal']['rows_with_spatial_signal']} / {summary['advanced_signal']['advanced_rows']}.",
        f"- Advanced max density: {summary['advanced_signal']['max_density']}.",
    ])
    output_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _selected_scenarios(names: list[str] | None, suite: str = "baseline") -> list[BenchmarkScenario]:
    baseline = _benchmark_scenarios()
    stress = _stress_scenarios()
    scenarios = baseline + stress
    if not names:
        if suite == "stress":
            return stress
        if suite == "all":
            return scenarios
        return baseline
    wanted = set(names)
    selected = [scenario for scenario in scenarios if scenario.name in wanted]
    missing = sorted(wanted - {scenario.name for scenario in selected})
    if missing:
        raise ValueError(f"Unknown benchmark scenario(s): {', '.join(missing)}")
    return selected


def _default_seeds(suite: str = "baseline") -> list[int]:
    raw = os.environ.get("BJTU_MOVEMENT_BENCHMARK_SEEDS")
    if not raw:
        if suite == "stress":
            return list(DEFAULT_STRESS_SEEDS)
        return list(DEFAULT_SEEDS)
    seeds = [int(item.strip()) for item in raw.split(",") if item.strip()]
    return seeds or (list(DEFAULT_STRESS_SEEDS) if suite == "stress" else list(DEFAULT_SEEDS))


def _benchmark_scenarios() -> list[BenchmarkScenario]:
    return [
        BenchmarkScenario(
            name="micro_window_queue",
            category="micro",
            source_mix="manual_arrivals",
            cafeteria_id="synthetic",
            config=_micro_window_queue_config(),
        ),
        BenchmarkScenario(
            name="micro_table_access",
            category="micro",
            source_mix="manual_arrivals",
            cafeteria_id="synthetic",
            config=_micro_table_access_config(),
        ),
        BenchmarkScenario(
            name="bjtu_breakfast_xuesi_reference",
            category="bjtu_reference",
            source_mix="residential_window",
            cafeteria_id="xuesi",
            config=_bjtu_breakfast_config(),
            simulation_population_scale=0.0015,
        ),
        BenchmarkScenario(
            name="bjtu_lunch_xuesi_reference",
            category="bjtu_reference",
            source_mix="teaching_event_plus_residential_window",
            cafeteria_id="xuesi",
            config=_bjtu_lunch_config(),
            simulation_population_scale=0.0015,
        ),
        BenchmarkScenario(
            name="performance_medium_manual",
            category="performance",
            source_mix="manual_arrivals",
            cafeteria_id="synthetic",
            config=_performance_medium_config(),
        ),
    ]


def _stress_scenarios() -> list[BenchmarkScenario]:
    return [
        BenchmarkScenario(
            name=f"stress_single_cafeteria_{target:04d}",
            category="stress",
            source_mix="manual_poisson_target",
            cafeteria_id="synthetic",
            config=_stress_single_cafeteria_config(target),
            simulation_population_scale=1.0,
            target_arrivals=target,
            stress_level=f"stress_{target:04d}",
        )
        for target in STRESS_TARGET_ARRIVALS
    ]


def _stress_single_cafeteria_config(target_arrivals: int) -> SimulationConfigData:
    duration_min = 60
    num_windows = min(30, max(8, math.ceil(target_arrivals / 100)))
    num_seats = min(2000, max(240, math.ceil(target_arrivals * 0.55)))
    return SimulationConfigData(
        layout=_stress_layout(num_windows, num_seats),
        num_windows=num_windows,
        num_seats=num_seats,
        arrival_rate=target_arrivals / duration_min,
        service_time_mean=1.0,
        dining_time_mean=8.0,
        duration_min=duration_min,
        peak_start_min=0,
        peak_end_min=duration_min,
        peak_multiplier=1.0,
        party_size_distribution={1: 0.70, 2: 0.24, 3: 0.06},
        window_choice_temperature=0.15,
        table_choice_temperature=0.10,
        floor_cell_size=16.0,
        floor_randomness=0.02,
        max_movement_ticks_per_minute=1,
    )


def _stress_layout(num_windows: int, num_seats: int) -> BenchmarkDiningLayoutData:
    table_capacities = _stress_table_capacities(num_seats)
    table_columns = 12
    table_rows = max(1, math.ceil(len(table_capacities) / table_columns))
    floor_width = 1280.0
    floor_height = max(760.0, 280.0 + table_rows * 84.0 + 100.0)
    windows_per_row = 15
    doors = [
        LayoutDoorData(id="D1", x=18, y=260, wall_side="left", arrival_share=0.34),
        LayoutDoorData(id="D2", x=18, y=max(520.0, floor_height - 220.0), wall_side="left", arrival_share=0.33),
        LayoutDoorData(id="D3", x=floor_width - 18, y=floor_height / 2, wall_side="right", arrival_share=0.33),
    ]
    windows = [
        LayoutWindowData(
            id=f"W{index + 1}",
            x=96 + (index % windows_per_row) * 64,
            y=48 + (index // windows_per_row) * 44,
            wall_side="top",
        )
        for index in range(num_windows)
    ]
    tables = [
        LayoutTableData(
            id=f"T{index + 1}",
            x=110 + (index % table_columns) * 96,
            y=280 + (index // table_columns) * 84,
            table_type="four_seat" if capacity <= 4 else "six_seat",
            capacity=capacity,
            rotation=90 if index % 2 else 0,
        )
        for index, capacity in enumerate(table_capacities)
    ]
    return BenchmarkDiningLayoutData(
        floor=BenchmarkFloorData(width=floor_width, height=floor_height),
        doors=doors,
        windows=windows,
        tables=tables,
    )


def _stress_table_capacities(num_seats: int) -> list[int]:
    remaining = max(0, int(num_seats))
    capacities: list[int] = []
    while remaining > 0:
        capacity = min(6, remaining)
        capacities.append(capacity)
        remaining -= capacity
    return capacities


def _micro_window_queue_config() -> SimulationConfigData:
    layout = DiningLayoutData(
        doors=[LayoutDoorData(id="D1", x=18, y=500, wall_side="left")],
        windows=[LayoutWindowData(id="W1", x=220, y=48, wall_side="top")],
        tables=[
            LayoutTableData(id="T1", x=180, y=300, table_type="four_seat", capacity=4),
            LayoutTableData(id="T2", x=280, y=300, table_type="four_seat", capacity=4),
            LayoutTableData(id="T3", x=180, y=410, table_type="four_seat", capacity=4),
        ],
    )
    return SimulationConfigData(
        layout=layout,
        num_windows=1,
        num_seats=12,
        arrival_rate=1.8,
        service_time_mean=1.0,
        dining_time_mean=3.0,
        duration_min=6,
        party_size_distribution={1: 1.0},
        floor_randomness=0.0,
        floor_cell_size=18.0,
        max_movement_ticks_per_minute=1,
    )


def _micro_table_access_config() -> SimulationConfigData:
    layout = DiningLayoutData(
        doors=[LayoutDoorData(id="D1", x=24, y=160, wall_side="left")],
        windows=[LayoutWindowData(id="W1", x=156, y=48, wall_side="top")],
        tables=[
            LayoutTableData(id="T1", x=170, y=260, table_type="four_seat", capacity=4),
            LayoutTableData(id="T2", x=250, y=260, table_type="four_seat", capacity=4),
        ],
    )
    return SimulationConfigData(
        layout=layout,
        num_windows=1,
        num_seats=8,
        arrival_rate=1.4,
        service_time_mean=1.0,
        dining_time_mean=3.0,
        duration_min=6,
        party_size_distribution={2: 1.0},
        floor_randomness=0.0,
        floor_cell_size=18.0,
        max_movement_ticks_per_minute=1,
    )


def _bjtu_breakfast_config() -> SimulationConfigData:
    campus = CampusDemandConfigData(
        enabled=True,
        cafeteria_id="xuesi",
        buildings=[],
        population_pool=CampusPopulationPoolData(
            enabled=True,
            meal_period="breakfast",
            total_population_pool=18,
            meal_participation_rate=0.6,
        ),
        meal_period="breakfast",
    )
    return SimulationConfigData(
        num_windows=3,
        num_seats=60,
        service_time_mean=1.8,
        dining_time_mean=8.0,
        duration_min=90,
        campus_demand=campus,
        party_size_distribution={1: 0.8, 2: 0.2},
        floor_cell_size=18.0,
        max_movement_ticks_per_minute=1,
    )


def _bjtu_lunch_config() -> SimulationConfigData:
    campus = CampusDemandConfigData(
        enabled=True,
        cafeteria_id="xuesi",
        buildings=[
            CampusBuildingDemandData(
                building_id="no9",
                dismissal_minute=700,
                release_ratio=1.0,
                floors=[
                    CampusFloorDemandData(floor=1, count=5),
                    CampusFloorDemandData(floor=2, count=4),
                ],
            )
        ],
        population_pool=CampusPopulationPoolData(
            enabled=True,
            meal_period="lunch",
            total_population_pool=18,
            meal_participation_rate=0.75,
            other_known_population=1,
        ),
        meal_period="lunch",
    )
    return SimulationConfigData(
        num_windows=3,
        num_seats=60,
        service_time_mean=1.8,
        dining_time_mean=8.0,
        duration_min=90,
        campus_demand=campus,
        party_size_distribution={1: 0.75, 2: 0.25},
        floor_cell_size=18.0,
        max_movement_ticks_per_minute=1,
    )


def _performance_medium_config() -> SimulationConfigData:
    return SimulationConfigData(
        num_windows=2,
        num_seats=30,
        arrival_rate=2.4,
        service_time_mean=1.2,
        dining_time_mean=5.0,
        duration_min=8,
        party_size_distribution={1: 0.75, 2: 0.25},
        floor_cell_size=18.0,
        max_movement_ticks_per_minute=1,
    )


if __name__ == "__main__":
    raise SystemExit(main())
