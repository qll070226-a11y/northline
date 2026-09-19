from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from .agent_runtime import CodexCliRuntime
from .engine import ProtocolEngine
from .models import MissionState
from .version import __version__

Scenario = Callable[[Path], dict[str, Any]]


def run_product_forward_tests(output: str | Path) -> dict[str, Any]:
    """Run isolated product workflows without starting a real model call."""

    output_path = Path(output).expanduser().resolve()
    started_at = _timestamp()
    started = perf_counter()
    scenarios: list[dict[str, Any]] = []
    definitions: tuple[tuple[str, str, Scenario], ...] = (
        ("verified_integration", "verified result is integrated and its worktree is cleaned", _verified_integration),
        ("bounded_nested_delegation", "a Worker may delegate one depth-2 Leaf with a root-aware packet", _nested),
        ("scope_violation", "a forbidden file change is rejected", _scope_violation),
        ("stale_parent", "a result based on an old parent HEAD is rejected", _stale_parent),
        ("runtime_retry", "a failed runtime is checkpointed and one bounded retry can resume", _runtime_retry),
    )
    with tempfile.TemporaryDirectory(prefix="northline-forward-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        for index, (name, expected, scenario) in enumerate(definitions, start=1):
            scenarios.append(_run_scenario(name, expected, root / f"{index:02d}-{name}", scenario))

    passed = sum(bool(item["passed"]) for item in scenarios)
    summary = {
        "scenario_count": len(scenarios),
        "passed": passed,
        "failed": len(scenarios) - passed,
        "elapsed_ms": round((perf_counter() - started) * 1000, 3),
        "protocol_event_count": sum(int(item["metrics"].get("protocol_event_count", 0)) for item in scenarios),
        "artifact_count": sum(int(item["metrics"].get("artifact_count", 0)) for item in scenarios),
        "artifact_bytes": sum(int(item["metrics"].get("artifact_bytes", 0)) for item in scenarios),
    }
    report = {
        "report_type": "northline_product_forward_test",
        "schema_version": 1,
        "northline_version": __version__,
        "started_at": started_at,
        "finished_at": _timestamp(),
        "real_model_calls": 0,
        "summary": summary,
        "scenarios": scenarios,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return report


def _run_scenario(name: str, expected: str, root: Path, scenario: Scenario) -> dict[str, Any]:
    root.mkdir(parents=True)
    started = perf_counter()
    try:
        observed = scenario(root)
        passed = bool(observed.pop("passed"))
        error = None
    except Exception as exc:
        observed = {}
        passed = False
        error = f"{type(exc).__name__}: {exc}"
    repository = root / "repo"
    metrics = _metrics(repository, started)
    return {
        "name": name,
        "expected": expected,
        "passed": passed,
        "observed": observed,
        "metrics": metrics,
        "error": error,
    }


def _verified_integration(root: Path) -> dict[str, Any]:
    repo, base = _repository(root)
    engine = _engine(repo, base, "mission_integration")
    contract = _contract(engine, "contract_integration")
    engine.delegate(contract, agent_id="worker_integration", role="worker")
    child = root / "worker"
    engine.prepare_workspace("contract_integration", child)
    _transition_to_reporting(engine, "contract_integration")
    _write_commit(child, "src/app.py", "integrated\n", "implement allowed change")
    receipt = engine.draft_receipt(
        "contract_integration",
        diff_summary="implemented the allowed application change",
        acceptance_evidence={"application behavior is updated": "required command completed"},
    )
    verification = engine.verify_handoff("contract_integration", receipt, evidence_workspace=child)
    _git(repo, "merge", "--ff-only", receipt["result_commit"])
    integration = engine.record_integration("contract_integration")
    cleanup = engine.cleanup_workspace("contract_integration", confirmed_by_root=True)
    return {
        "passed": verification["mergeable"] and integration["integrated"] and cleanup["cleaned"],
        "final_status": engine.store.read_execution("contract_integration")["status"],
        "mergeable": verification["mergeable"],
        "cleaned": cleanup["cleaned"],
    }


def _nested(root: Path) -> dict[str, Any]:
    repo, base = _repository(root)
    engine = _engine(repo, base, "mission_nested")
    worker = _contract(engine, "contract_worker", objective="coordinate the application change")
    engine.delegate(worker, agent_id="worker_nested", role="worker")
    engine.prepare_workspace("contract_worker", root / "worker")
    worker_packet = engine.create_agent_task_packet("contract_worker")
    engine.transition("contract_worker", "claimed")
    engine.transition("contract_worker", "executing")
    leaf = _contract(
        engine,
        "contract_leaf",
        objective="implement the focused helper",
        parent_id="worker_nested",
        allowed_files=("src/helper.py",),
        forbidden_files=("src/app.py",),
    )
    engine.delegate(leaf, agent_id="leaf_nested", role="leaf")
    engine.prepare_workspace("contract_leaf", root / "leaf")
    leaf_packet = engine.create_agent_task_packet("contract_leaf")
    report = engine.project_report()
    depths = {item["contract_id"]: item["depth"] for item in report["delegation_tree"]}
    passed = (
        worker_packet["role"] == "worker"
        and leaf_packet["role"] == "leaf"
        and leaf_packet["parent_id"] == "worker_nested"
        and depths == {"contract_worker": 1, "contract_leaf": 2}
    )
    return {"passed": passed, "depths": depths, "dispatch_count": report["metrics"]["dispatch_count"]}


def _scope_violation(root: Path) -> dict[str, Any]:
    repo, base = _repository(root)
    engine = _engine(repo, base, "mission_scope")
    contract = _contract(engine, "contract_scope")
    engine.delegate(contract, agent_id="worker_scope", role="worker")
    child = root / "worker"
    engine.prepare_workspace("contract_scope", child)
    _transition_to_reporting(engine, "contract_scope")
    _write_commit(child, "pyproject.toml", "[project]\nname = 'out-of-scope'\n", "change forbidden file")
    receipt = engine.draft_receipt(
        "contract_scope",
        diff_summary="changed configuration",
        acceptance_evidence={"application behavior is updated": "required command completed"},
    )
    verification = engine.verify_handoff("contract_scope", receipt, evidence_workspace=child)
    codes = sorted(item["code"] for item in verification["findings"] if item["severity"] == "block")
    cleanup = engine.cleanup_workspace("contract_scope", confirmed_by_root=True)
    return {
        "passed": not verification["mergeable"] and "FORBIDDEN_FILE" in codes and cleanup["cleaned"],
        "mergeable": verification["mergeable"],
        "blocking_findings": codes,
    }


def _stale_parent(root: Path) -> dict[str, Any]:
    repo, base = _repository(root)
    engine = _engine(repo, base, "mission_stale")
    contract = _contract(engine, "contract_stale")
    engine.delegate(contract, agent_id="worker_stale", role="worker")
    child = root / "worker"
    engine.prepare_workspace("contract_stale", child)
    _transition_to_reporting(engine, "contract_stale")
    _write_commit(child, "src/app.py", "child result\n", "child result")
    _write_commit(repo, "parent.txt", "parent advanced\n", "advance parent")
    receipt = engine.draft_receipt(
        "contract_stale",
        diff_summary="implemented against the delegated base",
        acceptance_evidence={"application behavior is updated": "required command completed"},
    )
    verification = engine.verify_handoff("contract_stale", receipt, evidence_workspace=child)
    codes = sorted(item["code"] for item in verification["findings"] if item["severity"] == "block")
    cleanup = engine.cleanup_workspace("contract_stale", confirmed_by_root=True)
    return {
        "passed": not verification["mergeable"] and "STALE_BASE" in codes and cleanup["cleaned"],
        "mergeable": verification["mergeable"],
        "blocking_findings": codes,
    }


def _runtime_retry(root: Path) -> dict[str, Any]:
    repo, base = _repository(root)
    engine = _engine(repo, base, "mission_retry")
    contract = _contract(engine, "contract_retry")
    engine.delegate(contract, agent_id="worker_retry", role="worker")
    engine.prepare_workspace("contract_retry", root / "worker")
    calls = 0

    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            events = '\n'.join(
                ('{"type":"thread.started","thread_id":"thread_forward"}',
                 '{"type":"turn.failed","error":"simulated transient failure"}')
            )
            return subprocess.CompletedProcess(command, 1, stdout=events, stderr="")
        final_path = Path(command[command.index("--output-last-message") + 1])
        final_path.write_text("simulated completion", encoding="utf-8")
        events = '\n'.join(
            ('{"type":"thread.started","thread_id":"thread_forward"}',
             '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}')
        )
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr="")

    runtime = CodexCliRuntime(executable=sys.executable, runner=runner)
    first = engine.run_codex_agent("contract_retry", authorized_by_root=True, runtime=runtime)
    retried = engine.retry_execution("contract_retry", reason="simulated transient failure")
    second = engine.run_codex_agent(
        "contract_retry", authorized_by_root=True, resume_previous=True, runtime=runtime
    )
    report = engine.project_report()
    passed = (
        first["execution"]["status"] == "partial"
        and retried["attempt"] == 2
        and second["execution"]["status"] == "reporting"
        and second["run"]["usage"] == {"input_tokens": 12, "output_tokens": 3}
    )
    return {
        "passed": passed,
        "attempt": retried["attempt"],
        "final_status": second["execution"]["status"],
        "checkpoint_count": report["metrics"]["checkpoint_count"],
        "agent_run_count": report["metrics"]["agent_run_count"],
        "resumed_thread": second["run"]["thread_id"],
    }


def _repository(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "forward-test@example.invalid")
    _git(repo, "config", "user.name", "Northline Forward Test")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _engine(repo: Path, base: str, mission_id: str) -> ProtocolEngine:
    engine = ProtocolEngine(repo)
    mission = MissionState(
        mission_id,
        "preserve the root objective while completing delegated work",
        global_constraints=("do not change build configuration",),
        acceptance_criteria=("application behavior is updated",),
        root_commit=base,
    )
    engine.initialize(mission.to_dict())
    return engine


def _contract(
    engine: ProtocolEngine,
    contract_id: str,
    *,
    objective: str = "update the application implementation",
    parent_id: str = "root",
    allowed_files: tuple[str, ...] = ("src/**/*.py",),
    forbidden_files: tuple[str, ...] = ("pyproject.toml",),
) -> dict[str, Any]:
    return engine.draft_contract(
        objective=objective,
        in_scope=("application implementation",),
        out_of_scope=("build configuration",),
        allowed_files=allowed_files,
        forbidden_files=forbidden_files,
        acceptance_criteria=("application behavior is updated",),
        required_tests=("git status --porcelain",),
        parent_id=parent_id,
        contract_id=contract_id,
    )


def _transition_to_reporting(engine: ProtocolEngine, contract_id: str) -> None:
    for state in ("claimed", "executing", "reporting"):
        engine.transition(contract_id, state)


def _write_commit(repo: Path, relative: str, content: str, message: str) -> str:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", relative)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _metrics(repo: Path, started: float) -> dict[str, Any]:
    control = repo / ".northline"
    artifacts = [path for path in control.rglob("*") if path.is_file()] if control.is_dir() else []
    events = control / "events.jsonl"
    event_count = len(events.read_text(encoding="utf-8").splitlines()) if events.is_file() else 0
    return {
        "elapsed_ms": round((perf_counter() - started) * 1000, 3),
        "protocol_event_count": event_count,
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(path.stat().st_size for path in artifacts),
    }


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=repo, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
