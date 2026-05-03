# Campus Occupancy Arrival Design

## Goal

Use real BJTU classroom occupancy signals to drive cafeteria arrival demand, so simulations can model which teaching buildings release people, when they leave class, how long they take to reach a selected cafeteria, and how staggered dismissal changes queue pressure.

## External Data Findings

`BJTUselfService` does not expose a packaged official campus API. Its classroom occupancy feature uses these sources:

- Classroom people counts come from `http://yaya.csoci.com:2333/api/classnum/?building=<buildingName>`.
- The response is parsed as JSON with `time` and `data`; each classroom row contains room name plus used and capacity values.
- The supported building names include 第十七号教学楼, 思源楼, 思源西楼, 思源东楼, 第九教学楼, 第八教学楼, 第五教学楼, 逸夫教学楼, 机械楼, 东区二教, 东区一教.
- The bundled `model.pt` is used by `CaptchaModel` for captcha recognition, not classroom people detection.
- A second classroom schedule source exists at BJTU AA `classroomtimeholdresult/room_view/`, but it depends on an authenticated session and HTML parsing. This should not be used in the first integration.

Primary source references:

- `ApiConstant.CLASSROOM_CAPACITY_URL`: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/constant/ApiConstant.java
- `ClassroomCapacityService` JSON parsing: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/web/ClassroomCapacityService.java
- Building list and classroom UI: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/screen/DetectionScreen.kt
- Captcha model usage: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/CaptchaModel.java
- Authenticated AA classroom schedule parsing: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/web/MisDataManager.java

## Scope

### In Scope

- Add backend campus data models for real cafeterias, teaching buildings, distances, walking times, and classroom occupancy summaries.
- Add a backend connector that fetches and normalizes `yaya.csoci.com` classroom occupancy data for selected buildings.
- Add a fallback path using bundled/static sample occupancy values when the external service is unavailable.
- Add a campus demand model that converts building occupancy and dismissal schedules into a per-minute arrival curve.
- Add frontend controls to choose a cafeteria, choose source teaching buildings, set dismissal times, refresh occupancy data, and run simulation from campus-driven demand.
- Preserve existing manual `arrival_rate` simulation path.

### Out Of Scope

- BJTU AA login, cookie handling, captcha solving, or authenticated HTML scraping.
- Per-person outdoor pathfinding, crowd collision, or route congestion.
- Predicting how many students choose a cafeteria from private personal schedules.
- Storing external occupancy data permanently beyond short-lived run/session cache.

## User Flow

1. User opens the simulation page and switches arrival mode from manual to campus-driven.
2. User selects a target cafeteria from a preset list.
3. User selects one or more teaching buildings.
4. User clicks refresh to load current classroom occupancy for the selected buildings.
5. User reviews total current people, estimated release count, distance, walking time, and arrival peak time per building.
6. User sets or accepts dismissal times for each building.
7. User runs the simulation. The backend converts the selected campus demand sources into arrivals and runs the same cafeteria queue/seat simulation.

## Data Model

### Campus Location

```python
@dataclass(frozen=True)
class CampusLocationData:
    id: str
    name: str
    kind: str  # "cafeteria" or "teaching_building"
    x: float
    y: float
```

Coordinates are campus-map units, not the existing cafeteria floor-plan coordinates. They are only used for walking-time estimates between teaching buildings and cafeterias.

### Classroom Occupancy

```python
@dataclass(frozen=True)
class ClassroomOccupancyData:
    room_name: str
    capacity: int
    used: int

@dataclass(frozen=True)
class BuildingOccupancyData:
    building_name: str
    classrooms: list[ClassroomOccupancyData]
    effective_start: str
    effective_end: str
    source: str  # "live" or "fallback"
```

### Campus Demand Source

```python
@dataclass(frozen=True)
class CampusDemandSourceData:
    building_name: str
    dismissal_minute: int
    release_ratio: float
    cafeteria_share: float
```

`release_ratio` converts current building occupancy into people leaving at dismissal. `cafeteria_share` estimates the fraction who choose the selected cafeteria.

### Simulation Config Extension

```python
@dataclass(frozen=True)
class CampusDemandConfigData:
    enabled: bool = False
    cafeteria_id: str | None = None
    sources: list[CampusDemandSourceData] = field(default_factory=list)
    occupancy_by_building: dict[str, BuildingOccupancyData] = field(default_factory=dict)
```

