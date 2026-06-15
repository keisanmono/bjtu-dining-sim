import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))


class QualityStressScriptTests(unittest.TestCase):
    def test_non_positive_wall_clock_timeout_disables_timeout_guard(self):
        from scripts.run_quality_stress import Scenario, run_scenario

        row = run_scenario(
            Scenario(arrival_rate=0.1, seed=9031, duration_min=5),
            scenario_timeout_sec=0.0,
            max_steps=80,
            freeze_minutes=3,
        )

        self.assertTrue(row["natural_done"])
        self.assertEqual(row["total_arrived"], row["total_served"])
        self.assertEqual(row["walking_to_window_count"], 0)
        self.assertEqual(sum(row["physical_queue_lengths"]), 0)


if __name__ == "__main__":
    unittest.main()
