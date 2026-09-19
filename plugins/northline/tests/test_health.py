from __future__ import annotations

import json
from pathlib import Path

from northline.engine import ProtocolEngine
from northline.health import northline_health_check, preflight_live_forward_test, run_product_forward_test


def test_health_check_reports_dependencies_and_optional_forward_suite(tmp_path: Path):
    output = tmp_path / "health.json"
    report = northline_health_check(output=output, run_forward=True)
    assert report["healthy"] is True
    assert report["real_model_calls"] == 0
    assert report["forward_test"]["passed"] is True
    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "northline_health_check"


def test_mcp_forward_wrapper_runs_deterministic_suite(tmp_path: Path):
    report = run_product_forward_test(tmp_path / "forward.json")
    assert report["report_type"] == "northline_product_forward_test"
    assert report["summary"]["failed"] == 0
    assert report["real_model_calls"] == 0


def test_mcp_live_wrapper_is_authorization_free(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    engine = ProtocolEngine(workspace)
    engine.store.initialize(
        {
            "mission_id": "mission_mcp_live",
            "objective": "test MCP preflight",
            "global_constraints": [],
            "decisions": [],
            "acceptance_criteria": ["report exists"],
            "root_commit": "base",
            "max_depth": 2,
            "max_children": 4,
        }
    )
    engine.store.save_contract(
        {
            "contract_id": "contract_mcp_live",
            "version": 1,
            "mission_id": "mission_mcp_live",
            "parent_id": "root",
            "objective": "run preflight",
            "in_scope": ["report"],
            "out_of_scope": [],
            "allowed_files": ["report.txt"],
            "forbidden_files": [],
            "dependencies": [],
            "acceptance_criteria": ["report exists"],
            "required_tests": ["python -V"],
            "base_commit": "base",
            "deadline_or_budget": None,
        }
    )
    engine.store.save_execution(
        {"contract_id": "contract_mcp_live", "status": "planned", "workspace": str(workspace), "attempt": 1}
    )
    report = preflight_live_forward_test(workspace, "contract_mcp_live", tmp_path / "live.json")
    assert report["status"] == "authorization_required"
    assert report["real_model_calls"] is False
    assert report["model_exposure_status"] == "not_started"
