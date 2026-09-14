"""Prepare and optionally build reproducible task-level Docker images.

The build context is deliberately outside the repository and contains only the
base checkout. Sealed tests, oracle patches, and evaluator data are never
copied into a context. A blocked Docker daemon produces a truthful pending
manifest rather than a synthetic image digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

EXCLUDED_NAMES = {".git", ".github", "hidden_tests", "oracle", "gold.patch"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in relative.parts)


def copy_public_checkout(source: Path, destination: Path) -> list[str]:
    if not source.is_dir():
        raise ValueError(f"source checkout does not exist: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    omitted: list[str] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if _excluded(relative):
            omitted.append(relative.as_posix())
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return omitted


def dockerfile_for(task: dict[str, Any]) -> str:
    image = str(task["container_image"])
    task_id = str(task["source_id"])
    return (
        f"FROM {image}\n"
        f"LABEL org.longhorizon.task=" + json.dumps(task_id) + "\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "WORKDIR /workspace\n"
        "COPY . /workspace\n"
        "RUN python -m compileall -q .\n"
    )


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


def build_one(context: Path, task: dict[str, Any], build: bool, platform: str) -> dict[str, Any]:
    task_id = str(task["source_id"])
    tag = f"northline/{task_id}:context"
    result: dict[str, Any] = {
        "source_id": task_id,
        "base_image": task["container_image"],
        "image_kind": "task_image",
        "tag": tag,
        "context": str(context),
        "context_sha256": tree_digest(context),
        "dockerfile_sha256": sha256_bytes((context / "Dockerfile").read_bytes()),
        "status": "prepared",
    }
    if not build:
        result["status"] = "dry_run"
        return result
    command = ["docker", "build", "--platform", platform, "--pull=false", "-t", tag, str(context)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
    result["build_command"] = command
    result["build_returncode"] = completed.returncode
    result["build_log_tail"] = (completed.stdout + "\n" + completed.stderr)[-4000:]
    if completed.returncode != 0:
        result["status"] = "build_failed"
        return result
    inspected = subprocess.run(
        ["docker", "image", "inspect", tag, "--format", "{{json .RepoDigests}}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if inspected.returncode != 0:
        result["status"] = "digest_missing"
        result["inspect_error"] = (inspected.stderr or inspected.stdout).strip()[-1000:]
        return result
    try:
        digests = json.loads(inspected.stdout.strip())
    except json.JSONDecodeError:
        digests = []
    if not isinstance(digests, list) or not digests:
        result["status"] = "digest_missing"
        return result
    result["image_digest"] = str(digests[0])
    result["status"] = "built"
    return result


def prepare(source_path: Path, output_path: Path, context_root: Path, build: bool = False, platform: str = "linux/amd64") -> dict[str, Any]:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("source must contain a non-empty tasks list")
    context_root.mkdir(parents=True, exist_ok=True)
    probe = docker_probe()
    if build and not probe["available"]:
        build = False
        blocked = True
    else:
        blocked = False
    entries = []
    for task in sorted(tasks, key=lambda item: str(item["source_id"])):
        source_id = str(task["source_id"])
        if not source_id or Path(source_id).name != source_id or source_id in {".", ".."}:
            raise ValueError(f"source_id must be a single safe path component: {source_id!r}")
        source = Path(str(task["source_checkout"]))
        context = context_root / source_id
        if context.exists():
            shutil.rmtree(context)
        omitted = copy_public_checkout(source, context)
        (context / "Dockerfile").write_text(dockerfile_for(task), encoding="utf-8", newline="\n")
        entry = build_one(context, task, build, platform)
        entry["omitted_paths"] = omitted
        entries.append(entry)
    statuses = {str(entry["status"]) for entry in entries}
    if blocked:
        status = "pending_docker_daemon"
    elif statuses == {"built"}:
        status = "built_task_images"
    elif "build_failed" in statuses or "digest_missing" in statuses:
        status = "task_image_build_failed"
    else:
        status = "prepared_task_image_contexts"
    report = {
        "version": "1.0",
        "status": status,
        "source_sha256": sha256_bytes(source_path.read_bytes()),
        "docker_probe": probe,
        "requested_build": bool(build or blocked),
        "platform": platform,
        "task_count": len(entries),
        "sealed_data_in_context": False,
        "tasks": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Prepare/build sealed task-level Docker image contexts")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=project / "results" / "task-image-manifest.json")
    parser.add_argument("--context-root", type=Path, default=project.parent / "benchmark-data" / "controlled-pilot-images")
    parser.add_argument("--build", action="store_true", help="build only when a Docker server is reachable")
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args()
    report = prepare(args.source, args.output, args.context_root, args.build, args.platform)
    print(json.dumps({"status": report["status"], "task_count": report["task_count"]}))


if __name__ == "__main__":
    main()
