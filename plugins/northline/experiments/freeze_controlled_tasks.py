from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_RE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
SEALED_KEYS = {
    "base_commit", "container_image", "container_image_kind", "hidden_tests", "setup_command", "gold_patch",
    "oracle", "injected_fault", "repository", "source_id",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def validate_source(payload: dict[str, Any], expected_count: int) -> list[dict[str, Any]]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != expected_count:
        raise ValueError(f"controlled suite must contain exactly {expected_count} tasks")
    required = {
        "source_id", "task_family_id", "repository", "base_commit", "container_image", "container_image_kind",
        "objective", "task_type", "public_constraints", "allowed_files", "forbidden_files",
        "required_tests", "hidden_tests",
    }
    source_ids: set[str] = set()
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"task {index} is not an object")
        missing = required - set(task)
        if missing:
            raise ValueError(f"task {index} is missing fields: {sorted(missing)}")
        source_id = str(task["source_id"])
        if source_id in source_ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        if not COMMIT_RE.fullmatch(str(task["base_commit"])):
            raise ValueError(f"task {source_id} has an invalid full Git commit")
        if not IMAGE_RE.fullmatch(str(task["container_image"])):
            raise ValueError(f"task {source_id} must pin a container image digest")
        image_kind = str(task["container_image_kind"])
        if image_kind not in {"base_image", "task_image"}:
            raise ValueError(f"task {source_id} has an invalid container_image_kind")
        if expected_count >= 120 and image_kind != "task_image":
            raise ValueError(f"confirmatory task {source_id} must pin a task-level image digest")
        for field in ("public_constraints", "allowed_files", "forbidden_files", "required_tests", "hidden_tests"):
            value = task[field]
            if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
                raise ValueError(f"task {source_id} requires a non-empty string list for {field}")
    repositories = {str(task["repository"]) for task in tasks}
    families = {str(task["task_family_id"]) for task in tasks}
    if len(repositories) < 8:
        raise ValueError("controlled suite requires at least eight repositories")
    if len(families) != expected_count:
        raise ValueError("every confirmatory task must belong to a distinct independent task family")
    return sorted(tasks, key=lambda task: str(task["source_id"]))


def agent_record(task: dict[str, Any], task_id: str) -> dict[str, Any]:
    record = {
        "task_id": task_id,
        "task_type": str(task["task_type"]),
        "task_family_id": str(task["task_family_id"]),
        "objective": str(task["objective"]),
        "agent_context": {
            "public_constraints": list(task["public_constraints"]),
            "allowed_files": list(task["allowed_files"]),
            "forbidden_files": list(task["forbidden_files"]),
            "required_tests": list(task["required_tests"]),
        },
        "evaluator_context": {},
    }
    leaked = SEALED_KEYS.intersection(record["agent_context"])
    if leaked:
        raise ValueError(f"sealed keys leaked into agent context: {sorted(leaked)}")
    return record


def freeze(payload: dict[str, Any], expected_count: int = 120) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    tasks = validate_source(payload, expected_count)
    mappings = [(f"controlled-{index:03d}", task) for index, task in enumerate(tasks, start=1)]
    agent_tasks = [agent_record(task, task_id) for task_id, task in mappings]
    manifest = {
        "version": "1.0",
        "status": (
            "frozen_controlled_suite"
            if expected_count >= 120
            else "validated_controlled_pilot_pending_task_images"
        ),
        "gold_fields_excluded": sorted(SEALED_KEYS),
        "tasks": agent_tasks,
    }
    oracle = [{"opaque_task_id": task_id, **task} for task_id, task in mappings]
    report = {
        "task_count": len(tasks),
        "repository_count": len({str(task["repository"]) for task in tasks}),
        "task_family_count": len({str(task["task_family_id"]) for task in tasks}),
        "repository_counts": dict(sorted(Counter(str(task["repository"]) for task in tasks).items())),
        "family_counts": dict(sorted(Counter(str(task["task_family_id"]) for task in tasks).items())),
        "agent_manifest_sha256": sha256_bytes(json.dumps(manifest, sort_keys=True).encode("utf-8")),
        "sealed_oracle_sha256": sha256_bytes(json.dumps(oracle, sort_keys=True).encode("utf-8")),
    }
    return manifest, oracle, report


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Freeze agent-visible and sealed controlled task manifests")
    parser.add_argument("source", type=Path)
    parser.add_argument("--expected-count", type=int, default=120)
    parser.add_argument("--agent-output", type=Path, default=project / "experiments" / "controlled_tasks.json")
    parser.add_argument("--oracle-output", type=Path, default=project.parent / "benchmark-data" / "controlled_tasks_oracle.json")
    parser.add_argument("--report-output", type=Path, default=project / "experiments" / "controlled_tasks_freeze.json")
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    payload = json.loads(source_bytes)
    manifest, oracle, report = freeze(payload, args.expected_count)
    report["source_sha256"] = sha256_bytes(source_bytes)
    report["freeze_script_sha256"] = sha256_file(Path(__file__))
    for path, output in ((args.agent_output, manifest), (args.oracle_output, oracle), (args.report_output, report)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
