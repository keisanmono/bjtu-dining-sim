# Campus Occupancy Arrival Design

## Goal

Use real BJTU classroom occupancy signals to drive cafeteria arrival demand, so simulations can model which teaching buildings release people, when they leave class, how long they take to reach a selected cafeteria, and how staggered dismissal changes queue pressure.

The simulation remains a single-cafeteria service model. The user selects one target cafeteria. The campus demand model still considers all main-campus teaching buildings, but each student probabilistically chooses among all cafeteria targets, with the nearest cafeteria receiving the highest probability. Only students who choose the selected target cafeteria enter the cafeteria queue and seating simulation.

## External Data Findings

`BJTUselfService` does not expose a packaged official campus API. Its classroom occupancy feature uses these sources:

- Classroom people counts come from `http://yaya.csoci.com:2333/api/classnum/?building=<buildingName>`.
- The response is parsed as JSON with `time` and `data`; each classroom row contains room name plus used and capacity values.
- The supported classroom-count building names include 第十七号教学楼, 思源楼, 思源西楼, 思源东楼, 第九教学楼, 第八教学楼, 第五教学楼, 逸夫教学楼, 机械楼. 东区一教 and 东区二教 exist in `BJTUselfService`, but this project excludes them because the simulation scope is the BJTU main campus.
- The bundled `model.pt` is used by `CaptchaModel` for captcha recognition, not classroom people detection.
- A second classroom schedule source exists at BJTU AA `classroomtimeholdresult/room_view/`, but it depends on an authenticated session and HTML parsing. This should not be used in the first integration.

Primary source references:

- `ApiConstant.CLASSROOM_CAPACITY_URL`: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/constant/ApiConstant.java
- `ClassroomCapacityService` JSON parsing: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/web/ClassroomCapacityService.java
- Building list and classroom UI: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/screen/DetectionScreen.kt
- Captcha model usage: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/CaptchaModel.java
- Authenticated AA classroom schedule parsing: https://github.com/HFDLYS/BJTUselfService/blob/main/app/src/main/java/team/bjtuss/bjtuselfservice/web/MisDataManager.java
- Baidu walking RouteMatrix API used for one-time precomputation: https://lbs.baidu.com/faq/api?title=webapi%2Froutchtout-walk
- Baidu light walking route API reference for single-route fallback checks: https://lbs.baidu.com/faq/api?title=webapi%2Fguide%2Fwebservice-lwrouteplanapi%2Fwalk

## Scope

### In Scope

- Add backend campus data models for real cafeterias, teaching buildings, distances, walking times, and classroom occupancy summaries.
- Add a static main-campus walking-time data file generated once from Baidu walking RouteMatrix results.
- Add a backend connector that fetches and normalizes `yaya.csoci.com` classroom occupancy data for selected buildings.
- Add a fallback path using bundled/static sample occupancy values when the external service is unavailable.
- Add a campus demand model that converts building occupancy and dismissal schedules into a per-minute arrival curve.
- Track teaching-building occupancy by floor because descending from upper floors adds time before the outdoor route starts.
- Support three occupancy inputs in the UI: fetch live classroom data, generate random floor counts, and manually edit floor counts.
- Add frontend controls to choose a cafeteria, choose source teaching buildings, set dismissal times, refresh occupancy data, and run simulation from campus-driven demand.
- Preserve existing manual `arrival_rate` simulation path.

### Out Of Scope

- BJTU AA login, cookie handling, captcha solving, or authenticated HTML scraping.
- Per-person outdoor pathfinding, crowd collision, or route congestion.
- Runtime calls to Baidu Maps. The application reads precomputed walking times instead.
- Predicting how many students choose a cafeteria from private personal schedules.
- Storing external occupancy data permanently beyond short-lived run/session cache.
- Simulating queues and seats for all cafeterias in one run. A run models one selected cafeteria.

## User Flow

1. User opens the simulation page and switches arrival mode from manual to campus-driven.
2. User selects a target cafeteria from a preset list.
3. User selects one or more teaching buildings.
4. User clicks "获取实时数据" to load classroom-derived floor counts, or clicks "随机生成" to create plausible floor counts.
5. User can manually edit every floor count before running.
6. User reviews total current people, estimated selected-cafeteria share, walking time, and arrival peak time per building.
7. User sets or accepts dismissal times for each building.
8. User runs the simulation. The backend converts the selected campus demand sources into arrivals and runs the same cafeteria queue/seat simulation.

## Data Model

### Campus Location

```python
@dataclass(frozen=True)
class CampusLocationData:
    id: str
    name: str
    kind: str  # "cafeteria" or "teaching_building"
    lat: float
    lng: float
    source: str
```

Coordinates are Baidu-map latitude/longitude values used to document how the static walking-time table was generated. Runtime demand calculation must use the precomputed walking-time table, not straight-line distance.

### Campus Walking Times

Static walking times live in `backend/app/data/campus_walk_times.json`.

