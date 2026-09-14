"""Validate task-level images and run visible/hidden baseline tests in Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker_probe() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc)}
    version = result.stdout.strip()
    if result.returncode == 0 and version:
        return {"available": True, "server_version": version}
    return {"available": False, "reason": (result.stderr or result.stdout).strip()[-1000:]}


def run_container(image: str, command: list[str], hidden_dir: Path) -> dict[str, Any]:
    mount = f"{hidden_dir.resolve()}:/workspace/hidden_tests:ro"
    docker_command = [
        "docker", "run", "--rm", "--network", "none", "--read-only", "-v", mount,
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", image, *command,
    ]
    completed = subprocess.run(docker_command, capture_output=True, text=True, timeout=300, check=False)
    return {
        "command": docker_command,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def validate(manifest_path: Path, source_path: Path, output_path: Path, *, execute: bool = True) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_tasks = {str(task["source_id"]): task for task in source.get("tasks", [])}
    entries = manifest.get("tasks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("image manifest must contain a non-empty tasks list")
    probe = docker_probe()
    report_tasks: list[dict[str, Any]] = []
    blocked = not probe["available"] or not execute
    for entry in entries:
        task_id = str(entry.get("source_id", ""))
        task = source_tasks.get(task_id)
        if task is None:
            raise ValueError(f"image manifest task is absent from source: {task_id}")
        result: dict[str, Any] = {
            "source_id": task_id,
            "image": entry.get("image_digest") or entry.get("tag"),
            "manifest_status": entry.get("status"),
            "status": "pending",
        }
        image = str(result["image"] or "")
        if entry.get("status") != "built" or not DIGEST_RE.fullmatch(image):
            result["status"] = "missing_immutable_digest"
            blocked = True
            report_tasks.append(result)
            continue
        if blocked:
            report_tasks.append(result)
            continue
        hidden_dir = Path(str(task["sealed_task_dir"])) / "hidden_tests"
        if not hidden_dir.is_dir():
            result["status"] = "missing_hidden_tests"
            blocked = True
            report_tasks.append(result)
            continue
        result["visible"] = run_container(image, ["python", "-m", "unittest", "discover", "-s", "tests", "-v"], hidden_dir)
        result["hidden"] = run_container(image, ["python", "-m", "unittest", "discover", "-s", "hidden_tests", "-v"], hidden_dir)
        result["status"] = "validated" if result["visible"]["passed"] and result["hidden"]["passed"] else "rejected"
        report_tasks.append(result)
    if not probe["available"]:
        status = "blocked_docker_daemon"
    elif any(item["status"] == "rejected" for item in report_tasks):
        status = "task_image_validation_failed"
    elif all(item["status"] == "validated" for item in report_tasks):
        status = "validated_task_images"
    else:
        status = "pending_task_image_digests"
    report = {
        "version": "1.0",
        "status": status,
        "manifest_sha256": sha256_file(manifest_path),
        "source_sha256": sha256_file(source_path),
        "docker_probe": probe,
        "network": "none",
        "task_count": len(report_tasks),
        "tasks": report_tasks,
        "sealed_data_in_image": False,
        "execution_requested": bool(execute),
        "runtime_environment": {"python": os.environ.get("PYTHON", "container image interpreter")},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Validate immutable task images in isolated Docker containers")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=project / "results" / "task-image-validation.json")
    parser.add_argument("--no-execute", action="store_true")
    args = parser.parse_args()
    report = validate(args.manifest, args.source, args.output, execute=not args.no_execute)
    print(json.dumps({"status": report["status"], "task_count": report["task_count"]}))


if __name__ == "__main__":
    main()
