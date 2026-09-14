import importlib.util
import unittest
from collections import Counter
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "generate_tasks.py"
SPEC = importlib.util.spec_from_file_location("task_generator", MODULE_PATH)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(generator)


class ExperimentGenerationTests(unittest.TestCase):
    def test_default_design_is_balanced(self):
        tasks = generator.generate()
        self.assertEqual(len(tasks), 24)
        self.assertEqual(set(Counter(task["task_type"] for task in tasks).values()), {6})
        self.assertEqual(set(Counter(task["evaluator_context"]["injected_fault"] for task in tasks).values()), {6})

    def test_oracles_use_detector_codes(self):
        for task in generator.generate():
            evaluator = task["evaluator_context"]
            expected = generator.FINDING_CODES[evaluator["injected_fault"]]
            self.assertEqual(evaluator["oracle"]["must_detect"], expected)