`SimulationConfigData` gains `campus_demand: CampusDemandConfigData | None = None`.

## Arrival Model

For each selected building:

1. Sum `used` across classrooms.
2. Estimate released people: `round(total_used * release_ratio * cafeteria_share)`.
3. Compute walking time from teaching building to selected cafeteria:
   - `distance = hypot(building.x - cafeteria.x, building.y - cafeteria.y)`
   - `walk_minutes = clamp(round(distance / walking_speed_units_per_min), 2, 20)`
4. Spread arrivals around `dismissal_minute + walk_minutes` using a short distribution:
   - 20% arrive 2 minutes before peak
   - 30% arrive 1 minute before peak
   - 30% arrive at peak
   - 15% arrive 1 minute after peak
   - 5% arrive 2 minutes after peak
5. Add all building curves into an integer per-minute arrival schedule.

If campus demand is enabled, `_generate_arrivals(minute)` uses the generated schedule instead of Poisson `arrival_rate`. Peak multiplier and stagger settings remain available only for manual mode unless explicitly mapped later.

## Backend API

### `GET /api/campus/locations`

Returns preset cafeterias and teaching buildings.

```json
{
  "cafeterias": [{"id": "xuehuo", "name": "学活食堂", "x": 0, "y": 0}],
  "teaching_buildings": [{"id": "sy", "name": "思源楼", "x": 120, "y": 80}]
}
```

### `POST /api/campus/occupancy`

Request:

```json
{"buildings": ["思源楼", "第九教学楼"]}
```

Response:

```json
{
  "items": [
    {
      "building_name": "思源楼",
      "total_used": 820,
      "total_capacity": 1600,
      "effective_start": "2026-05-03 11:00",
      "effective_end": "2026-05-03 11:10",
      "source": "live"
    }
  ],
  "warnings": []
}
```

If the external service fails, response uses fallback values and includes a warning. The UI must clearly show fallback status.

### Existing Simulation APIs

`/api/sim/step`, `/api/sim/run`, and config validation accept the extended campus demand config. Existing clients that omit `campus_demand` continue working.

## Frontend UI

Add a campus-demand section to the run configuration panel:

- Arrival mode segmented control: manual / campus.
- Cafeteria select.
- Teaching building multi-select.
- Refresh occupancy button.
- Building table with current used people, capacity, source status, dismissal time, release ratio, cafeteria share, walking minutes, and estimated arrival peak.
- Run button uses campus config when campus mode is active.

The UI should stay operational if external occupancy fetch fails. It should let users run with fallback values after showing a warning.

## Error Handling

- External service timeout: 5 seconds per building.
- Invalid JSON or missing fields: mark the building as fallback and continue.
- Unknown building: validation error before simulation run.
- No selected buildings in campus mode: validation error.
- Zero estimated arrivals: validation warning, not an error.
- HTTP external data is treated as untrusted input. Values are clamped to non-negative integers.

## Testing

Backend tests:

- Parse a representative `classnum` JSON response into building totals.
- Fall back cleanly when the connector raises timeout or malformed JSON.
- Convert selected building occupancy and dismissal time into the expected per-minute arrival curve.
- Campus-demand simulation uses the schedule instead of Poisson arrival rate.
- Existing manual simulation tests still pass.

Frontend tests:

- Campus mode includes cafeteria select, building selection, occupancy refresh, and building table terms.
- Simulation payload includes `campus_demand` only in campus mode.
- Fallback warnings from occupancy refresh are surfaced to the user.
- Existing manual mode payload remains unchanged.

## Privacy And Operational Notes

The first version must not ask for BJTU user credentials. It only queries the classroom count endpoint already used by `BJTUselfService`. Because the service is not under this project’s control, the app must be useful with fallback data and must label live data as best-effort.

## Acceptance Criteria

- User can select a real cafeteria and one or more teaching buildings.
- User can refresh building occupancy data and see live or fallback status.
- Simulation run can be driven by campus demand rather than a single average arrival rate.
- Metrics such as peak queue and average wait change when building selection, dismissal time, or cafeteria choice changes.
- Manual arrival-rate simulation remains available and unchanged.
