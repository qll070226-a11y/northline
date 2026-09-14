from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def load_oracle(task_id: str) -> dict[str, Any]:
    path_value = os.environ.get("NORTHLINE_ORACLE_PATH")
    if not path_value:
        raise RuntimeError("NORTHLINE_ORACLE_PATH is required")
    rows = json.loads(Path(path_value).read_text(encoding="utf-8"))
    matches = [row for row in rows if row.get("opaque_task_id") == task_id]
    if len(matches) != 1:
        raise RuntimeError(f"sealed oracle has {len(matches)} matches for {task_id}")
    return matches[0]


def main() -> None:
    payload = json.load(sys.stdin)
    kind = payload.get("kind")
    if kind == "preflight":
        print(json.dumps({"ready": True, "backend": "sealed_patch_evaluator_validation"}))
        return
    if kind == "task_preflight":
        task = payload["episode"]["task"]
        load_oracle(str(task["task_id"]))
        print(json.dumps({"ready": True, "task_id": task["task_id"]}))
        return
    if kind != "agent_run":
        raise ValueError("expected an agent_run payload")
    task = payload["episode"]["task"]
    oracle = load_oracle(str(task["task_id"]))
    patch = str(oracle["gold_patch"])
    print(json.dumps({
        "final_commit": "sealed-gold-patch",
        "token_cost": 0,
        "latency_seconds": 0.0,
        "raw": {"model": "sealed-oracle-validation-only", "model_patch": patch},
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
