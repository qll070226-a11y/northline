import importlib.util
import unittest
from pathlib import Path

import pandas as pd

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "freeze_public_tasks.py"
SPEC = importlib.util.spec_from_file_location("freeze_public_tasks", MODULE_PATH)
freeze = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(freeze)


class PublicTaskSelectionTests(unittest.TestCase):
    def test_classifier_uses_problem_text_only(self):
        self.assertEqual(freeze.task_type("Refactor legacy parser implementation"), "refactor")
        self.assertEqual(freeze.task_type("Add missing tests for parser"), "test_completion")
        self.assertEqual(freeze.task_type("API should expose timeout option"), "api_change")
        self.assertEqual(freeze.task_type("Parser crashes on empty input"), "bug_fix")

    def test_selection_enforces_preregistered_quotas(self):
        rows = []
        difficulties = ["15 min - 1 hour"] * 12 + ["1-4 hours"] * 12
        types = ["bug_fix"] * 24
        for index in range(24):
            rows.append({
                "instance_id": f"repo{index % 12}__task-{index}",
                "repo": f"owner/repo{index % 12}",
                "difficulty": difficulties[index],
                "problem_statement": "Parser crashes on empty input",
                "task_type": types[index],
                "difficulty_band": freeze.difficulty_band(difficulties[index]),
                "selection_score": index / 24,
            })
        selected = freeze.select_instances(pd.DataFrame(rows))
        self.assertEqual(len(selected), 24)
        self.assertEqual(selected["difficulty_band"].value_counts().to_dict(), freeze.DIFFICULTY_QUOTAS)
        self.assertGreaterEqual(selected["repo"].nunique(), freeze.MIN_REPOSITORIES)
        self.assertLessEqual(selected["repo"].value_counts().max(), freeze.MAX_PER_REPOSITORY)


if __name__ == "__main__":
    unittest.main()
