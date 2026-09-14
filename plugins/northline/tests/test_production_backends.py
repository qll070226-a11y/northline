import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


codex_backend = load("codex_cli_backend", "experiments/backends/codex_cli_backend.py")
swebench_backend = load("swebench_evaluator", "experiments/backends/swebench_evaluator.py")


class ProductionBackendTests(unittest.TestCase):
    def test_prompt_contains_no_sealed_context(self):
        episode = {
            "task": {"task_id": "public-001", "objective": "fix parser", "context": {"workspace": "x"}},
            "condition": "single_agent", "seed": 0, "run_fingerprint": "abc",
        }
        prompt = codex_backend.prompt_for(episode)
        self.assertIn("fix parser", prompt)
        self.assertNotIn("instance_id", prompt)
        self.assertNotIn("FAIL_TO_PASS", prompt)

    def test_usage_parser_is_robust(self):
        jsonl = "\n".join((
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}}),
            json.dumps({"type": "tool", "name": "spawn_agent"}),
        ))
        usage = codex_backend.extract_usage(jsonl)
        self.assertEqual(usage["total_tokens"], 14)
        self.assertEqual(usage["delegation_count"], 1)

    def test_report_parser_finds_nested_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "logs" / "results.json"
            report.parent.mkdir()
            report.write_text(json.dumps({"resolved_ids": ["x"]}), encoding="utf-8")
            self.assertEqual(swebench_backend.locate_report(root, "run")["resolved_ids"], ["x"])


if __name__ == "__main__":
    unittest.main()
