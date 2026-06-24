# 文件说明：住宅来源数据测试，确保宿舍 source 是扁平、独立、可路径计算的真实点位。

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.campus import (  # noqa: E402
    CampusPopulationPoolData,
    CampusResidentialDemandData,
    build_mixed_campus_arrival_schedule,
    estimate_residential_population_from_residual,
    known_cafeteria_ids,
)


DATA_PATH = ROOT / "backend" / "app" / "data" / "campus_residential_sources.json"


def _load_payload():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


class ResidentialSourcesFlatTests(unittest.TestCase):
    def test_residential_sources_do_not_use_forbidden_aggregate_ids_or_group_fields(self):
        payload = _load_payload()
        source_ids = {item["id"] for item in payload["residential_areas"]}
        payload_text = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("main_dorms", source_ids)
        self.assertNotIn("east_dorms", source_ids)
        self.assertNotIn('"main_dorms"', payload_text)
        self.assertNotIn('"east_dorms"', payload_text)
        for source in payload["residential_areas"]:
            self.assertNotIn("parent_id", source)
            self.assertNotIn("children", source)
            self.assertNotEqual(source.get("type"), "group")

    def test_participating_sources_have_required_fields_and_individual_walk_times(self):
        payload = _load_payload()
        cafeteria_ids = known_cafeteria_ids()
        walk_times = payload.get("walk_times", {})

        for source in payload["residential_areas"]:
            for field in ("id", "name", "address_query", "campus_area"):
                self.assertTrue(source.get(field), f"{source.get('id')} missing {field}")
            if source.get("exclude_from_simulation"):
                continue
            self.assertGreater(float(source.get("capacity_weight", 0)), 0)
            self.assertIn(source["id"], walk_times)
            self.assertEqual(set(walk_times[source["id"]]), cafeteria_ids)

    def test_invalid_xueyuan_1_source_is_removed(self):
        payload = _load_payload()
        source_ids = {item["id"] for item in payload["residential_areas"]}

        self.assertNotIn("xueyuan_1", source_ids)
        self.assertNotIn("xueyuan_1", payload.get("walk_times", {}))
        payload_text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("学苑1号楼", payload_text)
        self.assertNotIn("北京交通大学 学苑1号楼", payload_text)

    def test_residential_by_source_total_matches_residential_population(self):
        sources = [
            {"id": "jiayuan_a", "campus_area": "嘉园片区", "capacity_weight": 1, "exclude_from_simulation": False},
            {"id": "jiayuan_b", "campus_area": "嘉园片区", "capacity_weight": 2, "exclude_from_simulation": False},
            {"id": "dorm_12", "campus_area": "主校区编号宿舍楼", "capacity_weight": 3, "exclude_from_simulation": False},
        ]

        result = estimate_residential_population_from_residual(
            total_population_pool=1000,
            meal_participation_rate=0.8,
            teaching_population=200,
            other_known_population=50,
            residential_areas=sources,
            residential_participation_rate=0.5,
        )

        self.assertLessEqual(
            abs(sum(result["residential_by_source"].values()) - result["residential_population"]),
            1,
        )
        self.assertEqual(set(result["residential_by_area"]), {"嘉园片区", "主校区编号宿舍楼"})

    def test_schedule_generation_uses_each_source_own_walk_time(self):
        residential_data = {
            "residential_areas": [
                {"id": "jiayuan_a", "name": "嘉园A座", "campus_area": "嘉园片区", "capacity_weight": 1, "exclude_from_simulation": False},
                {"id": "dorm_12", "name": "12号宿舍楼", "campus_area": "主校区编号宿舍楼", "capacity_weight": 1, "exclude_from_simulation": False},
            ],
            "walk_times": {
                "jiayuan_a": {"xuesi": {"distance_m": 120, "duration_s": 60, "duration_min": 1}},
                "dorm_12": {"xuesi": {"distance_m": 1200, "duration_s": 900, "duration_min": 15}},
            },
        }

        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[
                CampusResidentialDemandData(residential_id="jiayuan_a", population_override=20),
                CampusResidentialDemandData(residential_id="dorm_12", population_override=20),
            ],
            population_pool=None,
            meal_period="breakfast",
            seed=7,
            force_target=True,
            residential_data=residential_data,
        )

        minutes_by_source = result["breakdown"]["residential_arrival_minutes_by_source"]
        self.assertLess(min(minutes_by_source["jiayuan_a"]), min(minutes_by_source["dorm_12"]))
        self.assertEqual(
            result["breakdown"]["residential_source_walk_times"]["jiayuan_a"]["xuesi"]["duration_s"],
            60,
        )
        self.assertEqual(
            result["breakdown"]["residential_source_walk_times"]["dorm_12"]["xuesi"]["duration_s"],
            900,
        )
