import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from app.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
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
        validation = self.client.post("/api/config/validate", json=self.config)
        self.assertEqual(validation.status_code, 200)
        self.assertTrue(validation.json()["valid"])

        run = self.client.post("/api/sim/run", json=self.config)
        self.assertEqual(run.status_code, 200)
        run_body = run.json()
        self.assertEqual(len(run_body["records"]), self.config["duration_min"])
        run_id = run_body["run_id"]

        records = self.client.get(f"/api/run/{run_id}/records")
        self.assertEqual(records.status_code, 200)
        self.assertEqual(len(records.json()), self.config["duration_min"])

        metrics = self.client.get(f"/api/run/{run_id}/metrics")
        self.assertEqual(metrics.status_code, 200)
        self.assertIn("bottleneck_type", metrics.json())

        recommendation = self.client.post(
            "/api/optimize/recommend",
            json={
                "base_config": self.config,
                "window_options": [3, 4],
                "seat_options": [80, 100],
                "stagger_options": [0, 10],
                "top_k": 3,
            },
        )
        self.assertEqual(recommendation.status_code, 200)
        rec_body = recommendation.json()
        self.assertEqual(len(rec_body["ranking"]), 3)
        self.assertIn("best", rec_body)

        explanation = self.client.post(
            "/api/explain",
            json={
                "run_id": run_id,
                "baseline_metrics": run_body["metrics"],
                "best_metrics": rec_body["best"]["metrics"],
                "recommended_strategy": rec_body["best"]["strategy"],
            },
        )
        self.assertEqual(explanation.status_code, 200)
        self.assertIn("建议采用", explanation.json()["text"])


if __name__ == "__main__":
    unittest.main()
