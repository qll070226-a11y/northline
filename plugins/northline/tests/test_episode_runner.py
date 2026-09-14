import json
import tempfile
import unittest
from pathlib import Path

from northline.episode import (
    AgentExecutionError,
    AgentRun,
    EpisodeRunner,
    EvaluationEvidence,
    EvaluatorError,
    PreflightError,
    TaskSpec,
    build_blocked_schedule,
)


class StubAgent:
    def __init__(self, fail=False, preflight_failures=0):
        self.calls = 0
        self.preflight_calls = 0
        self.fail = fail
        self.preflight_failures = preflight_failures

    def preflight(self, spec):
        self.preflight_calls += 1
        if self.preflight_calls <= self.preflight_failures:
            raise PreflightError("provider unavailable before task exposure")

    def solve(self, spec):
        self.calls += 1
        if self.fail:
            raise AgentExecutionError("agent timed out after task exposure")
        return AgentRun(final_commit=f"commit-{spec.seed}", token_cost=10, latency_seconds=0.01)


class StubEvaluator:
    def __init__(self, failures=0):
        self.calls = 0
        self.failures = failures

    def preflight(self, spec):
        pass

    def evaluate(self, spec, run):
        self.calls += 1
        if self.calls <= self.failures:
            raise EvaluatorError("test harness unavailable")
        return EvaluationEvidence(True, True, False, False, False, False, False, evidence={"hidden_tests": "pass"})


class EpisodeRunnerTests(unittest.TestCase):
    def task(self):
        return TaskSpec(
            "task-1",
            "bug_fix",
            "fix parser",
            agent_context={"public_constraint": "preserve API"},
            evaluator_context={"sealed": "gold"},
        )

    def schedule(self, fingerprint="freeze-a"):
        return build_blocked_schedule([self.task()], ["single_agent", "full_protocol"], [0, 1], fingerprint, 7)

    def test_agent_payload_cannot_contain_evaluator_context(self):
        spec = self.schedule()[0]
        payload = spec.to_agent_dict()
        self.assertNotIn("gold", json.dumps(payload))
        self.assertIn("gold", json.dumps(spec.to_evaluator_dict()))
        with self.assertRaises(ValueError):
            TaskSpec.from_dict({"task_id": "x", "task_type": "bug_fix", "objective": "x", "patch": "gold"})

    def test_schedule_is_deterministic_and_blocked(self):
        first = self.schedule()
        second = self.schedule()
        self.assertEqual([(item.key) for item in first], [(item.key) for item in second])
        for start in (0, 2):
            self.assertEqual({item.condition for item in first[start:start + 2]}, {"single_agent", "full_protocol"})

    def test_runner_resumes_only_same_fingerprint(self):
        agent = StubAgent()
        runner = EpisodeRunner(agent, StubEvaluator())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "episodes.jsonl"
            self.assertEqual(len(runner.run(self.schedule(), output)), 4)
            self.assertEqual(runner.run(self.schedule(), output), [])
            changed = build_blocked_schedule([self.task()], ["single_agent"], [0], "freeze-b", 7)
            self.assertEqual(len(runner.run(changed, output)), 1)
            self.assertEqual(agent.calls, 5)

    def test_agent_timeout_is_analysis_eligible_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "episodes.jsonl"
            records = EpisodeRunner(StubAgent(fail=True), StubEvaluator()).run(self.schedule()[:1], output)
            row = records[0].to_dict()
            self.assertEqual(row["status"], "agent_failure")
            self.assertTrue(row["analysis_eligible"])
            self.assertFalse(row["root_goal_satisfied"])

    def test_preflight_failure_is_ineligible_and_retried_without_task_exposure(self):
        agent = StubAgent(preflight_failures=1)
        runner = EpisodeRunner(agent, StubEvaluator())
        schedule = self.schedule()[:1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "episodes.jsonl"
            first = runner.run(schedule, output)
            self.assertEqual(first[0].status, "preflight_error")
            self.assertFalse(first[0].to_dict()["analysis_eligible"])
            self.assertEqual(agent.calls, 0)
            second = runner.run(schedule, output)
            self.assertEqual(second[0].status, "completed")
            self.assertEqual(agent.calls, 1)

    def test_unclassified_preflight_bug_is_not_silently_excluded(self):
        class BuggyAgent(StubAgent):
            def preflight(self, spec):
                raise ValueError("implementation defect")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "episodes.jsonl"
            with self.assertRaisesRegex(ValueError, "implementation defect"):
                EpisodeRunner(BuggyAgent(), StubEvaluator()).run(self.schedule()[:1], output)

    def test_evaluator_retry_does_not_rerun_agent(self):
        agent = StubAgent()
        evaluator = StubEvaluator(failures=1)
        runner = EpisodeRunner(agent, evaluator)
        schedule = self.schedule()[:1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "episodes.jsonl"
            first = runner.run(schedule, output)
            self.assertEqual(first[0].status, "evaluation_pending")
            second = runner.run(schedule, output)
            self.assertEqual(second[0].status, "completed")
            self.assertEqual(agent.calls, 1)
            self.assertEqual(evaluator.calls, 2)


if __name__ == "__main__":
    unittest.main()
