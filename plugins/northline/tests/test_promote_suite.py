import json
from pathlib import Path

from experiments.promote_suite import promote


def test_promotion_blocks_missing_image_and_review_gates(tmp_path: Path):
    image = tmp_path / "image.json"
    review = tmp_path / "review.json"
    output = tmp_path / "promotion.json"
    image.write_text(json.dumps({"status": "blocked_docker_daemon", "sealed_data_in_image": False, "tasks": [{"source_id": "a", "status": "missing_immutable_digest"}]}), encoding="utf-8")
    review.write_text(json.dumps({"status": "pending_two_rater_review", "task_count": 1}), encoding="utf-8")
    report = promote(image, review, output, expected_count=1)
    assert report["status"] == "blocked_promotion"
    assert report["model_execution_authorized"] is False
    assert any("image validation status" in reason for reason in report["reasons"])


def test_promotion_allows_complete_gates(tmp_path: Path):
    image = tmp_path / "image.json"
    review = tmp_path / "review.json"
    adjudication = tmp_path / "adjudication.json"
    blueprint = tmp_path / "blueprint.json"
    output = tmp_path / "promotion.json"
    image.write_text(json.dumps({"status": "validated_task_images", "sealed_data_in_image": False, "tasks": [{"source_id": "a", "status": "validated"}]}), encoding="utf-8")
    review.write_text(json.dumps({"status": "pending_two_rater_review", "task_count": 1, "sealed_data_in_packets": False}), encoding="utf-8")
    adjudication.write_text(json.dumps({"status": "adjudication_ready", "task_count": 1}), encoding="utf-8")
    blueprint.write_text(json.dumps({"status": "ready_for_controlled_build", "expected_count": 1}), encoding="utf-8")
    report = promote(image, review, output, adjudication_path=adjudication, blueprint_audit_path=blueprint, expected_count=1)
    assert report["status"] == "ready_for_model_experiments"
    assert report["model_execution_authorized"] is True
