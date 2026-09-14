from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol, Sequence

CONDITIONS = (
    "single_agent",
    "flat_multi_agent",
    "natural_language_recursive",
    "structured_contract",
    "full_protocol",
)


class BackendError(RuntimeError):
    """Base class for backend failures."""


class PreflightError(BackendError):
    """Failure before an agent can observe the task; excluded and retryable."""


class AgentExecutionError(BackendError):
    """Failure after task exposure; counted as an unsuccessful outcome."""


class EvaluatorError(BackendError):
    """Evaluator failure; retain the agent run and retry only evaluation."""


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    task_type: str
    objective: str
    task_family_id: str | None = None
    agent_context: dict[str, Any] = field(default_factory=dict)
    evaluator_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskSpec":
        allowed = {"task_id", "task_type", "objective", "task_family_id", "agent_context", "evaluator_context"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"task manifest has non-whitelisted fields: {sorted(unknown)}")
        return cls(
            task_id=str(payload["task_id"]),
            task_type=str(payload["task_type"]),
            objective=str(payload["objective"]),
            task_family_id=str(payload["task_family_id"]) if payload.get("task_family_id") else None,
            agent_context=dict(payload.get("agent_context", {})),
            evaluator_context=dict(payload.get("evaluator_context", {})),
        )


@dataclass(frozen=True)
class EpisodeSpec:
    task: TaskSpec
    condition: str
    seed: int
    run_fingerprint: str

    def __post_init__(self) -> None:
        if self.condition not in CONDITIONS:
            raise ValueError(f"unknown experiment condition: {self.condition}")
        if not self.run_fingerprint.strip():
            raise ValueError("run_fingerprint is required")

    @property
    def key(self) -> tuple[str, str, int, str]:
        return self.task.task_id, self.condition, self.seed, self.run_fingerprint

    def to_agent_dict(self) -> dict[str, Any]:
        return {
            "task": {"task_id": self.task.task_id, "objective": self.task.objective, "context": self.task.agent_context},
            "condition": self.condition,
            "seed": self.seed,
            "run_fingerprint": self.run_fingerprint,
        }

    def to_evaluator_dict(self) -> dict[str, Any]:
        return {
            "task": {
                "task_id": self.task.task_id,
                "task_type": self.task.task_type,
                "task_family_id": self.task.task_family_id,
                "objective": self.task.objective,
                "context": self.task.evaluator_context,
            },
            "condition": self.condition,
            "seed": self.seed,
            "run_fingerprint": self.run_fingerprint,
        }


@dataclass(frozen=True)
class AgentRun:
    final_commit: str | None
    artifacts: tuple[str, ...] = ()
    token_cost: int = 0
    latency_seconds: float = 0.0
    manual_interventions: int = 0
    retry_count: int = 0
    delegation_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentRun":
        return cls(
            final_commit=payload.get("final_commit"),
            artifacts=tuple(payload.get("artifacts", ())),
            token_cost=int(payload.get("token_cost", 0)),
            latency_seconds=float(payload.get("latency_seconds", 0.0)),
            manual_interventions=int(payload.get("manual_interventions", 0)),
            retry_count=int(payload.get("retry_count", 0)),
            delegation_count=int(payload.get("delegation_count", 0)),
            raw=dict(payload.get("raw", payload.get("agent_raw", {}))),
        )


@dataclass(frozen=True)
class EvaluationEvidence:
    root_goal_satisfied: bool
    tests_passed: bool
    scope_violation: bool
    stale_state_accepted: bool
    unsupported_completion: bool
    conflict_missed: bool
    regression: bool
    verifier_blocks: int = 0
    handoff_constraints_expected: int = 0
    handoff_constraints_preserved: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvaluationEvidence":
        required = (
            "root_goal_satisfied", "tests_passed", "scope_violation", "stale_state_accepted",
            "unsupported_completion", "conflict_missed", "regression",
        )
        missing = [name for name in required if name not in payload]
        if missing:
            raise EvaluatorError(f"evaluator omitted required outcomes: {', '.join(missing)}")
        return cls(
            **{name: bool(payload[name]) for name in required},
            verifier_blocks=int(payload.get("verifier_blocks", 0)),
            handoff_constraints_expected=int(payload.get("handoff_constraints_expected", 0)),
            handoff_constraints_preserved=int(payload.get("handoff_constraints_preserved", 0)),
            evidence=dict(payload.get("evidence", {})),
        )

    @classmethod
    def agent_failure(cls, detail: str) -> "EvaluationEvidence":
        return cls(False, False, False, False, False, False, False, evidence={"agent_failure": detail})


