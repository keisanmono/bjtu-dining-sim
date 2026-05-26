# 文件说明：仿真核心测试：验证排队、座位、推荐、结伴和实时地图快照行为。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.optimization as optimization_module
from app.optimization import RecommendationRequestData, recommend_config
from app.simulation import (
    CampusBuildingDemandData,
    CampusDemandConfigData,
    CampusFloorDemandData,
    DiningLayoutData,
    DiningSimulationRunner,
    LayoutDoorData,
    LayoutTableData,
    LayoutWindowData,
    SimulationConfigData,
    run_simulation,
)


# 仿真核心测试，覆盖到达、排队、入座、推荐估算和实时地图快照。
class DiningSimulationTests(unittest.TestCase):
    # 验证相同 seed 下完整仿真结果可复现。
    def test_run_is_reproducible_with_same_seed(self):
        config = SimulationConfigData(
            num_windows=3,
            num_seats=80,
            arrival_rate=9.0,
            service_time_mean=3.0,
            dining_time_mean=18.0,
            duration_min=45,
            seed=20260428,
        )

        first = run_simulation(config)
        second = run_simulation(config)

        self.assertGreaterEqual(len(first.records), config.duration_min)
        self.assertEqual([r.queue_lengths for r in first.records], [r.queue_lengths for r in second.records])
        self.assertEqual(first.metrics.avg_wait, second.metrics.avg_wait)
        self.assertEqual(first.metrics.peak_queue, second.metrics.peak_queue)
        self.assertEqual(first.metrics.total_left, first.metrics.total_arrived)

    # 验证到达期结束后系统会继续运行，直到所有已到达学生离开。
    def test_simulation_drains_all_arrivals_after_arrival_period(self):
        config = SimulationConfigData(
            num_windows=1,
            num_seats=4,
            arrival_rate=4.0,
            service_time_mean=3.0,
            dining_time_mean=8.0,
            duration_min=8,
            seed=20260429,
        )

        result = run_simulation(config)

        self.assertGreater(len(result.records), config.duration_min)
        self.assertTrue(all(record.arrived_count == 0 for record in result.records[config.duration_min:]))
        self.assertEqual(result.metrics.total_left, result.metrics.total_arrived)
        self.assertEqual(result.final_state["totals"]["left"], result.final_state["totals"]["arrived"])
        self.assertEqual(sum(result.final_state["queue_lengths"]), 0)
        self.assertEqual(result.final_state["occupied_seats"], 0)
        self.assertEqual(result.final_state["waiting_for_seat_count"], 0)
        self.assertNotIn("seat_matrix", result.final_state)

    # 验证窗口不足时峰值队列和瓶颈类型会体现窗口服务压力。
    def test_window_capacity_pressure_is_reported(self):
        result = run_simulation(
            SimulationConfigData(
                num_windows=1,
                num_seats=200,
                arrival_rate=12.0,
                service_time_mean=4.0,
                dining_time_mean=12.0,
                duration_min=40,
                seed=7,
            )
        )

        self.assertGreater(result.metrics.peak_queue, 100)
        self.assertEqual(result.metrics.bottleneck_type, "窗口服务")
        self.assertGreater(result.metrics.window_utilization, 0.85)

    # 验证座位不足时会出现等座，并把瓶颈归因为座位容量。
    def test_seat_capacity_pressure_is_reported(self):
        result = run_simulation(
            SimulationConfigData(
                num_windows=8,
                num_seats=12,
                arrival_rate=10.0,
                service_time_mean=1.0,
                dining_time_mean=30.0,
                duration_min=50,
                seed=8,
            )
        )

        self.assertGreater(max(r.waiting_for_seat_count for r in result.records), 0)
        self.assertEqual(result.metrics.bottleneck_type, "座位容量")
        self.assertGreater(result.metrics.seat_utilization, 0.75)

    # 验证推荐排序会优先给出比基准等待更低的方案。
    def test_recommendation_ranks_lower_waiting_plan_first(self):
        base = SimulationConfigData(
            num_windows=2,
            num_seats=60,
            arrival_rate=9.0,
            service_time_mean=3.5,
            dining_time_mean=18.0,
            duration_min=45,
            seed=99,
        )
        request = RecommendationRequestData(
            base_config=base,
            window_options=[2, 3, 4],
            seat_options=[60, 80],
            stagger_options=[0, 10],
            top_k=4,
        )

        recommendation = recommend_config(request)

        self.assertEqual(len(recommendation.ranking), 4)
        self.assertLessEqual(
            recommendation.best.metrics.avg_wait,
            run_simulation(base).metrics.avg_wait,
        )
        self.assertIn(recommendation.best.config.num_windows, [3, 4])

    # 验证推荐候选改变窗口和座位数时会同步扩展布局资源。
    def test_recommendation_resizes_layout_for_candidate_resource_counts(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[LayoutTableData(id="T1", x=20, y=20, table_type="four_seat", capacity=4)],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=1,
                num_seats=4,
                arrival_rate=3.0,
                service_time_mean=2.0,
                dining_time_mean=8.0,
                duration_min=12,
                seed=30,
                layout=layout,
            ),
            window_options=[2],
            seat_options=[8],
            stagger_options=[0],
            top_k=1,
        )

        recommendation = recommend_config(request)

        self.assertEqual(recommendation.best.config.num_windows, 2)
        self.assertEqual(recommendation.best.config.num_seats, 8)
        self.assertIsNotNone(recommendation.best.config.layout)
        self.assertEqual(len(recommendation.best.config.layout.windows), 2)
        self.assertEqual(sum(table.capacity for table in recommendation.best.config.layout.tables), 8)

    # 验证推荐生成候选布局时保留已有自定义坐标和餐桌旋转。
    def test_recommendation_preserves_custom_layout_coordinates_for_candidates(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=35, y=155)],
            windows=[
                LayoutWindowData(id="W1", x=145, y=75),
                LayoutWindowData(id="W2", x=230, y=75),
            ],
            tables=[
                LayoutTableData(id="T1", x=90, y=280, table_type="two_seat", capacity=2, rotation=90),
                LayoutTableData(id="T2", x=170, y=280, table_type="four_seat", capacity=4),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=2,
                num_seats=6,
                arrival_rate=3.0,
                service_time_mean=2.0,
                dining_time_mean=8.0,
                duration_min=12,
                seed=31,
                layout=layout,
            ),
            window_options=[3],
            seat_options=[8],
            stagger_options=[0],
            top_k=1,
        )

        recommendation = recommend_config(request)

        candidate_layout = recommendation.best.config.layout
        self.assertIsNotNone(candidate_layout)
        self.assertEqual(len(candidate_layout.windows), 3)
        self.assertEqual(sum(table.capacity for table in candidate_layout.tables), 8)
        self.assertEqual(candidate_layout.doors[0].x, 35)
        self.assertEqual(candidate_layout.windows[0].x, 145)
        self.assertEqual(candidate_layout.tables[0].x, 90)
        self.assertEqual(candidate_layout.tables[0].rotation, 90)

    # 验证座位数不变时推荐不会重建已有餐桌类型和容量。
    def test_recommendation_keeps_custom_table_types_when_seat_count_is_unchanged(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=35, y=155)],
            windows=[
                LayoutWindowData(id="W1", x=145, y=75),
                LayoutWindowData(id="W2", x=230, y=75),
            ],
            tables=[
                LayoutTableData(id="T1", x=90, y=280, table_type="six_seat", capacity=6),
                LayoutTableData(id="T2", x=170, y=280, table_type="two_seat", capacity=2),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=2,
                num_seats=8,
                arrival_rate=3.0,
                service_time_mean=2.0,
                dining_time_mean=8.0,
                duration_min=12,
                seed=32,
                layout=layout,
            ),
            window_options=[2],
            seat_options=[8],
            stagger_options=[10],
            top_k=1,
        )

        recommendation = recommend_config(request)

        candidate_layout = recommendation.best.config.layout
        self.assertEqual([table.capacity for table in candidate_layout.tables], [6, 2])
        self.assertEqual([table.table_type for table in candidate_layout.tables], ["six_seat", "two_seat"])

    # 验证校园推荐会把教学楼分配到多个错峰下课时间。
    def test_recommendation_splits_campus_buildings_into_dismissal_peaks(self):
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=90)],
                ),
                CampusBuildingDemandData(
                    building_id="siyuan",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=80)],
                ),
                CampusBuildingDemandData(
                    building_id="yifu",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=70)],
                ),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=2,
                num_seats=120,
                arrival_rate=1.0,
                service_time_mean=1.0,
                dining_time_mean=5.0,
                duration_min=80,
                seed=43,
                campus_demand=campus,
            ),
            window_options=[2],
            seat_options=[120],
            stagger_options=[10],
            peak_count_options=[3],
            top_k=1,
        )

        recommendation = recommend_config(request)

        candidate_campus = recommendation.best.config.campus_demand
        self.assertIsNotNone(candidate_campus)
        self.assertEqual({building.building_id for building in candidate_campus.buildings}, {"no9", "siyuan", "yifu"})
        self.assertEqual(sorted({building.dismissal_minute for building in candidate_campus.buildings}), [0, 10, 20])
        self.assertEqual(recommendation.best.config.stagger_minutes, 0)
        self.assertIn("3 峰下课", recommendation.best.strategy)
        self.assertIn("间隔 10 分钟", recommendation.best.strategy)

    # 验证校园推荐候选使用快速估算器，不为每个候选跑完整仿真。
    def test_campus_recommendation_uses_fast_estimator_for_candidates(self):
        campus = CampusDemandConfigData(
            enabled=True,
            cafeteria_id="xuesi",
            source_mode="manual",
            buildings=[
                CampusBuildingDemandData(
                    building_id="no9",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=80)],
                ),
                CampusBuildingDemandData(
                    building_id="siyuan",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=70)],
                ),
                CampusBuildingDemandData(
                    building_id="yifu",
                    dismissal_minute=0,
                    release_ratio=1.0,
                    floors=[CampusFloorDemandData(floor=1, count=60)],
                ),
            ],
        )
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=4,
                num_seats=120,
                arrival_rate=1.0,
                service_time_mean=1.0,
                dining_time_mean=5.0,
                duration_min=80,
                seed=44,
                campus_demand=campus,
            ),
            window_options=[2, 3, 4, 5, 6, 7],
            seat_options=[60, 80, 100, 120, 140, 160, 180, 200],
            stagger_options=[0, 5, 10, 15],
            peak_count_options=[1, 2, 3, 4],
            top_k=4,
        )
        # 若候选枚举误调用完整仿真，测试应立即失败。
        def fail_if_full_simulation_runs(config):
            raise AssertionError("校园推荐候选应使用快速估算器，而不是完整仿真。")

        original_run_simulation = optimization_module.run_simulation
        optimization_module.run_simulation = fail_if_full_simulation_runs
        try:
            recommendation = optimization_module.recommend_config(request)
        finally:
            optimization_module.run_simulation = original_run_simulation

        self.assertEqual(len(recommendation.ranking), 4)
        self.assertGreater(recommendation.baseline_metrics.total_arrived, 0)
        self.assertTrue(any("峰下课" in candidate.strategy for candidate in recommendation.ranking))

    # 验证手动到达模式下推荐候选同样走快速估算器。
    def test_manual_recommendation_uses_fast_estimator_for_candidates(self):
        request = RecommendationRequestData(
            base_config=SimulationConfigData(
                num_windows=4,
                num_seats=120,
                arrival_rate=8.0,
                service_time_mean=3.0,
                dining_time_mean=20.0,
                duration_min=60,
                seed=45,
                peak_start_min=15,
                peak_end_min=40,
                peak_multiplier=1.4,
            ),
            window_options=[3, 4, 5, 6],
            seat_options=[80, 100, 120, 140, 160],
            stagger_options=[0, 5, 10],
            top_k=3,
        )

        # 若手动候选枚举误调用完整仿真，测试应立即失败。
        def fail_if_full_simulation_runs(config):
            raise AssertionError("手动平均推荐候选应使用快速估算器，而不是完整仿真。")

        original_run_simulation = optimization_module.run_simulation
        optimization_module.run_simulation = fail_if_full_simulation_runs
        try:
            recommendation = optimization_module.recommend_config(request)
        finally:
            optimization_module.run_simulation = original_run_simulation

        self.assertEqual(len(recommendation.ranking), 3)
        self.assertGreater(recommendation.baseline_metrics.total_arrived, 0)
        self.assertTrue(any(candidate.config.num_windows > request.base_config.num_windows for candidate in recommendation.ranking))

    # 验证同一小组内的成员仍会按窗口队列和距离独立选择排队窗口。
    def test_party_members_choose_windows_independently(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[
                LayoutWindowData(id="W1", x=10, y=0),
                LayoutWindowData(id="W2", x=80, y=0),
            ],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=2,
                num_seats=4,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=22,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)

        runner._enqueue_arrivals(students)

        self.assertEqual(students[0].party_id, students[1].party_id)
        self.assertEqual([len(queue) for queue in runner.queues], [1, 1])
        self.assertEqual({student.window_index for student in students}, {0, 1})

    # 验证实时地图快照暴露排队、等座、入座小组和餐桌占用信息。
    def test_snapshot_exposes_party_locations_for_live_map(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[
                LayoutWindowData(id="W1", x=10, y=0),
                LayoutWindowData(id="W2", x=80, y=0),
            ],
            tables=[LayoutTableData(id="T1", x=30, y=30, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=2,
                num_seats=4,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=22,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        runner._enqueue_arrivals(students)

        queued_snapshot = runner._snapshot()

        self.assertEqual(
            sorted(group["member_count"] for group in queued_snapshot["queue_groups"]),
            [1, 1],
        )
        self.assertEqual({group["party_id"] for group in queued_snapshot["queue_groups"]}, {students[0].party_id})
        self.assertEqual(queued_snapshot["table_occupancy"][0]["party_count"], 0)

        party = runner.parties[students[0].party_id]
        runner.queues = [[], []]
        for student in students:
            student.window_index = 0
            student.service_end_time = 3
        party.ready_time = 3
        runner.waiting_for_seat.append(party)
        waiting_snapshot = runner._snapshot()
        self.assertEqual(waiting_snapshot["waiting_parties"][0]["window_index"], 0)
        runner._seat_waiting_students(minute=4)
        runner._advance_walking_to_seats(end_time_sec=5 * 60)

        seated_snapshot = runner._snapshot()

        self.assertEqual(seated_snapshot["seated_parties"][0]["party_id"], students[0].party_id)
        self.assertEqual(seated_snapshot["seated_parties"][0]["size"], 2)
        self.assertEqual(seated_snapshot["seated_parties"][0]["table_id"], "T1")
        self.assertEqual(seated_snapshot["table_occupancy"][0]["party_count"], 1)

    # 验证结伴小组入座时会被安排到同一张有足够容量的餐桌。
    def test_party_seating_keeps_companions_at_one_table(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[
                LayoutTableData(id="T1", x=20, y=20, table_type="two_seat", capacity=2),
                LayoutTableData(id="T2", x=80, y=20, table_type="two_seat", capacity=2),
            ],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=23,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        party = runner.parties[students[0].party_id]
        for student in students:
            student.service_end_time = 3
        party.ready_time = 3
        runner.waiting_for_seat.append(party)

        seated = runner._seat_waiting_students(minute=4)
        arrived = runner._advance_walking_to_seats(end_time_sec=5 * 60)

        self.assertEqual(seated, 2)
        self.assertEqual(arrived, 2)
        self.assertEqual(runner.table_occupied_seats, [2, 0])
        self.assertEqual({student.seat_time for student in students}, {5})
        self.assertEqual(runner.metrics_counters["party_split_count"], 0)

    # 验证单人学生在有空桌时优先选择空桌而不是拼桌。
    def test_solo_student_prefers_empty_table_before_sharing(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=0)],
            windows=[LayoutWindowData(id="W1", x=10, y=0)],
            tables=[
                LayoutTableData(id="T1", x=15, y=20, table_type="four_seat", capacity=4),
                LayoutTableData(id="T2", x=120, y=20, table_type="four_seat", capacity=4),
            ],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=8,
                layout=layout,
                party_size_distribution={1: 1.0},
                seed=24,
            )
        )
        occupied_student = runner._create_party_students(minute=0, person_count=1)[0]
        occupied_student.window_index = 0
        runner.table_occupied_seats[0] = 1
        runner.table_party_ids[0].add(occupied_student.party_id)
        solo = runner._create_party_students(minute=1, person_count=1)[0]
        solo.window_index = 0
        solo.service_end_time = 2
        party = runner.parties[solo.party_id]
        party.ready_time = 2
        runner.waiting_for_seat.append(party)

        runner._seat_waiting_students(minute=3)

        self.assertEqual(party.table_index, 1)

    # 验证取餐完成小组通过后端 timeline 行走到餐桌并最终入座。
    def test_ready_party_walks_to_seat_through_backend_timeline(self):
        layout = DiningLayoutData(
            doors=[LayoutDoorData(id="D1", x=0, y=120)],
            windows=[LayoutWindowData(id="W1", x=120, y=24)],
            tables=[LayoutTableData(id="T1", x=220, y=220, table_type="four_seat", capacity=4)],
        )
        runner = DiningSimulationRunner(
            SimulationConfigData(
                num_windows=1,
                num_seats=4,
                arrival_rate=1.0,
                service_time_mean=1.0,
                dining_time_mean=8.0,
                duration_min=5,
                layout=layout,
                party_size_distribution={2: 1.0},
                seed=25,
            )
        )
        students = runner._create_party_students(minute=0, person_count=2)
        party = runner.parties[students[0].party_id]
        for student in students:
            student.window_index = 0
            student.service_end_time = 5
        party.ready_time = 5
        runner.waiting_for_seat.append(party)
        runner.current_minute = 5

        record = runner.step()

        timeline = record.snapshot["timeline"]
        event = timeline["events"][0]
        self.assertEqual(record.seated_count, 2)
        self.assertEqual(event["type"], "walk_to_seat")
        self.assertEqual(event["party_id"], party.party_id)
        self.assertEqual(event["table_id"], "T1")
        self.assertEqual(event["window_index"], 0)
        self.assertGreater(event["duration_sec"], 0)
        self.assertLess(event["duration_sec"], 60)
        self.assertEqual(event["frames"][0]["progress"], 0)
        self.assertEqual(event["frames"][-1]["progress"], 1)
        self.assertEqual(event["path"][0], event["from"])
        self.assertEqual(event["path"][-1], event["to"])
        self.assertGreaterEqual(timeline["playback_ms"], event["playback_end_ms"])
        self.assertEqual(record.snapshot["walking_parties"], [])
        self.assertEqual(record.snapshot["seated_parties"][0]["party_id"], party.party_id)
        self.assertEqual(record.snapshot["table_occupancy"][0]["occupied"], 2)


if __name__ == "__main__":
    unittest.main()
