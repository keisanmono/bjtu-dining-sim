# 文件说明：接口集成测试：验证 FastAPI 主要接口从运行到推荐解释的完整链路。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.main as main_module
from app.main import (
    campus_locations,
    campus_occupancy,
    explain,
    get_run_metrics,
    get_run_records,
    recommend,
    run_full_simulation,
    validate_simulation_config,
)
from app.schemas import CampusOccupancyRequest, ExplanationRequest, RecommendationRequest, SimulationConfig, StepRequest


# 接口层集成测试，直接调用 FastAPI handler 验证主要业务链路。
class ApiTests(unittest.TestCase):
    # 每个用例共用一份规模较小但能完整跑完的基础仿真配置。
    def setUp(self):
        self.config = {
            "num_windows": 3,
            "num_seats": 80,
            "arrival_rate": 7,
            "service_time_mean": 2.5,
            "dining_time_mean": 16,
            "duration_min": 20,
            "seed": 200,
            "peak_start_min": 5,
            "peak_end_min": 14,
            "peak_multiplier": 1.3,
            "stagger_minutes": 0,
            "seat_columns": 10,
        }

    def tearDown(self):
        main_module.ACTIVE_RUNS.clear()

    # 验证默认数据目录不随启动工作目录漂移。
    def test_default_data_dir_is_repo_root_data_directory(self):
        self.assertTrue(main_module.DATA_DIR.is_absolute())
        self.assertEqual((ROOT / "data").resolve(), main_module.DATA_DIR)

    # 验证实时运行表会清理长时间未访问的 runner，避免内存状态无限保留。
    def test_stale_active_runs_are_pruned_before_creating_new_runner(self):
        first = main_module._resolve_runner(StepRequest(config=SimulationConfig(**self.config), reset=True))
        first.last_access_monotonic = -1_000_000.0

        second = main_module._resolve_runner(StepRequest(config=SimulationConfig(**self.config), reset=True))

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertNotIn(first.run_id, main_module.ACTIVE_RUNS)
        self.assertIn(second.run_id, main_module.ACTIVE_RUNS)

    # 验证参数校验、完整仿真、记录查询、指标查询、推荐和解释能串联执行。
    def test_run_records_metrics_recommendation_and_explanation(self):
        validation = validate_simulation_config(SimulationConfig(**self.config))
        self.assertTrue(validation.valid)

        run_body = run_full_simulation(SimulationConfig(**self.config)).model_dump()
        self.assertGreaterEqual(len(run_body["records"]), self.config["duration_min"])
        self.assertEqual(run_body["metrics"]["total_left"], run_body["metrics"]["total_arrived"])
        run_id = run_body["run_id"]

        records = get_run_records(run_id)
        self.assertGreaterEqual(len(records), self.config["duration_min"])

        metrics = get_run_metrics(run_id)
        self.assertIn("bottleneck_type", metrics)

        rec_body = recommend(
            RecommendationRequest(
                base_config=self.config,
                window_options=[3, 4],
                seat_options=[80, 100],
                stagger_options=[0, 10],
                top_k=3,
            )
        )
        self.assertEqual(len(rec_body["ranking"]), 3)
        self.assertIn("best", rec_body)

        explanation = explain(
            ExplanationRequest(
                run_id=run_id,
                baseline_metrics=run_body["metrics"],
                best_metrics=rec_body["best"]["metrics"],
                recommended_strategy=rec_body["best"]["strategy"],
            )
        )
        self.assertIn("建议采用", explanation.text)

    # 验证校园推荐接口会接收 peak_count_options 并把教学楼拆成多个下课峰。
    def test_recommendation_accepts_campus_peak_count_options(self):
        rec_body = recommend(
            RecommendationRequest(
                base_config={
                    **self.config,
                    "duration_min": 80,
                    "campus_demand": {
                        "enabled": True,
                        "cafeteria_id": "xuesi",
                        "source_mode": "manual",
                        "buildings": [
                            {
                                "building_id": "no9",
                                "dismissal_minute": 0,
                                "release_ratio": 1,
                                "floors": [{"floor": 1, "count": 30}],
                            },
                            {
                                "building_id": "siyuan",
                                "dismissal_minute": 0,
                                "release_ratio": 1,
                                "floors": [{"floor": 1, "count": 25}],
                            },
                            {
                                "building_id": "yifu",
                                "dismissal_minute": 0,
                                "release_ratio": 1,
                                "floors": [{"floor": 1, "count": 20}],
                            },
                        ],
                    },
                },
                window_options=[3],
                seat_options=[80],
                stagger_options=[10],
                peak_count_options=[3],
                top_k=1,
            )
        )

        buildings = rec_body["best"]["config"]["campus_demand"]["buildings"]
        self.assertEqual(sorted({building["dismissal_minute"] for building in buildings}), [0, 10, 20])
        self.assertIn("3 峰下课", rec_body["best"]["strategy"])

    # 验证前端布局 payload 会影响最终餐桌状态和分桌类型指标。
    def test_layout_payload_drives_table_state_and_metrics(self):
        config = {
            **self.config,
            "num_windows": 2,
            "num_seats": 6,
            "arrival_rate": 3,
            "duration_min": 8,
            "layout": {
                "doors": [{"id": "west-door", "x": 18, "y": 145, "arrival_share": 1.0}],
                "windows": [
                    {"id": "noodle", "x": 140, "y": 88, "service_rate_factor": 1.0},
                    {"id": "rice", "x": 220, "y": 88, "service_rate_factor": 1.2},
                ],
                "tables": [
                    {"id": "solo-1", "x": 148, "y": 238, "table_type": "two_seat", "capacity": 2, "rotation": 90},
                    {"id": "group-1", "x": 226, "y": 238, "table_type": "four_seat", "capacity": 4},
                ],
            },
            "party_size_distribution": {"1": 0.5, "2": 0.5},
        }

        config_model = SimulationConfig(**config)
        self.assertEqual(config_model.to_data().layout.tables[0].rotation, 90)

        body = run_full_simulation(config_model).model_dump()

        self.assertEqual(body["final_state"]["table_occupancy"][0]["id"], "solo-1")
        self.assertEqual(body["final_state"]["table_occupancy"][1]["type"], "four_seat")
        self.assertIn("two_seat", body["metrics"]["table_utilization_by_type"])
        self.assertIn("avg_party_gather_wait", body["metrics"])

    # 验证校园位置接口暴露主校区教学楼、食堂和步行时间表。
    def test_campus_locations_expose_main_campus_buildings_and_cafeterias(self):
        payload = campus_locations()

        self.assertEqual(payload["campus_scope"], "main_campus_only")
        self.assertGreaterEqual(len(payload["teaching_buildings"]), 9)
        self.assertEqual({item["id"] for item in payload["cafeterias"]}, {"xuehuo", "minghu", "xuesi", "xueyuan"})
        self.assertIn("walk_times", payload)
        self.assertIn("residential_sources", payload)
        self.assertGreater(len(payload["residential_sources"]), 0)
        residential_ids = {item["id"] for item in payload["residential_sources"]}
        self.assertNotIn("main_dorms", residential_ids)
        self.assertNotIn("east_dorms", residential_ids)
        self.assertIn("residential_walk_times", payload)
        valid_residential_ids = {
            item["id"]
            for item in payload["residential_sources"]
            if not item.get("exclude_from_simulation") and item.get("capacity_weight", 0) > 0
        }
        self.assertTrue(valid_residential_ids)
        self.assertTrue(valid_residential_ids.issubset(set(payload["residential_walk_times"])))
        first_residential_id = sorted(valid_residential_ids)[0]
        self.assertIn("xuesi", payload["residential_walk_times"][first_residential_id])
        self.assertIn("residential_release_profiles", payload)
        self.assertEqual(payload["residential_release_profiles"]["breakfast"]["start_minute"], 420)
        self.assertLess(
            payload["residential_release_profiles"]["breakfast"]["residential_participation_rate"],
            payload["residential_release_profiles"]["dinner"]["residential_participation_rate"],
        )
        self.assertIn("population_pool_defaults", payload)
        self.assertEqual(payload["population_pool_defaults"]["lunch"]["total_population_pool"], 15000)
        self.assertEqual(payload["population_pool_defaults"]["lunch"]["meal_participation_rate"], 0.75)

    # 验证随机校园人数接口返回按楼层组织的人数行。
    def test_random_campus_occupancy_returns_floor_rows(self):
        payload = campus_occupancy(CampusOccupancyRequest(source_mode="random", buildings=["no9"], seed=7))

        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["items"][0]["building_id"], "no9")
        self.assertGreater(len(payload["items"][0]["floors"]), 1)
        self.assertGreater(payload["items"][0]["total_used"], 0)


if __name__ == "__main__":
    unittest.main()
