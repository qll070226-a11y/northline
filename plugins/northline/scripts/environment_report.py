from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

PACKAGES = (
    "langgraph", "mcp", "numpy", "scipy", "pandas", "statsmodels", "jsonschema",
    "pytest", "pyyaml", "ruff", "swebench", "datasets", "openai",
)


def main() -> None:
    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    git = subprocess.run(["git", "--version"], text=True, capture_output=True, check=False)
    docker = subprocess.run(["docker", "--version"], text=True, capture_output=True, check=False)
    codex = subprocess.run(["codex", "--version"], text=True, capture_output=True, check=False)
    report = {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "git": git.stdout.strip() if git.returncode == 0 else None,
        "docker_client": docker.stdout.strip() if docker.returncode == 0 else None,
        "codex_cli": codex.stdout.strip() if codex.returncode == 0 else None,
        "packages": versions,
    }
    output = Path("results/environment.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
