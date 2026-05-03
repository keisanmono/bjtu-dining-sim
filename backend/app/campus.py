from __future__ import annotations

import json
import math
import copy
import random
import re
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DATA_PATH = Path(__file__).resolve().parent / "data" / "campus_walk_times.json"
DEFAULT_FLOOR_SECONDS = 32
DEFAULT_CHOICE_POWER = 2.4
LIVE_TIMEOUT_SEC = 6
LIVE_RETRY_COUNT = 1
CLASSROOM_CAPACITY_URL = "http://yaya.csoci.com:2333/api/classnum/"
_LIVE_OCCUPANCY_CACHE: dict[str, dict[str, Any]] = {}

DEFAULT_BUILDING_FLOORS: dict[str, int] = {
    "siyuan": 5,
    "siyuan_west": 6,
    "siyuan_east": 5,
    "no9": 6,
    "no8": 5,
    "no5": 5,
    "yifu": 6,
    "mechanical": 6,
    "no17": 5,
}

DEFAULT_FLOOR_CAPACITY: dict[str, int] = {
    "siyuan": 150,
    "siyuan_west": 130,
    "siyuan_east": 130,
    "no9": 180,
    "no8": 160,
    "no5": 160,
    "yifu": 170,
    "mechanical": 150,
    "no17": 120,
}


@dataclass(frozen=True)
class CampusFloorDemandData:
    floor: int
    count: int


@dataclass(frozen=True)
class CampusBuildingDemandData:
    building_id: str
    dismissal_minute: int = 0
    release_ratio: float = 1.0
    floors: list[CampusFloorDemandData] = field(default_factory=list)


@dataclass(frozen=True)
class CampusDemandConfigData:
    enabled: bool = False
    cafeteria_id: str | None = None
    source_mode: str = "manual"
    buildings: list[CampusBuildingDemandData] = field(default_factory=list)


def load_campus_walk_times() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def campus_locations() -> dict[str, Any]:
    data = load_campus_walk_times()
    return {
        "campus_scope": data["campus_scope"],
        "source": data["source"],
        "generated_at": data["generated_at"],
        "cafeterias": data["locations"]["cafeterias"],
        "teaching_buildings": [
            {
                **building,
                "default_floor_count": DEFAULT_BUILDING_FLOORS.get(building["id"], 5),
            }
            for building in data["locations"]["teaching_buildings"]
        ],
        "walk_times": data["walk_times"],
    }


def building_name_by_id() -> dict[str, str]:
    return {item["id"]: item["name"] for item in load_campus_walk_times()["locations"]["teaching_buildings"]}


def known_building_ids() -> set[str]:
    return set(building_name_by_id())


def known_cafeteria_ids() -> set[str]:
    data = load_campus_walk_times()
    return {item["id"] for item in data["locations"]["cafeterias"]}


def cafeteria_choice_probabilities(building_id: str, choice_power: float = DEFAULT_CHOICE_POWER) -> dict[str, float]:
    walk_times = load_campus_walk_times()["walk_times"]
    if building_id not in walk_times:
        raise KeyError(f"未知教学楼：{building_id}")
    durations = {
        cafeteria_id: max(1, int(route["duration_s"]))
        for cafeteria_id, route in walk_times[building_id].items()
    }
    nearest = min(durations.values())
    weights = {
        cafeteria_id: math.pow(nearest / duration, max(0.1, choice_power))
        for cafeteria_id, duration in durations.items()
    }
    total = sum(weights.values())
    return {cafeteria_id: weight / total for cafeteria_id, weight in weights.items()}


