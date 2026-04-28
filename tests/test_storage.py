import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.simulation import SimulationConfigData, run_simulation
from app.storage import SimulationStore


class SimulationStoreTests(unittest.TestCase):
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

            self.assertEqual(len(records), result.config.duration_min)
            self.assertEqual(records[-1]["total_arrived"], result.metrics.total_arrived)
            self.assertEqual(metrics["run_id"], result.run_id)
            self.assertEqual(metrics["peak_queue"], result.metrics.peak_queue)
            self.assertIn("chart_data", metrics)


if __name__ == "__main__":
    unittest.main()
