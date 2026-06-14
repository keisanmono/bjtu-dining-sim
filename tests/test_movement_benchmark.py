# 文件说明：movement benchmark 测试，验证 path/static/advanced 的 baseline 对比可复跑。

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))


class MovementBenchmarkTests(unittest.TestCase):
    def test_benchmark_generates_rows_for_all_quality_presets(self):
        from scripts.run_movement_benchmark import BENCHMARK_FIELDS, run_benchmark

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "benchmark.csv"
            summary_path = tmp_path / "summary.json"
            doc_path = tmp_path / "benchmark.md"

            rows, summary = run_benchmark(
                output_csv=csv_path,
                output_summary=summary_path,
                output_doc=doc_path,
                scenario_names=["micro_window_queue"],
                seeds=[6101],
            )

            self.assertEqual(len(rows), 3)
            self.assertEqual({row["movement_model"] for row in rows}, {"path", "static_floor_field", "advanced_floor_field"})
            self.assertEqual({row["quality_preset"] for row in rows}, {"fast", "balanced", "quality"})
            self.assertTrue({
                "quality_preset",
                "preset_label",
                "preset_role",
                "expected_use_case",
                "realism_score",
                "spatial_signal_score",
                "behavior_coupling_score",
                "congestion_response_score",
                "runtime_penalty_score",
                "arrival_stream_hash",
                "arrival_series_json",
                "runtime_sec",
            }.issubset(set(BENCHMARK_FIELDS)))
            self.assertTrue(csv_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(doc_path.exists())

            with csv_path.open(encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(len(csv_rows), 3)
            self.assertEqual(summary["row_count"], 3)

    def test_same_seed_uses_identical_arrival_stream_across_models(self):
        from scripts.run_movement_benchmark import run_benchmark

        with tempfile.TemporaryDirectory() as tmp:
            rows, summary = run_benchmark(
                output_csv=Path(tmp) / "benchmark.csv",
                output_summary=Path(tmp) / "summary.json",
                output_doc=Path(tmp) / "benchmark.md",
                scenario_names=["micro_window_queue"],
                seeds=[6102],
            )

            hashes = {row["arrival_stream_hash"] for row in rows}
            totals = {row["total_arrived"] for row in rows}

            self.assertEqual(len(hashes), 1)
            self.assertEqual(len(totals), 1)
            self.assertEqual(summary["fairness"]["groups_with_mismatched_arrival_streams"], 0)

    def test_advanced_model_records_spatial_signal_in_benchmark(self):
        from scripts.run_movement_benchmark import run_benchmark

        with tempfile.TemporaryDirectory() as tmp:
            rows, summary = run_benchmark(
                output_csv=Path(tmp) / "benchmark.csv",
                output_summary=Path(tmp) / "summary.json",
                output_doc=Path(tmp) / "benchmark.md",
                scenario_names=["micro_window_queue"],
                seeds=[6103],
            )

            advanced = next(row for row in rows if row["movement_model"] == "advanced_floor_field")

            self.assertGreater(float(advanced["avg_walking_time"]), 0.0)
            self.assertGreater(int(advanced["max_density"]), 0)
            self.assertGreaterEqual(summary["advanced_signal"]["rows_with_spatial_signal"], 1)

    def test_summary_json_and_doc_explain_baseline_roles(self):
        from scripts.run_movement_benchmark import run_benchmark

        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "summary.json"
            doc_path = Path(tmp) / "benchmark.md"
            _rows, summary = run_benchmark(
                output_csv=Path(tmp) / "benchmark.csv",
                output_summary=summary_path,
                output_doc=doc_path,
                scenario_names=["micro_window_queue"],
                seeds=[6104],
            )

            saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            doc = doc_path.read_text(encoding="utf-8")

            self.assertEqual(saved_summary["quality_presets"], ["fast", "balanced", "quality"])
            self.assertEqual(summary["quality_presets"], saved_summary["quality_presets"])
            self.assertIn("快速 Fast", doc)
            self.assertIn("平衡 Balanced", doc)
            self.assertIn("质量 Quality", doc)

    def test_summary_contains_multi_seed_confidence_statistics(self):
        from scripts.run_movement_benchmark import run_benchmark

        with tempfile.TemporaryDirectory() as tmp:
            _rows, summary = run_benchmark(
                output_csv=Path(tmp) / "benchmark.csv",
                output_summary=Path(tmp) / "summary.json",
                output_doc=Path(tmp) / "benchmark.md",
                scenario_names=["micro_window_queue"],
                seeds=[6101, 6102, 6103],
            )

            stats = summary["confidence_by_preset"]

            for preset in ("fast", "balanced", "quality"):
                self.assertEqual(stats[preset]["sample_count"], 3)
                for metric in ("avg_wait", "peak_queue", "runtime_sec", "realism_score"):
                    self.assertTrue({"mean", "std", "p50", "p90", "p95"}.issubset(stats[preset][metric]))

    def test_realism_score_orders_quality_above_baselines(self):
        from scripts.run_movement_benchmark import run_benchmark

        with tempfile.TemporaryDirectory() as tmp:
            rows, summary = run_benchmark(
                output_csv=Path(tmp) / "benchmark.csv",
                output_summary=Path(tmp) / "summary.json",
                output_doc=Path(tmp) / "benchmark.md",
                scenario_names=["micro_window_queue"],
                seeds=[6101, 6102, 6103],
            )

            mean_scores = summary["realism_score_by_preset"]

            self.assertGreater(mean_scores["quality"]["mean"], mean_scores["balanced"]["mean"])
            self.assertGreaterEqual(mean_scores["balanced"]["mean"], mean_scores["fast"]["mean"])
            self.assertTrue(all(0 <= float(row["realism_score"]) <= 100 for row in rows))

    def test_stress_suite_generates_large_population_rows(self):
        from scripts.run_movement_benchmark import BENCHMARK_FIELDS, run_benchmark

        with tempfile.TemporaryDirectory() as tmp:
            rows, summary = run_benchmark(
                output_csv=Path(tmp) / "stress.csv",
                output_summary=Path(tmp) / "stress.json",
                output_doc=Path(tmp) / "stress.md",
                suite="stress",
                scenario_names=["stress_single_cafeteria_0300"],
                seeds=[7201],
                quality_presets=["fast"],
            )

            self.assertEqual(len(rows), 1)
            self.assertIn("target_arrivals", BENCHMARK_FIELDS)
            self.assertIn("stress_level", BENCHMARK_FIELDS)
            self.assertEqual(rows[0]["category"], "stress")
            self.assertEqual(rows[0]["target_arrivals"], 300)
            self.assertEqual(rows[0]["stress_level"], "stress_0300")
            self.assertGreaterEqual(rows[0]["total_arrived"], 240)
            self.assertEqual(summary["stress"]["target_arrivals"], [300])

    def test_stress_suite_default_presets_cap_quality_target(self):
        from scripts.run_movement_benchmark import _presets_for_scenario, _stress_scenarios

        stress_300 = next(scenario for scenario in _stress_scenarios() if scenario.target_arrivals == 300)
        stress_800 = next(scenario for scenario in _stress_scenarios() if scenario.target_arrivals == 800)
        presets = ["fast", "balanced", "quality"]

        self.assertEqual(_presets_for_scenario(stress_300, presets, explicit_presets=False), presets)
        self.assertEqual(_presets_for_scenario(stress_800, presets, explicit_presets=False), ["fast", "balanced"])
        self.assertEqual(_presets_for_scenario(stress_800, presets, explicit_presets=True), presets)

    def test_stress_quality_layout_does_not_trap_students(self):
        from dataclasses import replace

        from app.simulation import DiningSimulationRunner, apply_movement_quality_preset
        from scripts.run_movement_benchmark import _stress_single_cafeteria_config

        config = apply_movement_quality_preset(
            replace(_stress_single_cafeteria_config(50), seed=7201, movement_quality_preset="quality")
        )
        runner = DiningSimulationRunner(config)

        for _ in range(180):
            if runner.done:
                break
            runner.step()

        self.assertTrue(
            runner.done,
            {
                "minute": runner.current_minute,
                "students": len(runner.students),
                "waiting_to_queue": len(runner.waiting_to_queue_student_ids),
                "waiting_for_seat": sum(party.size for party in runner.waiting_for_seat),
                "walking_to_seat": sum(transfer.party.size for transfer in runner.walking_to_seat),
                "seated": len(runner.seated),
            },
        )


if __name__ == "__main__":
    unittest.main()
