"""Audit controlled-task blueprints before expensive build and model runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

TASK_TYPES = ("bug_fix", "api_change", "test_completion", "refactor")
FORBIDDEN_BLUEPRINT_KEYS = {"gold_patch", "oracle", "evaluator_context", "result_commit", "hidden_tests"}
REQUIRED_FIELDS = {
    "source_id", "task_family_id", "repository", "task_type", "objective",
    "base_files", "gold_files", "hidden_test_files",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(payload: dict[str, Any], expected_count: int = 32, per_type: int = 8, min_repositories: int = 8) -> dict[str, Any]:
    errors: list[str] = []
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
        errors.append("payload.tasks must be a list")
    if len(tasks) != expected_count:
        errors.append(f"expected exactly {expected_count} tasks, found {len(tasks)}")
    source_ids: set[str] = set()
    family_ids: set[str] = set()
    repositories: set[str] = set()
    task_types: Counter[str] = Counter()
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            errors.append(f"task {index} is not an object")
            continue
        missing = REQUIRED_FIELDS - set(task)
        if missing:
            errors.append(f"task {index} missing fields: {sorted(missing)}")
        leaked = FORBIDDEN_BLUEPRINT_KEYS.intersection(task)
        if leaked:
            errors.append(f"task {task.get('source_id', index)} contains sealed/evaluator fields: {sorted(leaked)}")
        source_id = str(task.get("source_id", ""))
        family_id = str(task.get("task_family_id", ""))
        repository = str(task.get("repository", ""))
        task_type = str(task.get("task_type", ""))
        if not source_id or source_id in source_ids:
            errors.append(f"duplicate or empty source_id: {source_id!r}")
        if not family_id or family_id in family_ids:
            errors.append(f"duplicate or empty task_family_id: {family_id!r}")
        source_ids.add(source_id)
        family_ids.add(family_id)
        repositories.add(repository)
        task_types[task_type] += 1
        if task_type not in TASK_TYPES:
            errors.append(f"task {source_id} has unsupported task_type: {task_type!r}")
        if not str(task.get("objective", "")).strip():
            errors.append(f"task {source_id} has an empty objective")
        for field in ("base_files", "gold_files", "hidden_test_files"):
            files = task.get(field)
            if not isinstance(files, dict) or not files:
                errors.append(f"task {source_id} requires non-empty {field}")
                continue
            for relative in files:
                path = PurePosixPath(str(relative))
                if path.is_absolute() or ".." in path.parts:
                    errors.append(f"task {source_id} has unsafe {field} path: {relative}")
                if any(part in {"hidden_tests", "oracle", "gold.patch"} for part in path.parts):
                    errors.append(f"task {source_id} has sealed path in {field}: {relative}")
    if len(repositories) < min_repositories:
        errors.append(f"requires at least {min_repositories} repositories, found {len(repositories)}")
    expected_types = {task_type: per_type for task_type in TASK_TYPES}
    if dict(task_types) != expected_types:
        errors.append(f"task type counts must be {expected_types}, found {dict(task_types)}")
    return {
        "version": "1.0",
        "status": "ready_for_controlled_build" if not errors else "blocked_blueprint_audit",
        "expected_count": expected_count,
        "task_count": len(tasks),
        "repository_count": len(repositories),
        "task_family_count": len(family_ids),
        "task_type_counts": dict(sorted(task_types.items())),
        "errors": errors,
    }


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Audit independent controlled-task blueprints")
    parser.add_argument("source", type=Path)
    parser.add_argument("--expected-count", type=int, default=32)
    parser.add_argument("--per-type", type=int, default=8)
    parser.add_argument("--min-repositories", type=int, default=8)
    parser.add_argument("--output", type=Path, default=project / "results" / "controlled-blueprint-audit.json")
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    report = audit(payload, args.expected_count, args.per_type, args.min_repositories)
    report["source_sha256"] = sha256_file(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "task_count": report["task_count"], "errors": len(report["errors"])}))


if __name__ == "__main__":
    main()
