from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

DATASET_NAME = "SWE-bench/SWE-bench_Verified"
DATASET_REVISION = "78f471bf655a3137b2e8a75af1501690ec009ec3"
DATASET_SHA256 = "030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25"
SELECTION_SEED = 20260912
DIFFICULTY_QUOTAS = {"medium": 12, "long": 12}
MIN_REPOSITORIES = 8
MAX_PER_REPOSITORY = 4


def task_type(problem_statement: str) -> str:
    text = problem_statement.lower()
    title = text.splitlines()[0] if text else ""
    rules = (
        ("refactor", r"\b(refactor|cleanup|clean up|rename|deprecat|remove legacy|simplif)\w*\b"),
        ("test_completion", r"\b(test suite|test coverage|add tests?|missing tests?|doctest|testing)\b"),
        ("api_change", r"\b(api|new option|new parameter|new argument|add support|feature request|expose|allow users?)\b"),
    )
    for label, pattern in rules:
        if re.search(pattern, title):
            return label
    return "bug_fix"


def difficulty_band(value: str) -> str:
    if value == "<15 min fix":
        return "quick"
    if value == "15 min - 1 hour":
        return "medium"
    return "long"


def stable_score(instance_id: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{instance_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / (2**64 - 1)


def annotate(frame: pd.DataFrame, seed: int = SELECTION_SEED) -> pd.DataFrame:
    result = frame.copy()
    result["task_type"] = result["problem_statement"].map(task_type)
    result["difficulty_band"] = result["difficulty"].map(difficulty_band)
    result["selection_score"] = result["instance_id"].map(lambda value: stable_score(str(value), seed))
    return result


def select_instances(frame: pd.DataFrame, count: int = 24) -> pd.DataFrame:
    if count != sum(DIFFICULTY_QUOTAS.values()):
        raise ValueError("v1 selection is preregistered for exactly 24 tasks")
    required = {"instance_id", "repo", "difficulty", "problem_statement"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"dataset is missing required columns: {sorted(missing)}")

    frame = frame[frame["difficulty_band"].isin(DIFFICULTY_QUOTAS)].reset_index(drop=True)
    repositories = sorted(frame["repo"].unique())
    variable_count = len(frame) + len(repositories)
    rows: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(mask: pd.Series, minimum: float, maximum: float) -> None:
        row = np.zeros(variable_count)
        row[:len(frame)] = mask.to_numpy(dtype=float)
        rows.append(row)
        lower.append(minimum)
        upper.append(maximum)

    add(pd.Series(True, index=frame.index), count, count)
    for label, quota in DIFFICULTY_QUOTAS.items():
        add(frame["difficulty_band"] == label, quota, quota)
    for repo_index, repo in enumerate(repositories):
        membership = (frame["repo"] == repo).to_numpy(dtype=float)
        selected_if_used = np.zeros(variable_count)
        selected_if_used[:len(frame)] = membership
        selected_if_used[len(frame) + repo_index] = -1
        rows.append(selected_if_used)
        lower.append(0)
        upper.append(np.inf)
        within_cap = np.zeros(variable_count)
        within_cap[:len(frame)] = membership
        within_cap[len(frame) + repo_index] = -MAX_PER_REPOSITORY
        rows.append(within_cap)
        lower.append(-np.inf)
        upper.append(0)
    repository_count = np.zeros(variable_count)
    repository_count[len(frame):] = 1
    rows.append(repository_count)
    lower.append(MIN_REPOSITORIES)
    upper.append(len(repositories))

    result = milp(
        c=np.concatenate((frame["selection_score"].to_numpy(dtype=float), np.zeros(len(repositories)))),
        integrality=np.ones(variable_count, dtype=int),
        bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
        constraints=LinearConstraint(np.vstack(rows), np.asarray(lower), np.asarray(upper)),
        options={"time_limit": 60},
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"task selection is infeasible: {result.message}")
    selected = frame.loc[result.x[:len(frame)] > 0.5].sort_values("instance_id").copy()
    if len(selected) != count:
        raise RuntimeError(f"solver selected {len(selected)} tasks, expected {count}")
    return selected


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def public_record(row: pd.Series, opaque_task_id: str) -> dict[str, object]:
    return {
        "task_id": opaque_task_id,
        "task_type": "pending_blind_annotation",
        "objective": str(row["problem_statement"]),
        "agent_context": {"hints_enabled": False},
        "evaluator_context": {},
    }


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    default_source = project.parent / "benchmark-data" / "swebench_verified_test.parquet"
    default_oracle = project.parent / "benchmark-data" / "public_tasks_oracle.json"
    parser = argparse.ArgumentParser(description="Freeze a leakage-resistant 24-task SWE-bench Verified sample")
    parser.add_argument("--source", type=Path, default=default_source)
    parser.add_argument("--output", type=Path, default=project / "experiments" / "public_tasks.json")
    parser.add_argument("--selection-report", type=Path, default=project / "experiments" / "public_tasks_selection.json")
    parser.add_argument("--oracle-output", type=Path, default=default_oracle)
    parser.add_argument("--eligibility-output", type=Path, default=project.parent / "benchmark-data" / "public_tasks_eligible_pool.json")
    parser.add_argument("--annotation-template", type=Path, default=project / "experiments" / "public_task_annotations.csv")
    parser.add_argument("--seed", type=int, default=SELECTION_SEED)
    args = parser.parse_args()

    actual_hash = sha256(args.source)
    if actual_hash != DATASET_SHA256:
        raise ValueError(f"dataset checksum mismatch: {actual_hash}")
    frame = annotate(pd.read_parquet(args.source), args.seed)
    selected = select_instances(frame)
    opaque_ids = [f"public-{index:03d}" for index in range(1, len(selected) + 1)]
    public = [public_record(row, opaque_id) for opaque_id, (_, row) in zip(opaque_ids, selected.iterrows())]
    heuristic_counts = Counter(str(row["task_type"]) for _, row in selected.iterrows())
    difficulty_counts = Counter(str(row["difficulty_band"]) for _, row in selected.iterrows())
    repo_counts = Counter(str(row["repo"]) for _, row in selected.iterrows())

    manifest = {
        "version": "1.0",
        "dataset": DATASET_NAME,
        "dataset_revision": DATASET_REVISION,
        "dataset_sha256": DATASET_SHA256,
        "selection_seed": args.seed,
        "status": "candidate_set_pending_container_and_blind_annotation_validation",
        "gold_fields_excluded": ["patch", "test_patch", "eval_script", "hints_text", "FAIL_TO_PASS", "PASS_TO_PASS"],
        "tasks": public,
    }
    report = {
        "dataset_rows": len(frame),
        "selected_rows": len(selected),
        "selection_method": "binary linear optimization over a SHA-256 seeded objective",
        "difficulty_quotas": dict(sorted(difficulty_counts.items())),
        "repo_counts": dict(sorted(repo_counts.items())),
        "heuristic_title_labels_not_for_inference": dict(sorted(heuristic_counts.items())),
        "constraints": {
            "minimum_repositories": MIN_REPOSITORIES,
            "per_repository_max": MAX_PER_REPOSITORY,
            "quick_tasks_excluded": True
        },
        "selection_script_sha256": sha256(Path(__file__)),
        "selected_problem_sha256": {
            opaque_id: hashlib.sha256(str(row["problem_statement"]).encode("utf-8")).hexdigest()
            for opaque_id, (_, row) in zip(opaque_ids, selected.iterrows())
        },
    }
    oracle_rows = [
        {"opaque_task_id": opaque_id, **row.to_dict()}
        for opaque_id, (_, row) in zip(opaque_ids, selected.iterrows())
    ]
    eligible = frame[frame["difficulty_band"].isin(DIFFICULTY_QUOTAS)].sort_values(
        ["difficulty_band", "selection_score", "instance_id"]
    )
    eligibility = {
        "included": [row.to_dict() for _, row in eligible.iterrows()],
        "excluded": [
            {"instance_id": str(row["instance_id"]), "reason": "official difficulty below 15 minutes"}
            for _, row in frame[~frame["difficulty_band"].isin(DIFFICULTY_QUOTAS)].iterrows()
        ],
    }

    for path, payload in (
        (args.output, manifest),
        (args.selection_report, report),
        (args.oracle_output, oracle_rows),
        (args.eligibility_output, eligibility),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
        print(path)
    args.annotation_template.parent.mkdir(parents=True, exist_ok=True)
    with args.annotation_template.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("task_id", "rater_id", "task_type", "delegation_opportunity", "rationale"))
        writer.writeheader()
        for opaque_id in opaque_ids:
            writer.writerow({"task_id": opaque_id, "rater_id": "", "task_type": "", "delegation_opportunity": "", "rationale": ""})
    print(args.annotation_template)


if __name__ == "__main__":
    main()
