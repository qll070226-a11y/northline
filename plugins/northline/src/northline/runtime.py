from __future__ import annotations

from dataclasses import dataclass, field

from .detector import DriftDetector, DriftFinding, FindingSeverity
from .events import EventLog
from .models import (
    AgentRole,
    DelegationContract,
    EscalationDecision,
    EscalationKind,
    EscalationRequest,
    ExecutionState,
    HandoffReceipt,
    HandoffStatus,
    MissionState,
)
from .state_machine import HandoffStateMachine


@dataclass
class AgentNode:
    agent_id: str
    role: AgentRole
    depth: int
    parent_id: str | None = None
    children: list[str] = field(default_factory=list)


class DelegationRuntime:
    """Framework-neutral deterministic runtime used by tests and experiment smoke runs."""

    def __init__(self, mission: MissionState, event_log: EventLog | None = None) -> None:
        self.mission = mission
        self.detector = DriftDetector()
        self.event_log = event_log or EventLog()
        self.nodes: dict[str, AgentNode] = {"root": AgentNode("root", AgentRole.ROOT, 0)}
        self.contracts: dict[str, DelegationContract] = {}
        self.receipts: dict[str, HandoffReceipt] = {}
        self.transitions: dict[str, HandoffStateMachine] = {}
        self.assignments: dict[str, str] = {}
        self.contract_history: dict[str, list[DelegationContract]] = {}
        self.escalations: dict[str, EscalationRequest] = {}
        self.escalation_decisions: dict[str, EscalationDecision] = {}

    def delegate(self, parent_id: str, contract: DelegationContract, role: AgentRole) -> ExecutionState:
        parent = self.nodes.get(parent_id)
        if parent is None:
            raise ValueError(f"unknown parent: {parent_id}")
        if parent.role == AgentRole.LEAF:
            raise ValueError("leaf agents cannot delegate")
        if parent.depth >= self.mission.max_depth:
            raise ValueError("maximum recursion depth reached")
        if len(parent.children) >= self.mission.max_children:
            raise ValueError("maximum child count reached")
        if contract.parent_id != parent_id or contract.mission_id != self.mission.mission_id:
            raise ValueError("contract parent or mission does not match runtime")
        if contract.contract_id in self.contracts:
            raise ValueError("contract_id already exists")
        unknown_dependencies = [dependency for dependency in contract.dependencies if dependency not in self.contracts]
        if unknown_dependencies:
            raise ValueError(f"unknown contract dependencies: {unknown_dependencies}")
        if role not in {AgentRole.WORKER, AgentRole.LEAF}:
            raise ValueError("delegated role must be worker or leaf")
        expected_role = AgentRole.WORKER if parent.role == AgentRole.ROOT else AgentRole.LEAF
        if role != expected_role:
            raise ValueError(f"{parent.role.value} must delegate to {expected_role.value}")
        agent_id = f"{role.value}_{len(self.nodes):03d}"
        self.nodes[agent_id] = AgentNode(agent_id, role, parent.depth + 1, parent_id)
        parent.children.append(agent_id)
        self.contracts[contract.contract_id] = contract
        self.contract_history[contract.contract_id] = [contract]
        self.transitions[contract.contract_id] = HandoffStateMachine()
        self.assignments[contract.contract_id] = agent_id
        self.event_log.append("delegated", self.mission.mission_id, parent_id, contract_id=contract.contract_id, payload={"agent_id": agent_id, "role": role.value, "depth": parent.depth + 1})
        return ExecutionState(contract.contract_id, agent_id, role, HandoffStatus.PLANNED, current_commit=contract.base_commit)

    def submit_escalation(self, request: EscalationRequest) -> HandoffStatus:
        contract = self.contracts[request.contract_id]
        if self.transitions[request.contract_id].status != HandoffStatus.EXECUTING:
            raise ValueError("escalations can only be submitted while executing")
        if request.agent_id != self.assignments[request.contract_id]:
            raise ValueError("escalation requester is not assigned to the contract")
        if request.contract_version != contract.version:
            raise ValueError("escalation uses a stale contract version")
        if not request.stopped_work:
            raise ValueError("agent must stop work before escalating")
        self.escalations[request.request_id] = request
        has_stale_state = EscalationKind.STALE_STATE in request.kinds or request.contract_base_commit != request.parent_head
        needs_decision = bool(request.requested_changes) or request.requires_user_decision or any(
            kind in request.kinds for kind in (EscalationKind.SCOPE_CHANGE, EscalationKind.ROOT_CONSTRAINT_CONFLICT)
        )
        if has_stale_state:
            self.advance(request.contract_id, HandoffStatus.STALE)
        if needs_decision:
            self.advance(request.contract_id, HandoffStatus.NEEDS_PARENT_DECISION)
        elif not has_stale_state:
            self.advance(request.contract_id, HandoffStatus.BLOCKED)
        self.event_log.append("escalation_submitted", self.mission.mission_id, request.agent_id, contract_id=request.contract_id, payload={"request_id": request.request_id, "kinds": [kind.value for kind in request.kinds]})
        return self.transitions[request.contract_id].status

    def resolve_escalation(self, request_id: str, *, approved: bool, rationale: str, user_approved: bool = False) -> EscalationDecision:
        request = self.escalations[request_id]
        status = self.transitions[request.contract_id].status
        if status not in {HandoffStatus.NEEDS_PARENT_DECISION, HandoffStatus.STALE, HandoffStatus.BLOCKED}:
            raise ValueError("escalation can only be resolved from a waiting state")
        if request_id in self.escalation_decisions:
            raise ValueError("escalation already has a recorded decision")
        if request.requires_user_decision and approved and not user_approved:
            raise ValueError("this root-constraint change requires explicit user approval")
        decision = EscalationDecision(request_id, request.contract_id, approved, rationale, user_approved=user_approved)
        self.escalation_decisions[request_id] = decision
        self.event_log.append("escalation_decided", self.mission.mission_id, "root", contract_id=request.contract_id, payload=decision.to_dict())
        if not approved:
            self.advance(request.contract_id, HandoffStatus.REJECTED)
        return decision

    def revise_contract(self, request_id: str, revised: DelegationContract, *, current_head: str) -> ExecutionState:
        request = self.escalations[request_id]
        decision = self.escalation_decisions.get(request_id)
        current = self.contracts[request.contract_id]
        if decision is None or not decision.approved:
            raise ValueError("contract revision requires an approved escalation")
        if decision.contract_id != request.contract_id:
            raise ValueError("escalation decision references a different contract")
        if revised.contract_id != current.contract_id or revised.version != current.version + 1:
            raise ValueError("revised contract must keep its id and increment version by one")
        if revised.mission_id != current.mission_id or revised.parent_id != current.parent_id:
            raise ValueError("revision cannot change mission or parent")
        if revised.base_commit != current_head:
            raise ValueError("revised contract must use the current parent head")
        self.contracts[revised.contract_id] = revised
        self.contract_history[revised.contract_id].append(revised)
        self.transitions[revised.contract_id] = HandoffStateMachine()
        agent_id = self.assignments[revised.contract_id]
        role = self.nodes[agent_id].role
        self.event_log.append("contract_revised", self.mission.mission_id, "root", contract_id=revised.contract_id, payload={"request_id": request_id, "old_version": current.version, "new_version": revised.version, "base_commit": revised.base_commit})
        return ExecutionState(revised.contract_id, agent_id, role, HandoffStatus.PLANNED, current_commit=revised.base_commit)

    def advance(self, contract_id: str, target: HandoffStatus) -> HandoffStatus:
        machine = self.transitions[contract_id]
        status = machine.transition(target)
        self.event_log.append("state_transition", self.mission.mission_id, "runtime", contract_id=contract_id, payload={"status": status.value})
        return status

    def submit_receipt(self, receipt: HandoffReceipt, *, current_head: str | None = None) -> list[DriftFinding]:
        contract = self.contracts[receipt.contract_id]
        if self.transitions[receipt.contract_id].status != HandoffStatus.REPORTING:
            raise ValueError("receipt can only be submitted while runtime is reporting")
        findings = self.detector.inspect(
            self.mission,
            contract,
            receipt,
            current_head=current_head,
            root_constraints=self.mission.global_constraints,
            expected_agent_id=self.assignments[receipt.contract_id],
        )
        self.event_log.append("receipt_verified" if self.detector.is_mergeable(findings) else "receipt_rejected", self.mission.mission_id, receipt.agent_id, contract_id=receipt.contract_id, payload={"finding_codes": [f.code for f in findings]})
        if self.detector.is_mergeable(findings):
            self.receipts[receipt.contract_id] = receipt
        return findings

    def verify_receipt(self, contract_id: str, receipt: HandoffReceipt, *, current_head: str | None = None) -> list[DriftFinding]:
        if contract_id != receipt.contract_id:
            raise ValueError("contract_id does not match receipt.contract_id")
        contract = self.contracts[contract_id]
        if self.transitions[contract_id].status != HandoffStatus.REPORTING:
            raise ValueError("integration requires reporting runtime state")
        missing_dependencies = [
            dependency for dependency in contract.dependencies
            if dependency not in self.transitions or self.transitions[dependency].status != HandoffStatus.INTEGRATED
        ]
        if missing_dependencies:
            finding = DriftFinding(
                "DEPENDENCY_NOT_INTEGRATED",
                FindingSeverity.BLOCK,
                "contract dependencies are not integrated",
                ", ".join(missing_dependencies),
            )
            self.event_log.append("receipt_rejected", self.mission.mission_id, receipt.agent_id, contract_id=contract_id, payload={"finding_codes": [finding.code]})
            self.advance(contract_id, HandoffStatus.REJECTED)
            return [finding]
        findings = self.submit_receipt(receipt, current_head=current_head)
        if not self.detector.is_mergeable(findings):
            self.advance(contract_id, HandoffStatus.REJECTED)
            return findings
        if not self.transitions[contract_id].can_transition(HandoffStatus.VERIFIED):
            raise ValueError("receipt can only be verified after reporting")
        self.advance(contract_id, HandoffStatus.VERIFIED)
        return findings

    def mark_integrated(self, contract_id: str) -> HandoffStatus:
        if self.transitions[contract_id].status != HandoffStatus.VERIFIED:
            raise ValueError("only verified work can be marked integrated")
        self.advance(contract_id, HandoffStatus.INTEGRATED)
        return self.transitions[contract_id].status


