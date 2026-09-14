import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "analysis.py"
SPEC = importlib.util.spec_from_file_location("experiment_analysis", MODULE_PATH)
analysis = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(analysis)


class AnalysisTests(unittest.TestCase):
    def test_holm_adjustment_preserves_order_and_bounds(self):
        adjusted = analysis.holm_adjust([0.01, 0.04, 0.03])
        self.assertEqual(len(adjusted), 3)
        self.assertTrue(all(0 <= value <= 1 for value in adjusted))
        self.assertLessEqual(adjusted[0], adjusted[1])

    def test_paired_permutation_identical_is_one(self):
        self.assertEqual(analysis.paired_permutation_pvalue(np.zeros(5)), 1.0)

    def test_analysis_requires_paired_rows(self):
        with self.assertRaises(ValueError):
            analysis.paired_values([{"task_id": "t", "seed": 0, "condition": "a", "x": True}], "a", "b", "x")

    def test_task_differences_average_seeds_before_inference(self):
        rows = [
            {"task_id": "t1", "seed": 0, "condition": "a", "x": 0},
            {"task_id": "t1", "seed": 0, "condition": "b", "x": 1},
            {"task_id": "t1", "seed": 1, "condition": "a", "x": 1},
            {"task_id": "t1", "seed": 1, "condition": "b", "x": 1},
            {"task_id": "t2", "seed": 0, "condition": "a", "x": 1},
            {"task_id": "t2", "seed": 0, "condition": "b", "x": 0},
        ]
        differences = analysis.task_mean_differences(rows, "a", "b", "x")
        self.assertEqual(len(differences), 2)
        self.assertCountEqual(differences.tolist(), [0.5, -1.0])

    def test_reader_excludes_infrastructure_failures(self):
        rows = [
            {"task_id": "ok", "condition": "a", "seed": 0, "status": "completed", "analysis_eligible": True},
            {"task_id": "infra", "condition": "a", "seed": 0, "status": "infrastructure_error", "analysis_eligible": False},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "episodes.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            self.assertEqual([row["task_id"] for row in analysis.read_jsonl(path)], ["ok"])


if __name__ == "__main__":
    unittest.main()
