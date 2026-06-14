# 文件说明：宿舍需求端到端测试，覆盖数据读取、混合到达表和无百度 AK 的脚本行为。

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.campus import (  # noqa: E402
    CampusBuildingDemandData,
    CampusFloorDemandData,
    CampusPopulationPoolData,
    CampusResidentialDemandData,
    build_mixed_campus_arrival_schedule,
    known_cafeteria_ids,
    load_residential_sources,
)


class ResidentialDemandTests(unittest.TestCase):
    def test_residential_source_data_can_be_loaded(self):
        payload = load_residential_sources()

        self.assertIn("residential_areas", payload)
        self.assertGreater(len(payload["residential_areas"]), 0)
        self.assertIn("walk_times", payload)

    def test_east_dorms_and_main_dorms_are_not_sources(self):
        payload = load_residential_sources()
        source_ids = {source["id"] for source in payload["residential_areas"]}

        self.assertNotIn("east_dorms", source_ids)
        self.assertNotIn("main_dorms", source_ids)

    def test_each_residential_source_has_weight_confidence_and_notes(self):
        payload = load_residential_sources()

        for source in payload["residential_areas"]:
            for field in ("id", "name", "capacity_weight", "confidence", "source_notes"):
                self.assertIn(field, source)

    def test_residential_walk_times_only_reference_known_cafeterias(self):
        payload = load_residential_sources()
        known = known_cafeteria_ids()

        for source_id, routes in payload["walk_times"].items():
            self.assertTrue(set(routes).issubset(known), source_id)

    def test_residential_source_can_generate_nonempty_arrival_schedule(self):
        payload = load_residential_sources()
        source_id = next(
            source["id"]
            for source in payload["residential_areas"]
            if not source.get("exclude_from_simulation") and source["id"] in payload["walk_times"]
        )

        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[CampusResidentialDemandData(source_id, population_override=50)],
            population_pool=None,
            meal_period="breakfast",
            seed=21,
            force_target=True,
        )

        self.assertGreater(sum(result["schedule"].values()), 0)
        self.assertGreater(result["breakdown"]["residential_arrived"], 0)

    def test_breakfast_residential_window_arrives_more_than_teaching(self):
        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[],
            population_pool=CampusPopulationPoolData(
                enabled=True,
                meal_period="breakfast",
                total_population_pool=200,
                meal_participation_rate=0.6,
            ),
            meal_period="breakfast",
            seed=22,
            force_target=True,
        )

        self.assertGreater(result["breakdown"]["residential_arrived"], result["breakdown"]["teaching_arrived"])

    def test_lunch_teaching_event_can_dominate_residential_window(self):
        building = CampusBuildingDemandData(
            building_id="no9",
            dismissal_minute=700,
            release_ratio=1.0,
            floors=[CampusFloorDemandData(floor=1, count=120)],
        )

        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[building],
            residential_sources=[],
            population_pool=CampusPopulationPoolData(
                enabled=True,
                meal_period="lunch",
                total_population_pool=160,
                meal_participation_rate=0.75,
            ),
            meal_period="lunch",
            seed=23,
            force_target=True,
        )

        self.assertGreaterEqual(result["breakdown"]["teaching_arrived"], result["breakdown"]["residential_arrived"])

    def test_missing_walk_time_returns_warning_without_crashing(self):
        residential_data = {
            "residential_areas": [
                {"id": "jiayuan_a", "name": "嘉园A座", "campus_area": "嘉园片区", "capacity_weight": 1, "exclude_from_simulation": False}
            ],
            "walk_times": {},
        }

        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[CampusResidentialDemandData("jiayuan_a", population_override=20)],
            population_pool=None,
            meal_period="breakfast",
            seed=24,
            residential_data=residential_data,
        )

        self.assertEqual(result["breakdown"]["residential_arrived"], 0)
        self.assertTrue(result["breakdown"]["warnings"])

    def test_fixed_seed_mixed_schedule_is_reproducible(self):
        kwargs = dict(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[CampusResidentialDemandData("jiayuan_a", population_override=50)],
            population_pool=None,
            meal_period="weekend",
            seed=25,
            force_target=True,
        )

        first = build_mixed_campus_arrival_schedule(**kwargs)
        second = build_mixed_campus_arrival_schedule(**kwargs)

        self.assertEqual(first["schedule"], second["schedule"])
        self.assertEqual(first["breakdown"]["residential_by_source"], second["breakdown"]["residential_by_source"])

    def test_generate_residential_walk_times_without_baidu_key_fails_cleanly(self):
        env = os.environ.copy()
        env.pop("BAIDU_MAP_AK", None)

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_residential_walk_times.py")],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("缺少 BAIDU_MAP_AK，请先设置百度地图 API key。", result.stderr + result.stdout)
        self.assertNotIn("api_key", (result.stderr + result.stdout).lower())

    def test_generate_script_reuses_cached_successful_geocode_and_routes(self):
        import scripts.generate_residential_walk_times as generator

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            campus_path = tmp_path / "campus_walk_times.json"
            residential_path = tmp_path / "campus_residential_sources.json"
            campus_path.write_text(json.dumps({
                "locations": {
                    "cafeterias": [
                        {"id": "xuesi", "name": "学四食堂", "lat": 39.955, "lng": 116.35}
                    ]
                }
            }, ensure_ascii=False), encoding="utf-8")
            residential_path.write_text(json.dumps({
                "residential_areas": [
                    {
                        "id": "jiayuan_a",
                        "name": "嘉园A座",
                        "address_query": "北京交通大学 嘉园A座",
                        "lat": 39.95,
                        "lng": 116.34,
                        "geocode_status": "success",
                        "exclude_from_simulation": False,
                    }
                ],
                "walk_times": {
                    "jiayuan_a": {
                        "xuesi": {"distance_m": 100, "duration_s": 80, "duration_min": 2, "source": "baidu_walking_api"}
                    }
                },
                "warnings": [
                    "BAIDU_MAP_AK was not available when this offline seed file was created; run scripts/generate_residential_walk_times.py to replace seed coordinates and walk times with Baidu Maps API results.",
                    "jiayuan_a 到 xuesi 路线失败：old warning",
                    "jiayuan_a 到 minghu 路线失败：old warning",
                ],
            }, ensure_ascii=False), encoding="utf-8")

            original_paths = (generator.CAMPUS_WALK_TIMES_PATH, generator.RESIDENTIAL_PATH)
            original_env = os.environ.get("BAIDU_MAP_AK")
            original_geocode = generator._geocode
            original_route = generator._walking_route
            calls = []

            def fail_geocode(_address, _ak):
                calls.append("geocode")
                raise AssertionError("cached geocode should be reused")

            def fail_route(_origin, _cafeteria, _ak):
                calls.append("route")
                raise AssertionError("cached route should be reused")

            generator.CAMPUS_WALK_TIMES_PATH = campus_path
            generator.RESIDENTIAL_PATH = residential_path
            generator._geocode = fail_geocode
            generator._walking_route = fail_route
            os.environ["BAIDU_MAP_AK"] = "test-ak"
            try:
                with redirect_stdout(io.StringIO()):
                    exit_code = generator.main()
            finally:
                generator.CAMPUS_WALK_TIMES_PATH, generator.RESIDENTIAL_PATH = original_paths
                generator._geocode = original_geocode
                generator._walking_route = original_route
                if original_env is None:
                    os.environ.pop("BAIDU_MAP_AK", None)
                else:
                    os.environ["BAIDU_MAP_AK"] = original_env

            payload = json.loads(residential_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(calls, [])
            self.assertEqual(payload["walk_times"]["jiayuan_a"]["xuesi"]["duration_s"], 80)

    def test_generate_script_uses_cached_coordinates_and_only_fetches_missing_routes(self):
        import scripts.generate_residential_walk_times as generator

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            campus_path = tmp_path / "campus_walk_times.json"
            residential_path = tmp_path / "campus_residential_sources.json"
            campus_path.write_text(json.dumps({
                "locations": {
                    "cafeterias": [
                        {"id": "xuesi", "name": "学四食堂", "lat": 39.955, "lng": 116.35},
                        {"id": "minghu", "name": "明湖餐厅", "lat": 39.958, "lng": 116.349},
                    ]
                }
            }, ensure_ascii=False), encoding="utf-8")
            residential_path.write_text(json.dumps({
                "residential_areas": [
                    {
                        "id": "jiayuan_a",
                        "name": "嘉园A座",
                        "address_query": "北京交通大学 嘉园A座",
                        "lat": 39.95,
                        "lng": 116.34,
                        "geocode_status": "success",
                        "exclude_from_simulation": False,
                    }
                ],
                "walk_times": {
                    "jiayuan_a": {
                        "xuesi": {"distance_m": 100, "duration_s": 80, "duration_min": 2, "source": "baidu_walking_api"}
                    }
                },
                "warnings": [
                    "BAIDU_MAP_AK was not available when this offline seed file was created; run scripts/generate_residential_walk_times.py to replace seed coordinates and walk times with Baidu Maps API results.",
                    "jiayuan_a 到 xuesi 路线失败：old warning",
                    "jiayuan_a 到 minghu 路线失败：old warning",
                ],
            }, ensure_ascii=False), encoding="utf-8")

            original_paths = (generator.CAMPUS_WALK_TIMES_PATH, generator.RESIDENTIAL_PATH)
            original_env = os.environ.get("BAIDU_MAP_AK")
            original_geocode = generator._geocode
            original_route = generator._walking_route
            route_calls = []

            def fail_geocode(_address, _ak):
                raise AssertionError("cached coordinates should avoid geocoding")

            def fake_route(_origin, cafeteria, _ak):
                route_calls.append(cafeteria["id"])
                return {"distance_m": 200, "duration_s": 160, "duration_min": 3, "source": "baidu_walking_api"}, None

            generator.CAMPUS_WALK_TIMES_PATH = campus_path
            generator.RESIDENTIAL_PATH = residential_path
            generator._geocode = fail_geocode
            generator._walking_route = fake_route
            os.environ["BAIDU_MAP_AK"] = "test-ak"
            try:
                with redirect_stdout(io.StringIO()):
                    exit_code = generator.main()
            finally:
                generator.CAMPUS_WALK_TIMES_PATH, generator.RESIDENTIAL_PATH = original_paths
                generator._geocode = original_geocode
                generator._walking_route = original_route
                if original_env is None:
                    os.environ.pop("BAIDU_MAP_AK", None)
                else:
                    os.environ["BAIDU_MAP_AK"] = original_env

            payload = json.loads(residential_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(route_calls, ["minghu"])
            self.assertEqual(payload["walk_times"]["jiayuan_a"]["xuesi"]["duration_s"], 80)
            self.assertEqual(payload["walk_times"]["jiayuan_a"]["minghu"]["duration_s"], 160)
            self.assertFalse(any("路线失败" in warning for warning in payload["warnings"]))
            self.assertFalse(any("BAIDU_MAP_AK was not available" in warning for warning in payload["warnings"]))

    def test_walking_route_retries_baidu_quota_status_before_success(self):
        import scripts.generate_residential_walk_times as generator

        original_request = generator._request_json
        original_sleep = generator.time.sleep
        responses = [
            ({"status": 302, "message": "当前并发量已经超过约定并发配额，限制访问"}, None),
            ({
                "status": 0,
                "result": [
                    {
                        "distance": {"value": 300},
                        "duration": {"value": 240},
                    }
                ],
            }, None),
        ]

        def fake_request(_url, _params):
            return responses.pop(0)

        generator._request_json = fake_request
        generator.time.sleep = lambda _seconds: None
        try:
            route, warning = generator._walking_route(
                {"lat": 39.95, "lng": 116.34},
                {"id": "xuesi", "lat": 39.955, "lng": 116.35},
                "test-ak",
            )
        finally:
            generator._request_json = original_request
            generator.time.sleep = original_sleep

        self.assertIsNone(warning)
        self.assertEqual(route["distance_m"], 300)
        self.assertEqual(route["duration_s"], 240)
