# 文件说明：存储测试：验证 SQLite 保存、读取和 CSV 导出。

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.simulation import SimulationConfigData, run_simulation
from app.storage import SimulationStore


# 存储层测试，验证仿真结果写入 SQLite 后能按 run_id 读回。
class SimulationStoreTests(unittest.TestCase):
    # 验证分钟记录和最终指标保存后字段完整且与原结果一致。
    def test_save_and_load_run_records_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sim.sqlite"
            store = SimulationStore(db_path)
            result = run_simulation(
                SimulationConfigData(
                    num_windows=2,
                    num_seats=30,
                    arrival_rate=5,
                    service_time_mean=2,
                    dining_time_mean=12,
                    duration_min=20,
                    seed=123,
                )
            )

            store.save_result(result)

            records = store.get_records(result.run_id)
            metrics = store.get_metrics(result.run_id)

            self.assertGreaterEqual(len(records), result.config.duration_min)
            self.assertEqual(records[-1]["total_arrived"], result.metrics.total_arrived)
            self.assertEqual(records[-1]["total_left"], result.metrics.total_arrived)
            self.assertIn("reserved_seats", records[-1])
            self.assertIn("available_seats", records[-1])
            self.assertEqual(metrics["run_id"], result.run_id)
            self.assertEqual(metrics["peak_queue"], result.metrics.peak_queue)
            self.assertIn("chart_data", metrics)

    # 验证高级行人移动指标会随 metrics_summary 的 extra_metrics_json 一起持久化。
    def test_save_and_load_advanced_movement_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sim.sqlite"
            store = SimulationStore(db_path)
            result = run_simulation(
                SimulationConfigData(
                    num_windows=1,
                    num_seats=8,
                    arrival_rate=3,
                    service_time_mean=1,
                    dining_time_mean=2,
                    duration_min=5,
                    seed=20260615,
                    movement_model="advanced_floor_field",
                )
            )

            store.save_result(result)

            metrics = store.get_metrics(result.run_id)

            self.assertIsNotNone(metrics)
            for field in (
                "avg_walking_time",
                "movement_conflict_count",
                "avg_stuck_ticks",
                "max_density",
                "avg_walking_distance_ratio",
            ):
                self.assertIn(field, metrics)
                self.assertEqual(metrics[field], getattr(result.metrics, field))

    # 验证校园到达采样记录会保存采集时间、教学楼人数和反推宿舍人数，并支持多条求平均。
    def test_save_and_average_campus_arrival_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sim.sqlite"
            store = SimulationStore(db_path)
            first = _campus_record_payload(10, 20, 100)
            second = _campus_record_payload(30, 40, 300)

            first_record = store.save_campus_arrival_record("record-1", first)
            second_record = store.save_campus_arrival_record("record-2", second)

            records = store.list_campus_arrival_records()
            average = store.average_campus_arrival_records([first_record["record_id"], second_record["record_id"]])

            self.assertEqual([record["record_id"] for record in records], ["record-2", "record-1"])
            self.assertIn("created_at", records[0])
            self.assertEqual(records[0]["total_population"], 370)
            self.assertEqual(first_record["teaching_population"], 30)
            self.assertEqual(first_record["residential_population"], 100)
            self.assertEqual(average["teaching_population"], 50)
            self.assertEqual(average["residential_population"], 200)
            self.assertEqual(average["campus_demand"]["buildings"][0]["floors"][0]["count"], 20)
            self.assertEqual(average["campus_demand"]["buildings"][0]["floors"][1]["count"], 30)
            self.assertEqual(average["campus_demand"]["residential_sources"][0]["population_override"], 200)
            self.assertEqual(average["record_ids"], ["record-1", "record-2"])


def _campus_record_payload(first_floor: int, second_floor: int, residential_population: int) -> dict:
    return {
        "enabled": True,
        "cafeteria_id": "xuesi",
        "source_mode": "live",
        "meal_period": "lunch",
        "buildings": [
            {
                "building_id": "no9",
                "dismissal_minute": 690,
                "release_ratio": 0.8,
                "choice_probability": 0.5,
                "floors": [
                    {"floor": 1, "count": first_floor},
                    {"floor": 2, "count": second_floor},
                ],
            }
        ],
        "residential_sources": [
            {
                "residential_id": "jiayuan_1",
                "release_ratio": 1,
                "choice_probability": 0.4,
                "population_override": residential_population,
                "source_type": "residential",
            }
        ],
        "population_pool": {
            "enabled": True,
            "meal_period": "lunch",
            "total_population_pool": 1000,
            "total_population_mode": "manual",
            "meal_participation_rate": 0.75,
            "other_known_population": 50,
            "residential_allocation_mode": "capacity_weight",
            "residual_policy": "clamp_zero",
        },
        "residential_release_profile": {
            "meal_period": "lunch",
            "start_minute": 660,
            "end_minute": 780,
            "peak_minute": 720,
            "distribution": "triangular",
            "residential_participation_rate": 0.65,
        },
    }


if __name__ == "__main__":
    unittest.main()
