# 文件说明：接口集成测试：验证 FastAPI 主要接口从运行到推荐解释的完整链路。

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

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
from app.schemas import CampusOccupancyRequest, ExplanationRequest, RecommendationRequest, SimulationConfig


# 讲解注释：ApiTests 封装本文件的一组相关数据或测试行为。
class ApiTests(unittest.TestCase):
    # 讲解注释：setUp() 封装本文件中的一个独立处理步骤。
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

    # 讲解注释：test_run_records_metrics_recommendation_and_explanation() 读取或计算指标汇总。
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

    # 讲解注释：test_recommendation_accepts_campus_peak_count_options() 处理校园教学楼、食堂或到达数据。
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

    # 讲解注释：test_layout_payload_drives_table_state_and_metrics() 处理餐桌容量、位置或占用状态。
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

    # 讲解注释：test_campus_locations_expose_main_campus_buildings_and_cafeterias() 处理校园教学楼、食堂或到达数据。
    def test_campus_locations_expose_main_campus_buildings_and_cafeterias(self):
        payload = campus_locations()

        self.assertEqual(payload["campus_scope"], "main_campus_only")
        self.assertGreaterEqual(len(payload["teaching_buildings"]), 9)
        self.assertEqual({item["id"] for item in payload["cafeterias"]}, {"xuehuo", "minghu", "xuesi", "xueyuan"})
        self.assertIn("walk_times", payload)

    # 讲解注释：test_random_campus_occupancy_returns_floor_rows() 处理校园教学楼、食堂或到达数据。
    def test_random_campus_occupancy_returns_floor_rows(self):
        payload = campus_occupancy(CampusOccupancyRequest(source_mode="random", buildings=["no9"], seed=7))

        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["items"][0]["building_id"], "no9")
        self.assertGreater(len(payload["items"][0]["floors"]), 1)
        self.assertGreater(payload["items"][0]["total_used"], 0)


if __name__ == "__main__":
    unittest.main()
