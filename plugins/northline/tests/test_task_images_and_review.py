import json
from pathlib import Path

import pytest

from experiments.build_task_images import prepare
from experiments.review_protocol import cohens_kappa, create_packets, validate_ratings


def _source(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "hidden_tests").mkdir()
    (checkout / "tests").mkdir()
    (checkout / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (checkout / "tests" / "test_visible.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (checkout / "hidden_tests" / "test_hidden.py").write_text("def test_hidden(): pass\n", encoding="utf-8")
    payload = {
        "tasks": [{
            "source_id": "task-001",
            "source_checkout": str(checkout),
            "container_image": "python:3.12-slim@sha256:" + "a" * 64,
            "objective": "fix it",
            "task_type": "bug_fix",
            "public_constraints": ["keep api"],
            "allowed_files": ["app.py"],
            "forbidden_files": ["Dockerfile"],
            "required_tests": ["python -m unittest"],
        }],
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return source


def test_task_image_context_excludes_sealed_paths(tmp_path: Path):
    source = _source(tmp_path)
    report = prepare(source, tmp_path / "manifest.json", tmp_path / "contexts", build=False)
    context = tmp_path / "contexts" / "task-001"
    assert report["status"] == "prepared_task_image_contexts"
    assert (context / "Dockerfile").exists()
    assert not (context / "hidden_tests").exists()
    assert not (context / ".git").exists()
    assert report["sealed_data_in_context"] is False


def test_review_packets_and_ratings_require_two_raters(tmp_path: Path):
    source = _source(tmp_path)
    report = create_packets(source, tmp_path / "review", tmp_path / "review" / "ratings.csv")
    packet = tmp_path / "review" / "packets" / "review-001"
    assert report["status"] == "pending_two_rater_review"
    assert (packet / "task.json").exists()
    assert not (packet / "repository" / "hidden_tests").exists()
    row = {"review_id": "review-001", "rater_id": "a", "task_clarity": "4", "scope_clarity": "4", "feasible": "yes", "ambiguity_flag": "no", "notes": "ok"}
    with pytest.raises(ValueError, match="exactly two"):
        validate_ratings([row], {"review-001"})


def test_kappa_perfect_and_disagreement():
    assert cohens_kappa(["yes", "no"], ["yes", "no"]) == 1.0
    assert cohens_kappa(["yes", "no"], ["no", "yes"]) == -1.0
