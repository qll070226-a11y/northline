"""Create blinded task-review packets and adjudicate two-rater annotations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

RATING_COLUMNS = (
    "review_id",
    "rater_id",
    "task_clarity",
    "scope_clarity",
    "feasible",
    "ambiguity_flag",
    "notes",
)
CATEGORICAL_COLUMNS = ("feasible", "ambiguity_flag")
NUMERIC_COLUMNS = ("task_clarity", "scope_clarity")
VALID_YES_NO_UNCLEAR = {"yes", "no", "unclear"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _public_path(relative: Path) -> bool:
    return not any(part in {".git", ".github", "hidden_tests", "oracle", "gold.patch"} for part in relative.parts)


def copy_public_files(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not _public_path(relative):
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def create_packets(source_path: Path, output_root: Path, ratings_path: Path) -> dict[str, Any]:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("source must contain a non-empty tasks list")
    packet_root = output_root / "packets"
    packet_root.mkdir(parents=True, exist_ok=True)
    packets = []
    for index, task in enumerate(sorted(tasks, key=lambda item: str(item["source_id"])), start=1):
        review_id = f"review-{index:03d}"
        if Path(review_id).name != review_id:
            raise ValueError(f"invalid generated review_id: {review_id}")
        packet = packet_root / review_id
        if packet.exists():
            shutil.rmtree(packet)
        code = packet / "repository"
        copy_public_files(Path(str(task["source_checkout"])), code)
        public_task = {
            "review_id": review_id,
            "objective": str(task["objective"]),
            "task_type": str(task["task_type"]),
            "public_constraints": list(task["public_constraints"]),
            "allowed_files": list(task["allowed_files"]),
            "forbidden_files": list(task["forbidden_files"]),
            "required_tests": list(task["required_tests"]),
            "review_scope": "Assess task clarity, scope, feasibility, and ambiguity from the public specification only.",
        }
        (packet / "task.json").write_text(json.dumps(public_task, ensure_ascii=True, indent=2), encoding="utf-8")
        packets.append({"review_id": review_id, "path": str(packet), "task_type": public_task["task_type"]})
    ratings_path.parent.mkdir(parents=True, exist_ok=True)
    with ratings_path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=RATING_COLUMNS).writeheader()
    report = {
        "version": "1.0",
        "status": "pending_two_rater_review",
        "source_sha256": sha256_file(source_path),
        "task_count": len(packets),
        "rater_count_required": 2,
        "packets": packets,
        "ratings_template": str(ratings_path),
        "sealed_data_in_packets": False,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "review-protocol.json").write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report


def _read_ratings(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != RATING_COLUMNS:
            raise ValueError(f"ratings columns must be exactly {RATING_COLUMNS}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("ratings file is empty; two independent ratings per task are required")
    return rows


def validate_ratings(rows: Iterable[dict[str, str]], expected_review_ids: set[str]) -> None:
    rows = list(rows)
    seen: set[tuple[str, str]] = set()
    by_review: dict[str, set[str]] = {}
    for row in rows:
        review_id, rater_id = row.get("review_id", "").strip(), row.get("rater_id", "").strip()
        if review_id not in expected_review_ids:
            raise ValueError(f"unknown review_id: {review_id}")
        if not rater_id:
            raise ValueError("rater_id cannot be empty")
        key = (review_id, rater_id)
        if key in seen:
            raise ValueError(f"duplicate rating: {review_id}/{rater_id}")
        seen.add(key)
        by_review.setdefault(review_id, set()).add(rater_id)
        for column in NUMERIC_COLUMNS:
            try:
                value = int(row.get(column, ""))
            except ValueError as exc:
                raise ValueError(f"{column} must be an integer from 1 to 5") from exc
            if value not in range(1, 6):
                raise ValueError(f"{column} must be an integer from 1 to 5")
        for column in CATEGORICAL_COLUMNS:
            if row.get(column, "").strip().lower() not in VALID_YES_NO_UNCLEAR:
                raise ValueError(f"{column} must be yes, no, or unclear")
    missing = expected_review_ids - by_review.keys()
    if missing:
        raise ValueError(f"missing ratings for: {sorted(missing)}")
    incomplete = {review_id: raters for review_id, raters in by_review.items() if len(raters) != 2}
    if incomplete:
        raise ValueError(f"each task needs exactly two distinct raters: {incomplete}")


def cohens_kappa(first: list[str], second: list[str]) -> float:
    if len(first) != len(second) or not first:
        raise ValueError("kappa requires equal non-empty lists")
    agreement = sum(a == b for a, b in zip(first, second)) / len(first)
    labels = sorted(set(first) | set(second))
    first_counts, second_counts = Counter(first), Counter(second)
    expected = sum((first_counts[label] / len(first)) * (second_counts[label] / len(second)) for label in labels)
    return 1.0 if expected == 1.0 else (agreement - expected) / (1.0 - expected)


def adjudicate(ratings_path: Path, protocol_path: Path, output_path: Path) -> dict[str, Any]:
    rows = _read_ratings(ratings_path)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    expected = {str(item["review_id"]) for item in protocol.get("packets", [])}
    validate_ratings(rows, expected)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["review_id"], []).append(row)
    raters = sorted({row["rater_id"] for row in rows})
    if len(raters) != 2:
        raise ValueError(f"exactly two raters are required, found {raters}")
    ordered = [sorted(grouped[review_id], key=lambda row: row["rater_id"]) for review_id in sorted(grouped)]
    result: dict[str, Any] = {
        "version": "1.0",
        "status": "adjudication_ready",
        "task_count": len(ordered),
        "raters": raters,
        "agreement": {},
        "numeric_disagreement": {},
    }
    for column in CATEGORICAL_COLUMNS:
        first = [group[0][column].strip().lower() for group in ordered]
        second = [group[1][column].strip().lower() for group in ordered]
        result["agreement"][column] = {"cohens_kappa": cohens_kappa(first, second), "exact_rate": sum(a == b for a, b in zip(first, second)) / len(first)}
    for column in NUMERIC_COLUMNS:
        differences = [abs(int(group[0][column]) - int(group[1][column])) for group in ordered]
        result["numeric_disagreement"][column] = {"mean_absolute_difference": sum(differences) / len(differences), "exact_rate": sum(value == 0 for value in differences) / len(differences)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    return result


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Create blinded review packets or adjudicate ratings")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("source", type=Path)
    create_parser.add_argument("--output-root", type=Path, default=project.parent / "benchmark-data" / "controlled-pilot-review")
    create_parser.add_argument("--ratings", type=Path, default=project.parent / "benchmark-data" / "controlled-pilot-review" / "ratings.csv")
    adjudicate_parser = subparsers.add_parser("adjudicate")
    adjudicate_parser.add_argument("ratings", type=Path)
    adjudicate_parser.add_argument("protocol", type=Path)
    adjudicate_parser.add_argument("--output", type=Path, default=project / "results" / "review-adjudication.json")
    args = parser.parse_args()
    if args.command == "create":
        report = create_packets(args.source, args.output_root, args.ratings)
    else:
        report = adjudicate(args.ratings, args.protocol, args.output)
    print(json.dumps({"status": report["status"], "task_count": report["task_count"]}))


if __name__ == "__main__":
    main()
