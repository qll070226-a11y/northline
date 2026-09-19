from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .agent_runtime import CodexCliRuntime
from .engine import ProtocolEngine
from .version import __version__


def run_live_forward_test(
    workspace: str | Path,
    contract_id: str,
    output: str | Path,
    *,
    authorized: bool = False,
    model: str | None = None,
    timeout_seconds: float = 3600,
    resume_previous: bool = False,
    runtime: CodexCliRuntime | None = None,
    baseline: str | Path | None = None,
) -> dict[str, Any]:
    """Run or preflight one explicitly authorized live Codex contract.

    The default path is intentionally non-mutating: it validates that the
    contract is launchable and writes an authorization-required report. A
    model call happens only when ``authorized`` is true.
    """
    root = Path(workspace).expanduser().resolve()
    report_path = Path(output).expanduser().resolve()
    engine = ProtocolEngine(root)
    execution = engine.store.read_execution(contract_id)
    contract = engine.store.read_contract(contract_id)
    preflight = {
        "workspace": str(root),
        "contract_id": contract_id,
        "contract_version": int(contract.get("version", 1)),
        "execution_status": execution.get("status"),
        "assigned_workspace": execution.get("workspace"),
        "base_commit": contract.get("base_commit"),
        "resume_previous": resume_previous,
    }
    report: dict[str, Any] = {
        "report_type": "northline_live_forward_test",
        "schema_version": 1,
        "northline_version": __version__,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workspace": str(root),
        "contract_id": contract_id,
        "authorized": authorized,
        "real_model_calls": False,
        "preflight": preflight,
    }
    if not authorized:
        report.update(
            {
                "status": "authorization_required",
                "reason": "live Codex execution requires explicit Root authorization",
                "run": None,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "model_exposure_status": "not_started",
                "metrics": {
                    "elapsed_ms": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "event_count": 0,
                    "checkpoint_count": 0,
                    "manual_intervention_count": None,
                },
            }
        )
        _write(report_path, report)
        return report

    started = time.perf_counter()
    result = engine.run_codex_agent(
        contract_id,
        authorized_by_root=True,
        model=model,
        timeout_seconds=timeout_seconds,
        resume_previous=resume_previous,
        runtime=runtime,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    run = result.get("run", {})
    event_count = _line_count(run.get("event_log"))
    usage = run.get("usage") if isinstance(run.get("usage"), dict) else {}
    checkpoints = engine.store.checkpoints()
    checkpoint_count = sum(1 for item in checkpoints if item.get("contract_id") == contract_id)
    observed_tokens = sum(int(usage.get(key, 0)) for key in ("input_tokens", "output_tokens", "total_tokens"))
    metrics = {
        "elapsed_ms": elapsed_ms,
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
        "event_count": event_count,
        "checkpoint_count": checkpoint_count,
        "manual_intervention_count": None,
    }
    report.update(
        {
            "status": run.get("status", "failed"),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "real_model_calls": 1 if observed_tokens > 0 else 0,
            "model_exposure_status": "confirmed" if observed_tokens > 0 else "not_observed",
            "codex_process_started": True,
            "run": run,
            "execution": result.get("execution"),
            "metrics": metrics,
        }
    )
    if baseline is not None:
        report["baseline_comparison"] = compare_live_baseline(metrics, baseline)
    _write(report_path, report)
    return report


def compare_live_baseline(metrics: dict[str, Any], baseline: str | Path) -> dict[str, Any]:
    """Compare measurable live-run fields with a deterministic report."""
    path = Path(baseline).expanduser().resolve()
    expected = json.loads(path.read_text(encoding="utf-8"))
    baseline_metrics = expected.get("metrics") or expected.get("summary") or {}
    live_elapsed = float(metrics.get("elapsed_ms", 0))
    baseline_elapsed = float(baseline_metrics.get("elapsed_ms", 0))
    return {
        "baseline_path": str(path),
        "baseline_report_type": expected.get("report_type"),
        "elapsed_ms": {
            "live": live_elapsed,
            "baseline": baseline_elapsed,
            "delta": live_elapsed - baseline_elapsed,
        },
        "event_counts": {
            "live_codex_jsonl_events": int(metrics.get("event_count", 0)),
            "baseline_protocol_events": int(
                baseline_metrics.get("protocol_event_count", baseline_metrics.get("event_count", 0))
            ),
            "directly_comparable": False,
        },
        "live_token_metrics": {
            "input_tokens": int(metrics.get("input_tokens", 0)),
            "output_tokens": int(metrics.get("output_tokens", 0)),
            "total_tokens": int(metrics.get("total_tokens", 0)),
        },
        "live_checkpoint_count": int(metrics.get("checkpoint_count", 0)),
        "live_manual_intervention_count": metrics.get("manual_intervention_count"),
        "baseline_artifacts": {
            "artifact_count": int(baseline_metrics.get("artifact_count", 0)),
            "artifact_bytes": int(baseline_metrics.get("artifact_bytes", 0)),
        },
        "interpretation": (
            "Only elapsed time shares a unit. Codex JSONL events and Northline protocol events describe "
            "different layers and must not be treated as a direct delta."
        ),
    }


def _line_count(path_value: Any) -> int:
    if not path_value:
        return 0
    path = Path(str(path_value))
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
