import subprocess
import sys
from pathlib import Path

import pytest

from northline.agent_runtime import CodexCliRuntime
from northline.engine import ProtocolEngine
from northline.models import (
    DelegationContract,
    EscalationKind,
    EscalationRequest,
    HandoffReceipt,
    HandoffStatus,
    MissionState,
    ProtocolPolicy,
)
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


def test_engine_drafts_contract_and_receipt_from_observed_repository_state(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine = ProtocolEngine(repo)
    mission = MissionState("mission_draft", "draft trustworthy artifacts", root_commit=base)
    engine.initialize(mission.to_dict())
    contract_data = engine.draft_contract(
        objective="fix app",
        in_scope=("application",),
        out_of_scope=("configuration",),
        allowed_files=("src/**/*.py",),
        forbidden_files=("pyproject.toml",),
        acceptance_criteria=("app is fixed",),
        required_tests=("git status --porcelain",),
        contract_id="contract_draft",
    )
    assert contract_data["base_commit"] == base
    assert contract_data["mission_id"] == mission.mission_id
    engine.delegate(contract_data, agent_id="worker_draft", role="worker", workspace=str(child))
    for state in ("claimed", "executing", "reporting"):
        engine.transition("contract_draft", state)
    receipt_data = engine.draft_receipt(
        "contract_draft",
        diff_summary="fixed app",
        acceptance_evidence={"app is fixed": "required test passed"},
    )
    assert receipt_data["result_commit"] == result
    assert receipt_data["changed_files"] == ["src/app.py"]
    assert receipt_data["test_results"] == ["pass"]
    assert receipt_data["agent_id"] == "worker_draft"


def test_engine_dispatch_checkpoint_resume_and_report_root_worker_leaf(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    engine = ProtocolEngine(repo)
    mission = MissionState("mission_runtime", "complete nested work", root_commit=base)
    engine.initialize(mission.to_dict())

    worker_contract = engine.draft_contract(
        objective="coordinate application change",
        in_scope=("application",),
        out_of_scope=("configuration",),
        allowed_files=("src/**/*.py",),
        forbidden_files=("pyproject.toml",),
        acceptance_criteria=("tests pass",),
        required_tests=("git status --porcelain",),
        contract_id="contract_worker",
    )
    engine.delegate(worker_contract, agent_id="worker_runtime", role="worker")
    worker_workspace = tmp_path / "worker-runtime"
    engine.prepare_workspace("contract_worker", worker_workspace)
    worker_packet = engine.create_agent_task_packet("contract_worker")
    assert worker_packet["agent_id"] == "worker_runtime"
    assert worker_packet["role"] == "worker"
    assert worker_packet["root_objective"] == "complete nested work"
    engine.transition("contract_worker", "claimed")
    engine.transition("contract_worker", "executing")
    (worker_workspace / "src" / "app.py").write_text("in progress\n", encoding="utf-8")
    checkpoint = engine.record_agent_checkpoint(
        "contract_worker",
        completed=("inspected application",),
        pending=("finish implementation", "run tests"),
        notes=("resume from app.py",),
    )
    assert checkpoint["workspace_status"] == ["M src/app.py"]

    leaf_contract = engine.draft_contract(
        objective="prepare focused helper",
        in_scope=("application helper",),
        out_of_scope=("public API",),
        allowed_files=("src/helper.py",),
        forbidden_files=("src/app.py",),
        acceptance_criteria=("helper exists",),
        required_tests=("git status --porcelain",),
        parent_id="worker_runtime",
        contract_id="contract_leaf",
    )
    engine.delegate(leaf_contract, agent_id="leaf_runtime", role="leaf")
    leaf_workspace = tmp_path / "leaf-runtime"
    engine.prepare_workspace("contract_leaf", leaf_workspace)
    leaf_packet = engine.create_agent_task_packet("contract_leaf")
    assert leaf_packet["role"] == "leaf"
    assert leaf_packet["parent_id"] == "worker_runtime"

    resumed = ProtocolEngine(repo).resume_summary()
    worker = next(item for item in resumed["executions"] if item["contract_id"] == "contract_worker")
    assert worker["latest_checkpoint"]["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert worker["workspace_health"]["checkpoint_matches_head"] is True
    report = ProtocolEngine(repo).project_report()
    assert [(node["role"], node["depth"]) for node in report["delegation_tree"]] == [("worker", 1), ("leaf", 2)]
    assert report["metrics"]["dispatch_count"] == 2
    assert report["metrics"]["checkpoint_count"] == 1
    assert any(event["event_type"] == "agent_checkpoint_recorded" for event in report["timeline"])


def test_engine_runs_codex_records_failure_and_resumes_retry(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    engine = ProtocolEngine(repo)
    engine.initialize(MissionState("mission_run", "execute safely", root_commit=base).to_dict())
    contract = engine.draft_contract(
        objective="inspect app",
        in_scope=("application",),
        out_of_scope=(),
        allowed_files=("app.py",),
        forbidden_files=(),
        acceptance_criteria=("inspection complete",),
        required_tests=("git status --porcelain",),
        contract_id="contract_run",
    )
    engine.delegate(contract, agent_id="worker_run", role="worker")
    child = tmp_path / "run-child"
    engine.prepare_workspace("contract_run", child)

    calls = 0

    def runner(command, **kwargs):
        nonlocal calls
        calls += 1
        output_path = Path(command[command.index("--output-last-message") + 1])
        if calls == 1:
            events = "\n".join(
                (
                    '{"type":"thread.started","thread_id":"thread_retry"}',
                    '{"type":"turn.failed","error":"temporary failure"}',
                )
            )
            return subprocess.CompletedProcess(command, 1, stdout=events, stderr="failed")
        output_path.write_text("completed on retry", encoding="utf-8")
        events = "\n".join(
            (
                '{"type":"thread.started","thread_id":"thread_retry"}',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":4}}',
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout=events, stderr="")

    runtime = CodexCliRuntime(executable=sys.executable, runner=runner)
    with pytest.raises(PermissionError):
        engine.run_codex_agent("contract_run", authorized_by_root=False, runtime=runtime)
    failed = engine.run_codex_agent("contract_run", authorized_by_root=True, runtime=runtime)
    assert failed["execution"]["status"] == "partial"
    assert failed["run"]["status"] == "failed"
    assert engine.status()["checkpoint_count"] == 1

    retried = engine.retry_execution("contract_run", reason="temporary runtime failure")
    assert retried["attempt"] == 2
    assert retried["status"] == "planned"
    succeeded = engine.run_codex_agent(
        "contract_run",
        authorized_by_root=True,
        resume_previous=True,
        runtime=runtime,
    )
    assert succeeded["execution"]["status"] == "reporting"
    assert succeeded["run"]["status"] == "succeeded"
    assert "resume" in succeeded["run"]["command"]
    assert engine.project_report()["metrics"]["agent_run_count"] == 2


def test_engine_blocks_retry_after_policy_attempt_limit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    engine = ProtocolEngine(repo)
    engine.initialize(
        MissionState("mission_attempt_limit", "bound retries", root_commit=base).to_dict(),
        policy=ProtocolPolicy(max_agent_attempts=1).to_dict(),
    )
    contract = engine.draft_contract(
        objective="inspect app",
        in_scope=("application",),
        out_of_scope=(),
        allowed_files=("app.py",),
        forbidden_files=(),
        acceptance_criteria=("inspection complete",),
        required_tests=("git status --porcelain",),
        contract_id="contract_attempt_limit",
    )
    engine.delegate(contract, agent_id="worker_attempt_limit", role="worker")
    engine.prepare_workspace("contract_attempt_limit", tmp_path / "attempt-limit-child")

    def failing_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout='{"type":"turn.failed","error":"failed"}', stderr="")

    runtime = CodexCliRuntime(executable=sys.executable, runner=failing_runner)
    engine.run_codex_agent("contract_attempt_limit", authorized_by_root=True, runtime=runtime)
    with pytest.raises(ValueError, match="maximum agent attempts reached"):
        engine.retry_execution("contract_attempt_limit", reason="try again")


def test_engine_cleans_only_confirmed_clean_terminal_worktree(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine, contract = prepare_engine(repo, child, base)
    verification = engine.verify_handoff(
        contract.contract_id,
        receipt(contract, result, ("src/app.py",)).to_dict(),
        evidence_workspace=child,
    )
    assert verification["mergeable"] is True
    git(repo, "merge", "--ff-only", result)
    engine.record_integration(contract.contract_id)
    with pytest.raises(PermissionError):
        engine.cleanup_workspace(contract.contract_id, confirmed_by_root=False)
    cleaned = engine.cleanup_workspace(contract.contract_id, confirmed_by_root=True)
    assert cleaned["cleaned"] is True
    assert not child.exists()
    assert engine.store.read_execution(contract.contract_id)["workspace"] is None


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
    recovery = engine.resume_summary()
    assert "CHANGED_FILES_MISMATCH" in recovery["executions"][0]["blocking_findings"]


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


def test_engine_blocks_dirty_evidence_workspace_by_policy(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine, contract = prepare_engine(repo, child, base)
    (child / "src" / "app.py").write_text("uncommitted\n", encoding="utf-8")
    verification = engine.verify_handoff(
        contract.contract_id,
        receipt(contract, result, ("src/app.py",)).to_dict(),
        evidence_workspace=child,
    )
    assert "DIRTY_EVIDENCE_WORKSPACE" in {item["code"] for item in verification["findings"]}


def test_engine_blocks_change_count_above_policy_limit(tmp_path: Path):
    repo, child, base, _ = make_repository(tmp_path)
    extra = child / "src" / "extra.py"
    extra.write_text("extra\n", encoding="utf-8")
    git(child, "add", ".")
    git(child, "commit", "-q", "-m", "add extra file")
    result = git(child, "rev-parse", "HEAD")

    engine = ProtocolEngine(repo)
    mission = MissionState("mission_change_limit", "limit change size", root_commit=base)
    engine.initialize(mission.to_dict(), policy=ProtocolPolicy(max_changed_files=1).to_dict())
    contract = DelegationContract(
        contract_id="contract_change_limit",
        objective="fix app with helper",
        in_scope=("application implementation",),
        out_of_scope=(),
        allowed_files=("src/**/*.py",),
        forbidden_files=(),
        acceptance_criteria=("repository is clean",),
        required_tests=("git status --porcelain",),
        base_commit=base,
        parent_id="root",
        mission_id=mission.mission_id,
    )
    engine.delegate(contract.to_dict(), agent_id="worker_001", role="worker", workspace=str(child))
    for state in ("claimed", "executing", "reporting"):
        engine.transition(contract.contract_id, state)
    verification = engine.verify_handoff(
        contract.contract_id,
        receipt(contract, result, ("src/app.py", "src/extra.py")).to_dict(),
        evidence_workspace=child,
    )
    assert "CHANGE_LIMIT_EXCEEDED" in {item["code"] for item in verification["findings"]}


def test_engine_policy_requires_contract_tests(tmp_path: Path):
    repo, _, base, _ = make_repository(tmp_path)
    engine = ProtocolEngine(repo)
    engine.initialize(MissionState("mission_policy", "enforce tests", root_commit=base).to_dict())
    with pytest.raises(ValueError, match="requires at least one"):
        engine.draft_contract(
            objective="untested change",
            in_scope=("app",),
            out_of_scope=(),
            allowed_files=("src/**/*.py",),
            forbidden_files=(),
            acceptance_criteria=("works",),
            required_tests=(),
        )


def test_engine_blocks_stale_parent_head(tmp_path: Path):
    repo, child, base, result = make_repository(tmp_path)
    engine, contract = prepare_engine(repo, child, base)
    (repo / "parent.txt").write_text("advanced\n", encoding="utf-8")
    git(repo, "add", "parent.txt")
    git(repo, "commit", "-q", "-m", "parent advance")
    verification = engine.verify_handoff(
        contract.contract_id,
        receipt(contract, result, ("src/app.py",)).to_dict(),
        evidence_workspace=child,
    )
    assert "STALE_BASE" in {item["code"] for item in verification["findings"]}


def test_persistent_escalation_revision_rebases_contract_on_parent_head(tmp_path: Path):
    repo, child, base, _ = make_repository(tmp_path)
    engine = ProtocolEngine(repo)
    mission = MissionState("mission_escalation", "keep work current", root_commit=base)
    engine.initialize(mission.to_dict(), policy=ProtocolPolicy().to_dict())
    contract_data = engine.draft_contract(
        objective="fix app",
        in_scope=("app",),
        out_of_scope=(),
        allowed_files=("src/**/*.py",),
        forbidden_files=(),
        acceptance_criteria=("tests pass",),
        required_tests=("git status --porcelain",),
        contract_id="contract_escalation",
    )
    engine.delegate(contract_data, agent_id="worker_escalation", role="worker", workspace=str(child))
    engine.transition("contract_escalation", "claimed")
    engine.transition("contract_escalation", "executing")
    (repo / "parent.txt").write_text("advanced\n", encoding="utf-8")
    git(repo, "add", "parent.txt")
    git(repo, "commit", "-q", "-m", "parent advance")
    parent_head = git(repo, "rev-parse", "HEAD")
    request = EscalationRequest(
        contract_id="contract_escalation",
        contract_version=1,
        agent_id="worker_escalation",
        kinds=(EscalationKind.STALE_STATE,),
        contract_base_commit=base,
        workspace_merge_base=base,
        parent_head=parent_head,
        blocking_evidence=("parent HEAD advanced",),
        requested_changes={"base_commit": parent_head},
        request_id="escalation_forward",
    )
    execution = engine.submit_escalation(request.to_dict())
    assert execution["status"] == "needs_parent_decision"
    engine.decide_escalation(request.request_id, approved=True, rationale="rebase on current parent")
    revised = {**contract_data, "version": 2, "base_commit": parent_head}
    restarted = engine.revise_contract(request.request_id, revised)
    assert restarted["status"] == "planned"
    assert engine.store.read_contract("contract_escalation")["version"] == 2
