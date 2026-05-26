from __future__ import annotations

# 文件说明：校园到达数据模块：负责教学楼、食堂步行时间、实时/随机楼层人数和到达计划。

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
# 单层教学楼人数输入，用于把“几楼有多少人”转换成到达食堂的时间分布。
class CampusFloorDemandData:
    floor: int
    count: int


@dataclass(frozen=True)
# 单栋教学楼的下课释放设置，包含下课时间、就餐比例和各楼层人数。
class CampusBuildingDemandData:
    building_id: str
    dismissal_minute: int = 0
    release_ratio: float = 1.0
    floors: list[CampusFloorDemandData] = field(default_factory=list)


@dataclass(frozen=True)
# 校园到达模式的完整配置，仿真器会据此跳过手动泊松到达。
class CampusDemandConfigData:
    enabled: bool = False
    cafeteria_id: str | None = None
    source_mode: str = "manual"
    buildings: list[CampusBuildingDemandData] = field(default_factory=list)


# 读取内置校园步行时间 JSON，后续接口和到达计划都基于这份数据。
def load_campus_walk_times() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


# 返回前端需要展示的食堂、教学楼、默认楼层数和步行时间。
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


# 建立教学楼 id 到中文名称的索引，便于校验和实时接口查询。
def building_name_by_id() -> dict[str, str]:
    return {item["id"]: item["name"] for item in load_campus_walk_times()["locations"]["teaching_buildings"]}


# 返回系统已知教学楼 id 集合，供参数校验使用。
def known_building_ids() -> set[str]:
    return set(building_name_by_id())


# 返回系统已知食堂 id 集合，防止校园到达模式选择不存在的食堂。
def known_cafeteria_ids() -> set[str]:
    data = load_campus_walk_times()
    return {item["id"] for item in data["locations"]["cafeterias"]}


# 按步行时长计算学生选择各食堂的概率，距离越近权重越高。
def cafeteria_choice_probabilities(building_id: str, choice_power: float = DEFAULT_CHOICE_POWER) -> dict[str, float]:
    walk_times = load_campus_walk_times()["walk_times"]
    if building_id not in walk_times:
        raise KeyError(f"未知教学楼：{building_id}")
    durations = {
        cafeteria_id: max(1, int(route["duration_s"]))
        for cafeteria_id, route in walk_times[building_id].items()
    }
    nearest = min(durations.values())
    # 以最近食堂为基准做相对权重，choice_power 越大越偏向距离最近的食堂。
    weights = {
        cafeteria_id: math.pow(nearest / duration, max(0.1, choice_power))
        for cafeteria_id, duration in durations.items()
    }
    total = sum(weights.values())
    return {cafeteria_id: weight / total for cafeteria_id, weight in weights.items()}


