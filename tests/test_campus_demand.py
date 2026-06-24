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


# 校园到达模式测试，覆盖食堂选择概率、楼层到达、实时人数和降级缓存。
class CampusDemandTests(unittest.TestCase):
    # 每个用例前清空实时人数缓存，避免缓存状态相互影响。
    def setUp(self):
        campus_module._LIVE_OCCUPANCY_CACHE.clear()

    # 每个用例后再次清空缓存，保证后续测试从干净状态开始。
    def tearDown(self):
        campus_module._LIVE_OCCUPANCY_CACHE.clear()

    # 验证第九教学楼到最近的学思食堂选择概率最高。
    def test_nearest_cafeteria_has_highest_choice_probability(self):
        probabilities = cafeteria_choice_probabilities("no9")

        self.assertGreater(probabilities["xuesi"], probabilities["minghu"])
        self.assertGreater(probabilities["xuesi"], probabilities["xuehuo"])
        self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=6)

    # 验证教学楼可显式配置目标食堂选择概率，覆盖按距离估算的默认值。
    def test_building_choice_probability_can_be_configured(self):
        blocked = CampusBuildingDemandData(
            building_id="no9",
            dismissal_minute=0,
            release_ratio=1.0,
            choice_probability=0.0,
            floors=[CampusFloorDemandData(floor=1, count=12)],
        )
        forced = CampusBuildingDemandData(
            building_id="no9",
            dismissal_minute=0,
            release_ratio=1.0,
            choice_probability=1.0,
            floors=[CampusFloorDemandData(floor=1, count=12)],
        )

        self.assertEqual(build_campus_arrival_schedule("xuesi", [blocked], seed=3), {})
        self.assertEqual(sum(build_campus_arrival_schedule("xuesi", [forced], seed=3).values()), 12)

    # 验证高楼层因为下楼时间更长，到达食堂不会早于低楼层。
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

    # 验证校园模式使用预生成到达表，而不是手动 arrival_rate 泊松到达。
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

    # 验证校园模式结束边界由最后一批校园到达决定，不等待手动 duration_min。
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

    # 验证真实钟点下课时间会按仿真起始时间归一化，避免 11:00 场景空跑 660 分钟。
    def test_campus_schedule_is_relative_to_simulation_start_clock(self):
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=660,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=8)],
                )
            ],
        )
        config = SimulationConfigData(
            num_windows=4,
            num_seats=20,
            arrival_rate=99.0,
            service_time_mean=0.2,
            dining_time_mean=1.0,
            duration_min=60,
            seed=6,
            simulation_start_minute=660,
            campus_demand=campus,
        )

        result = run_simulation(config)
        first_arrival = next(record for record in result.records if record.arrived_count > 0)

        self.assertLess(first_arrival.t, 30)
        self.assertEqual(first_arrival.clock_minute, 660 + first_arrival.t)
        self.assertEqual(first_arrival.snapshot["clock_minute"], first_arrival.clock_minute)
        self.assertLess(len(result.records), 120)

    # 验证随机楼层人数在相同 seed 下可复现，并按楼层返回。
    def test_random_floor_occupancy_is_reproducible_and_floor_level(self):
        first = generate_random_floor_occupancy(["no9"], seed=9)
        second = generate_random_floor_occupancy(["no9"], seed=9)

        self.assertEqual(first, second)
        self.assertEqual(first[0]["building_id"], "no9")
        self.assertGreater(len(first[0]["floors"]), 1)
        self.assertTrue(all("floor" in item and "count" in item for item in first[0]["floors"]))

    # 验证实时教室容量 payload 会按楼层聚合人数和容量。
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

    # 验证满员占位行会被视为不可读异常值，而不是实际满员人数。
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

    # 验证实时人数第一次超时后会重试一次，重试成功则不降级。
    def test_live_occupancy_retries_once_before_falling_back(self):
        payload = {
            "time": ["2026-05-03 11:00", "2026-05-03 11:10"],
            "data": [["SX101", "", 12, 40]],
        }
        calls = []
        original = campus_module._fetch_classroom_capacity

        # 第一次模拟超时，第二次返回教室容量 payload。
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

    # 验证已有实时缓存时，后续超时会返回最近一次缓存数据。
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

        # 模拟实时服务持续超时，触发缓存兜底路径。
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

    # 验证无缓存且实时服务超时时返回模拟数据和面向用户的提示。
    def test_live_occupancy_without_cache_returns_friendly_fallback_warning(self):
        original = campus_module._fetch_classroom_capacity

        # 模拟实时服务不可用，确保 warning 不泄漏底层异常细节。
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
