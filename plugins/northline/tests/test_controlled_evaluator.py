import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "controlled_evaluator", ROOT / "experiments" / "backends" / "controlled_evaluator.py"
)
assert SPEC and SPEC.loader
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)


class ControlledEvaluatorTests(unittest.TestCase):
    def test_glob_matching_supports_zero_component_double_star(self):
        self.assertTrue(EVALUATOR.matches("tests/test_app.py", ["tests/**/*.py"]))
        self.assertTrue(EVALUATOR.matches("tests/unit/test_app.py", ["tests/**/*.py"]))
        self.assertFalse(EVALUATOR.matches("pyproject.toml", ["tests/**/*.py"]))

    def test_python_command_uses_current_interpreter(self):
        tokens = EVALUATOR.command_tokens("python -m unittest -v")
        self.assertTrue(Path(tokens[0]).is_file())
        self.assertEqual(tokens[1:], ["-m", "unittest", "-v"])


if __name__ == "__main__":
    unittest.main()
