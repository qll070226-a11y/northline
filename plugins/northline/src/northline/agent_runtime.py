from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class CodexRunResult:
    status: str
    returncode: int
    command: tuple[str, ...]
    thread_id: str | None
    usage: dict[str, int]
    event_log: str
    final_message_path: str
    final_message: str | None
    error: str | None


class CodexCliRuntime:
    """Explicit, workspace-scoped adapter for the Codex non-interactive CLI."""

    def __init__(
        self,
        executable: str = "codex",
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        resolved = shutil.which(executable) if executable == "codex" else executable
        if not resolved:
            raise FileNotFoundError("Codex CLI is not installed or is not on PATH")
        self.executable = resolved
        self.runner = runner

    def execute(
        self,
        packet: dict[str, Any],
        artifact_root: str | Path,
        *,
        timeout_seconds: float = 3600,
        model: str | None = None,
        resume_thread_id: str | None = None,
    ) -> CodexRunResult:
        if timeout_seconds <= 0:
            raise ValueError("agent runtime timeout must be positive")
        workspace = Path(str(packet["workspace"])).expanduser().resolve()
        if not workspace.is_dir():
            raise FileNotFoundError(f"assigned agent workspace does not exist: {workspace}")
        artifacts = Path(artifact_root).expanduser().resolve()
        artifacts.mkdir(parents=True, exist_ok=False)
        events_path = artifacts / "events.jsonl"
        final_path = artifacts / "final-message.txt"
        command = self.build_command(workspace, final_path, model=model, resume_thread_id=resume_thread_id)
        prompt = self._prompt(packet, resume=resume_thread_id is not None)
        try:
            completed = self.runner(
                command,
                cwd=workspace,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            returncode = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            stdout = self._stream_text(exc.stdout)
            stderr = self._stream_text(exc.stderr)
            returncode = 124
            stderr = f"Codex CLI timed out after {timeout_seconds} seconds\n{stderr}".strip()
        events_path.write_text(stdout, encoding="utf-8")
        thread_id, usage, event_error, last_agent_message = self._parse_events(stdout)
        final_message = final_path.read_text(encoding="utf-8") if final_path.is_file() else last_agent_message
        error = None if returncode == 0 else (event_error or stderr[-12000:] or f"Codex CLI exited with {returncode}")
        return CodexRunResult(
            status="succeeded" if returncode == 0 else "failed",
            returncode=returncode,
            command=tuple(command),
            thread_id=thread_id or resume_thread_id,
            usage=usage,
            event_log=str(events_path),
            final_message_path=str(final_path),
            final_message=final_message,
            error=error,
        )

    def build_command(
        self,
        workspace: Path,
        final_path: Path,
        *,
        model: str | None,
        resume_thread_id: str | None,
    ) -> list[str]:
        if resume_thread_id:
            command = [
                self.executable,
                "exec",
                "--sandbox",
                "workspace-write",
                "--cd",
                str(workspace),
            ]
            if model:
                command.extend(("--model", model))
            command.extend(
                (
                    "resume",
                    "--json",
                    "--output-last-message",
                    str(final_path),
                    resume_thread_id,
                    "-",
                )
            )
            return command
        command = [
            self.executable,
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(workspace),
            "--output-last-message",
            str(final_path),
        ]
        if model:
            command.extend(("--model", model))
        command.append("-")
        return command

    @staticmethod
    def _prompt(packet: dict[str, Any], *, resume: bool) -> str:
        mode = "Resume the interrupted assignment" if resume else "Execute the assignment"
        return (
            f"{mode} described by the authoritative Northline task packet below.\n"
            "Stay inside the assigned workspace and allowed file scope. Do not edit the mission or contract. "
            "If the base is stale, scope is insufficient, or a root constraint conflicts with the task, stop and "
            "report the blocker instead of widening the work. Run the required tests and commit completed changes "
            "before reporting. A prose claim does not authorize integration.\n\n"
            f"NORTHLINE_TASK_PACKET\n{json.dumps(packet, ensure_ascii=True, indent=2)}\n"
        )

    @staticmethod
    def _parse_events(payload: str) -> tuple[str | None, dict[str, int], str | None, str | None]:
        thread_id = None
        usage: dict[str, int] = {}
        error = None
        last_agent_message = None
        for line in payload.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")
            if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                usage = {str(key): int(value) for key, value in event["usage"].items() if isinstance(value, int)}
            if event.get("type") in {"error", "turn.failed"}:
                error = str(event.get("message") or event.get("error") or event)
            item = event.get("item")
            if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
                last_agent_message = str(item.get("text", ""))
        return thread_id, usage, error, last_agent_message

    @staticmethod
    def _stream_text(value: str | bytes | None) -> str:
        if value is None:
            return ""
        return value.decode(errors="replace") if isinstance(value, bytes) else value
