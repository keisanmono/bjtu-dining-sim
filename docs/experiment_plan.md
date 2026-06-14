# Experiment Plan

## Main-Campus Residential Scenarios

The new experiments add residential time-window demand to the existing teaching-building event model. The scope is limited to BJTU main campus and related residential areas. East campus dormitories are out of scope.

The model does not use a synthetic all-dormitory source. Every residential student is allocated to an individual dormitory or apartment building source, then routed from that source to the target cafeteria.

## Population Method

Each scenario sets:

- `total_population_pool`: the modeled potential dining population pool for that period
- `meal_participation_rate`: the scenario meal participation assumption
- `effective_meal_population = round(total_population_pool * meal_participation_rate)`
- `teaching_population`: floor-level teaching-building demand after release ratio
- `other_known_population`: reserved demand for non-modeled known sources

Residential demand is the residual:

```text
residential_population = max(0, effective_meal_population - teaching_population - other_known_population)
```

The residual is distributed to individual residential source points by `capacity_weight`. Capacity weights are allocation weights only and are not current attendance.

## Scenarios

### A. breakfast_residential_window

- meal period: breakfast
- total population pool: 12000
- meal participation rate: 0.55
- teaching-building demand: very low or zero
- residential source mix dominates
- residential release window: 7:00-8:30

### B. lunch_teaching_event_plus_residential_window

- meal period: lunch
- total population pool: 15000
- meal participation rate: 0.75
- teaching-building dismissal events dominate
- residential demand is the residual small part
- residential release window: 11:00-13:00

### C. dinner_mixed_window

- meal period: dinner
- total population pool: 15000
- meal participation rate: 0.70
- teaching-building and residential demand are mixed
- residential release window: 17:00-19:00
- residential participation is higher than breakfast

### D. weekend_residential_window

- meal period: weekend
- total population pool: 10000
- meal participation rate: 0.50
- teaching-building demand is low
- residential demand dominates
- release window is more dispersed

Each scenario is run for:

- `movement_model="path"`
- `movement_model="advanced_floor_field"`

The output CSV is:

```text
data/experiments/bjtu_residential_scenarios.csv
```

The CSV contains residual population fields, release profile fields, source-level residential allocation JSON, area-level reporting JSON, service and seating metrics, and advanced floor-field movement metrics.

For development-time reproducibility, `scripts/generate_bjtu_scenarios.py` defaults to `BJTU_SCENARIO_SIMULATION_SCALE=0.05` for DES/Floor Field execution while preserving the original scenario population pool and residual-allocation fields in the CSV. Set `BJTU_SCENARIO_SIMULATION_SCALE=1.0` for a full-size run.
