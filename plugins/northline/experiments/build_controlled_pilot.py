from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from experiments.freeze_controlled_tasks import freeze

DEFAULT_IMAGE = "python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"


def write_text_files(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe blueprint path: {relative}")
        target = root.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)


def checked(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({' '.join(command)}):\n{completed.stdout}\n{completed.stderr}")
    return completed


def test_command(workspace: Path, suite: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(workspace) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(suite), "-v"],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def reset_generated_directory(path: Path, allowed_parent: Path, force: bool) -> None:
    resolved = path.resolve()
    parent = allowed_parent.resolve()
    if resolved.parent != parent:
        raise ValueError(f"generated directory must be a direct child of {parent}: {resolved}")
    if path.exists():
        if not force:
            raise FileExistsError(f"generated directory already exists: {path}; pass --force to rebuild it")
        shutil.rmtree(path)
    path.mkdir(parents=True)


def tree_hash(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def build_one(
    blueprint: dict[str, Any],
    task_id: str,
    workspace_root: Path,
    sealed_root: Path,
    index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    required = {"source_id", "objective", "task_type", "base_files", "gold_files", "hidden_test_files"}
    missing = required - set(blueprint)
    if missing:
        raise ValueError(f"blueprint {task_id} is missing: {sorted(missing)}")
    base_files = dict(blueprint["base_files"])
    gold_files = dict(blueprint["gold_files"])
    hidden_files = dict(blueprint["hidden_test_files"])
    if not base_files or not gold_files or not hidden_files:
        raise ValueError(f"blueprint {task_id} requires base, gold, and hidden files")

    workspace = workspace_root / task_id
    sealed_task = sealed_root / task_id
    workspace.mkdir()
    sealed_task.mkdir()
    write_text_files(workspace, base_files)
    write_text_files(sealed_task / "hidden_tests", hidden_files)

    checked(["git", "init", "--initial-branch", "main"], cwd=workspace)
    checked(["git", "config", "user.name", "Controlled Task Builder"], cwd=workspace)
    checked(["git", "config", "user.email", "builder@example.invalid"], cwd=workspace)
    checked(["git", "config", "core.autocrlf", "false"], cwd=workspace)
    checked(["git", "add", "."], cwd=workspace)
    git_environment = os.environ.copy()
    timestamp = f"2000-01-{index + 1:02d}T00:00:00+00:00"
    git_environment["GIT_AUTHOR_DATE"] = timestamp
    git_environment["GIT_COMMITTER_DATE"] = timestamp
    checked(["git", "commit", "-m", "controlled task base"], cwd=workspace, env=git_environment)
    base_commit = checked(["git", "rev-parse", "HEAD"], cwd=workspace).stdout.strip()
    if checked(["git", "remote"], cwd=workspace).stdout.strip():
        raise RuntimeError(f"generated workspace unexpectedly has a remote: {workspace}")

    visible_base = test_command(workspace, workspace / "tests")
    hidden_base = test_command(workspace, sealed_task / "hidden_tests")
    if visible_base.returncode != 0:
        raise RuntimeError(f"visible baseline failed for {task_id}:\n{visible_base.stdout}\n{visible_base.stderr}")
    if hidden_base.returncode == 0:
        raise RuntimeError(f"hidden baseline unexpectedly passed for {task_id}")

    write_text_files(workspace, gold_files)
    visible_gold = test_command(workspace, workspace / "tests")
    hidden_gold = test_command(workspace, sealed_task / "hidden_tests")
    if visible_gold.returncode != 0 or hidden_gold.returncode != 0:
        raise RuntimeError(
            f"gold validation failed for {task_id}:\nvisible={visible_gold.stdout}{visible_gold.stderr}"
            f"\nhidden={hidden_gold.stdout}{hidden_gold.stderr}"
        )
    gold_patch = checked(["git", "diff", "--binary", "--no-ext-diff"], cwd=workspace).stdout
    if not gold_patch.strip():
        raise RuntimeError(f"gold patch is empty for {task_id}")
    (sealed_task / "gold.patch").write_text(gold_patch, encoding="utf-8")
    write_text_files(workspace, base_files)
    if subprocess.run(["git", "diff", "--quiet"], cwd=workspace, check=False).returncode != 0:
        raise RuntimeError(f"workspace was not restored to its base tree: {task_id}")

    log = {
        "visible_base": visible_base.returncode,
        "hidden_base": hidden_base.returncode,
        "visible_gold": visible_gold.returncode,
        "hidden_gold": hidden_gold.returncode,
    }
    (sealed_task / "validation.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    source = {
        "source_id": str(blueprint["source_id"]),
        "task_family_id": str(blueprint.get("task_family_id", blueprint["source_id"])),
        "repository": str(blueprint.get("repository", blueprint["source_id"])),
        "base_commit": base_commit,
        "container_image": str(blueprint.get("container_image", DEFAULT_IMAGE)),
        "container_image_kind": "base_image",
        "objective": str(blueprint["objective"]),
        "task_type": str(blueprint["task_type"]),
        "public_constraints": list(blueprint.get("public_constraints", ["Preserve documented public behavior."])),
        "allowed_files": list(blueprint.get("allowed_files", ["app.py", "tests/**/*.py"])),
        "forbidden_files": list(blueprint.get("forbidden_files", ["Dockerfile", ".github/**"])),
        "required_tests": ["python -m unittest discover -s tests -v"],
        "hidden_tests": ["python -m unittest discover -s hidden_tests -v"],
        "setup_command": "none",
        "gold_patch": gold_patch,
        "source_checkout": str(workspace.resolve()),
        "sealed_task_dir": str(sealed_task.resolve()),
        "base_tree_sha256": tree_hash(base_files),
    }
    return source, log


def build(
    blueprint_path: Path,
    workspace_root: Path,
    sealed_root: Path,
    *,
    force: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    payload = json.loads(blueprint_path.read_text(encoding="utf-8"))
    blueprints = sorted(payload.get("tasks", []), key=lambda item: str(item["source_id"]))
    if len(blueprints) != 8:
        raise ValueError("controlled pilot requires exactly eight independently authored blueprints")
    reset_generated_directory(workspace_root, workspace_root.parent, force)
    reset_generated_directory(sealed_root, sealed_root.parent, force)
    sources = []
    logs = {}
    for index, blueprint in enumerate(blueprints, start=1):
        task_id = f"controlled-{index:03d}"
        source, log = build_one(blueprint, task_id, workspace_root, sealed_root, index)
        sources.append(source)
        logs[task_id] = log
    source_payload = {"version": "pilot-1.0", "tasks": sources}
    manifest, oracle, freeze_report = freeze(source_payload, expected_count=8)
    report = {
        "status": "validated_on_host_pending_task_image_build",
        "task_count": 8,
        "all_visible_baselines_pass": all(item["visible_base"] == 0 for item in logs.values()),
        "all_hidden_baselines_fail": all(item["hidden_base"] != 0 for item in logs.values()),
        "all_gold_visible_pass": all(item["visible_gold"] == 0 for item in logs.values()),
        "all_gold_hidden_pass": all(item["hidden_gold"] == 0 for item in logs.values()),
        "freeze": freeze_report,
        "validation": logs,
    }
    return manifest, oracle, report, source_payload


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    default_data = project.parent / "benchmark-data"
    parser = argparse.ArgumentParser(description="Build and validate the eight-task controlled pilot")
    parser.add_argument("--blueprints", type=Path, default=default_data / "controlled_pilot_blueprints.json")
    parser.add_argument("--workspace-root", type=Path, default=project.parent / "controlled-pilot-workspaces")
    parser.add_argument("--sealed-root", type=Path, default=default_data / "controlled-pilot-sealed")
    parser.add_argument("--source-output", type=Path, default=default_data / "controlled_pilot_source.json")
    parser.add_argument("--oracle-output", type=Path, default=default_data / "controlled_pilot_oracle.json")
    parser.add_argument("--agent-output", type=Path, default=project / "experiments" / "controlled_pilot_tasks.json")
    parser.add_argument("--report-output", type=Path, default=project / "results" / "controlled-pilot-build.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest, oracle, report, source = build(
        args.blueprints.resolve(), args.workspace_root.resolve(), args.sealed_root.resolve(), force=args.force
    )
    for path, value in (
        (args.source_output, source),
        (args.oracle_output, oracle),
        (args.agent_output, manifest),
        (args.report_output, report),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
