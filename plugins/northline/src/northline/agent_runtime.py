from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
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
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        resolved = shutil.which(executable) if executable == "codex" else executable
        if not resolved:
            raise FileNotFoundError("Codex CLI is not installed or is not on PATH")
        self.executable = resolved
        self.runner = runner

    def preflight(self, *, timeout_seconds: float = 30) -> dict[str, Any]:
        """Check CLI/auth/provider readiness without starting a model turn."""

        if timeout_seconds <= 0:
            raise ValueError("preflight timeout must be positive")
        version = self._probe([self.executable, "--version"], timeout_seconds)
        login = self._probe([self.executable, "login", "status"], timeout_seconds)
        doctor = self._probe([self.executable, "doctor"], timeout_seconds)
        auth_source = "environment" if any(os.environ.get(name) for name in ("CODEX_API_KEY", "OPENAI_API_KEY")) else "cli"
        combined = f"{doctor['stdout']}\n{doctor['stderr']}".lower()
        provider_reachable = doctor["returncode"] == 0 and not any(
            marker in combined
            for marker in (
                "endpoint.*unreachable",
                "unreachable over http",
                "websocket.*timed out",
                "handshake timed out",
                "reachability.*fail",
            )
        )
        return {
            "ready": version["returncode"] == 0 and (login["returncode"] == 0 or auth_source == "environment") and provider_reachable,
            "executable": self.executable,
            "version": (version["stdout"] or version["stderr"]).strip()[-500:],
            "login_status": (login["stdout"] or login["stderr"]).strip()[-1000:],
            "auth_source": auth_source,
            "provider_reachable": provider_reachable,
            "doctor_status": doctor["returncode"],
            "doctor_output": (doctor["stdout"] or doctor["stderr"]).strip()[-3000:],
        }

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
        if self.runner is not None:
            stdout, stderr, returncode = self._execute_test_runner(command, workspace, prompt, timeout_seconds)
            events_path.write_text(stdout, encoding="utf-8")
        else:
            stdout, stderr, returncode = self._execute_streaming(
                command, workspace, prompt, events_path, timeout_seconds
            )
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

    def _execute_test_runner(
        self,
        command: list[str],
        workspace: Path,
        prompt: str,
        timeout_seconds: float,
    ) -> tuple[str, str, int]:
        try:
            completed = self.runner(
                command,
                cwd=workspace,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
            return completed.stdout or "", completed.stderr or "", int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            return self._stream_text(exc.stdout), self._stream_text(exc.stderr), 124

    def _execute_streaming(
        self,
        command: list[str],
        workspace: Path,
        prompt: str,
        events_path: Path,
        timeout_seconds: float,
    ) -> tuple[str, str, int]:
        started = time.monotonic()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        try:
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()
            assert process.stdout is not None
            output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()

            def pump(stream: Any, channel: str) -> None:
                for value in iter(stream.readline, ""):
                    output_queue.put((channel, value))
                output_queue.put((channel, None))

            stdout_thread = threading.Thread(target=pump, args=(process.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=pump, args=(process.stderr, "stderr"), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            stdout_done = False
            stderr_done = False
            with events_path.open("w", encoding="utf-8", newline="\n") as stream:
                while not (stdout_done and stderr_done and process.poll() is not None):
                    if time.monotonic() - started >= timeout_seconds:
                        raise subprocess.TimeoutExpired(command, timeout_seconds, output="".join(stdout_lines))
                    try:
                        channel, line = output_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if line is None:
                        if channel == "stdout":
                            stdout_done = True
                        else:
                            stderr_done = True
                        continue
                    if channel == "stdout":
                        stdout_lines.append(line)
                        stream.write(line)
                        stream.flush()
                    else:
                        stderr_lines.append(line)
            process.wait(timeout=10)
            return "".join(stdout_lines), "".join(stderr_lines), int(process.returncode or 0)
        except subprocess.TimeoutExpired as exc:
            self._terminate_process(process)
            stderr = process.stderr.read() if process.stderr else ""
            partial = self._stream_text(exc.output)
            return partial or "".join(stdout_lines), stderr + f"\nCodex CLI timed out after {timeout_seconds} seconds", 124

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if shutil.which("taskkill"):
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            process.kill()
        process.wait(timeout=10)

    @staticmethod
    def _probe(command: list[str], timeout_seconds: float) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
            return {"returncode": int(completed.returncode), "stdout": completed.stdout or "", "stderr": completed.stderr or ""}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"returncode": 124, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}

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
