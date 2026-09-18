from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from .agent_runtime import CodexCliRuntime
from .detector import DriftDetector, DriftFinding, FindingSeverity
from .models import (
    AgentCheckpoint,
    AgentRole,
    AgentRunRecord,
    AgentRunStatus,
    AgentTaskPacket,
    DelegationContract,
    EscalationDecision,
    EscalationKind,
    EscalationRequest,
    HandoffReceipt,
    HandoffStatus,
    MissionState,
    ProtocolPolicy,
)
from .project_store import ProjectStore
from .schema import validate_payload
from .state_machine import HandoffStateMachine
from .workspace import GitWorkspace, RepositoryEvidence


class ProtocolEngine:
    """Single application service for persistent delegation, verification, and integration."""

    def __init__(self, workspace: str | Path) -> None:
        self.store = ProjectStore(workspace)
        self.workspace = GitWorkspace(self.store.workspace)
        self.detector = DriftDetector()

    def initialize(
        self,
        mission: dict[str, Any],
        *,
        policy: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        validate_payload("mission", mission)
        model = MissionState.from_dict(mission)
        if not self.workspace.commit_exists(model.root_commit):
            raise ValueError(f"mission root commit does not exist: {model.root_commit}")
        policy_model = ProtocolPolicy.from_dict(policy)
        validate_payload("policy", policy_model.to_dict())
        return self.store.initialize(mission, policy=policy_model.to_dict(), overwrite=overwrite)

    def status(self) -> dict[str, Any]:
        return self.store.status()

    def project_schema(self) -> dict[str, Any]:
        return self.store.schema_status()

    def migrate_project(self) -> dict[str, Any]:
        return self.store.migrate()

    def create_agent_task_packet(self, contract_id: str) -> dict[str, Any]:
        mission = MissionState.from_dict(self.store.require_mission())
        contract = DelegationContract.from_dict(self.store.read_contract(contract_id))
        execution = self.store.read_execution(contract_id)
        if execution["status"] != HandoffStatus.PLANNED.value:
            raise ValueError("agent task dispatch requires planned state")
        workspace = execution.get("workspace")
        if not workspace:
            raise ValueError("prepare an isolated workspace before dispatch")
        execution_workspace = Path(str(workspace)).expanduser().resolve()
        git = GitWorkspace(execution_workspace)
        workspace_head = git.head()
        attempt = int(execution.get("attempt", 1))
        if attempt == 1 and workspace_head != contract.base_commit:
            raise ValueError("dispatch workspace HEAD does not match the contract base commit")
        if attempt > 1 and not git.is_ancestor(contract.base_commit, workspace_head):
            raise ValueError("retry workspace no longer descends from the contract base commit")
        workspace_status = git.status_porcelain()
        if workspace_status and attempt == 1:
            raise ValueError("dispatch workspace must be clean")
        if workspace_status and attempt > 1:
            checkpoint = self.store.latest_checkpoint(contract_id)
            if checkpoint["current_commit"] != workspace_head or tuple(checkpoint.get("workspace_status", ())) != workspace_status:
                raise ValueError("retry workspace differs from the latest checkpoint")
        packet = AgentTaskPacket(
            mission_id=mission.mission_id,
            root_objective=mission.objective,
            root_acceptance_criteria=mission.acceptance_criteria,
            root_decisions=mission.decisions,
            contract_id=contract.contract_id,
            contract_version=contract.version,
            attempt=attempt,
            agent_id=str(execution["agent_id"]),
            role=AgentRole(str(execution["role"])),
            parent_id=contract.parent_id,
            workspace=str(execution_workspace),
            base_commit=contract.base_commit,
            workspace_commit=workspace_head,
            workspace_status=workspace_status,
            objective=contract.objective,
            global_constraints=mission.global_constraints,
            in_scope=contract.in_scope,
            out_of_scope=contract.out_of_scope,
            allowed_files=contract.allowed_files,
            forbidden_files=contract.forbidden_files,
            acceptance_criteria=contract.acceptance_criteria,
            required_tests=contract.required_tests,
            deadline_or_budget=contract.deadline_or_budget,
            protocol_rules=(
                "Work only inside the assigned workspace and contract scope.",
                "Do not change the mission, contract, parent decisions, or delegation limits.",
                "Stop and escalate before acting on stale state, wider scope, or root-constraint conflict.",
                "Record a checkpoint before interruption or when blocked.",
                "Commit the result before reporting and do not claim tests that were not run.",
            ),
        )
        validate_payload("dispatch", packet.to_dict())
        return self.store.save_dispatch(packet.to_dict())

    def run_codex_agent(
        self,
        contract_id: str,
        *,
        authorized_by_root: bool,
        model: str | None = None,
        timeout_seconds: float = 3600,
        resume_previous: bool = False,
        runtime: CodexCliRuntime | None = None,
    ) -> dict[str, Any]:
        if not authorized_by_root:
            raise PermissionError("starting an external Codex run requires explicit Root authorization")
        execution = self.store.read_execution(contract_id)
        if execution["status"] != HandoffStatus.PLANNED.value:
            raise ValueError("Codex agent launch requires planned state")
        packet = self.create_agent_task_packet(contract_id)
        runtime_adapter = runtime or CodexCliRuntime()
        resume_thread_id = None
        if resume_previous:
            previous = self.store.latest_agent_run(contract_id)
            resume_thread_id = previous.get("thread_id")
            if not resume_thread_id:
                raise ValueError("previous run has no resumable Codex thread id")
        run_id = f"run_{uuid4().hex[:12]}"
        artifact_root = self.store.control / "run-artifacts" / run_id
        final_path = artifact_root / "final-message.txt"
        command = runtime_adapter.build_command(
            Path(str(packet["workspace"])),
            final_path,
            model=model,
            resume_thread_id=resume_thread_id,
        )
        running = AgentRunRecord(
            run_id=run_id,
            contract_id=contract_id,
            contract_version=int(packet["contract_version"]),
            attempt=int(packet["attempt"]),
            agent_id=str(packet["agent_id"]),
            runtime="codex_cli",
            status=AgentRunStatus.RUNNING,
            command=tuple(command),
            thread_id=resume_thread_id,
            event_log=str(artifact_root / "events.jsonl"),
            final_message_path=str(final_path),
        )
        self.store.save_agent_run(running.to_dict())
        self.transition(contract_id, HandoffStatus.CLAIMED.value)
        self.transition(contract_id, HandoffStatus.EXECUTING.value)
        try:
            result = runtime_adapter.execute(
                packet,
                artifact_root,
                timeout_seconds=timeout_seconds,
                model=model,
                resume_thread_id=resume_thread_id,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[-2000:]
            stored = self.store.update_agent_run(
                run_id,
                {"status": AgentRunStatus.FAILED.value, "returncode": 1, "error": error},
            )
            self.transition(contract_id, HandoffStatus.PARTIAL.value)
            self.record_agent_checkpoint(
                contract_id,
                completed=(),
                pending=("resume or retry the assigned task",),
                blockers=(error,),
                notes=(f"runtime run {run_id} raised before completion",),
            )
            return {"run": stored, "execution": self.store.read_execution(contract_id)}
        stored = self.store.update_agent_run(
            run_id,
            {
                "status": result.status,
                "returncode": result.returncode,
                "thread_id": result.thread_id,
                "event_log": result.event_log,
                "final_message_path": result.final_message_path,
                "final_message": result.final_message,
                "error": result.error,
                "usage": result.usage,
            },
        )
        if result.status == AgentRunStatus.SUCCEEDED.value:
            self.transition(contract_id, HandoffStatus.REPORTING.value)
        else:
            self.transition(contract_id, HandoffStatus.PARTIAL.value)
            self.record_agent_checkpoint(
                contract_id,
                completed=(),
                pending=("resume or retry the assigned task",),
                blockers=((result.error or f"Codex CLI exited with {result.returncode}")[-2000:],),
                notes=(f"runtime run {run_id} failed",),
            )
        return {"run": stored, "execution": self.store.read_execution(contract_id)}

    def retry_execution(self, contract_id: str, *, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("retry reason is required")
        execution = self.store.read_execution(contract_id)
        state = HandoffStatus(str(execution["status"]))
        if state not in {HandoffStatus.PARTIAL, HandoffStatus.REJECTED}:
            raise ValueError("retry requires partial or rejected state")
        contract = DelegationContract.from_dict(self.store.read_contract(contract_id))
        if contract.base_commit != self.workspace.head():
            raise ValueError("parent HEAD changed; escalate and revise the contract instead of retrying")
        workspace = execution.get("workspace")
        if not workspace:
            raise ValueError("retry requires the assigned workspace")
        git = GitWorkspace(Path(str(workspace)).expanduser().resolve())
        head = git.head()
        attempt = int(execution.get("attempt", 1))
        if attempt >= self._policy().max_agent_attempts:
            raise ValueError("maximum agent attempts reached; escalate or reject the contract")
        if state == HandoffStatus.PARTIAL:
            checkpoint = self.store.latest_checkpoint(contract_id, attempt=attempt)
            if checkpoint["current_commit"] != head:
                raise ValueError("workspace HEAD changed after the failure checkpoint")
        elif git.status_porcelain():
            raise ValueError("rejected worktree must be clean before retry")
        execution.update(
            status=HandoffStatus.PLANNED.value,
            attempt=attempt + 1,
            current_commit=head,
            history=[*execution.get("history", []), HandoffStatus.PLANNED.value],
        )
        self.store.save_execution(execution, replace=True)
        self.store.append_event(
            "execution_retry_planned",
            {"contract_id": contract_id, "attempt": attempt + 1, "reason": reason},
        )
        return execution

    def cleanup_workspace(self, contract_id: str, *, confirmed_by_root: bool) -> dict[str, Any]:
        if not confirmed_by_root:
            raise PermissionError("worktree cleanup requires explicit Root confirmation")
        execution = self.store.read_execution(contract_id)
        state = HandoffStatus(str(execution["status"]))
        if state not in {HandoffStatus.INTEGRATED, HandoffStatus.REJECTED}:
            raise ValueError("worktree cleanup requires integrated or rejected state")
        workspace = execution.get("workspace")
        if not workspace:
            return {"contract_id": contract_id, "cleaned": False, "reason": "no assigned workspace"}
        target = Path(str(workspace)).expanduser().resolve()
        if target == self.store.workspace:
            raise ValueError("refusing to remove the root project workspace")
        if not target.is_dir():
            raise FileNotFoundError(f"assigned worktree does not exist: {target}")
        git = GitWorkspace(target)
        if git.status_porcelain():
            raise ValueError("refusing to remove a worktree with uncommitted changes")
        if not self.workspace.is_registered_worktree(target):
            raise ValueError("assigned workspace is not a registered Git worktree")
        self.workspace.remove_worktree(target)
        execution["workspace"] = None
        self.store.save_execution(execution, replace=True)
        self.store.append_event("workspace_cleaned", {"contract_id": contract_id, "workspace": str(target)})
        return {"contract_id": contract_id, "cleaned": True, "workspace": str(target)}

    def record_agent_checkpoint(
        self,
        contract_id: str,
        *,
        completed: tuple[str, ...],
        pending: tuple[str, ...],
        blockers: tuple[str, ...] = (),
        notes: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        contract = DelegationContract.from_dict(self.store.read_contract(contract_id))
        execution = self.store.read_execution(contract_id)
        state = HandoffStatus(str(execution["status"]))
        if state not in {
            HandoffStatus.CLAIMED,
            HandoffStatus.EXECUTING,
            HandoffStatus.PARTIAL,
            HandoffStatus.BLOCKED,
        }:
            raise ValueError("checkpoint requires claimed, executing, partial, or blocked state")
        workspace = execution.get("workspace")
        if not workspace:
            raise ValueError("checkpoint requires an assigned workspace")
        git = GitWorkspace(Path(str(workspace)).expanduser().resolve())
        checkpoint = AgentCheckpoint(
            contract_id=contract.contract_id,
            contract_version=contract.version,
            attempt=int(execution.get("attempt", 1)),
            agent_id=str(execution["agent_id"]),
            status=state,
            current_commit=git.head(),
            completed=completed,
            pending=pending,
            blockers=blockers,
            notes=notes,
            workspace_status=git.status_porcelain(),
        )
        validate_payload("checkpoint", checkpoint.to_dict())
        execution["current_commit"] = checkpoint.current_commit
        self.store.save_execution(execution, replace=True)
        return self.store.save_checkpoint(checkpoint.to_dict())

    def draft_contract(
        self,
        *,
        objective: str,
        in_scope: tuple[str, ...],
        out_of_scope: tuple[str, ...],
        allowed_files: tuple[str, ...],
        forbidden_files: tuple[str, ...],
        acceptance_criteria: tuple[str, ...],
        required_tests: tuple[str, ...],
        parent_id: str = "root",
        dependencies: tuple[str, ...] = (),
        deadline_or_budget: str | None = None,
        contract_id: str | None = None,
    ) -> dict[str, Any]:
        mission = MissionState.from_dict(self.store.require_mission())
        policy = self._policy()
        if policy.require_required_tests and not required_tests:
            raise ValueError("project policy requires at least one contract test")
        values: dict[str, Any] = {
            "objective": objective,
            "in_scope": in_scope,
            "out_of_scope": out_of_scope,
            "allowed_files": allowed_files,
            "forbidden_files": forbidden_files,
            "acceptance_criteria": acceptance_criteria,
            "required_tests": required_tests,
            "base_commit": self.workspace.head(),
            "parent_id": parent_id,
            "mission_id": mission.mission_id,
            "dependencies": dependencies,
            "deadline_or_budget": deadline_or_budget,
        }
        if contract_id is not None:
            values["contract_id"] = contract_id
        contract = DelegationContract(**values)
        validate_payload("contract", contract.to_dict())
        return contract.to_dict()

    def draft_receipt(
        self,
        contract_id: str,
        *,
        diff_summary: str,
        acceptance_evidence: dict[str, str],
        assumptions: tuple[str, ...] = (),
        risks: tuple[str, ...] = (),
        unresolved_questions: tuple[str, ...] = (),
        evidence_links: tuple[str, ...] = (),
        recommended_next_action: str | None = "parent verification",
        evidence_workspace: str | Path | None = None,
        test_timeout_seconds: float = 600,
    ) -> dict[str, Any]:
        if not diff_summary.strip():
            raise ValueError("diff_summary is required")
        contract = DelegationContract.from_dict(self.store.read_contract(contract_id))
        execution = self.store.read_execution(contract_id)
        if execution["status"] != HandoffStatus.REPORTING.value:
            raise ValueError("receipt drafting requires reporting state")
        evidence_path = self._resolve_evidence_workspace(execution, evidence_workspace)
        timeout = self._bounded_timeout(test_timeout_seconds)
        git = GitWorkspace(evidence_path)
        result_commit = git.head()
        evidence = git.collect_evidence(
            contract.base_commit,
            result_commit,
            contract.required_tests,
            timeout_seconds=timeout,
        )
        receipt = HandoffReceipt(
            contract_id=contract.contract_id,
            contract_version=contract.version,
            agent_id=str(execution["agent_id"]),
            status=HandoffStatus.REPORTING,
            base_commit=contract.base_commit,
            result_commit=result_commit,
            changed_files=evidence.changed_files,
            diff_summary=diff_summary,
            tests_run=tuple(item.command for item in evidence.tests),
            test_results=tuple("pass" if item.passed else "fail" for item in evidence.tests),
            evidence_links=evidence_links,
            assumptions=assumptions,
            risks=risks,
            unresolved_questions=unresolved_questions,
            acceptance_evidence=acceptance_evidence,
            recommended_next_action=recommended_next_action,
        )
        validate_payload("receipt", receipt.to_dict())
        return receipt.to_dict()

    def resume_summary(self) -> dict[str, Any]:
        status = self.store.status()
        if not status["initialized"]:
            return {**status, "current_head": self.workspace.head(), "executions": [], "next_actions": ["initialize mission"]}
        current_head = self.workspace.head()
        summaries = []
        next_actions = []
        for execution in sorted(self.store.executions(), key=lambda item: (int(item["depth"]), str(item["contract_id"]))):
            contract = self.store.read_contract(str(execution["contract_id"]))
            state = HandoffStatus(str(execution["status"]))
            action = self._recommended_action(state, str(execution["contract_id"]))
            findings: list[str] = []
            checkpoint = None
            try:
                verification = self.store.latest_verification(str(execution["contract_id"]))
                if int(verification.get("attempt", 1)) == int(execution.get("attempt", 1)):
                    findings = [
                        str(item["code"])
                        for item in verification.get("findings", [])
                        if item.get("severity") == "block"
                    ]
            except FileNotFoundError:
                pass
            try:
                checkpoint = self.store.latest_checkpoint(
                    str(execution["contract_id"]), attempt=int(execution.get("attempt", 1))
                )
            except FileNotFoundError:
                pass
            stale = state not in {HandoffStatus.INTEGRATED, HandoffStatus.REJECTED} and contract["base_commit"] != current_head
            workspace_health = self._workspace_health(execution, checkpoint)
            if not workspace_health["exists"] and state not in {HandoffStatus.INTEGRATED, HandoffStatus.REJECTED}:
                action = "restore or prepare the assigned workspace before continuing"
            elif checkpoint and not workspace_health["checkpoint_matches_head"]:
                action = "inspect workspace changes made after the latest checkpoint"
            item = {
                **execution,
                "objective": contract["objective"],
                "contract_version": contract["version"],
                "base_commit": contract["base_commit"],
                "parent_head": current_head,
                "stale_against_parent": stale,
                "blocking_findings": findings,
                "latest_checkpoint": checkpoint,
                "workspace_health": workspace_health,
                "recommended_action": "escalate stale base" if stale else action,
            }
            summaries.append(item)
            if state != HandoffStatus.INTEGRATED:
                next_actions.append({"contract_id": execution["contract_id"], "action": item["recommended_action"]})
        return {
            **status,
            "current_head": current_head,
            "root_commit_changed": status["mission"]["root_commit"] != current_head,
            "executions": summaries,
            "next_actions": next_actions,
        }

    def project_report(self) -> dict[str, Any]:
        status = self.store.status()
        if not status["initialized"]:
            return {"status": status, "delegation_tree": [], "timeline": [], "metrics": {"event_count": 0}}
        events = self.store.events()
        nodes = []
        blocking_finding_count = 0
        for execution in sorted(self.store.executions(), key=lambda item: (int(item["depth"]), str(item["contract_id"]))):
            contract_id = str(execution["contract_id"])
            contract = self.store.read_contract(contract_id)
            try:
                checkpoint = self.store.latest_checkpoint(contract_id, attempt=int(execution.get("attempt", 1)))
            except FileNotFoundError:
                checkpoint = None
            try:
                latest_run = self.store.latest_agent_run(contract_id)
            except FileNotFoundError:
                latest_run = None
            try:
                verification = self.store.latest_verification(contract_id)
                findings = (
                    [
                        item
                        for item in verification.get("findings", [])
                        if item.get("severity") == FindingSeverity.BLOCK.value
                    ]
                    if int(verification.get("attempt", 1)) == int(execution.get("attempt", 1))
                    else []
                )
            except FileNotFoundError:
                verification = None
                findings = []
            blocking_finding_count += len(findings)
            nodes.append(
                {
                    "contract_id": contract_id,
                    "contract_version": contract["version"],
                    "objective": contract["objective"],
                    "agent_id": execution["agent_id"],
                    "role": execution["role"],
                    "parent_id": execution["parent_id"],
                    "depth": execution["depth"],
                    "status": execution["status"],
                    "workspace": execution.get("workspace"),
                    "latest_checkpoint": checkpoint,
                    "latest_agent_run": latest_run,
                    "latest_verification": None
                    if verification is None
                    else {
                        "receipt_id": verification["receipt_id"],
                        "mergeable": verification["mergeable"],
                        "verified_at": verification.get("verified_at"),
                        "blocking_findings": [item["code"] for item in findings],
                    },
                    "recommended_action": self._recommended_action(HandoffStatus(execution["status"]), contract_id),
                }
            )
        return {
            "mission": status["mission"],
            "policy": status["policy"],
            "schema": status["schema"],
            "delegation_tree": nodes,
            "timeline": events,
            "metrics": {
                "event_count": len(events),
                "contract_count": status["contract_count"],
                "dispatch_count": status["dispatch_count"],
                "checkpoint_count": status["checkpoint_count"],
                "agent_run_count": status["agent_run_count"],
                "verification_count": status["verification_count"],
                "integration_count": status["integration_count"],
                "blocking_finding_count": blocking_finding_count,
            },
        }

    def delegate(
        self,
        contract: dict[str, Any],
        *,
        agent_id: str,
        role: str,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        validate_payload("contract", contract)
        mission = MissionState.from_dict(self.store.require_mission())
        policy = self._policy()
        model = DelegationContract.from_dict(contract)
        if policy.require_required_tests and not model.required_tests:
            raise ValueError("project policy requires at least one contract test")
        if model.mission_id != mission.mission_id:
            raise ValueError("contract mission_id does not match the active mission")
        if self.store.contract_exists(model.contract_id):
            raise ValueError("contract_id already exists; use contract revision after escalation")

        executions = self.store.executions()
        if model.parent_id == "root":
            parent_depth = 0
            expected_role = AgentRole.WORKER
        else:
            parent = next((item for item in executions if item["agent_id"] == model.parent_id), None)
            if parent is None:
                raise ValueError(f"unknown parent agent: {model.parent_id}")
            if parent["role"] == AgentRole.LEAF.value:
                raise ValueError("leaf agents cannot delegate")
            parent_depth = int(parent["depth"])
            expected_role = AgentRole.LEAF
        assigned_role = AgentRole(role)
        if assigned_role != expected_role:
            raise ValueError(f"parent must delegate to {expected_role.value}")
        depth = parent_depth + 1
        if depth > mission.max_depth:
            raise ValueError("maximum recursion depth reached")
        children = [item for item in executions if item.get("parent_id") == model.parent_id]
        if len(children) >= mission.max_children:
            raise ValueError("maximum child count reached")
        known_contracts = {item["contract_id"] for item in self.store.contracts()}
        unknown = sorted(set(model.dependencies) - known_contracts)
        if unknown:
            raise ValueError(f"unknown contract dependencies: {unknown}")
        if not self.workspace.commit_exists(model.base_commit):
            raise ValueError(f"contract base commit does not exist: {model.base_commit}")
        if workspace and policy.require_isolated_workspace and Path(workspace).expanduser().resolve() == self.store.workspace:
            raise ValueError("project policy requires an isolated execution workspace")

        self.store.save_contract(model.to_dict())
        execution = {
            "contract_id": model.contract_id,
            "agent_id": agent_id,
            "role": assigned_role.value,
            "parent_id": model.parent_id,
            "depth": depth,
            "status": HandoffStatus.PLANNED.value,
            "workspace": workspace,
            "current_commit": model.base_commit,
            "history": [HandoffStatus.PLANNED.value],
            "attempt": 1,
        }
        self.store.save_execution(execution)
        self.store.append_event(
            "delegated",
            {"contract_id": model.contract_id, "agent_id": agent_id, "role": assigned_role.value, "depth": depth},
        )
        return execution

    def transition(self, contract_id: str, target: str) -> dict[str, Any]:
        execution = self.store.read_execution(contract_id)
        current = HandoffStatus(execution["status"])
        machine = HandoffStateMachine(current, [HandoffStatus(item) for item in execution.get("history", [current.value])])
        status = machine.transition(HandoffStatus(target))
        execution["status"] = status.value
        execution["history"] = [item.value for item in machine.history]
        self.store.save_execution(execution, replace=True)
        self.store.append_event("state_transition", {"contract_id": contract_id, "status": status.value})
        return execution

    def prepare_workspace(self, contract_id: str, target: str | Path) -> dict[str, Any]:
        execution = self.store.read_execution(contract_id)
        if execution["status"] != HandoffStatus.PLANNED.value:
            raise ValueError("workspace preparation requires planned state")
        contract = DelegationContract.from_dict(self.store.read_contract(contract_id))
        target_path = Path(target).expanduser().resolve()
        if self._policy().require_isolated_workspace and target_path == self.store.workspace:
            raise ValueError("project policy requires an isolated execution workspace")
        if target_path.exists():
            raise FileExistsError(f"worktree target already exists: {target_path}")
        child = self.workspace.create_worktree(target_path, contract.base_commit)
        execution["workspace"] = str(target_path)
        execution["current_commit"] = child.head()
        self.store.save_execution(execution, replace=True)
        self.store.append_event(
            "workspace_prepared",
            {"contract_id": contract_id, "workspace": str(target_path), "base_commit": contract.base_commit},
        )
        return execution

    def verify_handoff(
        self,
        contract_id: str,
        receipt: dict[str, Any],
        *,
        evidence_workspace: str | Path | None = None,
        test_timeout_seconds: float = 600,
    ) -> dict[str, Any]:
        validate_payload("receipt", receipt)
        mission = MissionState.from_dict(self.store.require_mission())
        contract = DelegationContract.from_dict(self.store.read_contract(contract_id))
        execution = self.store.read_execution(contract_id)
        receipt_model = HandoffReceipt.from_dict(receipt)
        if execution["status"] != HandoffStatus.REPORTING.value:
            raise ValueError("handoff verification requires reporting state")

        policy = self._policy()
        evidence_path = self._resolve_evidence_workspace(execution, evidence_workspace)
        timeout = self._bounded_timeout(test_timeout_seconds)
        parent_head = self.workspace.head()
        findings = self.detector.inspect(
            mission,
            contract,
            receipt_model,
            current_head=parent_head,
            root_constraints=mission.global_constraints,
            expected_agent_id=str(execution["agent_id"]),
        )
        findings.extend(self._dependency_findings(contract))
        evidence = self._collect_and_compare_evidence(
            contract,
            receipt_model,
            evidence_path,
            timeout,
            policy,
        )
        findings.extend(evidence[1])
        mergeable = self.detector.is_mergeable(findings)
        verification = {
            "receipt_id": receipt_model.receipt_id,
            "contract_id": contract_id,
            "mergeable": mergeable,
            "findings": [asdict(item) | {"severity": item.severity.value} for item in findings],
            "repository_evidence": self._evidence_dict(evidence[0]),
            "integration_authorized": mergeable,
            "integrated": False,
            "attempt": int(execution.get("attempt", 1)),
        }
        self.store.record_verification(receipt_model.to_dict(), verification)
        self.transition(contract_id, HandoffStatus.VERIFIED.value if mergeable else HandoffStatus.REJECTED.value)
        return verification

    def record_integration(
        self,
        contract_id: str,
        *,
        integration_tests: tuple[str, ...] = (),
        test_timeout_seconds: float = 600,
    ) -> dict[str, Any]:
        execution = self.store.read_execution(contract_id)
        if execution["status"] != HandoffStatus.VERIFIED.value:
            raise ValueError("only a verified handoff can be integrated")
        verification = self.store.latest_verification(contract_id)
        result_commit = str(verification["repository_evidence"]["result_commit"])
        head = self.workspace.head()
        if not self.workspace.is_ancestor(result_commit, head):
            raise ValueError("current repository HEAD does not contain the verified result commit")
        contract = DelegationContract.from_dict(self.store.read_contract(contract_id))
        timeout = self._bounded_timeout(test_timeout_seconds)
        commands = tuple(dict.fromkeys((*contract.required_tests, *integration_tests)))
        tests = []
        for command in commands:
            passed, output = self.workspace.run_tests(command, timeout_seconds=timeout)
            tests.append({"command": command, "passed": passed, "output": output[-12000:]})
        if any(not item["passed"] for item in tests):
            raise ValueError("integration tests failed; contract remains verified but not integrated")
        record = {
            "contract_id": contract_id,
            "receipt_id": verification["receipt_id"],
            "result_commit": result_commit,
            "integrated_commit": head,
            "tests": tests,
            "integrated": True,
        }
        self.store.record_integration(record)
        self.transition(contract_id, HandoffStatus.INTEGRATED.value)
        return record

    def submit_escalation(self, request: dict[str, Any]) -> dict[str, Any]:
        validate_payload("escalation", request)
        model = EscalationRequest.from_dict(request)
        contract = DelegationContract.from_dict(self.store.read_contract(model.contract_id))
        execution = self.store.read_execution(model.contract_id)
        if execution["status"] != HandoffStatus.EXECUTING.value:
            raise ValueError("escalations can only be submitted while executing")
        if model.agent_id != execution["agent_id"] or model.contract_version != contract.version:
            raise ValueError("escalation agent or contract version is stale")
        self.store.save_escalation(model.to_dict())
        stale = EscalationKind.STALE_STATE in model.kinds or model.contract_base_commit != model.parent_head
        needs_decision = bool(model.requested_changes) or model.requires_user_decision or any(
            item in model.kinds for item in (EscalationKind.SCOPE_CHANGE, EscalationKind.ROOT_CONSTRAINT_CONFLICT)
        )
        if stale:
            self.transition(model.contract_id, HandoffStatus.STALE.value)
        if needs_decision:
            self.transition(model.contract_id, HandoffStatus.NEEDS_PARENT_DECISION.value)
        elif not stale:
            self.transition(model.contract_id, HandoffStatus.BLOCKED.value)
        return self.store.read_execution(model.contract_id)

    def decide_escalation(
        self,
        request_id: str,
        *,
        approved: bool,
        rationale: str,
        user_approved: bool = False,
    ) -> dict[str, Any]:
        request = EscalationRequest.from_dict(self.store.read_escalation(request_id))
        if request.requires_user_decision and approved and not user_approved:
            raise ValueError("root-constraint changes require explicit user approval")
        decision = EscalationDecision(request_id, request.contract_id, approved, rationale, user_approved=user_approved)
        self.store.save_decision(decision.to_dict())
        if not approved:
            self.transition(request.contract_id, HandoffStatus.REJECTED.value)
        return decision.to_dict()

    def revise_contract(self, request_id: str, revised: dict[str, Any]) -> dict[str, Any]:
        request = self.store.read_escalation(request_id)
        decision = self.store.read_decision(request_id)
        if not decision["approved"]:
            raise ValueError("contract revision requires an approved escalation")
        current = DelegationContract.from_dict(self.store.read_contract(request["contract_id"]))
        model = DelegationContract.from_dict(revised)
        if model.contract_id != current.contract_id or model.version != current.version + 1:
            raise ValueError("revised contract must keep its id and increment version by one")
        if model.mission_id != current.mission_id or model.parent_id != current.parent_id:
            raise ValueError("revision cannot change mission or parent")
        if model.base_commit != self.workspace.head():
            raise ValueError("revised contract must use current parent HEAD")
        self.store.save_contract(model.to_dict())
        execution = self.store.read_execution(model.contract_id)
        execution.update(
            status=HandoffStatus.PLANNED.value,
            current_commit=model.base_commit,
            attempt=int(execution.get("attempt", 1)) + 1,
            history=[HandoffStatus.PLANNED.value],
        )
        self.store.save_execution(execution, replace=True)
        self.store.append_event(
            "contract_revised",
            {"contract_id": model.contract_id, "old_version": current.version, "new_version": model.version},
        )
        return execution

    def _dependency_findings(self, contract: DelegationContract) -> list[DriftFinding]:
        missing = []
        for dependency in contract.dependencies:
            try:
                status = self.store.read_execution(dependency)["status"]
            except FileNotFoundError:
                status = None
            if status != HandoffStatus.INTEGRATED.value:
                missing.append(dependency)
        if not missing:
            return []
        return [
            DriftFinding(
                "DEPENDENCY_NOT_INTEGRATED",
                FindingSeverity.BLOCK,
                "contract dependencies are not integrated",
                ", ".join(missing),
            )
        ]

    def _collect_and_compare_evidence(
        self,
        contract: DelegationContract,
        receipt: HandoffReceipt,
        evidence_workspace: Path,
        timeout_seconds: float,
        policy: ProtocolPolicy,
    ) -> tuple[RepositoryEvidence, list[DriftFinding]]:
        if not receipt.result_commit:
            evidence = GitWorkspace(evidence_workspace).collect_evidence(
                contract.base_commit, contract.base_commit, (), timeout_seconds=timeout_seconds
            )
            return evidence, []
        git = GitWorkspace(evidence_workspace.resolve())
        evidence = git.collect_evidence(
            contract.base_commit,
            receipt.result_commit,
            contract.required_tests,
            timeout_seconds=timeout_seconds,
        )
        findings: list[DriftFinding] = []
        if policy.require_isolated_workspace and evidence_workspace == self.store.workspace:
            findings.append(
                DriftFinding("SHARED_EVIDENCE_WORKSPACE", FindingSeverity.BLOCK, "project policy requires isolated evidence workspaces")
            )
        if policy.require_clean_evidence_workspace and not evidence.workspace_clean:
            findings.append(
                DriftFinding(
                    "DIRTY_EVIDENCE_WORKSPACE",
                    FindingSeverity.BLOCK,
                    "evidence workspace contains uncommitted changes",
                    ", ".join(evidence.workspace_status),
                )
            )
        if len(evidence.changed_files) > policy.max_changed_files:
            findings.append(
                DriftFinding(
                    "CHANGE_LIMIT_EXCEEDED",
                    FindingSeverity.BLOCK,
                    "changed-file count exceeds project policy",
                    f"actual={len(evidence.changed_files)}, limit={policy.max_changed_files}",
                )
            )
        if not evidence.base_exists:
            findings.append(DriftFinding("BASE_COMMIT_NOT_FOUND", FindingSeverity.BLOCK, "base commit does not exist"))
        if not evidence.result_exists:
            findings.append(DriftFinding("RESULT_COMMIT_NOT_FOUND", FindingSeverity.BLOCK, "result commit does not exist"))
        if evidence.result_exists and evidence.workspace_head != receipt.result_commit:
            findings.append(
                DriftFinding(
                    "EVIDENCE_HEAD_MISMATCH",
                    FindingSeverity.BLOCK,
                    "evidence workspace HEAD does not equal the reported result commit",
                    f"head={evidence.workspace_head}, result={receipt.result_commit}",
                )
            )
        if evidence.base_exists and evidence.result_exists and not evidence.result_descends_from_base:
            findings.append(DriftFinding("RESULT_NOT_DESCENDANT", FindingSeverity.BLOCK, "result commit does not descend from base commit"))
        claimed_files = tuple(sorted(path.replace("\\", "/") for path in receipt.changed_files))
        actual_files = tuple(sorted(evidence.changed_files))
        if claimed_files != actual_files:
            findings.append(
                DriftFinding(
                    "CHANGED_FILES_MISMATCH",
                    FindingSeverity.BLOCK,
                    "reported changed files do not match Git diff",
                    f"claimed={claimed_files}, actual={actual_files}",
                )
            )
        failed = [item.command for item in evidence.tests if not item.passed]
        if failed:
            findings.append(
                DriftFinding("SYSTEM_TEST_FAILED", FindingSeverity.BLOCK, "system-executed required tests failed", ", ".join(failed))
            )
        claimed_results = dict(zip(receipt.tests_run, receipt.test_results))
        contradicted = [item.command for item in evidence.tests if claimed_results.get(item.command, "").lower() in {"pass", "passed", "ok", "success"} and not item.passed]
        if contradicted:
            findings.append(
                DriftFinding("TEST_CLAIM_CONTRADICTED", FindingSeverity.BLOCK, "reported passing tests failed independently", ", ".join(contradicted))
            )
        return evidence, findings

    def _policy(self) -> ProtocolPolicy:
        return ProtocolPolicy.from_dict(self.store.read_policy())

    def _bounded_timeout(self, requested: float) -> float:
        if requested <= 0:
            raise ValueError("test timeout must be positive")
        return min(requested, self._policy().max_test_timeout_seconds)

    def _resolve_evidence_workspace(
        self,
        execution: dict[str, Any],
        requested: str | Path | None,
    ) -> Path:
        assigned_workspace = execution.get("workspace")
        requested_workspace = Path(requested).expanduser().resolve() if requested else None
        if assigned_workspace:
            assigned_path = Path(str(assigned_workspace)).expanduser().resolve()
            if requested_workspace is not None and requested_workspace != assigned_path:
                raise ValueError("evidence workspace does not match the assigned execution workspace")
            return assigned_path
        if requested_workspace is not None:
            return requested_workspace
        raise ValueError("verification requires an assigned evidence workspace")

    @staticmethod
    def _workspace_health(execution: dict[str, Any], checkpoint: dict[str, Any] | None) -> dict[str, Any]:
        workspace = execution.get("workspace")
        if not workspace:
            return {"exists": False, "head": None, "clean": None, "checkpoint_matches_head": None}
        path = Path(str(workspace)).expanduser().resolve()
        if not path.is_dir():
            return {"exists": False, "head": None, "clean": None, "checkpoint_matches_head": None}
        try:
            git = GitWorkspace(path)
            head = git.head()
            status = git.status_porcelain()
        except (RuntimeError, ValueError):
            return {"exists": True, "head": None, "clean": None, "checkpoint_matches_head": None}
        return {
            "exists": True,
            "head": head,
            "clean": not status,
            "workspace_status": list(status),
            "checkpoint_matches_head": checkpoint is None or checkpoint.get("current_commit") == head,
        }

    @staticmethod
    def _recommended_action(status: HandoffStatus, contract_id: str) -> str:
        actions = {
            HandoffStatus.PLANNED: "prepare workspace, then claim",
            HandoffStatus.CLAIMED: "start execution",
            HandoffStatus.EXECUTING: "continue work or escalate",
            HandoffStatus.REPORTING: "draft or verify handoff receipt",
            HandoffStatus.VERIFIED: "parent review, integrate commit, then record integration",
            HandoffStatus.INTEGRATED: "complete",
            HandoffStatus.PARTIAL: "resume execution or block",
            HandoffStatus.BLOCKED: "resolve blocker and resume",
            HandoffStatus.NEEDS_PARENT_DECISION: "record parent decision",
            HandoffStatus.STALE: "escalate and revise contract at current parent HEAD",
            HandoffStatus.REJECTED: "inspect findings and re-claim only after correction",
        }
        return actions[status] + f" ({contract_id})"

    @staticmethod
    def _evidence_dict(evidence: RepositoryEvidence) -> dict[str, Any]:
        return {
            **asdict(evidence),
            "tests": [asdict(item) for item in evidence.tests],
        }
