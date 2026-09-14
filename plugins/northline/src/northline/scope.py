from __future__ import annotations

from dataclasses import dataclass

from .models import DelegationContract


@dataclass(frozen=True)
class ParallelSafety:
    safe: bool
    reasons: tuple[str, ...]


def _static_prefix(pattern: str) -> str:
    normalized = pattern.replace("\\", "/").lstrip("./")
    wildcard_positions = [position for token in ("*", "?", "[") if (position := normalized.find(token)) >= 0]
    if wildcard_positions:
        normalized = normalized[: min(wildcard_positions)]
    return normalized.rstrip("/")


def assess_parallel_safety(left: DelegationContract, right: DelegationContract) -> ParallelSafety:
    reasons: list[str] = []
    if left.contract_id in right.dependencies or right.contract_id in left.dependencies:
        reasons.append("declared dependency requires serial execution")

    for left_pattern in left.allowed_files:
        left_prefix = _static_prefix(left_pattern)
        for right_pattern in right.allowed_files:
            right_prefix = _static_prefix(right_pattern)
            if not left_prefix or not right_prefix:
                reasons.append(f"unbounded file pattern overlap: {left_pattern} <> {right_pattern}")
            elif (
                left_prefix == right_prefix
                or left_prefix.startswith(right_prefix + "/")
                or right_prefix.startswith(left_prefix + "/")
            ):
                reasons.append(f"file scope may overlap: {left_pattern} <> {right_pattern}")

    return ParallelSafety(not reasons, tuple(dict.fromkeys(reasons)))
