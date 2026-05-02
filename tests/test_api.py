import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import (
    explain,
    get_run_metrics,
    get_run_records,
    recommend,
    run_full_simulation,
    validate_simulation_config,
)
from app.schemas import ExplanationRequest, RecommendationRequest, SimulationConfig


class ApiTests(unittest.TestCase):
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
                    {"id": "solo-1", "x": 148, "y": 238, "table_type": "two_seat", "capacity": 2},
                    {"id": "group-1", "x": 226, "y": 238, "table_type": "four_seat", "capacity": 4},
                ],
            },
            "party_size_distribution": {"1": 0.5, "2": 0.5},
        }

        body = run_full_simulation(SimulationConfig(**config)).model_dump()

        self.assertEqual(body["final_state"]["table_occupancy"][0]["id"], "solo-1")
        self.assertEqual(body["final_state"]["table_occupancy"][1]["type"], "four_seat")
        self.assertIn("two_seat", body["metrics"]["table_utilization_by_type"])
        self.assertIn("avg_party_gather_wait", body["metrics"])


if __name__ == "__main__":
    unittest.main()
