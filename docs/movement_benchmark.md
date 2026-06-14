# Movement Model Baseline Benchmark

Generated from `data/benchmarks/movement_baseline_benchmark.csv`.

## Baseline Roles

- `快速 Fast`: high-speed path baseline for batch experiments and parameter search.
- `平衡 Balanced`: static floor-field baseline with geometry-aware walking paths.
- `质量 Quality`: advanced CA/Floor Field model coupled to queue admission and seating.

## Fairness Check

- Scenario/seed groups checked: 15.
- Groups with mismatched arrival streams: 0.

## Model Means

| preset | avg_wait | peak_queue | avg_walking_time | movement_conflict_count | max_density | runtime_sec | realism_score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 快速 Fast | 4.51 | 5.0 | 0.0 | 0.0 | 0.0 | 0.0108 | 17.803 |
| 平衡 Balanced | 4.601 | 5.067 | 0.0 | 0.0 | 0.0 | 0.0415 | 29.92 |
| 质量 Quality | 7.537 | 4.067 | 238.368 | 35.867 | 4.733 | 0.4946 | 68.705 |

## Confidence Statistics

| preset | n | avg_wait mean/std/p95 | runtime mean/std/p95 | realism mean/std/p95 |
| --- | ---: | ---: | ---: | ---: |
| 快速 Fast | 15 | 4.51/1.659/7.523 | 0.011/0.009/0.026 | 17.803/5.371/26.24 |
| 平衡 Balanced | 15 | 4.601/1.667/7.523 | 0.042/0.022/0.079 | 29.92/5.489/38.282 |
| 质量 Quality | 15 | 7.537/2.664/11.639 | 0.495/0.204/0.794 | 68.705/13.834/84.538 |

## Interpretation

This benchmark measures whether advanced movement adds spatial constraints, not whether it always reduces waits.
A more realistic movement model can increase total wait because students must physically reach the window queue and table area.
The CSV keeps `arrival_series_json` and `arrival_stream_hash` so model comparisons can verify identical demand streams.

## Rows

- Total rows: 45.
- Advanced rows with spatial signal: 15 / 15.
- Advanced max density: 7.
