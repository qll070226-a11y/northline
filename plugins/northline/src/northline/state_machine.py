from __future__ import annotations

from dataclasses import dataclass, field

from .models import HandoffStatus


class InvalidTransition(ValueError):
    """Raised when a handoff attempts an unauthorized state transition."""


_ALLOWED: dict[HandoffStatus, set[HandoffStatus]] = {
    HandoffStatus.PLANNED: {HandoffStatus.CLAIMED, HandoffStatus.BLOCKED},
    HandoffStatus.CLAIMED: {HandoffStatus.EXECUTING, HandoffStatus.BLOCKED},
    HandoffStatus.EXECUTING: {
        HandoffStatus.REPORTING,
        HandoffStatus.PARTIAL,
        HandoffStatus.BLOCKED,
        HandoffStatus.STALE,
        HandoffStatus.NEEDS_PARENT_DECISION,
    },
    HandoffStatus.REPORTING: {
        HandoffStatus.VERIFIED,
        HandoffStatus.REJECTED,
        HandoffStatus.NEEDS_PARENT_DECISION,
    },
    HandoffStatus.VERIFIED: {HandoffStatus.INTEGRATED, HandoffStatus.STALE},
    HandoffStatus.INTEGRATED: set(),
    HandoffStatus.PARTIAL: {HandoffStatus.EXECUTING, HandoffStatus.BLOCKED},
    HandoffStatus.BLOCKED: {HandoffStatus.CLAIMED, HandoffStatus.EXECUTING},
    HandoffStatus.NEEDS_PARENT_DECISION: {HandoffStatus.CLAIMED, HandoffStatus.REJECTED},
    HandoffStatus.STALE: {HandoffStatus.CLAIMED, HandoffStatus.REJECTED, HandoffStatus.NEEDS_PARENT_DECISION},
    HandoffStatus.REJECTED: {HandoffStatus.CLAIMED},
}


@dataclass
class HandoffStateMachine:
    status: HandoffStatus = HandoffStatus.PLANNED
    history: list[HandoffStatus] = field(default_factory=lambda: [HandoffStatus.PLANNED])

    def transition(self, target: HandoffStatus) -> HandoffStatus:
        if target not in _ALLOWED[self.status]:
            raise InvalidTransition(f"cannot transition {self.status.value} -> {target.value}")
        self.status = target
        self.history.append(target)
        return self.status

    def can_transition(self, target: HandoffStatus) -> bool:
        return target in _ALLOWED[self.status]
