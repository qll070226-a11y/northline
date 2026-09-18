from __future__ import annotations

from typing import Any

from .detector import DriftDetector
from .engine import ProtocolEngine
from .models import DelegationContract, HandoffReceipt, HandoffStatus, MissionState
from .schema import validate_payload
from .scope import assess_parallel_safety
from .state_machine import HandoffStateMachine


def validate_handoff_data(
    mission: dict[str, Any],
    contract: dict[str, Any],
    receipt: dict[str, Any],
    current_head: str,
    expected_agent_id: str | None = None,
) -> dict[str, Any]:
    validate_payload("mission", mission)
    validate_payload("contract", contract)
    validate_payload("receipt", receipt)
    mission_model = MissionState.from_dict(mission)
    contract_model = DelegationContract.from_dict(contract)
    receipt_model = HandoffReceipt.from_dict(receipt)
    findings = DriftDetector().inspect(
        mission_model,
        contract_model,
        receipt_model,
        current_head=current_head,
        root_constraints=mission_model.global_constraints,
        expected_agent_id=expected_agent_id,
    )
    return {
        "mergeable": DriftDetector.is_mergeable(findings),
        "findings": [
            {"code": finding.code, "severity": finding.severity.value, "message": finding.message, "evidence": finding.evidence}
            for finding in findings
        ],
    }


def transition_data(current: str, target: str) -> dict[str, Any]:
    machine = HandoffStateMachine(status=HandoffStatus(current), history=[HandoffStatus(current)])
    return {"allowed": machine.can_transition(HandoffStatus(target)), "current": current, "target": target}


