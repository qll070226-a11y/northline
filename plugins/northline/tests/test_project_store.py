import json
from pathlib import Path

import pytest

from northline.models import DelegationContract, HandoffReceipt, HandoffStatus, MissionState
from northline.project_store import ProjectStore


def artifacts():
    mission = MissionState("mission_1", "preserve the root goal", acceptance_criteria=("tests pass",), root_commit="base")
    contract = DelegationContract(
        objective="fix parser",
        in_scope=("parser",),
        out_of_scope=("public API",),
        allowed_files=("src/**/*.py",),
        forbidden_files=("pyproject.toml",),
        acceptance_criteria=("tests pass",),
        required_tests=("pytest",),
        base_commit="base",
        parent_id="root",
        mission_id="mission_1",
        contract_id="contract_1",
    )
    receipt = HandoffReceipt(
        contract_id="contract_1",
        agent_id="worker_001",
        status=HandoffStatus.REPORTING,
        base_commit="base",
        result_commit="result",
        changed_files=("src/parser.py",),
        diff_summary="fixed parser",
        tests_run=("pytest",),
        test_results=("pass",),
        acceptance_evidence={"tests pass": "pytest: pass"},
        receipt_id="receipt_1",
    )
    return mission, contract, receipt


def test_project_store_persists_verification_without_integrating(tmp_path: Path):
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("original\n", encoding="utf-8")
    mission, contract, receipt = artifacts()
    store = ProjectStore(tmp_path)
    store.initialize(mission.to_dict())
    store.save_contract(contract.to_dict())
    result = store.record_verification(
        receipt.to_dict(),
        {
            "receipt_id": receipt.receipt_id,
            "contract_id": contract.contract_id,
            "mergeable": True,
            "findings": [],
            "integration_authorized": True,
            "integrated": False,
        },
    )
    status = store.status()
    assert result["mergeable"] is True
    assert result["integration_authorized"] is True
    assert result["integrated"] is False
    assert status["contract_count"] == 1
    assert status["mergeable_count"] == 1
    assert status["policy"]["require_clean_evidence_workspace"] is True
    assert status["schema"]["state"] == "ready"
    assert status["schema"]["schema_version"] == 2
    assert source.read_text(encoding="utf-8") == "original\n"
    assert (tmp_path / ".northline" / "events.jsonl").is_file()


def test_project_store_records_blocked_verification(tmp_path: Path):
    mission, contract, receipt = artifacts()
    store = ProjectStore(tmp_path)
    store.initialize(mission.to_dict())
    store.save_contract(contract.to_dict())
    bad = {**receipt.to_dict(), "receipt_id": "receipt_bad", "changed_files": ["pyproject.toml"]}
    result = store.record_verification(
        bad,
        {
            "receipt_id": "receipt_bad",
            "contract_id": contract.contract_id,
            "mergeable": False,
            "findings": [{"code": "OUT_OF_SCOPE", "severity": "block"}],
            "integration_authorized": False,
            "integrated": False,
        },
    )
    assert result["mergeable"] is False
    assert store.status()["blocked_count"] == 1


def test_project_store_refuses_overwrite_and_unsafe_ids(tmp_path: Path):
    mission, contract, _ = artifacts()
    store = ProjectStore(tmp_path)
    store.initialize(mission.to_dict())
    with pytest.raises(FileExistsError):
        store.initialize(mission.to_dict())
    bad = {**contract.to_dict(), "contract_id": "../escape"}
    with pytest.raises(ValueError, match="safe path component"):
        store.save_contract(bad)


def test_project_store_refuses_mission_overwrite_with_active_artifacts(tmp_path: Path):
    mission, contract, _ = artifacts()
    store = ProjectStore(tmp_path)
    store.initialize(mission.to_dict())
    store.save_contract(contract.to_dict())
    with pytest.raises(ValueError, match="active protocol artifacts"):
        store.initialize(mission.to_dict(), overwrite=True)


def test_project_store_requires_explicit_migration_for_new_artifacts(tmp_path: Path):
    mission, _, _ = artifacts()
    store = ProjectStore(tmp_path)
    store.initialize(mission.to_dict())
    store.project_path.unlink()
    assert store.schema_status()["state"] == "legacy"
    checkpoint = {
        "checkpoint_id": "checkpoint_legacy",
        "contract_id": "contract_legacy",
        "contract_version": 1,
        "attempt": 1,
        "agent_id": "worker_legacy",
        "status": "executing",
        "current_commit": "base",
        "completed": ["inspection"],
        "pending": ["implementation"],
        "blockers": [],
        "notes": [],
        "workspace_status": [],
    }
    with pytest.raises(ValueError, match="migration"):
        store.save_checkpoint(checkpoint)
    migrated = store.migrate()
    assert migrated["migrated"] is True
    assert migrated["from_schema_version"] == 0
    assert store.save_checkpoint(checkpoint)["checkpoint_id"] == "checkpoint_legacy"
    assert store.migrate()["migrated"] is False


def test_project_store_migrates_schema_one_to_two(tmp_path: Path):
    mission, _, _ = artifacts()
    store = ProjectStore(tmp_path)
    store.initialize(mission.to_dict())
    store.project_path.write_text(
        json.dumps({"schema_version": 1, "created_with": "0.5.0", "updated_with": "0.5.0"}),
        encoding="utf-8",
    )
    migrated = store.migrate()
    assert migrated["from_schema_version"] == 1
    assert migrated["schema_version"] == 2
    assert (store.control / "agent-runs").is_dir()