# 把楼层人数展开为“第几分钟到达多少人”，同时考虑下楼、步行波动和食堂选择概率。
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
                # 并不是教学楼所有学生都去当前食堂；按步行距离概率筛掉去其他食堂的人。
                if rng.random() > target_probability:
                    continue
                # 到达秒数由下课分钟、下楼时间和路上步行波动三部分组成。
                arrival_second = (
                    max(0, building.dismissal_minute) * 60
                    + _floor_descent_seconds(floor.floor, rng)
                    + _route_seconds_with_variation(route_seconds, rng)
                )
                schedule[max(0, int(arrival_second // 60))] += 1
    return dict(sorted(schedule.items()))


# 在没有实时数据时，为每栋楼生成可复现的楼层人数模拟数据。
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
            # 容量和占用率都带随机扰动，但 seed 固定后结果可复现。
            capacity = max(40, int(rng.gauss(base_capacity, base_capacity * 0.12)))
            occupancy_ratio = _clamp(rng.gauss(0.62, 0.20), 0.08, 0.96)
            count = int(round(capacity * occupancy_ratio))
            floors.append({"floor": floor, "count": count, "capacity": capacity})
        items.append(_building_occupancy_payload(building_id, names[building_id], floors, source="random"))
    return items


# 并发请求各教学楼实时教室人数，返回成功数据和可展示的降级警告。
def fetch_live_floor_occupancy(building_ids: list[str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    names = building_name_by_id()
    selected = building_ids or list(names)
    items = []
    warnings = []
    jobs = [(building_id, names.get(building_id)) for building_id in selected]
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(jobs)))) as executor:
        # 不同教学楼互不依赖，可以并发查询，避免一个楼的实时接口拖慢全部结果。
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
    # 并发完成顺序不稳定，返回前按用户选择的教学楼顺序排回去。
    items.sort(key=lambda item: selected.index(item["building_id"]) if item["building_id"] in selected else len(selected))
    return items, warnings


# 获取单栋楼实时人数；失败时优先用缓存，再退回随机模拟数据。
def _fetch_live_building_occupancy(building_id: str, building_name: str) -> tuple[dict[str, Any], str | None]:
    try:
        payload = _fetch_classroom_capacity_with_retry(building_name)
        item = parse_classroom_capacity_payload(building_id, building_name, payload)
        # 成功拿到实时数据时立即更新缓存，后续短时失败可以降级到 live_cache。
        _LIVE_OCCUPANCY_CACHE[building_id] = copy.deepcopy(item)
        return item, None
    except Exception as exc:  # noqa: BLE001 - external service must not break the simulation UI
        cached = _cached_live_occupancy(building_id)
        if cached is not None:
            return cached, _friendly_live_warning(building_name, exc, "最近一次实时数据")
        # 无缓存时才退回随机数据，保证前端校园模式仍可继续演示。
        fallback = generate_random_floor_occupancy([building_id], seed=_stable_seed(building_id))[0]
        return fallback, _friendly_live_warning(building_name, exc, "模拟数据")


# 解析教室容量接口行数据，过滤满员/无效教室后按楼层聚合人数。
def parse_classroom_capacity_payload(building_id: str, building_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    floors: dict[int, dict[str, int]] = {}
    for row in payload.get("data") or []:
        if not isinstance(row, list) or len(row) < 4:
            continue
        room_name = str(row[0])
        used = _safe_int(row[2])
        capacity = _safe_int(row[3])
        if capacity <= 0 or used >= capacity:
            # 满员行在该接口里经常代表不可读或占位数据，避免把异常值当成真实人数。
            continue
        floor = _floor_from_room_name(room_name)
        item = floors.setdefault(floor, {"floor": floor, "count": 0, "capacity": 0})
        item["count"] += used
        item["capacity"] += capacity
    floor_items = [floors[key] for key in sorted(floors)]
    result = _building_occupancy_payload(building_id, building_name, floor_items, source="live")
    times = payload.get("time") if isinstance(payload.get("time"), list) else []
    if len(times) >= 2:
        # 保留外部接口给出的生效时间，便于前端说明这批实时数据的时间范围。
        result["effective_start"] = str(times[0])
        result["effective_end"] = str(times[1])
    return result


# 按前端选择分发 live/random/manual 三种人数来源。
def campus_occupancy(source_mode: str, building_ids: list[str] | None = None, seed: int = 1) -> dict[str, Any]:
    if source_mode == "live":
        items, warnings = fetch_live_floor_occupancy(building_ids)
        return {"items": items, "warnings": warnings}
    if source_mode == "random":
        return {"items": generate_random_floor_occupancy(building_ids, seed=seed), "warnings": []}
    if source_mode == "manual":
        return {"items": [], "warnings": []}
    raise ValueError("source_mode 必须是 live、random 或 manual。")


# 统一楼层人数响应格式，前端表格和校园到达配置都读取这个结构。
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


# 请求外部教室人数接口，返回原始 JSON 给解析函数处理。
def _fetch_classroom_capacity(building_name: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"building": building_name})
    request = urllib.request.Request(
        f"{CLASSROOM_CAPACITY_URL}?{query}",
        headers={"User-Agent": "bjtu-dining-sim/0.1"},
    )
    with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT_SEC) as response:
        return json.loads(response.read().decode("utf-8"))


# 对实时人数接口做有限重试，仍失败时把最后一次异常交给降级逻辑。
def _fetch_classroom_capacity_with_retry(building_name: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for _attempt in range(LIVE_RETRY_COUNT + 1):
        try:
            return _fetch_classroom_capacity(building_name)
        except Exception as exc:  # noqa: BLE001 - preserve final failure for fallback classification
            # 这里只记录最后一次异常，不在重试中打印底层错误，最终交给友好降级提示。
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("实时人数服务未返回数据。")


# 返回实时人数缓存的深拷贝，避免后续调用修改缓存对象。
def _cached_live_occupancy(building_id: str) -> dict[str, Any] | None:
    cached = _LIVE_OCCUPANCY_CACHE.get(building_id)
    if cached is None:
        return None
    payload = copy.deepcopy(cached)
    payload["source"] = "live_cache"
    return payload


# 把外部服务异常转换成前端可直接展示的中文降级提示。
def _friendly_live_warning(building_name: str, exc: Exception, fallback_label: str) -> str:
    reason = "实时服务超时" if _is_timeout_error(exc) else "实时服务暂不可用"
    return f"{building_name} {reason}，已使用{fallback_label}，可重试。"


# 判断异常是否属于超时，用于生成更准确的降级原因。
def _is_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text


# 从教室号中提取楼层，无法识别时默认按一层处理。
def _floor_from_room_name(room_name: str) -> int:
    matches = re.findall(r"\d{3,}", room_name)
    if not matches:
        return 1
    tail = matches[-1][-3:]
    return max(1, int(tail[0]))


# 估算学生从所在楼层下楼到教学楼出口的耗时。
def _floor_descent_seconds(floor: int, rng: random.Random) -> int:
    level = max(1, int(floor))
    if level <= 1:
        return max(0, int(round(rng.gauss(8, 4))))
    return max(0, int(round((level - 1) * rng.gauss(DEFAULT_FLOOR_SECONDS, 6))))


# 给基础步行时长加入快走、正常、慢走和停留等随机波动。
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


# 安全读取接口中的人数/容量字段，异常或负值统一当作 0。
def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


# 将浮点数限制在指定闭区间内。
def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, float(value)))


# 根据教学楼 id 生成稳定种子，让降级随机数据可复现。
def _stable_seed(value: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(value)) % 10000
