from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

CONDITION_INSTRUCTIONS = {
    "single_agent": "Work alone. Do not delegate or create subagents.",
    "flat_multi_agent": "You are Root. You may delegate independent work directly to Workers, but Workers may not delegate further.",
    "natural_language_recursive": "You are Root. You may recursively delegate up to Root-Worker-Leaf using natural-language handoffs only.",
    "structured_contract": "You are Root. Use bounded Root-Worker-Leaf delegation and explicit objective, scope, base, tests, and acceptance criteria in every handoff.",
    "full_protocol": "You are Root. Apply the installed long-horizon delegation protocol, including contracts, isolated child work, receipts, deterministic verification, escalation, and Root-only integration.",
}


def backend_root() -> Path:
    return Path(os.environ.get("NORTHLINE_ARTIFACT_DIR", "results/backend-artifacts")).resolve()


def workspace_for(task: dict[str, object]) -> Path:
    context = task.get("context", {})
    assert isinstance(context, dict)
    explicit = context.get("workspace")
    if explicit:
        return Path(str(explicit)).resolve()
    root = Path(os.environ.get("NORTHLINE_WORKSPACE_ROOT", "workspaces")).resolve()
    return root / str(task["task_id"])


def task_preflight(episode: dict[str, object]) -> dict[str, object]:
    task = episode["task"]
    assert isinstance(task, dict)
    workspace = workspace_for(task)
    if not (workspace / ".git").exists():
        raise RuntimeError(f"workspace is not a Git checkout: {workspace}")
    remotes = subprocess.run(
        ["git", "-C", str(workspace), "remote"], capture_output=True, text=True, check=False
    )
    if remotes.returncode != 0:
        raise RuntimeError(f"cannot inspect workspace remotes: {remotes.stderr[-500:]}")
    if remotes.stdout.strip():
        raise RuntimeError("workspace still has a Git remote")
    return {"ready": True, "workspace": str(workspace)}


def prompt_for(episode: dict[str, object]) -> str:
    task = episode["task"]
    assert isinstance(task, dict)
    context = task.get("context", {})
    assert isinstance(context, dict)
    constraint_lines = [f"- {item}" for item in context.get("public_constraints", [])]
    if context.get("allowed_files"):
        constraint_lines.append(f"- Allowed files: {', '.join(context['allowed_files'])}")
    if context.get("forbidden_files"):
        constraint_lines.append(f"- Forbidden files: {', '.join(context['forbidden_files'])}")
    if context.get("required_tests"):
        constraint_lines.append(f"- Required tests: {', '.join(context['required_tests'])}")
    constraints_text = "\n".join(constraint_lines) or "- Preserve existing behavior outside the requested fix."
    condition = str(episode["condition"])
    return f"""Resolve the repository task below. Work only in the current checkout.

Condition policy:
{CONDITION_INSTRUCTIONS[condition]}

Task:
{task['objective']}

Shared constraints supplied to every condition:
{constraints_text}

Do not search the internet, inspect remotes, recover deleted Git refs, or look for benchmark answers. Do not weaken or delete tests. Run relevant visible tests. Finish with a concise summary and test evidence. Leave the final patch in the working tree; do not commit it.
"""


def run_codex(episode: dict[str, object]) -> dict[str, object]:
    task = episode["task"]
    assert isinstance(task, dict)
    workspace = workspace_for(task)

    key = f"{task['task_id']}-{episode['condition']}-{episode['seed']}-{episode['run_fingerprint'][:12]}"
    artifact_dir = backend_root() / key
    artifact_dir.mkdir(parents=True, exist_ok=True)
    trajectory = artifact_dir / "codex-events.jsonl"
    last_message = artifact_dir / "last-message.txt"
    model = os.environ.get("NORTHLINE_MODEL", "gpt-5.6-terra")
    command = [
        "codex", "exec", "--ephemeral", "--ignore-user-config", "--sandbox", "workspace-write",
        "--approve-for-me", "--json", "--output-last-message", str(last_message),
        "--model", model, "--cd", str(workspace), "-",
    ]
    started = perf_counter()
    completed = subprocess.run(command, input=prompt_for(episode), text=True, capture_output=True, check=False)
    elapsed = perf_counter() - started
    trajectory.write_text(completed.stdout, encoding="utf-8")
    (artifact_dir / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"codex exec exited with {completed.returncode}: {completed.stderr[-1000:]}")

    patch = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--binary", "--no-ext-diff"],
        capture_output=True, text=True, check=True,
    ).stdout
    patch_path = artifact_dir / "model.patch"
    patch_path.write_text(patch, encoding="utf-8")
    usage = extract_usage(completed.stdout)
    return {
        "final_commit": hashlib.sha256(patch.encode("utf-8")).hexdigest() if patch else None,
        "artifacts": [str(trajectory), str(patch_path), str(last_message)],
        "token_cost": usage["total_tokens"],
        "latency_seconds": elapsed,
        "delegation_count": usage["delegation_count"],
        "raw": {"model": model, "model_patch": patch, "usage": usage},
    }


def extract_usage(jsonl: str) -> dict[str, int]:
    totals = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "delegation_count": 0}
    latest_total = 0
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        serialized = json.dumps(event, ensure_ascii=True).lower()
        if any(marker in serialized for marker in ("spawn_agent", "delegate", "subagent")):
            totals["delegation_count"] += 1
        usage = event.get("usage") if isinstance(event, dict) else None
        if isinstance(usage, dict):
            for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                totals[key] = max(totals[key], int(usage.get(key, 0)))
            latest_total = max(latest_total, int(usage.get("total_tokens", 0)))
    totals["total_tokens"] = latest_total or totals["input_tokens"] + totals["output_tokens"]
    return totals


def preflight() -> dict[str, object]:
    version = subprocess.run(["codex", "--version"], capture_output=True, text=True, check=False)
    if version.returncode != 0:
        raise RuntimeError(f"codex CLI is unavailable: {version.stderr[-500:]}")
    auth = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, check=False)
    if auth.returncode != 0:
        raise RuntimeError(f"codex CLI authentication is unavailable: {auth.stderr[-500:]}")
    return {"ready": True, "version": version.stdout.strip(), "auth": auth.stdout.strip()}


def main() -> None:
    payload = json.load(sys.stdin)
    if payload.get("kind") == "preflight":
        print(json.dumps(preflight(), ensure_ascii=True))
        return
    if payload.get("kind") == "task_preflight":
        print(json.dumps(task_preflight(payload["episode"]), ensure_ascii=True))
        return
    if payload.get("kind") != "agent_run":
        raise ValueError("expected an agent_run payload")
    print(json.dumps(run_codex(payload["episode"]), ensure_ascii=True))


if __name__ == "__main__":
    main()
