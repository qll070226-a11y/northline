import json
from pathlib import Path

from experiments.validate_task_images import validate


def test_validation_stays_pending_without_immutable_digests(tmp_path: Path, monkeypatch):
    source = {"tasks": [{"source_id": "task-001", "sealed_task_dir": str(tmp_path / "sealed")}]}
    manifest = {"tasks": [{"source_id": "task-001", "status": "dry_run", "tag": "local:tag"}]}
    source_path = tmp_path / "source.json"
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "result.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr("experiments.validate_task_images.docker_probe", lambda: {"available": False, "reason": "test"})
    report = validate(manifest_path, source_path, output_path)
    assert report["status"] == "blocked_docker_daemon"
    assert report["tasks"][0]["status"] == "missing_immutable_digest"
    assert report["sealed_data_in_image"] is False
