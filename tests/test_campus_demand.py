# 文件说明：校园需求测试：验证校园人数、楼层到达和实时数据降级逻辑。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.campus as campus_module
from app.campus import (
    build_campus_arrival_schedule,
    cafeteria_choice_probabilities,
    fetch_live_floor_occupancy,
    generate_random_floor_occupancy,
    parse_classroom_capacity_payload,
)
from app.simulation import (
    CampusBuildingDemandData,
    CampusDemandConfigData,
    CampusFloorDemandData,
    SimulationConfigData,
    run_simulation,
)


# 讲解注释：CampusDemandTests 处理校园教学楼、食堂或到达数据。
class CampusDemandTests(unittest.TestCase):
    # 讲解注释：setUp() 封装本文件中的一个独立处理步骤。
    def setUp(self):
        campus_module._LIVE_OCCUPANCY_CACHE.clear()

    # 讲解注释：tearDown() 封装本文件中的一个独立处理步骤。
    def tearDown(self):
        campus_module._LIVE_OCCUPANCY_CACHE.clear()

    # 讲解注释：test_nearest_cafeteria_has_highest_choice_probability() 验证对应业务场景或回归行为。
    def test_nearest_cafeteria_has_highest_choice_probability(self):
        probabilities = cafeteria_choice_probabilities("no9")

        self.assertGreater(probabilities["xuesi"], probabilities["minghu"])
        self.assertGreater(probabilities["xuesi"], probabilities["xuehuo"])
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=6)

    # 讲解注释：test_upper_floor_arrivals_are_not_earlier_than_lower_floor() 计算或生成学生到达相关数据。
    def test_upper_floor_arrivals_are_not_earlier_than_lower_floor(self):
        lower = CampusBuildingDemandData(
            building_id="no9",
            dismissal_minute=0,
            release_ratio=1.0,
            floors=[CampusFloorDemandData(floor=1, count=10)],
        )
        upper = CampusBuildingDemandData(
            building_id="no9",
            dismissal_minute=0,
            release_ratio=1.0,
            floors=[CampusFloorDemandData(floor=6, count=10)],
        )

        lower_schedule = build_campus_arrival_schedule("xuesi", [lower], seed=1, force_target=True)
        upper_schedule = build_campus_arrival_schedule("xuesi", [upper], seed=1, force_target=True)

        self.assertLessEqual(min(lower_schedule), min(upper_schedule))
        self.assertLess(sum(minute * count for minute, count in lower_schedule.items()), sum(minute * count for minute, count in upper_schedule.items()))

    # 讲解注释：test_simulation_uses_campus_schedule_instead_of_poisson_arrivals() 处理校园教学楼、食堂或到达数据。
    def test_simulation_uses_campus_schedule_instead_of_poisson_arrivals(self):
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=12)],
                )
            ],
        )
        config = SimulationConfigData(
            arrival_rate=99.0,
            service_time_mean=1.0,
            dining_time_mean=1.0,
            duration_min=5,
            seed=4,
            campus_demand=campus,
        )

        expected_arrivals = sum(build_campus_arrival_schedule("xuesi", campus.buildings, seed=4).values())
        result = run_simulation(config)

        self.assertEqual(result.metrics.total_arrived, expected_arrivals)
        self.assertGreater(result.metrics.total_arrived, 0)
        self.assertLess(result.metrics.total_arrived, 99)

    # 讲解注释：test_campus_simulation_does_not_wait_for_manual_arrival_duration() 处理校园教学楼、食堂或到达数据。
    def test_campus_simulation_does_not_wait_for_manual_arrival_duration(self):
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=4)],
                )
            ],
        )
        config = SimulationConfigData(
            num_windows=4,
            num_seats=20,
            arrival_rate=99.0,
            service_time_mean=1.0,
            dining_time_mean=1.0,
            duration_min=120,
            seed=6,
            campus_demand=campus,
        )

        result = run_simulation(config)

        self.assertGreater(result.metrics.total_arrived, 0)
        self.assertEqual(result.metrics.total_left, result.metrics.total_arrived)
        self.assertLess(len(result.records), 120)

    # 讲解注释：test_random_floor_occupancy_is_reproducible_and_floor_level() 处理楼层人数占用数据。
    def test_random_floor_occupancy_is_reproducible_and_floor_level(self):
        first = generate_random_floor_occupancy(["no9"], seed=9)
        second = generate_random_floor_occupancy(["no9"], seed=9)

        self.assertEqual(first, second)
        self.assertEqual(first[0]["building_id"], "no9")
        self.assertGreater(len(first[0]["floors"]), 1)
        self.assertTrue(all("floor" in item and "count" in item for item in first[0]["floors"]))

    # 讲解注释：test_classroom_payload_is_aggregated_by_floor() 验证对应业务场景或回归行为。
    def test_classroom_payload_is_aggregated_by_floor(self):
        payload = {
            "time": ["2026-05-03 11:00", "2026-05-03 11:10"],
            "data": [
                ["九教2101", "", 20, 40],
                ["九教2201", "", "30", "50"],
                ["九教6302", "", 10, 20],
                ["九教6401", "", 60, 60],
            ],
        }

        result = parse_classroom_capacity_payload("no9", "第九教学楼", payload)

        self.assertEqual(result["building_id"], "no9")
        self.assertEqual(result["total_used"], 60)
        self.assertEqual(result["floors"], [
            {"floor": 1, "count": 20, "capacity": 40},
            {"floor": 2, "count": 30, "capacity": 50},
            {"floor": 3, "count": 10, "capacity": 20},
        ])

    # 讲解注释：test_classroom_rows_at_or_above_capacity_are_unreadable_not_full() 验证对应业务场景或回归行为。
    def test_classroom_rows_at_or_above_capacity_are_unreadable_not_full(self):
        payload = {
            "time": ["2026-05-03 11:00", "2026-05-03 11:10"],
            "data": [
                ["SY101", 1.11, 1, 90],
                ["SY108", 100.0, 253, 253],
                ["SY201", 0.9, 1, 110],
                ["SY209", 100.0, 253, 253],
            ],
        }

        result = parse_classroom_capacity_payload("siyuan", "思源楼", payload)

        self.assertEqual(result["total_used"], 2)
        self.assertEqual(result["floors"], [
            {"floor": 1, "count": 1, "capacity": 90},
            {"floor": 2, "count": 1, "capacity": 110},
        ])

    # 讲解注释：test_live_occupancy_retries_once_before_falling_back() 处理楼层人数占用数据。
    def test_live_occupancy_retries_once_before_falling_back(self):
        payload = {
            "time": ["2026-05-03 11:00", "2026-05-03 11:10"],
            "data": [["SX101", "", 12, 40]],
        }
        calls = []
        original = campus_module._fetch_classroom_capacity

        # 讲解注释：flaky_fetch() 封装本文件中的一个独立处理步骤。
        def flaky_fetch(building_name):
            calls.append(building_name)
            if len(calls) == 1:
                raise TimeoutError("timed out")
            return payload

        campus_module._fetch_classroom_capacity = flaky_fetch
        try:
            items, warnings = fetch_live_floor_occupancy(["siyuan_west"])
        finally:
            campus_module._fetch_classroom_capacity = original

        self.assertEqual(len(calls), 2)
        self.assertEqual(warnings, [])
        self.assertEqual(items[0]["source"], "live")
        self.assertEqual(items[0]["total_used"], 12)

    # 讲解注释：test_live_occupancy_uses_cache_after_later_timeout() 处理楼层人数占用数据。
    def test_live_occupancy_uses_cache_after_later_timeout(self):
        payload = {
            "time": ["2026-05-03 11:00", "2026-05-03 11:10"],
            "data": [["SX101", "", 12, 40]],
        }
        original = campus_module._fetch_classroom_capacity
        campus_module._fetch_classroom_capacity = lambda _building_name: payload
        try:
            first_items, first_warnings = fetch_live_floor_occupancy(["siyuan_west"])
        finally:
            campus_module._fetch_classroom_capacity = original
        self.assertEqual(first_warnings, [])

        # 讲解注释：timeout_fetch() 封装本文件中的一个独立处理步骤。
        def timeout_fetch(_building_name):
            raise TimeoutError("timed out")

        campus_module._fetch_classroom_capacity = timeout_fetch
        try:
            cached_items, warnings = fetch_live_floor_occupancy(["siyuan_west"])
        finally:
            campus_module._fetch_classroom_capacity = original

        self.assertEqual(cached_items[0]["source"], "live_cache")
        self.assertEqual(cached_items[0]["floors"], first_items[0]["floors"])
        self.assertIn("最近一次实时数据", warnings[0])
        self.assertNotIn("timed out", warnings[0])
        self.assertNotIn("urlopen", warnings[0])

    # 讲解注释：test_live_occupancy_without_cache_returns_friendly_fallback_warning() 处理楼层人数占用数据。
    def test_live_occupancy_without_cache_returns_friendly_fallback_warning(self):
        original = campus_module._fetch_classroom_capacity

        # 讲解注释：timeout_fetch() 封装本文件中的一个独立处理步骤。
        def timeout_fetch(_building_name):
            raise TimeoutError("timed out")

        campus_module._fetch_classroom_capacity = timeout_fetch
        try:
            items, warnings = fetch_live_floor_occupancy(["siyuan_west"])
        finally:
            campus_module._fetch_classroom_capacity = original

        self.assertEqual(items[0]["source"], "random")
        self.assertIn("实时服务超时", warnings[0])
        self.assertIn("模拟数据", warnings[0])
        self.assertNotIn("timed out", warnings[0])
        self.assertNotIn("urlopen", warnings[0])
        self.assertGreaterEqual(campus_module.LIVE_TIMEOUT_SEC, 6)
