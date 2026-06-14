# 文件说明：残差宿舍人口模型测试，验证宿舍人数只由总池扣除教学楼等来源后分配。

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.campus import (  # noqa: E402
    CampusPopulationPoolData,
    CampusResidentialDemandData,
    build_mixed_campus_arrival_schedule,
    estimate_residential_population_from_residual,
)


SOURCES = [
    {"id": "jiayuan_a", "name": "嘉园A座", "campus_area": "嘉园片区", "capacity_weight": 1, "exclude_from_simulation": False},
    {"id": "jiayuan_b", "name": "嘉园B座", "campus_area": "嘉园片区", "capacity_weight": 2, "exclude_from_simulation": False},
    {"id": "dorm_12", "name": "12号宿舍楼", "campus_area": "主校区编号宿舍楼", "capacity_weight": 3, "exclude_from_simulation": False},
]


class ResidualResidentialPopulationTests(unittest.TestCase):
    def test_residual_is_effective_total_minus_teaching_and_other(self):
        result = estimate_residential_population_from_residual(
            total_population_pool=1000,
            meal_participation_rate=0.75,
            teaching_population=200,
            other_known_population=50,
            residential_areas=SOURCES,
            residential_participation_rate=0.5,
        )

        self.assertEqual(result["effective_meal_population"], 750)
        self.assertEqual(result["residual_raw"], 500)
        self.assertEqual(result["residential_population"], 250)

    def test_teaching_population_above_effective_total_clamps_residential_to_zero(self):
        result = estimate_residential_population_from_residual(
            total_population_pool=1000,
            meal_participation_rate=0.5,
            teaching_population=800,
            other_known_population=0,
            residential_areas=SOURCES,
        )

        self.assertEqual(result["residual_raw"], 0)
        self.assertEqual(result["residential_population"], 0)
        self.assertEqual(sum(result["residential_by_source"].values()), 0)

    def test_residual_allocates_by_capacity_weight_with_small_rounding_error(self):
        result = estimate_residential_population_from_residual(
            total_population_pool=1200,
            meal_participation_rate=1.0,
            teaching_population=0,
            other_known_population=0,
            residential_areas=SOURCES,
        )

        self.assertEqual(result["residential_by_source"]["jiayuan_a"], 200)
        self.assertEqual(result["residential_by_source"]["jiayuan_b"], 400)
        self.assertEqual(result["residential_by_source"]["dorm_12"], 600)
        self.assertLessEqual(
            abs(sum(result["residential_by_source"].values()) - result["residential_population"]),
            1,
        )

    def test_population_override_replaces_one_source_and_is_marked(self):
        result = estimate_residential_population_from_residual(
            total_population_pool=600,
            meal_participation_rate=1.0,
            teaching_population=0,
            other_known_population=0,
            residential_areas=SOURCES,
            overrides={"jiayuan_b": 120},
        )

        self.assertEqual(result["residential_by_source"]["jiayuan_b"], 120)
        self.assertIn("jiayuan_b", result["residential_overrides"])
        self.assertTrue(result["residential_overrides"]["jiayuan_b"]["overridden"])
        self.assertLessEqual(
            abs(sum(result["residential_by_source"].values()) - result["residential_population"]),
            1,
        )

    def test_forbidden_aggregate_ids_are_excluded_from_allocation(self):
        sources = SOURCES + [
            {"id": "main_dorms", "campus_area": "聚合", "capacity_weight": 999, "exclude_from_simulation": False},
            {"id": "east_dorms", "campus_area": "聚合", "capacity_weight": 999, "exclude_from_simulation": False},
        ]

        result = estimate_residential_population_from_residual(
            total_population_pool=600,
            meal_participation_rate=1.0,
            teaching_population=0,
            other_known_population=0,
            residential_areas=sources,
        )

        self.assertNotIn("main_dorms", result["residential_by_source"])
        self.assertNotIn("east_dorms", result["residential_by_source"])

    def test_allocation_is_reproducible_without_randomness(self):
        first = estimate_residential_population_from_residual(1001, 0.9, 123, 17, SOURCES, 0.65)
        second = estimate_residential_population_from_residual(1001, 0.9, 123, 17, SOURCES, 0.65)

        self.assertEqual(first, second)

    def test_missing_residential_walk_time_warns_without_crashing(self):
        residential_data = {
            "residential_areas": SOURCES[:1],
            "walk_times": {"jiayuan_a": {}},
        }

        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[CampusResidentialDemandData("jiayuan_a", population_override=10)],
            population_pool=None,
            meal_period="breakfast",
            seed=1,
            residential_data=residential_data,
        )

        self.assertEqual(result["breakdown"]["residential_arrived"], 0)
        self.assertTrue(any("缺少 jiayuan_a 到 xuesi 的宿舍步行时间" in item for item in result["breakdown"]["warnings"]))

    def test_scenario_csv_fields_include_residential_breakdown_and_no_main_dorms_population(self):
        from scripts.generate_bjtu_scenarios import RESIDENTIAL_SCENARIO_FIELDS

        required = {
            "effective_meal_population",
            "teaching_population",
            "residential_population",
            "residential_by_source_json",
            "residential_by_area_json",
        }

        self.assertTrue(required.issubset(set(RESIDENTIAL_SCENARIO_FIELDS)))
        self.assertNotIn("main_dorms_population", RESIDENTIAL_SCENARIO_FIELDS)

        with tempfile.NamedTemporaryFile("w+", newline="", delete=False, encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=RESIDENTIAL_SCENARIO_FIELDS)
            writer.writeheader()
            path = handle.name
        try:
            with open(path, newline="", encoding="utf-8") as handle:
                header = next(csv.reader(handle))
            self.assertIn("residential_by_source_json", header)
            self.assertNotIn("main_dorms_population", header)
        finally:
            os.unlink(path)

    def test_scenario_simulation_scale_allows_small_development_runs(self):
        from scripts.generate_bjtu_scenarios import _simulation_scale

        original = os.environ.get("BJTU_SCENARIO_SIMULATION_SCALE")
        os.environ["BJTU_SCENARIO_SIMULATION_SCALE"] = "0.003"
        try:
            self.assertEqual(_simulation_scale(), 0.003)
        finally:
            if original is None:
                os.environ.pop("BJTU_SCENARIO_SIMULATION_SCALE", None)
            else:
                os.environ["BJTU_SCENARIO_SIMULATION_SCALE"] = original
