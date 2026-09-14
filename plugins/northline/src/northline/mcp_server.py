from __future__ import annotations

from typing import Any

from .detector import DriftDetector
from .models import DelegationContract, HandoffReceipt, HandoffStatus, MissionState
from .project_store import ProjectStore
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
    def initialize_project(workspace: str, mission: dict[str, Any], overwrite: bool = False) -> dict[str, Any]:
        return ProjectStore(workspace).initialize(mission, overwrite=overwrite)

    @server.tool(description="Save a versioned delegation contract under the repository-local .northline control directory.")
    def save_project_contract(workspace: str, contract: dict[str, Any]) -> dict[str, Any]:
        return ProjectStore(workspace).save_contract(contract)

    @server.tool(description="Return mission and verification counts without exposing receipt contents.")
    def get_project_status(workspace: str) -> dict[str, Any]:
        return ProjectStore(workspace).status()

    @server.tool(description="Verify and record a handoff. This never integrates or modifies source files.")
    def verify_project_handoff(
        workspace: str,
        contract_id: str,
        receipt: dict[str, Any],
        current_head: str,
        expected_agent_id: str | None = None,
    ) -> dict[str, Any]:
        return ProjectStore(workspace).verify_and_record(
            contract_id, receipt, current_head, expected_agent_id
        )

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
