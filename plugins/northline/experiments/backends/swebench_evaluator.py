from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def load_oracle(task_id: str) -> dict[str, object]:
    path_value = os.environ.get("NORTHLINE_ORACLE_PATH")
    if not path_value:
        raise RuntimeError("NORTHLINE_ORACLE_PATH is required")
    rows = json.loads(Path(path_value).read_text(encoding="utf-8"))
    matches = [row for row in rows if row.get("opaque_task_id") == task_id]
    if len(matches) != 1:
        raise RuntimeError(f"sealed oracle has {len(matches)} matches for {task_id}")
    return matches[0]


def evaluate(episode: dict[str, object], run: dict[str, object]) -> dict[str, object]:
    task = episode["task"]
    assert isinstance(task, dict)
    task_id = str(task["task_id"])
    oracle = load_oracle(task_id)
    raw = run.get("raw", {})
    if not isinstance(raw, dict):
        raw = {}
    patch = str(raw.get("model_patch", ""))
    patch_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    run_id = "northline-{}-{}-{}-{}-{}".format(
        episode["run_fingerprint"][:10], episode["condition"], episode["seed"], task_id, patch_hash[:10]
    )
    artifact_root = Path(os.environ.get("NORTHLINE_EVAL_DIR", "results/swebench-eval")).resolve()
    artifact_dir = artifact_root / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = artifact_dir / "prediction.jsonl"
    prediction = {
        "instance_id": oracle["instance_id"],
        "model_patch": patch,
        "model_name_or_path": raw.get("model", "unknown"),
    }
    prediction_path.write_text(json.dumps(prediction, ensure_ascii=True) + "\n", encoding="utf-8")
    command = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", "SWE-bench/SWE-bench_Verified",
        "--predictions_path", str(prediction_path),
        "--max_workers", "1",
        "--run_id", run_id,
        "--instance_ids", str(oracle["instance_id"]),
        "--timeout", os.environ.get("NORTHLINE_EVAL_TIMEOUT", "1800"),
    ]
    if os.environ.get("NORTHLINE_USE_MODAL", "false").lower() == "true":
        command.extend(("--modal", "true"))
    completed = subprocess.run(command, cwd=artifact_dir, capture_output=True, text=True, check=False)
    (artifact_dir / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (artifact_dir / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"SWE-bench evaluator exited with {completed.returncode}: {completed.stderr[-1000:]}")
    report = locate_report(artifact_dir, run_id)
    resolved = str(oracle["instance_id"]) in set(report.get("resolved_ids", []))
    return {
        "root_goal_satisfied": resolved,
        "tests_passed": resolved,
        "scope_violation": False,
        "stale_state_accepted": False,
        "unsupported_completion": not bool(patch),
        "conflict_missed": False,
        "regression": not resolved,
        "evidence": {"run_id": run_id, "patch_sha256": patch_hash, "report": report},
    }


def locate_report(root: Path, run_id: str) -> dict[str, object]:
    candidates = list(root.rglob("results.json")) + list(root.rglob(f"*{run_id}*.json"))
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            if "resolved_ids" in payload:
                return payload
            for value in payload.values():
                if isinstance(value, dict) and "resolved_ids" in value:
                    return value
    raise RuntimeError(f"could not locate SWE-bench result report below {root}")


def preflight() -> dict[str, object]:
    oracle_path = os.environ.get("NORTHLINE_ORACLE_PATH")
    if not oracle_path or not Path(oracle_path).is_file():
        raise RuntimeError("sealed oracle is unavailable")
    if os.environ.get("NORTHLINE_USE_MODAL", "false").lower() == "true":
        check = subprocess.run([sys.executable, "-m", "modal", "token", "current"], capture_output=True, text=True, check=False)
    else:
        check = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True, check=False)
    if check.returncode != 0:
        raise RuntimeError(f"evaluation runtime is unavailable: {check.stderr[-500:]}")
    modal = os.environ.get("NORTHLINE_USE_MODAL", "false").lower() == "true"
    return {"ready": True, "runtime": "modal" if modal else "docker"}


def task_preflight(episode: dict[str, object]) -> dict[str, object]:
    task = episode["task"]
    assert isinstance(task, dict)
    oracle = load_oracle(str(task["task_id"]))
    if not oracle.get("instance_id"):
        raise RuntimeError("sealed oracle row is missing instance_id")
    return {"ready": True, "task_id": task["task_id"]}


def main() -> None:
    payload = json.load(sys.stdin)
    if payload.get("kind") == "preflight":
        print(json.dumps(preflight(), ensure_ascii=True))
        return
    if payload.get("kind") == "task_preflight":
        print(json.dumps(task_preflight(payload["episode"]), ensure_ascii=True))
        return
    if payload.get("kind") != "evaluation":
        raise ValueError("expected an evaluation payload")
    print(json.dumps(evaluate(payload["episode"], payload["agent_run"]), ensure_ascii=True))


if __name__ == "__main__":
    main()
