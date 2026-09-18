import subprocess
import sys
from pathlib import Path

import pytest

from northline.engine import ProtocolEngine
from northline.models import DelegationContract, HandoffReceipt, HandoffStatus, MissionState
from northline.workspace import GitWorkspace


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def make_repository(tmp_path: Path) -> tuple[Path, Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    source = repo / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("original\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")

    child = tmp_path / "child"
    GitWorkspace(repo).create_worktree(child, base)
    git(child, "config", "user.email", "test@example.com")
    git(child, "config", "user.name", "Test")
    (child / "src" / "app.py").write_text("fixed\n", encoding="utf-8")
    git(child, "add", ".")
    git(child, "commit", "-q", "-m", "result")
    result = git(child, "rev-parse", "HEAD")
    return repo, child, base, result


def prepare_engine(repo: Path, child: Path, base: str) -> tuple[ProtocolEngine, DelegationContract]:
    engine = ProtocolEngine(repo)
    mission = MissionState(
        "mission_engine",
        "fix the application without leaving the delegated scope",
        acceptance_criteria=("repository is clean",),
        root_commit=base,
    )
    engine.initialize(mission.to_dict())
    contract = DelegationContract(
        contract_id="contract_engine",
        objective="fix app",
        in_scope=("application implementation",),
        out_of_scope=("build configuration",),
        allowed_files=("src/**/*.py",),
        forbidden_files=("pyproject.toml",),
        acceptance_criteria=("repository is clean",),
        required_tests=("git status --porcelain",),
        base_commit=base,
        parent_id="root",
        mission_id=mission.mission_id,
    )
    engine.delegate(contract.to_dict(), agent_id="worker_001", role="worker", workspace=str(child))
    for state in ("claimed", "executing", "reporting"):
        engine.transition(contract.contract_id, state)
    return engine, contract


def test_engine_prepares_contract_worktree_at_base_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    engine = ProtocolEngine(repo)
    mission = MissionState("mission_prepare", "prepare isolated work", root_commit=base)
    engine.initialize(mission.to_dict())
    contract = DelegationContract(
        contract_id="contract_prepare",
        objective="prepare",
        in_scope=("README",),
        out_of_scope=(),
        allowed_files=("README.md",),
        forbidden_files=(),
        acceptance_criteria=("worktree exists",),
        required_tests=("git status --porcelain",),
        base_commit=base,
        parent_id="root",
        mission_id=mission.mission_id,
    )
    engine.delegate(contract.to_dict(), agent_id="worker_prepare", role="worker")
    target = tmp_path / "prepared"
    execution = engine.prepare_workspace(contract.contract_id, target)
    assert execution["workspace"] == str(target.resolve())
    assert execution["current_commit"] == base
    assert GitWorkspace(target).head() == base


def receipt(contract: DelegationContract, result: str, changed_files: tuple[str, ...]) -> HandoffReceipt:
    return HandoffReceipt(
        contract_id=contract.contract_id,
        contract_version=contract.version,
        agent_id="worker_001",
        status=HandoffStatus.REPORTING,
        base_commit=contract.base_commit,
        result_commit=result,
        changed_files=changed_files,
        diff_summary="fixed app",
        tests_run=contract.required_tests,
        test_results=("pass",),
        acceptance_evidence={"repository is clean": "git status --porcelain: pass"},
        receipt_id="receipt_engine",
    )


def test_engine_rebuilds_evidence_and_separates_verification_from_integration(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine, contract = prepare_engine(repo, child, base)
    verification = engine.verify_handoff(
        contract.contract_id,
        receipt(contract, result, ("src/app.py",)).to_dict(),
        evidence_workspace=child,
    )
    assert verification["mergeable"] is True
    assert verification["integrated"] is False
    assert verification["repository_evidence"]["changed_files"] == ("src/app.py",)
    assert engine.status()["execution_states"] == {"verified": 1}

    with pytest.raises(ValueError, match="does not contain"):
        engine.record_integration(contract.contract_id)

    git(repo, "merge", "--ff-only", result)
    integration = engine.record_integration(contract.contract_id)
    assert integration["integrated"] is True
    assert engine.status()["execution_states"] == {"integrated": 1}
    assert engine.status()["integration_count"] == 1

    resumed = ProtocolEngine(repo)
    assert resumed.status()["execution_states"] == {"integrated": 1}


def test_engine_blocks_receipt_that_disagrees_with_git(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine, contract = prepare_engine(repo, child, base)
    verification = engine.verify_handoff(
        contract.contract_id,
        receipt(contract, result, ("tests/fake.py",)).to_dict(),
        evidence_workspace=child,
    )
    codes = {item["code"] for item in verification["findings"]}
    assert "CHANGED_FILES_MISMATCH" in codes
    assert verification["mergeable"] is False
    assert engine.status()["execution_states"] == {"rejected": 1}


def test_engine_rejects_unassigned_evidence_workspace(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine, contract = prepare_engine(repo, child, base)
    with pytest.raises(ValueError, match="does not match"):
        engine.verify_handoff(
            contract.contract_id,
            receipt(contract, result, ("src/app.py",)).to_dict(),
            evidence_workspace=repo,
        )


def test_engine_blocks_system_test_failure(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine = ProtocolEngine(repo)
    mission = MissionState("mission_failed_test", "verify tests", root_commit=base)
    engine.initialize(mission.to_dict())
    contract = DelegationContract(
        contract_id="contract_failed_test",
        objective="fix app",
        in_scope=("app",),
        out_of_scope=(),
        allowed_files=("src/**/*.py",),
        forbidden_files=(),
        acceptance_criteria=("test passes",),
        required_tests=(f'"{sys.executable}" -c "raise SystemExit(1)"',),
        base_commit=base,
        parent_id="root",
        mission_id=mission.mission_id,
    )
    engine.delegate(contract.to_dict(), agent_id="worker_001", role="worker", workspace=str(child))
    for state in ("claimed", "executing", "reporting"):
        engine.transition(contract.contract_id, state)
    failed_receipt = HandoffReceipt(
        contract_id=contract.contract_id,
        agent_id="worker_001",
        status=HandoffStatus.REPORTING,
        base_commit=base,
        result_commit=result,
        changed_files=("src/app.py",),
        diff_summary="claim",
        tests_run=contract.required_tests,
        test_results=("pass",),
        acceptance_evidence={"test passes": "claimed pass"},
        receipt_id="receipt_failed_test",
    )
    verification = engine.verify_handoff(
        contract.contract_id,
        failed_receipt.to_dict(),
        evidence_workspace=child,
    )
    codes = {item["code"] for item in verification["findings"]}
    assert {"SYSTEM_TEST_FAILED", "TEST_CLAIM_CONTRADICTED"}.issubset(codes)
