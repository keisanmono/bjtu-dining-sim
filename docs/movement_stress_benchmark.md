# Movement Stress Benchmark

Generated from `data/benchmarks/movement_stress_benchmark.csv`.

## Baseline Roles

- `快速 Fast`: high-speed path baseline for batch experiments and parameter search.
- `平衡 Balanced`: static floor-field baseline with geometry-aware walking paths.
- `质量 Quality`: advanced CA/Floor Field model coupled to queue admission and seating.

## Fairness Check

- Scenario/seed groups checked: 4.
- Groups with mismatched arrival streams: 0.

## Model Means

| preset | avg_wait | peak_queue | avg_walking_time | movement_conflict_count | max_density | runtime_sec | realism_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 快速 Fast | 17.988 | 554.75 | 0.0 | 0.0 | 0.0 | 4.9982 | 25.803 |
| 平衡 Balanced | 18.098 | 555.0 | 0.0 | 0.0 | 0.0 | 41.8725 | 38.115 |
| 质量 Quality | 14.07 | 5.0 | 599.34 | 1970.0 | 8.0 | 12.4868 | 81.34 |

## Confidence Statistics

| preset | n | avg_wait mean/std/p95 | runtime mean/std/p95 | realism mean/std/p95 |
| --- | ---: | ---: | ---: | ---: |
| 快速 Fast | 4 | 17.988/10.682/24.289 | 4.998/6.355/12.712 | 25.803/8.395/30.0 |
| 平衡 Balanced | 4 | 18.098/10.668/24.394 | 41.873/51.681/104.528 | 38.115/7.77/42.0 |
| 质量 Quality | 1 | 14.07/0.0/14.07 | 12.487/0.0/12.487 | 81.34/0.0/81.34 |

## Stress Scale

- Stress rows: 9.
- Target arrivals: [300, 800, 1500, 3000].
- Max actual arrivals: 3018.
- Max runtime: 116.8954 seconds.
- Default quality target cap: 300.
- Quality targets included by default: [300].

`quality` remains available for larger targets by explicitly passing `--preset quality`, but it is excluded by default above the cap because advanced CA/Floor Field is intended for high-fidelity analysis rather than bulk stress sweeps.

## Interpretation

This benchmark measures whether advanced movement adds spatial constraints, not whether it always reduces waits.
A more realistic movement model can increase total wait because students must physically reach the window queue and table area.
The CSV keeps `arrival_series_json` and `arrival_stream_hash` so model comparisons can verify identical demand streams.

## Rows

- Total rows: 9.
- Advanced rows with spatial signal: 1 / 1.
- Advanced max density: 8.
