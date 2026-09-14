from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from northline.episode import (
    CONDITIONS,
    EpisodeRunner,
    JsonCommandAgentBackend,
    JsonCommandEvaluator,
    TaskSpec,
    build_blocked_schedule,
)


def load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or plan paired long-horizon delegation episodes")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/episodes.jsonl"))
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    config = load_json(args.config)
    tasks = [TaskSpec.from_dict(item) for item in manifest.get("tasks", [])]
    conditions = [str(item) for item in config.get("conditions", CONDITIONS)]
    seeds = [int(item) for item in config.get("seeds", [0])]
    invalid = sorted(set(conditions) - set(CONDITIONS))
    if invalid:
        raise ValueError(f"unknown conditions: {invalid}")
    manifest_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    fingerprint_fields = {
        "manifest_sha256": manifest_hash,
        "conditions": conditions,
        "seeds": seeds,
        "model_id": config.get("model_id", "unset"),
        "prompt_version": config.get("prompt_version", "unset"),
        "protocol_version": config.get("protocol_version", "0.1.0"),
        "budgets": config.get("budgets", {}),
        "agent_command": config.get("agent_command", []),
        "evaluator_command": config.get("evaluator_command", []),
    }
    run_fingerprint = stable_hash(fingerprint_fields)
    schedule_seed = int(config.get("schedule_seed", 20260912))
    schedule = build_blocked_schedule(tasks, conditions, seeds, run_fingerprint, schedule_seed)
    schedule_rows = [
        {"position": index, "task_id": spec.task.task_id, "seed": spec.seed, "condition": spec.condition}
        for index, spec in enumerate(schedule, start=1)
    ]
    schedule_hash = stable_hash(schedule_rows)

    if args.plan_only:
        plan = {
            "tasks": len(tasks),
            "conditions": conditions,
            "seeds": seeds,
            "episode_count": len(tasks) * len(conditions) * len(seeds),
            "paired_by": ["task_id", "seed"],
            "condition_order": "SHA-256 blocked randomization within task_id x seed",
            "schedule_seed": schedule_seed,
            "manifest_sha256": manifest_hash,
            "run_fingerprint": run_fingerprint,
            "schedule_sha256": schedule_hash,
            "schedule": schedule_rows,
            "executes_models": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(args.output)
        return

    agent_command = config.get("agent_command")
    evaluator_command = config.get("evaluator_command")
    if not isinstance(agent_command, list) or not isinstance(evaluator_command, list):
        raise ValueError("config must provide agent_command and evaluator_command arrays")
    runner = EpisodeRunner(
        JsonCommandAgentBackend([str(item) for item in agent_command], timeout_seconds=float(config.get("agent_timeout_seconds", 1800))),
        JsonCommandEvaluator([str(item) for item in evaluator_command], timeout_seconds=float(config.get("evaluator_timeout_seconds", 600))),
    )
    records = runner.run(
        schedule,
        args.output,
        resume=not args.no_resume,
        continue_on_error=bool(config.get("continue_on_error", True)),
    )
    print(json.dumps({"output": str(args.output), "new_records": len(records), "run_fingerprint": run_fingerprint}, indent=2))


if __name__ == "__main__":
    main()
