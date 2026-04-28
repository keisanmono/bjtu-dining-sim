import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.optimization import RecommendationRequestData, recommend_config
from app.simulation import SimulationConfigData, run_simulation


class DiningSimulationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