def build_campus_arrival_schedule(
    cafeteria_id: str,
    buildings: list[CampusBuildingDemandData],
    seed: int = 1,
    force_target: bool = False,
) -> dict[int, int]:
    walk_times = load_campus_walk_times()["walk_times"]
    if cafeteria_id not in known_cafeteria_ids():
        raise ValueError(f"未知食堂：{cafeteria_id}")

    rng = random.Random(seed)
    schedule: Counter[int] = Counter()
    for building in buildings:
        if building.building_id not in walk_times:
            raise ValueError(f"未知教学楼：{building.building_id}")
        if cafeteria_id not in walk_times[building.building_id]:
            raise ValueError(f"缺少 {building.building_id} 到 {cafeteria_id} 的步行时间。")
        probabilities = cafeteria_choice_probabilities(building.building_id)
        target_probability = 1.0 if force_target else probabilities[cafeteria_id]
        route_seconds = int(walk_times[building.building_id][cafeteria_id]["duration_s"])
        release_ratio = _clamp(building.release_ratio, 0.0, 1.0)
        for floor in building.floors:
            released_count = max(0, int(round(floor.count * release_ratio)))
            for _ in range(released_count):
                if rng.random() > target_probability:
                    continue
                arrival_second = (
                    max(0, building.dismissal_minute) * 60
                    + _floor_descent_seconds(floor.floor, rng)
                    + _route_seconds_with_variation(route_seconds, rng)
                )
                schedule[max(0, int(arrival_second // 60))] += 1
    return dict(sorted(schedule.items()))


def generate_random_floor_occupancy(building_ids: list[str] | None = None, seed: int = 1) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    names = building_name_by_id()
    selected = building_ids or list(names)
    items = []
    for building_id in selected:
        if building_id not in names:
            continue
        floor_count = DEFAULT_BUILDING_FLOORS.get(building_id, 5)
        base_capacity = DEFAULT_FLOOR_CAPACITY.get(building_id, 140)
        floors = []
        for floor in range(1, floor_count + 1):
            capacity = max(40, int(rng.gauss(base_capacity, base_capacity * 0.12)))
            occupancy_ratio = _clamp(rng.gauss(0.62, 0.20), 0.08, 0.96)
            count = int(round(capacity * occupancy_ratio))
            floors.append({"floor": floor, "count": count, "capacity": capacity})
        items.append(_building_occupancy_payload(building_id, names[building_id], floors, source="random"))
    return items


def fetch_live_floor_occupancy(building_ids: list[str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    names = building_name_by_id()
    selected = building_ids or list(names)
    items = []
    warnings = []
    jobs = [(building_id, names.get(building_id)) for building_id in selected]
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(jobs)))) as executor:
        futures = {
            executor.submit(_fetch_live_building_occupancy, building_id, building_name): (building_id, building_name)
            for building_id, building_name in jobs
            if building_name is not None
        }
        for building_id, building_name in jobs:
            if building_name is None:
                warnings.append(f"未知教学楼 {building_id}，已跳过。")
        for future in as_completed(futures):
            building_id, building_name = futures[future]
            item, warning = future.result()
            items.append(item)
            if warning:
                warnings.append(warning)
    items.sort(key=lambda item: selected.index(item["building_id"]) if item["building_id"] in selected else len(selected))
    return items, warnings


def _fetch_live_building_occupancy(building_id: str, building_name: str) -> tuple[dict[str, Any], str | None]:
    try:
        payload = _fetch_classroom_capacity_with_retry(building_name)
        item = parse_classroom_capacity_payload(building_id, building_name, payload)
        _LIVE_OCCUPANCY_CACHE[building_id] = copy.deepcopy(item)
        return item, None
    except Exception as exc:  # noqa: BLE001 - external service must not break the simulation UI
        cached = _cached_live_occupancy(building_id)
        if cached is not None:
            return cached, _friendly_live_warning(building_name, exc, "最近一次实时数据")
        fallback = generate_random_floor_occupancy([building_id], seed=_stable_seed(building_id))[0]
        return fallback, _friendly_live_warning(building_name, exc, "模拟数据")


def parse_classroom_capacity_payload(building_id: str, building_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    floors: dict[int, dict[str, int]] = {}
    for row in payload.get("data") or []:
        if not isinstance(row, list) or len(row) < 4:
            continue
        room_name = str(row[0])
        used = _safe_int(row[2])
        capacity = _safe_int(row[3])
        if capacity <= 0 or used >= capacity:
            continue
        floor = _floor_from_room_name(room_name)
        item = floors.setdefault(floor, {"floor": floor, "count": 0, "capacity": 0})
        item["count"] += used
        item["capacity"] += capacity
    floor_items = [floors[key] for key in sorted(floors)]
    result = _building_occupancy_payload(building_id, building_name, floor_items, source="live")
    times = payload.get("time") if isinstance(payload.get("time"), list) else []
    if len(times) >= 2:
        result["effective_start"] = str(times[0])
        result["effective_end"] = str(times[1])
    return result


def campus_occupancy(source_mode: str, building_ids: list[str] | None = None, seed: int = 1) -> dict[str, Any]:
    if source_mode == "live":
        items, warnings = fetch_live_floor_occupancy(building_ids)
        return {"items": items, "warnings": warnings}
    if source_mode == "random":
        return {"items": generate_random_floor_occupancy(building_ids, seed=seed), "warnings": []}
    if source_mode == "manual":
        return {"items": [], "warnings": []}
    raise ValueError("source_mode 必须是 live、random 或 manual。")


def _building_occupancy_payload(
    building_id: str,
    building_name: str,
    floors: list[dict[str, int]],
    source: str,
) -> dict[str, Any]:
    return {
        "building_id": building_id,
        "building_name": building_name,
        "floors": floors,
        "total_used": sum(max(0, int(floor.get("count", 0))) for floor in floors),
        "total_capacity": sum(max(0, int(floor.get("capacity", 0))) for floor in floors),
        "effective_start": "",
        "effective_end": "",
        "source": source,
    }


def _fetch_classroom_capacity(building_name: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"building": building_name})
    request = urllib.request.Request(
        f"{CLASSROOM_CAPACITY_URL}?{query}",
        headers={"User-Agent": "bjtu-dining-sim/0.1"},
    )
    with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT_SEC) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_classroom_capacity_with_retry(building_name: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for _attempt in range(LIVE_RETRY_COUNT + 1):
        try:
            return _fetch_classroom_capacity(building_name)
        except Exception as exc:  # noqa: BLE001 - preserve final failure for fallback classification
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("实时人数服务未返回数据。")


def _cached_live_occupancy(building_id: str) -> dict[str, Any] | None:
    cached = _LIVE_OCCUPANCY_CACHE.get(building_id)
    if cached is None:
        return None
    payload = copy.deepcopy(cached)
    payload["source"] = "live_cache"
    return payload


def _friendly_live_warning(building_name: str, exc: Exception, fallback_label: str) -> str:
    reason = "实时服务超时" if _is_timeout_error(exc) else "实时服务暂不可用"
    return f"{building_name} {reason}，已使用{fallback_label}，可重试。"


def _is_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text


def _floor_from_room_name(room_name: str) -> int:
    matches = re.findall(r"\d{3,}", room_name)
    if not matches:
        return 1
    tail = matches[-1][-3:]
    return max(1, int(tail[0]))


def _floor_descent_seconds(floor: int, rng: random.Random) -> int:
    level = max(1, int(floor))
    if level <= 1:
        return max(0, int(round(rng.gauss(8, 4))))
    return max(0, int(round((level - 1) * rng.gauss(DEFAULT_FLOOR_SECONDS, 6))))


def _route_seconds_with_variation(route_seconds: int, rng: random.Random) -> int:
    roll = rng.random()
    if roll < 0.14:
        multiplier = rng.uniform(0.45, 0.72)
    elif roll < 0.84:
        multiplier = rng.uniform(0.86, 1.16)
    else:
        multiplier = rng.uniform(1.22, 1.72)
    linger = 0 if rng.random() < 0.78 else rng.randint(30, 180)
    return max(30, int(round(route_seconds * multiplier + linger)))


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, float(value)))


def _stable_seed(value: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(value)) % 10000
