import unittest

from northline.detector import DriftDetector
from northline.models import (
    AgentRole,
    DelegationContract,
    EscalationKind,
    EscalationRequest,
    HandoffReceipt,
    HandoffStatus,
    MissionState,
)
from northline.runtime import DelegationRuntime
from northline.state_machine import HandoffStateMachine, InvalidTransition


def contract() -> DelegationContract:
    return DelegationContract(
        objective="change parser",
        in_scope=("parser",),
        out_of_scope=("API",),
        allowed_files=("src/**/*.py", "tests/**/*.py"),
        forbidden_files=("pyproject.toml",),
        acceptance_criteria=("tests pass",),
        required_tests=("python -m unittest",),
        base_commit="abc",
        parent_id="root",
        mission_id="m1",
    )


class ProtocolTests(unittest.TestCase):
    def test_state_machine_rejects_skip(self):
        machine = HandoffStateMachine()
        with self.assertRaises(InvalidTransition):
            machine.transition(HandoffStatus.INTEGRATED)

    def test_detector_blocks_scope_and_stale(self):
        c = contract()
        mission = MissionState("m1", "objective")
        receipt = HandoffReceipt(c.contract_id, "worker_1", HandoffStatus.REPORTING, "old", "new", ("pyproject.toml",), "x", ("t",), ("pass",), acceptance_evidence={"tests pass": "pass"})
        findings = DriftDetector().inspect(mission, c, receipt, current_head="current")
        codes = {f.code for f in findings}
        self.assertIn("STALE_BASE", codes)
        self.assertIn("FORBIDDEN_FILE", codes)
        self.assertFalse(DriftDetector.is_mergeable(findings))

    def test_runtime_integrates_verified_receipt(self):
        mission = MissionState("m1", "objective", root_commit="abc")
        runtime = DelegationRuntime(mission)
        c = contract()
        execution = runtime.delegate("root", c, role=AgentRole.WORKER)
        for status in (HandoffStatus.CLAIMED, HandoffStatus.EXECUTING, HandoffStatus.REPORTING):
            runtime.advance(c.contract_id, status)
        receipt = HandoffReceipt(c.contract_id, execution.agent_id, HandoffStatus.REPORTING, "abc", "def", ("src/parser.py",), "implemented", ("python -m unittest",), ("pass",), acceptance_evidence={"tests pass": "python -m unittest: pass"})
        findings = runtime.verify_and_integrate(c.contract_id, receipt, current_head="abc")
        self.assertTrue(DriftDetector.is_mergeable(findings))
        self.assertEqual(len(runtime.receipts), 1)
        self.assertGreaterEqual(len(runtime.event_log.events), 5)

    def test_detector_blocks_wrong_agent_and_missing_criteria(self):
        c = contract()
        mission = MissionState("m1", "objective")
        receipt = HandoffReceipt(c.contract_id, "intruder", HandoffStatus.REPORTING, "abc", "def", ("src/parser.py",), "implemented", ("python -m unittest",), ("pass",))
        findings = DriftDetector().inspect(mission, c, receipt, current_head="abc", expected_agent_id="worker_001")
        codes = {finding.code for finding in findings}
        self.assertIn("AGENT_ID_MISMATCH", codes)
        self.assertIn("ACCEPTANCE_EVIDENCE_MISSING", codes)

    def test_unresolved_question_requires_parent_decision(self):
        c = contract()
        receipt = HandoffReceipt(
            c.contract_id, "worker_001", HandoffStatus.REPORTING, "abc", "def", ("src/parser.py",), "implemented",
            ("python -m unittest",), ("pass",), unresolved_questions=("Change API?",), acceptance_evidence={"tests pass": "pass"},
        )
        findings = DriftDetector().inspect(MissionState("m1", "objective"), c, receipt, current_head="abc", expected_agent_id="worker_001")
        self.assertIn("UNRESOLVED_QUESTIONS", {finding.code for finding in findings})
        self.assertFalse(DriftDetector.is_mergeable(findings))

    def test_integration_rejects_contract_parameter_mismatch(self):
        mission = MissionState("m1", "objective", root_commit="abc")
        runtime = DelegationRuntime(mission)
        c = contract()
        execution = runtime.delegate("root", c, AgentRole.WORKER)
        receipt = HandoffReceipt(c.contract_id, execution.agent_id, HandoffStatus.REPORTING, "abc", "def", ("src/parser.py",), "implemented", ("python -m unittest",), ("pass",), acceptance_evidence={"tests pass": "pass"})
        with self.assertRaises(ValueError):
            runtime.verify_and_integrate("different-contract", receipt, current_head="abc")

    def test_runtime_enforces_depth(self):
        mission = MissionState("m1", "objective", max_depth=1)
        runtime = DelegationRuntime(mission)
        c = contract()
        runtime.delegate("root", c, AgentRole.WORKER)
        child = DelegationContract(
            objective="leaf", in_scope=("x",), out_of_scope=(), allowed_files=("src/*.py",), forbidden_files=(),
            acceptance_criteria=("pass",), required_tests=("test",), base_commit="abc", parent_id="worker_001", mission_id="m1"
        )
        with self.assertRaises(ValueError):
            runtime.delegate("worker_001", child, AgentRole.LEAF)

    def test_missing_dependency_is_rejected(self):
        mission = MissionState("m1", "objective", root_commit="abc")
        runtime = DelegationRuntime(mission)
        first = contract()
        runtime.delegate("root", first, AgentRole.WORKER)
        dependent = DelegationContract(
            objective="dependent", in_scope=("x",), out_of_scope=(), allowed_files=("tests/*.py",), forbidden_files=(),
            acceptance_criteria=("pass",), required_tests=("test",), base_commit="abc", parent_id="root", mission_id="m1",
            dependencies=(first.contract_id,),
        )
        execution = runtime.delegate("root", dependent, AgentRole.WORKER)
        for status in (HandoffStatus.CLAIMED, HandoffStatus.EXECUTING, HandoffStatus.REPORTING):
            runtime.advance(dependent.contract_id, status)
        receipt = HandoffReceipt(
            dependent.contract_id, execution.agent_id, HandoffStatus.REPORTING, "abc", "def", ("tests/test_x.py",),
            "implemented", ("test",), ("pass",), acceptance_evidence={"pass": "test: pass"},
        )
        findings = runtime.verify_and_integrate(dependent.contract_id, receipt, current_head="abc")
        self.assertEqual([finding.code for finding in findings], ["DEPENDENCY_NOT_INTEGRATED"])
        self.assertEqual(runtime.transitions[dependent.contract_id].status, HandoffStatus.REJECTED)

    def test_compound_escalation_requires_user_and_invalidates_old_receipt(self):
        mission = MissionState(
            "m1",
            "change parser without silently changing the public API",
            global_constraints=("preserve public API unless the user approves a revision",),
            root_commit="base-v1",
        )
        runtime = DelegationRuntime(mission)
        original = contract()
        original = DelegationContract.from_dict(
            {**original.to_dict(), "base_commit": "base-v1"}
        )
        execution = runtime.delegate("root", original, AgentRole.WORKER)
        runtime.advance(original.contract_id, HandoffStatus.CLAIMED)
        runtime.advance(original.contract_id, HandoffStatus.EXECUTING)

        request = EscalationRequest(
            contract_id=original.contract_id,
            contract_version=1,
            agent_id=execution.agent_id,
            kinds=(
                EscalationKind.STALE_STATE,
                EscalationKind.SCOPE_CHANGE,
                EscalationKind.ROOT_CONSTRAINT_CONFLICT,
            ),
            contract_base_commit="base-v1",
            workspace_merge_base="base-v1",
            parent_head="base-v2",
            blocking_evidence=("required fix changes pyproject.toml and the public API",),
            requested_changes={"allowed_files": ["src/**/*.py", "tests/**/*.py", "pyproject.toml"]},
            alternatives=("redesign the fix to preserve the existing API",),
            risks=("downstream callers may break",),
            required_tests=("python -m unittest",),
            requires_user_decision=True,
            stopped_work=True,
        )
        self.assertEqual(runtime.submit_escalation(request), HandoffStatus.NEEDS_PARENT_DECISION)
        self.assertIn(HandoffStatus.STALE, runtime.transitions[original.contract_id].history)
        with self.assertRaises(ValueError):
            runtime.resolve_escalation(request.request_id, approved=True, rationale="approve")
        runtime.resolve_escalation(
            request.request_id,
            approved=True,
            rationale="user accepted the compatibility risk",
            user_approved=True,
        )

        revised = DelegationContract(
            objective=original.objective,
            in_scope=original.in_scope + ("build metadata",),
            out_of_scope=original.out_of_scope,
            allowed_files=original.allowed_files + ("pyproject.toml",),
            forbidden_files=(),
            acceptance_criteria=original.acceptance_criteria,
            required_tests=original.required_tests,
            base_commit="base-v2",
            parent_id=original.parent_id,
            mission_id=original.mission_id,
            version=2,
            contract_id=original.contract_id,
        )
        runtime.revise_contract(request.request_id, revised, current_head="base-v2")
        self.assertEqual([item.version for item in runtime.contract_history[original.contract_id]], [1, 2])
        for status in (HandoffStatus.CLAIMED, HandoffStatus.EXECUTING, HandoffStatus.REPORTING):
            runtime.advance(original.contract_id, status)

        old_receipt = HandoffReceipt(
            original.contract_id,
            execution.agent_id,
            HandoffStatus.REPORTING,
            "base-v1",
            "result-v1",
            ("src/parser.py",),
            "old result",
            ("python -m unittest",),
            ("pass",),
            acceptance_evidence={"tests pass": "python -m unittest: pass"},
            contract_version=1,
        )
        findings = runtime.verify_and_integrate(original.contract_id, old_receipt, current_head="base-v2")
        codes = {finding.code for finding in findings}
        self.assertIn("CONTRACT_VERSION_MISMATCH", codes)
        self.assertIn("STALE_BASE", codes)
        self.assertEqual(runtime.transitions[original.contract_id].status, HandoffStatus.REJECTED)
        self.assertNotIn(original.contract_id, runtime.receipts)

    def test_escalation_rejects_continued_work(self):
        runtime = DelegationRuntime(MissionState("m1", "objective", root_commit="abc"))
        c = contract()
        execution = runtime.delegate("root", c, AgentRole.WORKER)
        runtime.advance(c.contract_id, HandoffStatus.CLAIMED)
        runtime.advance(c.contract_id, HandoffStatus.EXECUTING)
        request = EscalationRequest(
            contract_id=c.contract_id,
            contract_version=1,
            agent_id=execution.agent_id,
            kinds=(EscalationKind.BLOCKED,),
            contract_base_commit="abc",
            workspace_merge_base="abc",
            parent_head="abc",
            blocking_evidence=("dependency unavailable",),
            requested_changes={},
            stopped_work=False,
        )
        with self.assertRaises(ValueError):
            runtime.submit_escalation(request)


if __name__ == "__main__":
    unittest.main()
