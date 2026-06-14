#!/usr/bin/env python3
"""Generate BJTU residential coordinates and cafeteria walk times with Baidu Maps API."""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CAMPUS_WALK_TIMES_PATH = ROOT / "backend" / "app" / "data" / "campus_walk_times.json"
RESIDENTIAL_PATH = ROOT / "backend" / "app" / "data" / "campus_residential_sources.json"
GEOCODING_URL = "https://api.map.baidu.com/geocoding/v3/"
ROUTEMATRIX_URL = "https://api.map.baidu.com/routematrix/v2/walking"
USER_AGENT = "bjtu-dining-sim/0.1"


def main() -> int:
    refresh = "--refresh" in sys.argv[1:]
    ak = os.environ.get("BAIDU_MAP_AK")
    if not ak:
        print("缺少 BAIDU_MAP_AK，请先设置百度地图 API key。", file=sys.stderr)
        return 2

    campus = _read_json(CAMPUS_WALK_TIMES_PATH)
    residential = _read_json(RESIDENTIAL_PATH)
    cafeterias = campus["locations"]["cafeterias"]
    warnings = list(residential.get("warnings", []))
    existing_walk_times = residential.get("walk_times", {}) if isinstance(residential.get("walk_times"), dict) else {}
    walk_times: dict[str, dict[str, Any]] = {
        source_id: dict(routes)
        for source_id, routes in existing_walk_times.items()
        if isinstance(routes, dict)
    }

    for source in residential.get("residential_areas", []):
        source_id = source.get("id", "")
        if source_id in {"main_dorms", "east_dorms"}:
            source["exclude_from_simulation"] = True
            warnings.append(f"禁止的宿舍聚合 source {source_id} 已排除。")
            continue
        if source.get("exclude_from_simulation") and source.get("geocode_status") != "failed":
            continue

        if not refresh and _has_cached_location(source):
            location = {"lat": float(source["lat"]), "lng": float(source["lng"])}
        else:
            location, warning = _geocode(source.get("address_query") or source.get("name") or source_id, ak)
            if warning:
                source["lat"] = None
                source["lng"] = None
                source["coordinate_source"] = "baidu_geocoding_or_poi"
                source["geocode_status"] = "failed"
                source["exclude_from_simulation"] = True
                warnings.append(f"{source_id} 定位失败：{warning}")
                continue

            source["lat"] = location["lat"]
            source["lng"] = location["lng"]
            source["coordinate_source"] = "baidu_geocoding"
            source["geocode_status"] = "success"
            source["exclude_from_simulation"] = False
        source_routes = {} if refresh else dict(walk_times.get(source_id, {}))

        for cafeteria in cafeterias:
            if not refresh and _has_cached_route(source_routes, cafeteria["id"]):
                continue
            route, route_warning = _walking_route(location, cafeteria, ak)
            if route_warning:
                warnings.append(f"{source_id} 到 {cafeteria['id']} 路线失败：{route_warning}")
                continue
            source_routes[cafeteria["id"]] = route
            warnings = _without_route_warning(warnings, source_id, cafeteria["id"])
        if source_routes:
            walk_times[source_id] = source_routes
        time.sleep(0.2)

    residential["walk_times"] = walk_times
    residential["warnings"] = _clean_resolved_warnings(_dedupe(warnings), residential, cafeterias, walk_times)
    residential["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _write_json(RESIDENTIAL_PATH, residential)
    print(f"已更新 {RESIDENTIAL_PATH}")
    print(f"定位成功宿舍数：{len(walk_times)}")
    print("已复用现有成功坐标和路线；如需强制重新获取，请添加 --refresh。")
    if residential["warnings"]:
        print("warnings:")
        for warning in residential["warnings"]:
            print(f"- {warning}")
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _geocode(address: str, ak: str) -> tuple[dict[str, float], str | None]:
    params = {"address": address, "city": "北京市", "output": "json", "ak": ak}
    payload, warning = _request_baidu_json(GEOCODING_URL, params)
    if warning:
        return {}, warning
    if payload.get("status") != 0:
        return {}, str(payload.get("msg") or payload.get("message") or payload.get("status"))
    location = payload.get("result", {}).get("location", {})
    if "lat" not in location or "lng" not in location:
        return {}, "geocoding result missing location"
    return {"lat": float(location["lat"]), "lng": float(location["lng"])}, None


def _walking_route(origin: dict[str, float], cafeteria: dict[str, Any], ak: str) -> tuple[dict[str, Any], str | None]:
    params = {
        "origins": f"{origin['lat']},{origin['lng']}",
        "destinations": f"{cafeteria['lat']},{cafeteria['lng']}",
        "ak": ak,
    }
    payload, warning = _request_baidu_json(ROUTEMATRIX_URL, params)
    if warning:
        return {}, warning
    if payload.get("status") != 0:
        return {}, str(payload.get("message") or payload.get("status"))
    result = payload.get("result") or []
    if not result:
        return {}, "route matrix result empty"
    item = result[0]
    distance_m = int(item.get("distance", {}).get("value", 0))
    duration_s = int(item.get("duration", {}).get("value", 0))
    if distance_m <= 0 or duration_s <= 0:
        return {}, "route matrix distance or duration is empty"
    return {
        "distance_m": distance_m,
        "duration_s": duration_s,
        "duration_min": int(math.ceil(duration_s / 60)),
        "source": "baidu_walking_api",
    }, None


def _request_baidu_json(url: str, params: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    last_message = ""
    for attempt in range(3):
        payload, warning = _request_json(url, params)
        if warning:
            last_message = warning
        elif payload.get("status") == 0:
            return payload, None
        else:
            last_message = str(payload.get("msg") or payload.get("message") or payload.get("status"))
        if attempt < 2 and _is_retryable_baidu_message(last_message):
            time.sleep(1.0 + attempt)
            continue
        break
    return {}, last_message


def _is_retryable_baidu_message(message: str) -> bool:
    text = message.lower()
    return any(pattern in text for pattern in ("并发", "配额", "limit", "quota", "qps", "timeout", "timed out"))


def _has_cached_location(source: dict[str, Any]) -> bool:
    if source.get("geocode_status") != "success":
        return False
    try:
        float(source["lat"])
        float(source["lng"])
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _has_cached_route(routes: dict[str, Any], cafeteria_id: str) -> bool:
    route = routes.get(cafeteria_id)
    if not isinstance(route, dict):
        return False
    try:
        return int(route.get("distance_m", 0)) > 0 and int(route.get("duration_s", 0)) > 0
    except (TypeError, ValueError):
        return False


def _request_json(url: str, params: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    encoded = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{encoded}", headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode("utf-8")), None
        except Exception as exc:  # noqa: BLE001 - external API failures are reported as warnings
            last_error = exc
            time.sleep(0.5 + attempt * 0.5)
    return {}, f"{type(last_error).__name__}: {last_error}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _without_route_warning(warnings: list[str], source_id: str, cafeteria_id: str) -> list[str]:
    prefix = f"{source_id} 到 {cafeteria_id} 路线失败："
    return [warning for warning in warnings if not warning.startswith(prefix)]


def _clean_resolved_route_warnings(warnings: list[str], walk_times: dict[str, dict[str, Any]]) -> list[str]:
    cleaned = list(warnings)
    for source_id, routes in walk_times.items():
        for cafeteria_id, route in routes.items():
            if _has_cached_route(routes, cafeteria_id):
                cleaned = _without_route_warning(cleaned, source_id, cafeteria_id)
    return cleaned


def _clean_resolved_warnings(
    warnings: list[str],
    residential: dict[str, Any],
    cafeterias: list[dict[str, Any]],
    walk_times: dict[str, dict[str, Any]],
) -> list[str]:
    cleaned = _clean_resolved_route_warnings(warnings, walk_times)
    if _api_data_complete(residential, cafeterias, walk_times):
        cleaned = [
            warning
            for warning in cleaned
            if not warning.startswith("BAIDU_MAP_AK was not available")
        ]
    return cleaned


def _api_data_complete(
    residential: dict[str, Any],
    cafeterias: list[dict[str, Any]],
    walk_times: dict[str, dict[str, Any]],
) -> bool:
    cafeteria_ids = [cafeteria["id"] for cafeteria in cafeterias]
    active_sources = [
        source
        for source in residential.get("residential_areas", [])
        if not source.get("exclude_from_simulation")
    ]
    if not active_sources:
        return False
    for source in active_sources:
        source_id = source.get("id", "")
        if not _has_cached_location(source):
            return False
        routes = walk_times.get(source_id, {})
        if any(not _has_cached_route(routes, cafeteria_id) for cafeteria_id in cafeteria_ids):
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
