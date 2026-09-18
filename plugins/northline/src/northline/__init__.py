"""Verifiable recursive delegation protocol."""

__version__ = "0.4.0"

from .detector import DriftDetector, DriftFinding, FindingSeverity
from .engine import ProtocolEngine
from .events import Event, EventLog
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
    ProtocolPolicy,
)
from .schema import protocol_schema, validate_payload
from .scope import ParallelSafety, assess_parallel_safety
from .state_machine import HandoffStateMachine

__all__ = [
    "AgentRole",
    "DelegationContract",
    "EscalationDecision",
    "EscalationKind",
    "EscalationRequest",
    "DriftDetector",
    "DriftFinding",
    "Event",
    "EventLog",
    "ExecutionState",
    "FindingSeverity",
    "HandoffReceipt",
    "HandoffStateMachine",
    "HandoffStatus",
    "MissionState",
    "ProtocolPolicy",
    "protocol_schema",
    "validate_payload",
    "ParallelSafety",
    "ProtocolEngine",
    "assess_parallel_safety",
    "__version__",
]