class AgentBackend(Protocol):
    def preflight(self, spec: EpisodeSpec) -> None: ...
    def solve(self, spec: EpisodeSpec) -> AgentRun: ...


class EpisodeEvaluator(Protocol):
    def preflight(self, spec: EpisodeSpec) -> None: ...
    def evaluate(self, spec: EpisodeSpec, run: AgentRun) -> EvaluationEvidence: ...


@dataclass(frozen=True)
class EpisodeRecord:
    spec: EpisodeSpec
    status: str
    run: AgentRun | None = None
    evaluation: EvaluationEvidence | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        eligible = self.status in {"completed", "agent_failure"}
        base: dict[str, Any] = {
            "task_id": self.spec.task.task_id,
            "task_type": self.spec.task.task_type,
            "task_family_id": self.spec.task.task_family_id or self.spec.task.task_id,
            "condition": self.spec.condition,
            "seed": self.spec.seed,
            "run_fingerprint": self.spec.run_fingerprint,
            "status": self.status,
            "analysis_eligible": eligible,
        }
        if self.run is not None:
            base.update({
                "final_commit": self.run.final_commit,
                "artifacts": list(self.run.artifacts),
                "token_cost": self.run.token_cost,
                "latency_seconds": self.run.latency_seconds,
                "manual_interventions": self.run.manual_interventions,
                "retry_count": self.run.retry_count,
                "delegation_count": self.run.delegation_count,
                "agent_raw": self.run.raw,
            })
        if self.evaluation is not None:
            outcomes = asdict(self.evaluation)
            evidence = outcomes.pop("evidence")
            base.update(outcomes)
            expected = self.evaluation.handoff_constraints_expected
            base["handoff_information_loss"] = None if expected == 0 else 1 - (
                self.evaluation.handoff_constraints_preserved / expected
            )
            base["evaluation_evidence"] = evidence
        if self.error:
            base["error"] = self.error
        return base


class JsonCommandAgentBackend:
    def __init__(self, command: Sequence[str], *, timeout_seconds: float = 1800) -> None:
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self._environment_ready = False

    def preflight(self, spec: EpisodeSpec) -> None:
        if not self.command:
            raise PreflightError("agent command is empty")
        executable = self.command[0]
        if not Path(executable).exists() and shutil.which(executable) is None:
            raise PreflightError(f"agent executable is unavailable: {executable}")
        if not self._environment_ready:
            _invoke_json(self.command, {"kind": "preflight"}, min(self.timeout_seconds, 30), PreflightError)
            self._environment_ready = True
        _invoke_json(
            self.command,
            {"kind": "task_preflight", "episode": spec.to_agent_dict()},
            min(self.timeout_seconds, 30),
            PreflightError,
        )

    def solve(self, spec: EpisodeSpec) -> AgentRun:
        payload = _invoke_json(
            self.command,
            {"kind": "agent_run", "episode": spec.to_agent_dict()},
            self.timeout_seconds,
            AgentExecutionError,
        )
        return AgentRun.from_dict(payload)


class JsonCommandEvaluator:
    def __init__(self, command: Sequence[str], *, timeout_seconds: float = 600) -> None:
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        self._environment_ready = False

    def preflight(self, spec: EpisodeSpec) -> None:
        if not self.command:
            raise PreflightError("evaluator command is empty")
        if not self._environment_ready:
            _invoke_json(self.command, {"kind": "preflight"}, min(self.timeout_seconds, 30), PreflightError)
            self._environment_ready = True
        _invoke_json(
            self.command,
            {"kind": "task_preflight", "episode": spec.to_evaluator_dict()},
            min(self.timeout_seconds, 30),
            PreflightError,
        )

    def evaluate(self, spec: EpisodeSpec, run: AgentRun) -> EvaluationEvidence:
        payload = _invoke_json(
            self.command,
            {"kind": "evaluation", "episode": spec.to_evaluator_dict(), "agent_run": asdict(run)},
            self.timeout_seconds,
            EvaluatorError,
        )
        return EvaluationEvidence.from_dict(payload)