```python
@dataclass(frozen=True)
class CampusWalkRouteData:
    distance_m: int
    duration_s: int
    duration_min: int

@dataclass(frozen=True)
class CampusWalkTimesData:
    source: str
    generated_at: str
    campus_scope: str  # "main_campus_only"
    locations: dict[str, list[CampusLocationData]]
    walk_times: dict[str, dict[str, CampusWalkRouteData]]
```

The first version includes nine main-campus teaching buildings: 思源楼, 思源西楼, 思源东楼, 第九教学楼, 第八教学楼, 第五教学楼, 逸夫教学楼, 机械楼, 第十七号教学楼. It includes four student cafeteria targets: 学活餐厅, 明湖餐厅, 学四食堂, 学苑餐厅.

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

The first implemented version replaces fixed `cafeteria_share` with a distance-based choice model while keeping `release_ratio`.

```python
@dataclass(frozen=True)
class CampusFloorDemandData:
    floor: int
    count: int

@dataclass(frozen=True)
class CampusBuildingDemandData:
    building_id: str
    dismissal_minute: int
    release_ratio: float
    floors: list[CampusFloorDemandData]
```

### Simulation Config Extension

```python
@dataclass(frozen=True)
class CampusDemandConfigData:
    enabled: bool = False
    cafeteria_id: str | None = None
    source_mode: str = "manual"  # "live", "random", or "manual"
    buildings: list[CampusBuildingDemandData] = field(default_factory=list)
    occupancy_by_building: dict[str, BuildingOccupancyData] = field(default_factory=dict)
```

`SimulationConfigData` gains `campus_demand: CampusDemandConfigData | None = None`.

## Arrival Model

For each selected building:

1. Sum `count` across floors.
2. For each floor, estimate released people: `round(floor.count * release_ratio)`.
3. For each released student, sample whether they choose the selected cafeteria:
   - Load walking duration from the building to every cafeteria.
   - Assign a weight to each cafeteria inversely related to walking time.
   - The nearest cafeteria therefore has the highest probability, while farther cafeterias still receive a smaller probability.
4. Compute arrival time for selected-cafeteria students:
   - Load `walk_times[building_id][cafeteria_id]` from `backend/app/data/campus_walk_times.json`.
   - Start from `dismissal_minute * 60`.
   - Add floor descent time: upper floors leave later than lower floors.
   - Add outdoor route time using Baidu walking duration as the baseline.
   - Apply route-time variation:
     - cycling or fast walking: shorter than Baidu walking time
     - normal walking: near Baidu walking time
     - slow or delayed walking: longer than Baidu walking time
   - If a pair is missing, fail validation instead of silently using a straight-line estimate.
5. Bucket sampled arrivals into integer minutes and add all building curves into a per-minute arrival schedule.

If campus demand is enabled, `_generate_arrivals(minute)` uses the generated schedule instead of Poisson `arrival_rate`. The simulation arrival horizon extends to the last scheduled campus arrival so outdoor travel time is not cut off by the original arrival duration. Peak multiplier and stagger settings remain available only for manual mode unless explicitly mapped later.

## Backend API

### `GET /api/campus/locations`

Returns preset cafeterias and teaching buildings.

```json
{
  "cafeterias": [{"id": "xuehuo", "name": "学活餐厅", "lat": 39.955997, "lng": 116.344712}],
  "teaching_buildings": [{"id": "siyuan", "name": "思源楼", "lat": 39.956911, "lng": 116.347533}]
}
```

### `POST /api/campus/occupancy`

Request:

```json
{"source_mode": "random", "buildings": ["siyuan", "no9"], "seed": 20}
```

Response:

```json
{
  "items": [
    {
      "building_name": "思源楼",
      "total_used": 820,
      "total_capacity": 1600,
      "floors": [{"floor": 1, "count": 180, "capacity": 320}],
      "effective_start": "2026-05-03 11:00",
      "effective_end": "2026-05-03 11:10",
      "source": "live"
    }
  ],
  "warnings": []
}
```

If the external service fails, response uses fallback values and includes a warning. The UI must clearly show fallback status.

`source_mode=live` requests `yaya.csoci.com` and aggregates classroom rows into floors by parsing room numbers. `source_mode=random` generates plausible floor counts for all requested buildings. Manual edits are made in the frontend and submitted in `campus_demand.buildings`.

### Existing Simulation APIs

`/api/sim/step`, `/api/sim/run`, and config validation accept the extended campus demand config. Existing clients that omit `campus_demand` continue working.

## Frontend UI

Add a campus-demand section to the run configuration panel:

- Arrival mode segmented control: manual / campus.
- Cafeteria select.
- Buttons: 获取实时数据 and 随机生成.
- Building/floor table covering all main-campus teaching buildings. Each floor count is editable.
- Building table with current used people, capacity, source status, dismissal time, release ratio, target-cafeteria choice probability, walking minutes, and estimated arrival peak.
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
- Validate `backend/app/data/campus_walk_times.json` covers all main-campus building/cafeteria pairs and does not contain secrets.
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
