from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class EpisodeMetrics:
    task_id: str
    condition: str
    seed: int
    root_goal_satisfied: bool
    tests_passed: bool
    scope_violation: bool
    stale_state_accepted: bool
    unsupported_completion: bool
    conflict_missed: bool
    regression: bool
    token_cost: int = 0
    latency_seconds: float = 0.0
    manual_interventions: int = 0
    retry_count: int = 0
    delegation_count: int = 0
    verifier_blocks: int = 0
    handoff_constraints_expected: int = 0
    handoff_constraints_preserved: int = 0

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        expected = self.handoff_constraints_expected
        result["handoff_information_loss"] = None if expected == 0 else 1 - (self.handoff_constraints_preserved / expected)
        return result


def summarize(episodes: list[EpisodeMetrics]) -> dict[str, object]:
    if not episodes:
        return {"episodes": 0}
    n = len(episodes)
    boolean_fields = [
        "root_goal_satisfied", "tests_passed", "scope_violation", "stale_state_accepted",
        "unsupported_completion", "conflict_missed", "regression",
    ]
    rates = {field: sum(bool(getattr(e, field)) for e in episodes) / n for field in boolean_fields}
    losses = [e.to_dict()["handoff_information_loss"] for e in episodes if e.to_dict()["handoff_information_loss"] is not None]
    return {
        "episodes": n, "rates": rates,
        "mean_token_cost": sum(e.token_cost for e in episodes) / n,
        "mean_latency_seconds": sum(e.latency_seconds for e in episodes) / n,
        "mean_handoff_information_loss": None if not losses else sum(losses) / len(losses),
    }


def write_jsonl(path: Path, episodes: list[EpisodeMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e.to_dict(), ensure_ascii=True) + "\n" for e in episodes), encoding="utf-8")
