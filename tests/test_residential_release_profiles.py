# 文件说明：宿舍时间窗口释放测试，验证早餐/午餐/晚餐/周末 profile 与教学楼事件释放分离。

import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.campus import (  # noqa: E402
    CampusBuildingDemandData,
    CampusFloorDemandData,
    CampusPopulationPoolData,
    CampusResidentialDemandData,
    ResidentialReleaseProfile,
    build_mixed_campus_arrival_schedule,
    default_residential_release_profile,
    sample_residential_departure_minute,
)


def _residential_data(duration_a: int = 60, duration_b: int = 600):
    return {
        "residential_areas": [
            {"id": "jiayuan_a", "name": "嘉园A座", "campus_area": "嘉园片区", "capacity_weight": 1, "exclude_from_simulation": False},
            {"id": "dorm_12", "name": "12号宿舍楼", "campus_area": "主校区编号宿舍楼", "capacity_weight": 1, "exclude_from_simulation": False},
        ],
        "walk_times": {
            "jiayuan_a": {"xuesi": {"distance_m": duration_a, "duration_s": duration_a, "duration_min": max(1, duration_a // 60)}},
            "dorm_12": {"xuesi": {"distance_m": duration_b, "duration_s": duration_b, "duration_min": max(1, duration_b // 60)}},
        },
    }


class ResidentialReleaseProfileTests(unittest.TestCase):
    def test_breakfast_profile_has_expected_window_and_peak(self):
        profile = default_residential_release_profile("breakfast")

        self.assertEqual(profile.start_minute, 420)
        self.assertEqual(profile.end_minute, 510)
        self.assertEqual(profile.peak_minute, 465)
        self.assertEqual(profile.distribution, "triangular")

    def test_dinner_profile_is_later_than_lunch(self):
        lunch = default_residential_release_profile("lunch")
        dinner = default_residential_release_profile("dinner")

        self.assertGreater(dinner.start_minute, lunch.start_minute)
        self.assertGreater(dinner.end_minute, lunch.end_minute)

    def test_sampled_departure_minute_is_always_inside_profile_window(self):
        rng = random.Random(3)
        profile = default_residential_release_profile("weekend")

        samples = [sample_residential_departure_minute(profile, rng) for _ in range(200)]

        self.assertGreaterEqual(min(samples), profile.start_minute)
        self.assertLessEqual(max(samples), profile.end_minute)

    def test_triangular_sampling_is_reproducible_for_fixed_seed(self):
        profile = default_residential_release_profile("lunch")
        first_rng = random.Random(8)
        second_rng = random.Random(8)

        first = [sample_residential_departure_minute(profile, first_rng) for _ in range(20)]
        second = [sample_residential_departure_minute(profile, second_rng) for _ in range(20)]

        self.assertEqual(first, second)

    def test_breakfast_residential_participation_rate_is_lower_than_dinner(self):
        breakfast = default_residential_release_profile("breakfast")
        dinner = default_residential_release_profile("dinner")

        self.assertLess(breakfast.residential_participation_rate, dinner.residential_participation_rate)

    def test_teaching_release_uses_dismissal_minute_not_residential_window(self):
        building = CampusBuildingDemandData(
            building_id="no9",
            dismissal_minute=660,
            release_ratio=1.0,
            floors=[CampusFloorDemandData(floor=1, count=20)],
        )

        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[building],
            residential_sources=[],
            population_pool=None,
            meal_period="breakfast",
            seed=4,
            force_target=True,
            residential_data=_residential_data(),
        )

        self.assertGreaterEqual(min(result["schedule"]), 660)
        self.assertEqual(result["breakdown"]["teaching_release_mode"], "event")
        self.assertEqual(result["breakdown"]["residential_release_mode"], "time_window")

    def test_residential_release_spreads_across_multiple_minutes(self):
        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[CampusResidentialDemandData("jiayuan_a", population_override=160)],
            population_pool=None,
            meal_period="lunch",
            seed=11,
            force_target=True,
            residential_data=_residential_data(),
        )

        residential_minutes = result["breakdown"]["residential_arrival_minutes_by_source"]["jiayuan_a"]
        self.assertGreater(len(set(residential_minutes)), 10)

    def test_breakfast_residential_arrivals_are_near_breakfast_window(self):
        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[CampusResidentialDemandData("jiayuan_a", population_override=80)],
            population_pool=None,
            meal_period="breakfast",
            seed=13,
            force_target=True,
            residential_data=_residential_data(duration_a=180),
        )

        minutes = result["breakdown"]["residential_arrival_minutes_by_source"]["jiayuan_a"]
        self.assertGreaterEqual(min(minutes), 420)
        self.assertLessEqual(max(minutes), 540)

    def test_lunch_breakdown_reports_release_modes(self):
        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[CampusResidentialDemandData("jiayuan_a", population_override=10)],
            population_pool=None,
            meal_period="lunch",
            seed=2,
            force_target=True,
            residential_data=_residential_data(),
        )

        self.assertEqual(result["breakdown"]["teaching_release_mode"], "event")
        self.assertEqual(result["breakdown"]["residential_release_mode"], "time_window")

    def test_custom_residential_release_profile_overrides_default_window_and_rate(self):
        profile = ResidentialReleaseProfile("lunch", 700, 710, 705, "uniform", 0.25)

        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[],
            population_pool=CampusPopulationPoolData(
                enabled=True,
                meal_period="lunch",
                total_population_pool=100,
                meal_participation_rate=1.0,
            ),
            meal_period="lunch",
            seed=31,
            force_target=True,
            residential_data=_residential_data(duration_a=60, duration_b=60),
            residential_release_profile=profile,
        )

        self.assertEqual(result["breakdown"]["residential_release_profile"]["start_minute"], 700)
        self.assertEqual(result["breakdown"]["residential_release_profile"]["end_minute"], 710)
        self.assertEqual(result["breakdown"]["residential_release_profile"]["residential_participation_rate"], 0.25)
        self.assertEqual(result["breakdown"]["residential_population"], 25)

    def test_csv_fields_include_release_profile_columns(self):
        from scripts.generate_bjtu_scenarios import RESIDENTIAL_SCENARIO_FIELDS

        for field in (
            "residential_release_start_minute",
            "residential_release_end_minute",
            "residential_release_peak_minute",
            "residential_release_distribution",
            "residential_participation_rate",
        ):
            self.assertIn(field, RESIDENTIAL_SCENARIO_FIELDS)

    def test_generated_scenarios_start_at_meal_release_clock(self):
        from scripts import generate_bjtu_scenarios

        captured = {}
        original_run_simulation = generate_bjtu_scenarios.run_simulation

        def fake_run_simulation(config):
            captured["config"] = config
            return SimpleNamespace(
                metrics=SimpleNamespace(
                    avg_wait=0,
                    avg_queue_wait=0,
                    avg_seat_wait=0,
                    peak_queue=0,
                    peak_waiting_for_seat=0,
                    window_utilization=0,
                    seat_utilization=0,
                    bottleneck_type="整体均衡",
                    fragmented_seats=0,
                    avg_walking_time=0,
                    movement_conflict_count=0,
                    avg_stuck_ticks=0,
                    max_density=0,
                )
            )

        scenario = {
            "scenario": "lunch_test",
            "meal_period": "lunch",
            "source_mix": "teaching_event_plus_residential_window",
            "population_pool": CampusPopulationPoolData(
                enabled=True,
                meal_period="lunch",
                total_population_pool=100,
                meal_participation_rate=1.0,
            ),
            "buildings": [
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=700,
                    floors=[CampusFloorDemandData(floor=1, count=10)],
                )
            ],
            "num_windows": 2,
            "num_seats": 40,
            "seed": 101,
        }

        generate_bjtu_scenarios.run_simulation = fake_run_simulation
        try:
            generate_bjtu_scenarios._run_row(
                scenario,
                cafeteria_id="xuesi",
                cafeteria_name="学思食堂",
                movement_model="path",
                simulation_scale=1.0,
            )
        finally:
            generate_bjtu_scenarios.run_simulation = original_run_simulation

        self.assertEqual(
            captured["config"].simulation_start_minute,
            default_residential_release_profile("lunch").start_minute,
        )

    def test_multiple_sources_arrive_at_different_times_when_walk_times_differ(self):
        result = build_mixed_campus_arrival_schedule(
            cafeteria_id="xuesi",
            buildings=[],
            residential_sources=[
                CampusResidentialDemandData("jiayuan_a", population_override=40),
                CampusResidentialDemandData("dorm_12", population_override=40),
            ],
            population_pool=None,
            meal_period="weekend",
            seed=17,
            force_target=True,
            residential_data=_residential_data(duration_a=60, duration_b=900),
        )

        minutes = result["breakdown"]["residential_arrival_minutes_by_source"]
        self.assertLess(min(minutes["jiayuan_a"]), min(minutes["dorm_12"]))
