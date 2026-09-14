"""Gate a controlled suite before any model episodes are allowed to run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def promote(
    image_validation_path: Path,
    review_protocol_path: Path,
    output_path: Path,
    *,
    adjudication_path: Path | None = None,
    blueprint_audit_path: Path | None = None,
    expected_count: int = 8,
) -> dict[str, Any]:
    image = json.loads(image_validation_path.read_text(encoding="utf-8"))
    review = json.loads(review_protocol_path.read_text(encoding="utf-8"))
    reasons: list[str] = []
    image_tasks = image.get("tasks", [])
    review_count = int(review.get("task_count", -1))
    if image.get("status") != "validated_task_images":
        reasons.append(f"image validation status is {image.get('status')!r}")
    if len(image_tasks) != expected_count:
        reasons.append(f"image validation has {len(image_tasks)} tasks, expected {expected_count}")
    if image.get("sealed_data_in_image") is not False:
        reasons.append("image report does not prove sealed_data_in_image=false")
    if review_count != expected_count:
        reasons.append(f"review protocol has {review_count} tasks, expected {expected_count}")
    if review.get("sealed_data_in_packets") is not False:
        reasons.append("review protocol does not prove sealed_data_in_packets=false")
    if blueprint_audit_path is None or not blueprint_audit_path.is_file():
        reasons.append("controlled blueprint audit report is missing")
    else:
        blueprint = json.loads(blueprint_audit_path.read_text(encoding="utf-8"))
        if blueprint.get("status") != "ready_for_controlled_build":
            reasons.append(f"blueprint audit status is {blueprint.get('status')!r}")
        if int(blueprint.get("expected_count", -1)) != expected_count:
            reasons.append("blueprint audit expected count does not match promotion count")
    adjudication: dict[str, Any] | None = None
    if adjudication_path is None or not adjudication_path.is_file():
        reasons.append("two-rater adjudication report is missing")
    else:
        adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
        if adjudication.get("status") != "adjudication_ready":
            reasons.append(f"adjudication status is {adjudication.get('status')!r}")
        if int(adjudication.get("task_count", -1)) != expected_count:
            reasons.append("adjudication task count does not match expected count")
    for task in image_tasks:
        if task.get("status") != "validated":
            reasons.append(f"task {task.get('source_id')} is not container-validated")
    status = "ready_for_model_experiments" if not reasons else "blocked_promotion"
    report = {
        "version": "1.0",
        "status": status,
        "expected_count": expected_count,
        "image_validation_sha256": sha256_file(image_validation_path),
        "review_protocol_sha256": sha256_file(review_protocol_path),
        "adjudication_sha256": sha256_file(adjudication_path) if adjudication_path and adjudication_path.is_file() else None,
        "blueprint_audit_sha256": sha256_file(blueprint_audit_path) if blueprint_audit_path and blueprint_audit_path.is_file() else None,
        "reasons": reasons,
        "model_execution_authorized": status == "ready_for_model_experiments",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Promote a controlled suite only after all validation gates pass")
    parser.add_argument("image_validation", type=Path)
    parser.add_argument("review_protocol", type=Path)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--blueprint-audit", type=Path)
    parser.add_argument("--expected-count", type=int, default=8)
    parser.add_argument("--output", type=Path, default=project / "results" / "suite-promotion.json")
    args = parser.parse_args()
    report = promote(
        args.image_validation,
        args.review_protocol,
        args.output,
        adjudication_path=args.adjudication,
        blueprint_audit_path=args.blueprint_audit,
        expected_count=args.expected_count,
    )
    print(json.dumps({"status": report["status"], "model_execution_authorized": report["model_execution_authorized"]}))


if __name__ == "__main__":
    main()
