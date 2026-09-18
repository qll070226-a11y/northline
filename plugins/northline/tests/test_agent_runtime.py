import json
import subprocess
import sys
from pathlib import Path

from northline.agent_runtime import CodexCliRuntime


def packet(workspace: Path) -> dict:
    return {
        "mission_id": "mission_runtime",
        "root_objective": "preserve the root goal",
        "root_acceptance_criteria": ["tests pass"],
        "root_decisions": [],
        "contract_id": "contract_runtime",
        "contract_version": 1,
        "attempt": 1,
        "agent_id": "worker_runtime",
        "role": "worker",
        "parent_id": "root",
        "workspace": str(workspace),
        "base_commit": "base",
        "workspace_commit": "base",
        "workspace_status": [],
        "objective": "implement the bounded change",
        "global_constraints": ["preserve API"],
        "in_scope": ["implementation"],
        "out_of_scope": ["configuration"],
        "allowed_files": ["src/**/*.py"],
        "forbidden_files": ["pyproject.toml"],
        "acceptance_criteria": ["tests pass"],
        "required_tests": ["pytest"],
        "protocol_rules": ["stay in scope"],
        "deadline_or_budget": None,
        "packet_id": "dispatch_runtime",
    }


def test_codex_runtime_uses_workspace_sandbox_and_parses_jsonl(tmp_path: Path):
    workspace = tmp_path / "work"
    workspace.mkdir()

    def runner(command, **kwargs):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("completed", encoding="utf-8")
        events = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "thread_123"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 5}}),
            )
        )
        assert "NORTHLINE_TASK_PACKET" in kwargs["input"]
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr="")

    runtime = CodexCliRuntime(executable=sys.executable, runner=runner)
    result = runtime.execute(packet(workspace), tmp_path / "artifacts", timeout_seconds=30)
    assert result.status == "succeeded"
    assert result.thread_id == "thread_123"
    assert result.usage == {"input_tokens": 20, "output_tokens": 5}
    assert result.final_message == "completed"
    assert "workspace-write" in result.command
    assert "danger-full-access" not in result.command


def test_codex_runtime_records_failed_event_and_resume_command(tmp_path: Path):
    workspace = tmp_path / "work"
    workspace.mkdir()

    def runner(command, **kwargs):
        events = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "thread_failed"}),
                json.dumps({"type": "turn.failed", "error": "model unavailable"}),
            )
        )
        return subprocess.CompletedProcess(command, 1, stdout=events, stderr="failed")

    runtime = CodexCliRuntime(executable=sys.executable, runner=runner)
    result = runtime.execute(
        packet(workspace),
        tmp_path / "resume-artifacts",
        timeout_seconds=30,
        resume_thread_id="thread_existing",
    )
    assert result.status == "failed"
    assert result.thread_id == "thread_failed"
    assert result.error == "model unavailable"
    assert "resume" in result.command
    assert "workspace-write" in result.command
    assert str(workspace.resolve()) in result.command
    assert "thread_existing" in result.command