def create_server():
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:
        raise RuntimeError("Install the MCP extra with: pip install -e '.[mcp]'") from exc

    server = MCPServer(
        "northline",
        instructions="Validate recursive delegation handoffs. Deterministic BLOCK findings cannot be overridden by an LLM.",
    )

    @server.tool(description="Validate a handoff receipt against mission and delegation contract constraints.")
    def validate_handoff(
        mission: dict[str, Any],
        contract: dict[str, Any],
        receipt: dict[str, Any],
        current_head: str,
        expected_agent_id: str | None = None,
    ) -> dict[str, Any]:
        return validate_handoff_data(mission, contract, receipt, current_head, expected_agent_id)

    @server.tool(description="Check whether a handoff state transition is authorized by the protocol.")
    def check_transition(current: str, target: str) -> dict[str, Any]:
        return transition_data(current, target)

    @server.tool(description="Conservatively check whether two delegation contracts have disjoint file scopes and no dependency ordering.")
    def check_parallel_safety(left_contract: dict[str, Any], right_contract: dict[str, Any]) -> dict[str, Any]:
        validate_payload("contract", left_contract)
        validate_payload("contract", right_contract)
        result = assess_parallel_safety(DelegationContract.from_dict(left_contract), DelegationContract.from_dict(right_contract))
        return {"safe": result.safe, "reasons": list(result.reasons)}

    @server.tool(description="Initialize a repository-local .northline mission. Existing missions require explicit overwrite.")
    def initialize_project(
        workspace: str,
        mission: dict[str, Any],
        policy: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).initialize(mission, policy=policy, overwrite=overwrite)

    @server.tool(description="Draft a complete contract from Root-authored scope while filling mission id and current parent HEAD.")
    def draft_project_contract(
        workspace: str,
        objective: str,
        in_scope: list[str],
        allowed_files: list[str],
        acceptance_criteria: list[str],
        required_tests: list[str],
        out_of_scope: list[str] | None = None,
        forbidden_files: list[str] | None = None,
        parent_id: str = "root",
        dependencies: list[str] | None = None,
        deadline_or_budget: str | None = None,
        contract_id: str | None = None,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).draft_contract(
            objective=objective,
            in_scope=tuple(in_scope),
            out_of_scope=tuple(out_of_scope or ()),
            allowed_files=tuple(allowed_files),
            forbidden_files=tuple(forbidden_files or ()),
            acceptance_criteria=tuple(acceptance_criteria),
            required_tests=tuple(required_tests),
            parent_id=parent_id,
            dependencies=tuple(dependencies or ()),
            deadline_or_budget=deadline_or_budget,
            contract_id=contract_id,
        )

    @server.tool(description="Persist a contract and assign it to a bounded Worker or Leaf execution.")
    def delegate_project_task(
        workspace: str,
        contract: dict[str, Any],
        agent_id: str,
        role: str,
        execution_workspace: str | None = None,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).delegate(
            contract,
            agent_id=agent_id,
            role=role,
            workspace=execution_workspace,
        )

    @server.tool(description="Create a detached Git worktree for one planned contract at its immutable base commit.")
    def prepare_project_workspace(workspace: str, contract_id: str, target: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).prepare_workspace(contract_id, target)

    @server.tool(description="Advance one persistent contract execution through an authorized protocol transition.")
    def transition_project_handoff(workspace: str, contract_id: str, target: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).transition(contract_id, target)

    @server.tool(description="Return mission and verification counts without exposing receipt contents.")
    def get_project_status(workspace: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).status()

    @server.tool(description="Return actionable resume state for every delegated execution, including stale and blocked work.")
    def get_project_resume(workspace: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).resume_summary()

    @server.tool(description="Inspect whether the repository-local Northline schema is current or requires migration.")
    def get_project_schema(workspace: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).project_schema()

    @server.tool(description="Migrate a legacy repository-local Northline project through a supported deterministic path.")
    def migrate_project(workspace: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).migrate_project()

    @server.tool(description="Create and persist a bounded task packet for a prepared Worker or Leaf workspace.")
    def create_agent_task_packet(workspace: str, contract_id: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).create_agent_task_packet(contract_id)

    @server.tool(description="Record a Git-backed progress checkpoint so interrupted agent work can be resumed safely.")
    def record_agent_checkpoint(
        workspace: str,
        contract_id: str,
        completed: list[str],
        pending: list[str],
        blockers: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).record_agent_checkpoint(
            contract_id,
            completed=tuple(completed),
            pending=tuple(pending),
            blockers=tuple(blockers or ()),
            notes=tuple(notes or ()),
        )

    @server.tool(description="Return the delegation tree, event timeline, verification summaries, and protocol metrics.")
    def get_project_report(workspace: str) -> dict[str, Any]:
        return ProtocolEngine(workspace).project_report()

    @server.tool(description="Draft a receipt from the assigned worktree's observed commit, diff, and freshly executed tests.")
    def draft_project_receipt(
        workspace: str,
        contract_id: str,
        diff_summary: str,
        acceptance_evidence: dict[str, str],
        assumptions: list[str] | None = None,
        risks: list[str] | None = None,
        unresolved_questions: list[str] | None = None,
        evidence_links: list[str] | None = None,
        evidence_workspace: str | None = None,
        test_timeout_seconds: float = 600,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).draft_receipt(
            contract_id,
            diff_summary=diff_summary,
            acceptance_evidence=acceptance_evidence,
            assumptions=tuple(assumptions or ()),
            risks=tuple(risks or ()),
            unresolved_questions=tuple(unresolved_questions or ()),
            evidence_links=tuple(evidence_links or ()),
            evidence_workspace=evidence_workspace,
            test_timeout_seconds=test_timeout_seconds,
        )

    @server.tool(description="Rebuild Git and test evidence, then verify and record a handoff without integrating source files.")
    def verify_project_handoff(
        workspace: str,
        contract_id: str,
        receipt: dict[str, Any],
        evidence_workspace: str | None = None,
        test_timeout_seconds: float = 600,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).verify_handoff(
            contract_id,
            receipt,
            evidence_workspace=evidence_workspace,
            test_timeout_seconds=test_timeout_seconds,
        )

    @server.tool(description="Record integration only after repository HEAD contains the verified result and integration tests pass.")
    def record_project_integration(
        workspace: str,
        contract_id: str,
        integration_tests: list[str] | None = None,
        test_timeout_seconds: float = 600,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).record_integration(
            contract_id,
            integration_tests=tuple(integration_tests or ()),
            test_timeout_seconds=test_timeout_seconds,
        )

    @server.tool(description="Persist a stopped-work escalation and move its execution into a waiting state.")
    def submit_project_escalation(workspace: str, request: dict[str, Any]) -> dict[str, Any]:
        return ProtocolEngine(workspace).submit_escalation(request)

    @server.tool(description="Record the Root decision for a persistent escalation.")
    def decide_project_escalation(
        workspace: str,
        request_id: str,
        approved: bool,
        rationale: str,
        user_approved: bool = False,
    ) -> dict[str, Any]:
        return ProtocolEngine(workspace).decide_escalation(
            request_id,
            approved=approved,
            rationale=rationale,
            user_approved=user_approved,
        )

    @server.tool(description="Install an approved contract revision at current parent HEAD and restart its execution.")
    def revise_project_contract(workspace: str, request_id: str, revised_contract: dict[str, Any]) -> dict[str, Any]:
        return ProtocolEngine(workspace).revise_contract(request_id, revised_contract)

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