def demo_runtime() -> DelegationRuntime:
    mission = MissionState(
        mission_id="demo-mission",
        objective="Add a safe parsing helper without changing the public API.",
        global_constraints=("public API must remain backwards compatible",),
        acceptance_criteria=("unit tests pass", "no public signature changes"),
        root_commit="demo-base",
    )
    runtime = DelegationRuntime(mission)
    contract = DelegationContract(
        objective="Implement the parser helper and tests.",
        in_scope=("parser helper", "unit tests"),
        out_of_scope=("public API redesign",),
        allowed_files=("src/**/*.py", "tests/**/*.py"),
        forbidden_files=("pyproject.toml",),
        acceptance_criteria=("unit tests pass",),
        required_tests=("python -m unittest discover -s tests",),
        base_commit="demo-base",
        parent_id="root",
        mission_id=mission.mission_id,
    )
    execution = runtime.delegate("root", contract, AgentRole.WORKER)
    runtime.advance(contract.contract_id, HandoffStatus.CLAIMED)
    runtime.advance(contract.contract_id, HandoffStatus.EXECUTING)
    runtime.advance(contract.contract_id, HandoffStatus.REPORTING)
    receipt = HandoffReceipt(
        contract_id=contract.contract_id,
        agent_id=execution.agent_id,
        status=HandoffStatus.REPORTING,
        base_commit="demo-base",
        result_commit="demo-result",
        changed_files=("src/parser.py", "tests/test_parser.py"),
        diff_summary="Added parser helper and unit tests.",
        tests_run=("python -m unittest discover -s tests",),
        test_results=("pass",),
        acceptance_evidence={"unit tests pass": "python -m unittest discover -s tests: pass"},
    )
    runtime.verify_receipt(contract.contract_id, receipt, current_head="demo-base")
    runtime.mark_integrated(contract.contract_id)
    return runtime
