# BJTU Residential Scenarios Summary

This summary is generated from `data/experiments/bjtu_residential_scenarios.csv`.
All population pool, participation, and capacity-weight parameters are modeling assumptions, not school operation data.
Default runtime simulation scale in this CSV: 0.001.

## Scenario Mix
- `breakfast_residential_window`: total_arrived=7, teaching_arrived=0, residential_arrived=7, residential_share=100.0%.
- `dinner_mixed_window`: total_arrived=23, teaching_arrived=23, residential_arrived=0, residential_share=0.0%.
- `lunch_teaching_event_plus_residential_window`: total_arrived=26, teaching_arrived=26, residential_arrived=0, residential_share=0.0%.
- `weekend_residential_window`: total_arrived=13, teaching_arrived=7, residential_arrived=6, residential_share=46.2%.

## Congestion
- Highest peak queue in this run: `lunch_teaching_event_plus_residential_window` / `xuesi` / `advanced_floor_field` with peak_queue=1.
- Advanced floor field average conflict count across rows: 0.44.
- Advanced floor field max observed density across rows: 4.

## Interpretation Notes
- `residential_by_source_json` is the calculation-level allocation by individual dormitory source.
- `residential_by_area_json` is only a reporting summary; it is not used for pathing or schedule generation.
- Residential time-window release spreads departures and avoids putting all dormitory students into one minute.
- `simulation_population_scale` records the runtime scale used for DES/Floor Field execution; set `BJTU_SCENARIO_SIMULATION_SCALE=1.0` for a full-size run.
