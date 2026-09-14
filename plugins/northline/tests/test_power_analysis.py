import unittest

from experiments.power_analysis import build_report, exact_mcnemar_power, minimum_tasks


class PowerAnalysisTests(unittest.TestCase):
    def test_power_increases_with_sample_size_and_effect(self):
        low = exact_mcnemar_power(24, 0.30, 0.75)
        more_tasks = exact_mcnemar_power(100, 0.30, 0.75)
        larger_effect = exact_mcnemar_power(24, 0.30, 0.90)
        self.assertLess(low, more_tasks)
        self.assertLess(low, larger_effect)

    def test_null_power_does_not_exceed_alpha(self):
        self.assertLessEqual(exact_mcnemar_power(100, 0.30, 0.50), 0.05)

    def test_minimum_sample_reaches_target(self):
        sample = minimum_tasks(0.40, 0.75, alpha=0.05)
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertGreaterEqual(exact_mcnemar_power(sample, 0.40, 0.75), 0.80)
        self.assertLess(exact_mcnemar_power(sample - 1, 0.40, 0.75), 0.80)

    def test_report_marks_results_as_planning_sensitivity(self):
        report = build_report()
        self.assertIn("not observed evidence", report["interpretation"])
        self.assertEqual(report["inference_unit"], "task")


if __name__ == "__main__":
    unittest.main()
