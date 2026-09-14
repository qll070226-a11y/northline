from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any


def load_evaluator(project: Path):
    path = project / "experiments" / "backends" / "controlled_evaluator.py"
    spec = importlib.util.spec_from_file_location("controlled_evaluator_validation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load evaluator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(oracle_path: Path, project: Path) -> dict[str, Any]:
    evaluator = load_evaluator(project)
    rows = json.loads(oracle_path.read_text(encoding="utf-8"))
    previous = os.environ.get("NORTHLINE_ORACLE_PATH")
    os.environ["NORTHLINE_ORACLE_PATH"] = str(oracle_path.resolve())
    results = []
    try:
        evaluator.preflight()
        for row in rows:
            task_id = str(row["opaque_task_id"])
            episode = {"task": {"task_id": task_id}}
            evaluator.task_preflight(episode)
            gold = evaluator.evaluate(episode, {"raw": {"model_patch": row["gold_patch"]}})
            empty = evaluator.evaluate(episode, {"raw": {"model_patch": ""}})
            results.append({
                "task_id": task_id,
                "gold_root_goal_satisfied": gold["root_goal_satisfied"],
                "gold_scope_violation": gold["scope_violation"],
                "empty_root_goal_satisfied": empty["root_goal_satisfied"],
                "empty_unsupported_completion": empty["unsupported_completion"],
            })
    finally:
        if previous is None:
            os.environ.pop("NORTHLINE_ORACLE_PATH", None)
        else:
            os.environ["NORTHLINE_ORACLE_PATH"] = previous
    passed = all(
        item["gold_root_goal_satisfied"]
        and not item["gold_scope_violation"]
        and not item["empty_root_goal_satisfied"]
        and item["empty_unsupported_completion"]
        for item in results
    )
    return {"status": "passed" if passed else "failed", "task_count": len(results), "tasks": results}


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Validate the controlled evaluator against gold and empty patches")
    parser.add_argument(
        "--oracle", type=Path, default=project.parent / "benchmark-data" / "controlled_pilot_oracle.json"
    )
    parser.add_argument("--output", type=Path, default=project / "results" / "controlled-evaluator-validation.json")
    args = parser.parse_args()
    report = validate(args.oracle.resolve(), project)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(args.output)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
