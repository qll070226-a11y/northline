from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class AgentRole(str, Enum):
    ROOT = "root"
    WORKER = "worker"
    LEAF = "leaf"
    VERIFIER = "verifier"
    INTEGRATOR = "integrator"


class HandoffStatus(str, Enum):
    PLANNED = "planned"
    CLAIMED = "claimed"
    EXECUTING = "executing"
    REPORTING = "reporting"
    VERIFIED = "verified"
    INTEGRATED = "integrated"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    NEEDS_PARENT_DECISION = "needs_parent_decision"
    STALE = "stale"
    REJECTED = "rejected"


class EscalationKind(str, Enum):
    STALE_STATE = "stale_state"
    SCOPE_CHANGE = "scope_change"
    ROOT_CONSTRAINT_CONFLICT = "root_constraint_conflict"
    BLOCKED = "blocked"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class MissionState:
    mission_id: str
    objective: str
    global_constraints: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    root_commit: str | None = None
    max_depth: int = 2
    max_children: int = 4

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("mission objective must not be empty")
        if not 0 <= self.max_depth <= 2:
            raise ValueError("v1 max_depth must be between 0 and 2")
        if self.max_children < 1:
            raise ValueError("max_children must be positive")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionState":
        return cls(
            mission_id=str(data["mission_id"]),
            objective=str(data["objective"]),
            global_constraints=tuple(data.get("global_constraints", ())),
            decisions=tuple(data.get("decisions", ())),
            acceptance_criteria=tuple(data.get("acceptance_criteria", ())),
            root_commit=data.get("root_commit"),
            max_depth=int(data.get("max_depth", 2)),
            max_children=int(data.get("max_children", 4)),
        )


@dataclass(frozen=True)
class ProtocolPolicy:
    require_isolated_workspace: bool = True
    require_clean_evidence_workspace: bool = True
    require_required_tests: bool = True
    max_changed_files: int = 200
    max_test_timeout_seconds: float = 600
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError("unsupported policy version")
        if self.max_changed_files < 1:
            raise ValueError("max_changed_files must be positive")
        if not 1 <= self.max_test_timeout_seconds <= 3600:
            raise ValueError("max_test_timeout_seconds must be between 1 and 3600")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProtocolPolicy":
        if data is None:
            return cls()
        return cls(
            require_isolated_workspace=bool(data.get("require_isolated_workspace", True)),
            require_clean_evidence_workspace=bool(data.get("require_clean_evidence_workspace", True)),
            require_required_tests=bool(data.get("require_required_tests", True)),
            max_changed_files=int(data.get("max_changed_files", 200)),
            max_test_timeout_seconds=float(data.get("max_test_timeout_seconds", 600)),
            version=int(data.get("version", 1)),
        )


@dataclass(frozen=True)
class DelegationContract:
    objective: str
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    allowed_files: tuple[str, ...]
    forbidden_files: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    required_tests: tuple[str, ...]
    base_commit: str
    parent_id: str
    mission_id: str
    version: int = 1
    dependencies: tuple[str, ...] = ()
    deadline_or_budget: str | None = None
    contract_id: str = field(default_factory=lambda: _id("contract"))

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("contract objective must not be empty")
        if not self.base_commit.strip():
            raise ValueError("base_commit is required")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if not self.acceptance_criteria:
            raise ValueError("at least one acceptance criterion is required")
        forbidden = set(self.forbidden_files)
        overlap = forbidden.intersection(self.allowed_files)
        if overlap:
            raise ValueError(f"file cannot be both allowed and forbidden: {sorted(overlap)}")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DelegationContract":
        tuple_fields = {
            name: tuple(data.get(name, ()))
            for name in ("in_scope", "out_of_scope", "allowed_files", "forbidden_files", "acceptance_criteria", "required_tests", "dependencies")
        }
        return cls(
            objective=str(data["objective"]), base_commit=str(data["base_commit"]),
            parent_id=str(data["parent_id"]), mission_id=str(data["mission_id"]),
            version=int(data.get("version", 1)), deadline_or_budget=data.get("deadline_or_budget"),
            contract_id=str(data.get("contract_id") or _id("contract")), **tuple_fields,
        )