def _invoke_json(
    command: Sequence[str], payload: dict[str, Any], timeout_seconds: float, error_type: type[BackendError]
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            input=json.dumps(payload, ensure_ascii=True),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise error_type(f"backend process failed: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-2000:]
        raise error_type(f"backend exited with {completed.returncode}: {detail}")
    try:
        decoded = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise error_type("backend stdout is not one JSON object") from exc
    if not isinstance(decoded, dict):
        raise error_type("backend response must be a JSON object")
    return decoded


def build_blocked_schedule(
    tasks: Sequence[TaskSpec], conditions: Sequence[str], seeds: Sequence[int], run_fingerprint: str, schedule_seed: int
) -> list[EpisodeSpec]:
    schedule: list[EpisodeSpec] = []
    for task in tasks:
        for seed in seeds:
            ranked = sorted(
                conditions,
                key=lambda condition: hashlib.sha256(
                    f"{schedule_seed}:{task.task_id}:{seed}:{condition}".encode("utf-8")
                ).digest(),
            )
            schedule.extend(EpisodeSpec(task, condition, int(seed), run_fingerprint) for condition in ranked)
    return schedule


class EpisodeRunner:
    def __init__(self, agent: AgentBackend, evaluator: EpisodeEvaluator) -> None:
        self.agent = agent
        self.evaluator = evaluator

    def run(
        self,
        schedule: Sequence[EpisodeSpec],
        output: Path,
        *,
        resume: bool = True,
        continue_on_error: bool = True,
    ) -> list[EpisodeRecord]:
        previous = _existing_records(output) if resume else {}
        records: list[EpisodeRecord] = []
        output.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if resume else "w"
        with output.open(mode, encoding="utf-8") as stream:
            for spec in schedule:
                prior = previous.get(spec.key)
                if prior and prior.get("status") in {"completed", "agent_failure"}:
                    continue
                if prior and prior.get("status") == "evaluation_pending":
                    run = AgentRun.from_dict(prior)
                    record = self._evaluate_only(spec, run)
                else:
                    record = self._run_once(spec)
                if not continue_on_error and record.status not in {"completed", "agent_failure"}:
                    raise BackendError(record.error or record.status)
                serialized = record.to_dict()
                stream.write(json.dumps(serialized, ensure_ascii=True) + "\n")
                stream.flush()
                previous[spec.key] = serialized
                records.append(record)
        return records

    def _run_once(self, spec: EpisodeSpec) -> EpisodeRecord:
        try:
            self.agent.preflight(spec)
            self.evaluator.preflight(spec)
        except PreflightError as exc:
            return EpisodeRecord(spec, "preflight_error", error=f"{type(exc).__name__}: {exc}")
        started = perf_counter()
        try:
            run = self.agent.solve(spec)
            if run.latency_seconds <= 0:
                run = replace(run, latency_seconds=perf_counter() - started)
        except AgentExecutionError as exc:
            elapsed = perf_counter() - started
            detail = f"{type(exc).__name__}: {exc}"
            run = AgentRun(final_commit=None, latency_seconds=elapsed, raw={"failure": detail})
            return EpisodeRecord(
                spec, "agent_failure", run=run, evaluation=EvaluationEvidence.agent_failure(detail), error=detail
            )
        return self._evaluate_only(spec, run)

    def _evaluate_only(self, spec: EpisodeSpec, run: AgentRun) -> EpisodeRecord:
        try:
            evaluation = self.evaluator.evaluate(spec, run)
            return EpisodeRecord(spec, "completed", run=run, evaluation=evaluation)
        except EvaluatorError as exc:
            return EpisodeRecord(spec, "evaluation_pending", run=run, error=f"{type(exc).__name__}: {exc}")


def _existing_records(path: Path) -> dict[tuple[str, str, int, str], dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (str(row["task_id"]), str(row["condition"]), int(row["seed"]), str(row["run_fingerprint"]))
        records[key] = row
    return records
