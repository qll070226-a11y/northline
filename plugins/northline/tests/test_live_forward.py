from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from northline.agent_runtime import CodexCliRuntime
from northline.forward_testing import _contract, _engine, _repository
from northline.live_testing import compare_live_baseline, run_live_forward_test


def test_live_forward_preflight_does_not_call_model(tmp_path: Path):
    from northline.engine import ProtocolEngine

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    # The preflight path only needs the persisted project objects. Use the
    # product's regular initializer and replace the contract execution with a
    # minimal valid record to keep this test model-free.
    engine = ProtocolEngine(workspace)
    engine.store.initialize(
        {
            "mission_id": "mission_live",
            "objective": "test live launch guard",
            "global_constraints": [],
            "decisions": [],
            "acceptance_criteria": ["report exists"],
            "root_commit": "base",
            "max_depth": 2,
            "max_children": 4,
        }
    )
    contract = {
        "contract_id": "live_contract",
        "version": 1,
        "mission_id": "mission_live",
        "parent_id": "root",
        "objective": "run guard",
        "in_scope": ["report"],
        "out_of_scope": [],
        "allowed_files": ["report.txt"],
        "forbidden_files": [],
        "dependencies": [],
        "acceptance_criteria": ["report exists"],
        "required_tests": ["python -V"],
        "base_commit": "base",
        "deadline_or_budget": None,
    }
    engine.store.save_contract(contract)
    engine.store.save_execution(
        {"contract_id": "live_contract", "status": "planned", "workspace": str(workspace), "attempt": 1}
    )
    output = tmp_path / "live.json"
    report = run_live_forward_test(workspace, "live_contract", output)
    assert report["status"] == "authorization_required"
    assert report["real_model_calls"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["contract_id"] == "live_contract"


def test_baseline_comparison_reports_deltas(tmp_path: Path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "report_type": "northline_product_forward_test",
                "summary": {"elapsed_ms": 10, "protocol_event_count": 5, "artifact_count": 4, "artifact_bytes": 100},
            }
        ),
        encoding="utf-8",
    )
    result = compare_live_baseline(
        {
            "elapsed_ms": 13,
            "event_count": 8,
            "checkpoint_count": 2,
            "manual_intervention_count": None,
            "input_tokens": 4,
            "output_tokens": 5,
            "total_tokens": 9,
        },
        baseline,
    )
    assert result["elapsed_ms"]["delta"] == 3
    assert result["event_counts"] == {
        "live_codex_jsonl_events": 8,
        "baseline_protocol_events": 5,
        "directly_comparable": False,
    }
    assert result["live_token_metrics"]["total_tokens"] == 9
    assert result["live_checkpoint_count"] == 2
    assert result["live_manual_intervention_count"] is None


def test_authorized_live_forward_records_confirmed_usage(tmp_path: Path):
    repo, base = _repository(tmp_path)
    engine = _engine(repo, base, "mission_live_authorized")
    contract = _contract(engine, "contract_live_authorized")
    engine.delegate(contract, agent_id="worker_live", role="worker")
    engine.prepare_workspace("contract_live_authorized", tmp_path / "worker")

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        final_path = Path(command[command.index("--output-last-message") + 1])
        final_path.write_text("controlled completion", encoding="utf-8")
        events = "\n".join(
            (
                '{"type":"thread.started","thread_id":"thread_live"}',
                '{"type":"turn.completed","usage":{"input_tokens":9,"output_tokens":4,"total_tokens":13}}',
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr="")

    runtime = CodexCliRuntime(executable=sys.executable, runner=runner)
    output = tmp_path / "authorized.json"
    report = run_live_forward_test(
        repo,
        "contract_live_authorized",
        output,
        authorized=True,
        runtime=runtime,
    )

    assert report["status"] == "succeeded"
    assert report["execution"]["status"] == "reporting"
    assert report["real_model_calls"] == 1
    assert report["model_exposure_status"] == "confirmed"
    assert report["metrics"]["total_tokens"] == 13
    assert report["metrics"]["event_count"] == 2
