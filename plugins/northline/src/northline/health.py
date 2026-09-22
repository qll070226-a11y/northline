from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .agent_runtime import CodexCliRuntime
from .engine import ProtocolEngine
from .forward_testing import run_product_forward_tests
from .live_testing import run_live_forward_test
from .version import __version__


def run_product_forward_test(output: str | Path) -> dict[str, Any]:
    """Expose the deterministic product suite through the MCP surface."""

    return run_product_forward_tests(output)


def preflight_live_forward_test(
    workspace: str | Path,
    contract_id: str,
    output: str | Path,
    baseline: str | Path | None = None,
) -> dict[str, Any]:
    """Run the model-free live-test preflight through the MCP surface."""

    return run_live_forward_test(
        workspace,
        contract_id,
        output,
        authorized=False,
        baseline=baseline,
    )


def northline_health_check(
    workspace: str | Path | None = None,
    output: str | Path | None = None,
    run_forward: bool = False,
    check_runtime: bool = False,
) -> dict[str, Any]:
    """Report runtime capabilities without starting a model or changing source files."""

    workspace_path = Path(workspace).expanduser().resolve() if workspace else None
    dependencies = {
        name: bool(importlib.util.find_spec(name))
        for name in ("jsonschema", "mcp")
    }
    git_available = shutil.which("git") is not None
    report: dict[str, Any] = {
        "report_type": "northline_health_check",
        "schema_version": 1,
        "northline_version": __version__,
        "healthy": all(dependencies.values()) and git_available,
        "real_model_calls": 0,
        "capabilities": {
            "mcp_tools": True,
            "deterministic_forward_test": True,
            "live_forward_preflight": True,
            "authorized_live_execution": True,
            "root_only_integration": True,
        },
        "dependencies": {
            "python": True,
            "git": git_available,
            **dependencies,
        },
        "workspace": None,
        "forward_test": None,
        "runtime": None,
    }

    if check_runtime:
        runtime = CodexCliRuntime()
        report["runtime"] = runtime.preflight(timeout_seconds=30)
        report["healthy"] = report["healthy"] and bool(report["runtime"]["ready"])

    if workspace_path is not None:
        workspace_info: dict[str, Any] = {
            "path": str(workspace_path),
            "exists": workspace_path.is_dir(),
            "git_repository": False,
            "northline_initialized": (workspace_path / ".northline").is_dir(),
        }
        if not workspace_info["exists"]:
            report["healthy"] = False
        if workspace_path.is_dir() and git_available:
            completed = subprocess.run(
                ["git", "-C", str(workspace_path), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
            workspace_info["git_repository"] = completed.returncode == 0
            if not workspace_info["git_repository"]:
                report["healthy"] = False
            if completed.returncode == 0:
                workspace_info["git_root"] = completed.stdout.strip()
        if workspace_info["northline_initialized"]:
            try:
                engine = ProtocolEngine(workspace_path)
                workspace_info["project_schema"] = engine.project_schema()
                workspace_info["status"] = engine.status()
            except Exception as exc:
                workspace_info["protocol_error"] = f"{type(exc).__name__}: {exc}"
                report["healthy"] = False
        report["workspace"] = workspace_info

    if run_forward:
        with tempfile.NamedTemporaryFile(prefix="northline-health-", suffix=".json", delete=False) as handle:
            temporary_output = Path(handle.name)
        try:
            forward = run_product_forward_tests(temporary_output)
            report["forward_test"] = {
                "passed": forward["summary"]["failed"] == 0,
                "summary": forward["summary"],
                "report_type": forward["report_type"],
            }
            if forward["summary"]["failed"]:
                report["healthy"] = False
        finally:
            temporary_output.unlink(missing_ok=True)

    if output is not None:
        output_path = Path(output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        report["output"] = str(output_path)
    return report