@dataclass(frozen=True)
class ExecutionState:
    contract_id: str
    agent_id: str
    role: AgentRole
    status: HandoffStatus = HandoffStatus.PLANNED
    workspace: str | None = None
    current_commit: str | None = None
    tests_run: tuple[str, ...] = ()
    test_results: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class AgentTaskPacket:
    mission_id: str
    root_objective: str
    root_acceptance_criteria: tuple[str, ...]
    root_decisions: tuple[str, ...]
    contract_id: str
    contract_version: int
    agent_id: str
    role: AgentRole
    parent_id: str
    workspace: str
    base_commit: str
    objective: str
    global_constraints: tuple[str, ...]
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    allowed_files: tuple[str, ...]
    forbidden_files: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    required_tests: tuple[str, ...]
    protocol_rules: tuple[str, ...]
    deadline_or_budget: str | None = None
    packet_id: str = field(default_factory=lambda: _id("dispatch"))

    def __post_init__(self) -> None:
        if self.contract_version < 1:
            raise ValueError("contract_version must be >= 1")
        if self.role not in {AgentRole.WORKER, AgentRole.LEAF}:
            raise ValueError("task packets can only target worker or leaf agents")
        if not self.workspace.strip() or not self.base_commit.strip():
            raise ValueError("task packet requires workspace and base commit")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class AgentCheckpoint:
    contract_id: str
    contract_version: int
    agent_id: str
    status: HandoffStatus
    current_commit: str
    completed: tuple[str, ...]
    pending: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    workspace_status: tuple[str, ...] = ()
    checkpoint_id: str = field(default_factory=lambda: _id("checkpoint"))

    def __post_init__(self) -> None:
        if self.contract_version < 1:
            raise ValueError("contract_version must be >= 1")
        if self.status not in {
            HandoffStatus.CLAIMED,
            HandoffStatus.EXECUTING,
            HandoffStatus.PARTIAL,
            HandoffStatus.BLOCKED,
        }:
            raise ValueError("checkpoint status must describe active or interrupted work")
        if not self.current_commit.strip():
            raise ValueError("checkpoint current_commit is required")
        if not self.completed and not self.pending and not self.blockers:
            raise ValueError("checkpoint must record progress, pending work, or blockers")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentCheckpoint":
        return cls(
            contract_id=str(data["contract_id"]),
            contract_version=int(data["contract_version"]),
            agent_id=str(data["agent_id"]),
            status=HandoffStatus(data["status"]),
            current_commit=str(data["current_commit"]),
            completed=tuple(data.get("completed", ())),
            pending=tuple(data.get("pending", ())),
            blockers=tuple(data.get("blockers", ())),
            notes=tuple(data.get("notes", ())),
            workspace_status=tuple(data.get("workspace_status", ())),
            checkpoint_id=str(data.get("checkpoint_id") or _id("checkpoint")),
        )


@dataclass(frozen=True)
class HandoffReceipt:
    contract_id: str
    agent_id: str
    status: HandoffStatus
    base_commit: str
    result_commit: str | None
    changed_files: tuple[str, ...]
    diff_summary: str
    tests_run: tuple[str, ...]
    test_results: tuple[str, ...]
    evidence_links: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    acceptance_evidence: dict[str, str] = field(default_factory=dict)
    recommended_next_action: str | None = None
    contract_version: int = 1
    receipt_id: str = field(default_factory=lambda: _id("receipt"))

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HandoffReceipt":
        tuple_fields = {
            name: tuple(data.get(name, ()))
            for name in ("changed_files", "tests_run", "test_results", "evidence_links", "assumptions", "risks", "unresolved_questions")
        }
        return cls(
            contract_id=str(data["contract_id"]), agent_id=str(data["agent_id"]),
            status=HandoffStatus(data["status"]), base_commit=str(data["base_commit"]),
            result_commit=data.get("result_commit"), diff_summary=str(data.get("diff_summary", "")),
            acceptance_evidence=dict(data.get("acceptance_evidence", {})),
            recommended_next_action=data.get("recommended_next_action"),
            contract_version=int(data.get("contract_version", 1)),
            receipt_id=str(data.get("receipt_id") or _id("receipt")), **tuple_fields,
        )


@dataclass(frozen=True)
class EscalationRequest:
    contract_id: str
    contract_version: int
    agent_id: str
    kinds: tuple[EscalationKind, ...]
    contract_base_commit: str
    workspace_merge_base: str
    parent_head: str
    blocking_evidence: tuple[str, ...]
    requested_changes: dict[str, Any]
    alternatives: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    requires_user_decision: bool = False
    stopped_work: bool = True
    request_id: str = field(default_factory=lambda: _id("escalation"))

    def __post_init__(self) -> None:
        if self.contract_version < 1:
            raise ValueError("contract_version must be >= 1")
        if not self.kinds:
            raise ValueError("at least one escalation kind is required")
        if not self.blocking_evidence:
            raise ValueError("blocking evidence is required")
        if not all((self.contract_base_commit, self.workspace_merge_base, self.parent_head)):
            raise ValueError("all three commit references are required")
        if EscalationKind.ROOT_CONSTRAINT_CONFLICT in self.kinds and not self.requires_user_decision:
            raise ValueError("root-constraint conflicts require an explicit user decision")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EscalationRequest":
        return cls(
            contract_id=str(data["contract_id"]),
            contract_version=int(data["contract_version"]),
            agent_id=str(data["agent_id"]),
            kinds=tuple(EscalationKind(item) for item in data["kinds"]),
            contract_base_commit=str(data["contract_base_commit"]),
            workspace_merge_base=str(data["workspace_merge_base"]),
            parent_head=str(data["parent_head"]),
            blocking_evidence=tuple(data["blocking_evidence"]),
            requested_changes=dict(data["requested_changes"]),
            alternatives=tuple(data.get("alternatives", ())),
            risks=tuple(data.get("risks", ())),
            required_tests=tuple(data.get("required_tests", ())),
            requires_user_decision=bool(data.get("requires_user_decision", False)),
            stopped_work=bool(data.get("stopped_work", True)),
            request_id=str(data["request_id"]),
        )


@dataclass(frozen=True)
class EscalationDecision:
    request_id: str
    contract_id: str
    approved: bool
    rationale: str
    decided_by: AgentRole = AgentRole.ROOT
    user_approved: bool = False

    def __post_init__(self) -> None:
        if self.decided_by != AgentRole.ROOT:
            raise ValueError("only root can record an escalation decision")
        if not self.rationale.strip():
            raise ValueError("decision rationale is required")

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))
