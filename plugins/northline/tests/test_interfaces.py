import asyncio
import unittest

from jsonschema import ValidationError

from northline.langgraph_runtime import build_langgraph
from northline.mcp_server import create_server, transition_data, validate_handoff_data
from northline.models import (
    AgentCheckpoint,
    AgentRole,
    AgentTaskPacket,
    DelegationContract,
    EscalationKind,
    EscalationRequest,
    HandoffReceipt,
    HandoffStatus,
    MissionState,
    ProtocolPolicy,
)
from northline.schema import validate_payload


def payloads():
    mission = MissionState("m1", "implement parser", acceptance_criteria=("tests pass",), root_commit="base")
    contract = DelegationContract(
        objective="implement parser", in_scope=("parser",), out_of_scope=("API",),
        allowed_files=("src/**/*.py",), forbidden_files=("pyproject.toml",),
        acceptance_criteria=("tests pass",), required_tests=("pytest",),
        base_commit="base", parent_id="root", mission_id="m1",
    )
    receipt = HandoffReceipt(
        contract_id=contract.contract_id, agent_id="worker_001", status=HandoffStatus.REPORTING,
        base_commit="base", result_commit="result", changed_files=("src/parser.py",),
        diff_summary="implemented parser", tests_run=("pytest",), test_results=("pass",),
        acceptance_evidence={"tests pass": "pytest: pass"},
    )
    return mission.to_dict(), contract.to_dict(), receipt.to_dict()


class InterfaceTests(unittest.TestCase):
    def test_json_schema_accepts_valid_payloads(self):
        mission, contract, receipt = payloads()
        validate_payload("mission", mission)
        validate_payload("contract", contract)
        validate_payload("receipt", receipt)
        validate_payload("policy", ProtocolPolicy().to_dict())
        dispatch = AgentTaskPacket(
            mission_id="m1", root_objective="implement parser", root_acceptance_criteria=("tests pass",),
            root_decisions=(), contract_id=contract["contract_id"], contract_version=1,
            agent_id="worker_001", role=AgentRole.WORKER, parent_id="root",
            workspace="/tmp/work", base_commit="base", objective="implement parser",
            global_constraints=(), in_scope=("parser",), out_of_scope=("API",),
            allowed_files=("src/**/*.py",), forbidden_files=("pyproject.toml",),
            acceptance_criteria=("tests pass",), required_tests=("pytest",), protocol_rules=("stay in scope",),
        )
        validate_payload("dispatch", dispatch.to_dict())
        checkpoint = AgentCheckpoint(
            contract_id=contract["contract_id"], contract_version=1, agent_id="worker_001",
            status=HandoffStatus.EXECUTING, current_commit="base", completed=("inspection",), pending=("tests",),
        )
        validate_payload("checkpoint", checkpoint.to_dict())
        escalation = EscalationRequest(
            contract_id=contract["contract_id"], contract_version=1, agent_id="worker_001",
            kinds=(EscalationKind.STALE_STATE,), contract_base_commit="base",
            workspace_merge_base="base", parent_head="new-base",
            blocking_evidence=("parent advanced",), requested_changes={"base_commit": "new-base"},
        )
        validate_payload("escalation", escalation.to_dict())

    def test_json_schema_rejects_unknown_fields(self):
        mission, _, _ = payloads()
        mission["typo_field"] = True
        with self.assertRaises(ValidationError):
            validate_payload("mission", mission)

    def test_mcp_validation_is_mergeable(self):
        mission, contract, receipt = payloads()
        result = validate_handoff_data(mission, contract, receipt, "base", "worker_001")
        self.assertTrue(result["mergeable"])

    def test_mcp_registers_expected_tools(self):
        tools = asyncio.run(create_server().list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            {
                "validate_handoff",
                "check_transition",
                "check_parallel_safety",
                "initialize_project",
                "draft_project_contract",
                "delegate_project_task",
                "prepare_project_workspace",
                "transition_project_handoff",
                "get_project_status",
                "get_project_resume",
                "get_project_schema",
                "migrate_project",
                "create_agent_task_packet",
                "record_agent_checkpoint",
                "get_project_report",
                "draft_project_receipt",
                "verify_project_handoff",
                "record_project_integration",
                "submit_project_escalation",
                "decide_project_escalation",
                "revise_project_contract",
            },
        )

    def test_transition_tool(self):
        self.assertTrue(transition_data("planned", "claimed")["allowed"])
        self.assertFalse(transition_data("planned", "integrated")["allowed"])

    def test_langgraph_adapter_runs(self):
        graph = build_langgraph(lambda state: {**state, "worked": True}, lambda state: {**state, "verified": True})
        result = graph.invoke({"mission": "demo"})
        self.assertTrue(result["worked"])
        self.assertTrue(result["verified"])


if __name__ == "__main__":
    unittest.main()
