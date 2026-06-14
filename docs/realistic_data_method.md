# Realistic Data Method

## Scope

This round only models Beijing Jiaotong University main campus and related main-campus residential areas. East campus dormitories are excluded from the model scope.

## Existing Geographic Data

Teaching-building to cafeteria walking times are stored in `backend/app/data/campus_walk_times.json`. These data cover the main campus teaching buildings and four cafeterias:

- 学活餐厅 (`xuehuo`)
- 明湖餐厅 (`minghu`)
- 学四食堂 (`xuesi`)
- 学苑餐厅 (`xueyuan`)

The original teaching-building arrival model is unchanged: each teaching building has floor-level demand, a `dismissal_minute`, and a release ratio.

## Residential Sources

Residential sources are stored in `backend/app/data/campus_residential_sources.json`. The file is flat. Every source is an individual dormitory or apartment building point, such as 嘉园A座、学苑1号楼、北京交通大学12号宿舍楼.

The model does not use a synthetic all-campus dormitory point. The phrase “主校区编号宿舍楼” is only a reporting category. It is not a simulation source and is not used for path calculation.

Each residential source has:

- `id`
- `name`
- `campus_area`
- `address_query`
- coordinates and geocode status
- `capacity_weight`
- source notes
- independent walking times to each cafeteria

Coordinates and walking times should be generated with Baidu Maps API by running:

```bash
BAIDU_MAP_AK=... python scripts/generate_residential_walk_times.py
```

When the API key is missing, the script exits with a clear message and does not affect core tests. The committed offline seed data are marked as pending Baidu API verification and are not school operation data.

The generator is cache-aware. By default it reuses existing successful coordinates and existing source-to-cafeteria routes in `campus_residential_sources.json`, then only requests missing or failed items. Use `--refresh` when a full Baidu API refresh is intentionally needed:

```bash
BAIDU_MAP_AK=... python scripts/generate_residential_walk_times.py --refresh
```

## Capacity And Population

Dormitory capacity is not treated as the number of students arriving at a cafeteria. Capacity or estimated capacity is only a weight for distributing residual residential population across individual dormitory sources.

The residual method is:

```text
effective_meal_population = round(total_population_pool * meal_participation_rate)
residential_population = effective_meal_population - teaching_population - other_known_population
```

If teaching and other known sources exceed the effective meal population, residential population is clamped to zero.

`total_population_pool` means the potential meal-period dining population pool for the scenario. It is not the university registration count. `meal_participation_rate` is a scenario assumption. `effective_meal_population` is the modeled number of potential cafeteria participants for that period.

Residual residential population is distributed directly to valid dormitory source points by `capacity_weight`. It is not first assigned to a campus area or aggregate source.

`residential_by_source_json` is the calculation-level allocation. `residential_by_area_json` is only a reporting summary for the report and must not be used for pathing or schedule generation.

## Release Logic

Teaching-building sources use event-based release:

- release mode: `event`
- trigger: `dismissal_minute`
- arrival time: dismissal minute plus floor descent and walking-time variation

Residential sources use time-window release:

- release mode: `time_window`
- every residential student samples a departure minute
- arrival time: sampled departure minute plus the source-specific walking-time variation

Default residential profiles are modeling assumptions:

- Breakfast: 7:00-8:30, peak 7:45, lower residential participation rate
- Lunch: 11:00-13:00, peak 12:00
- Dinner: 17:00-19:00, peak 18:00, higher residential participation rate
- Weekend: 8:30-13:00, peak 11:00, more dispersed participation

This avoids:

- double-counting teaching-building students as dormitory students
- treating dormitory capacity as real-time attendance
- merging multiple dormitory buildings into one path point
- releasing all residential students in a single minute
- overestimating breakfast by using dinner-like participation
