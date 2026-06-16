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


if __name__ == "__main__":
    unittest.main()
