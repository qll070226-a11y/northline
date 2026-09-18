from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ProtocolPolicy
from .schema import validate_payload
from .version import __version__

CURRENT_SCHEMA_VERSION = 2


class ProjectStore:
    """Persist product-facing mission artifacts under one repository's `.northline` directory."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"workspace must be an existing directory: {self.workspace}")
        self.control = self.workspace / ".northline"

    @property
    def mission_path(self) -> Path:
        return self.control / "mission.json"

    @property
    def policy_path(self) -> Path:
        return self.control / "policy.json"

    @property
    def project_path(self) -> Path:
        return self.control / "project.json"

    def initialize(
        self,
        mission: dict[str, Any],
        *,
        policy: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        validate_payload("mission", mission)
        policy_payload = ProtocolPolicy.from_dict(policy).to_dict()
        validate_payload("policy", policy_payload)
        if self.mission_path.exists() and not overwrite:
            raise FileExistsError("mission already exists; explicit overwrite is required")
        if self.mission_path.exists() and overwrite:
            artifact_directories = ("contracts", "executions", "receipts", "verifications", "integrations")
            if any(self._json_files(directory) for directory in artifact_directories):
                raise ValueError("cannot overwrite a mission with active protocol artifacts")
        self._write_json(self.mission_path, mission)
        self._write_json(self.policy_path, policy_payload)
        self._write_json(
            self.project_path,
            {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "created_with": __version__,
                "updated_with": __version__,
            },
        )
        for directory in (
            "contracts",
            "contract-history",
            "dispatches",
            "checkpoints",
            "agent-runs",
            "executions",
            "receipts",
            "verifications",
            "escalations",
            "decisions",
            "integrations",
        ):
            (self.control / directory).mkdir(parents=True, exist_ok=True)
        self._append_event("mission_initialized", {"mission_id": mission["mission_id"], "policy": policy_payload})
        return self.status()

    def schema_status(self) -> dict[str, Any]:
        initialized = self.mission_path.is_file()
        if not initialized:
            return {
                "state": "uninitialized",
                "schema_version": None,
                "current_schema_version": CURRENT_SCHEMA_VERSION,
                "migration_required": False,
            }
        if not self.project_path.is_file():
            return {
                "state": "legacy",
                "schema_version": 0,
                "current_schema_version": CURRENT_SCHEMA_VERSION,
                "migration_required": True,
            }
        metadata = self._read_json(self.project_path)
        version = int(metadata.get("schema_version", 0))
        if version > CURRENT_SCHEMA_VERSION:
            state = "unsupported_newer"
        elif version < CURRENT_SCHEMA_VERSION:
            state = "migration_required"
        else:
            state = "ready"
        return {
            **metadata,
            "state": state,
            "schema_version": version,
            "current_schema_version": CURRENT_SCHEMA_VERSION,
            "migration_required": version < CURRENT_SCHEMA_VERSION,
        }

    def migrate(self) -> dict[str, Any]:
        status = self.schema_status()
        if status["state"] == "uninitialized":
            raise FileNotFoundError("project is not initialized")
        if status["state"] == "unsupported_newer":
            raise ValueError("project schema is newer than this Northline version")
        if not status["migration_required"]:
            return {**status, "migrated": False}
        from_version = int(status["schema_version"])
        if from_version not in {0, 1}:
            raise ValueError(f"no migration path from schema version {from_version}")
        for directory in ("dispatches", "checkpoints", "agent-runs"):
            (self.control / directory).mkdir(parents=True, exist_ok=True)
        previous = self._read_json(self.project_path) if self.project_path.is_file() else {}
        metadata = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "created_with": previous.get("created_with", "legacy"),
            "updated_with": __version__,
        }
        self._write_json(self.project_path, metadata)
        self._append_event(
            "project_migrated",
            {"from_schema_version": from_version, "to_schema_version": CURRENT_SCHEMA_VERSION},
        )
        return {**self.schema_status(), "migrated": True, "from_schema_version": from_version}

    def read_policy(self) -> dict[str, Any]:
        if not self.policy_path.is_file():
            return ProtocolPolicy().to_dict()
        policy = self._read_json(self.policy_path)
        validate_payload("policy", policy)
        return policy

    def save_contract(self, contract: dict[str, Any]) -> dict[str, Any]:
        mission = self._require_mission()
        validate_payload("contract", contract)
        if contract["mission_id"] != mission["mission_id"]:
            raise ValueError("contract mission_id does not match the project mission")
        path = self.control / "contracts" / f"{self._safe_id(str(contract['contract_id']))}.json"
        if path.exists():
            current = self._read_json(path)
            if int(contract.get("version", 1)) <= int(current.get("version", 1)):
                raise ValueError("contract update must increment the version")
        history_path = (
            self.control
            / "contract-history"
            / self._safe_id(str(contract["contract_id"]))
            / f"v{int(contract.get('version', 1))}.json"
        )
        if history_path.exists():
            raise FileExistsError(f"contract version already exists: {contract['contract_id']} v{contract.get('version', 1)}")
        self._write_json(path, contract)
        self._write_json(history_path, contract)
        self._append_event(
            "contract_saved",
            {"contract_id": contract["contract_id"], "version": contract.get("version", 1)},
        )
        return {"saved": True, "path": str(path), "contract_id": contract["contract_id"]}

    def require_mission(self) -> dict[str, Any]:
        return self._require_mission()

    def contract_exists(self, contract_id: str) -> bool:
        return (self.control / "contracts" / f"{self._safe_id(contract_id)}.json").is_file()

    def contracts(self) -> list[dict[str, Any]]:
        return self._json_files("contracts")

    def read_contract(self, contract_id: str) -> dict[str, Any]:
        path = self.control / "contracts" / f"{self._safe_id(contract_id)}.json"
        if not path.is_file():
            raise FileNotFoundError(f"unknown contract: {contract_id}")
        return self._read_json(path)

    def executions(self) -> list[dict[str, Any]]:
        return self._json_files("executions")

    def read_execution(self, contract_id: str) -> dict[str, Any]:
        path = self.control / "executions" / f"{self._safe_id(contract_id)}.json"
        if not path.is_file():
            raise FileNotFoundError(f"unknown execution: {contract_id}")
        return self._read_json(path)

    def save_execution(self, execution: dict[str, Any], *, replace: bool = False) -> dict[str, Any]:
        contract_id = self._safe_id(str(execution["contract_id"]))
        path = self.control / "executions" / f"{contract_id}.json"
        if path.exists() and not replace:
            raise FileExistsError(f"execution already exists: {contract_id}")
        self._write_json(path, execution)
        return execution

    def save_dispatch(self, packet: dict[str, Any]) -> dict[str, Any]:
        self._require_current_schema()
        validate_payload("dispatch", packet)
        packet_id = self._safe_id(str(packet["packet_id"]))
        path = self.control / "dispatches" / f"{packet_id}.json"
        if path.exists():
            raise FileExistsError(f"dispatch packet already exists: {packet_id}")
        payload = {**packet, "dispatched_at": self._timestamp()}
        self._write_json(path, payload)
        self._append_event(
            "agent_task_dispatched",
            {
                "packet_id": packet_id,
                "contract_id": packet["contract_id"],
                "contract_version": packet["contract_version"],
                "agent_id": packet["agent_id"],
            },
        )
        return payload

    def dispatches(self) -> list[dict[str, Any]]:
        return self._json_files("dispatches")

    def save_checkpoint(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        self._require_current_schema()
        validate_payload("checkpoint", checkpoint)
        contract_id = self._safe_id(str(checkpoint["contract_id"]))
        checkpoint_id = self._safe_id(str(checkpoint["checkpoint_id"]))
        path = self.control / "checkpoints" / contract_id / f"{checkpoint_id}.json"
        if path.exists():
            raise FileExistsError(f"checkpoint already exists: {checkpoint_id}")
        payload = {**checkpoint, "recorded_at": self._timestamp()}
        self._write_json(path, payload)
        self._append_event(
            "agent_checkpoint_recorded",
            {
                "checkpoint_id": checkpoint_id,
                "contract_id": contract_id,
                "status": checkpoint["status"],
            },
        )
        return payload

    def latest_checkpoint(self, contract_id: str, attempt: int | None = None) -> dict[str, Any]:
        root = self.control / "checkpoints" / self._safe_id(contract_id)
        matches = [self._read_json(path) for path in sorted(root.glob("*.json"))] if root.is_dir() else []
        if attempt is not None:
            matches = [item for item in matches if int(item.get("attempt", 1)) == attempt]
        if not matches:
            raise FileNotFoundError(f"no checkpoint for contract: {contract_id}")
        return max(matches, key=lambda item: str(item.get("recorded_at", "")))

    def checkpoints(self) -> list[dict[str, Any]]:
        root = self.control / "checkpoints"
        return [self._read_json(path) for path in sorted(root.glob("*/*.json"))] if root.is_dir() else []

    def save_agent_run(self, run: dict[str, Any]) -> dict[str, Any]:
        self._require_current_schema()
        validate_payload("agentRun", run)
        run_id = self._safe_id(str(run["run_id"]))
        path = self.control / "agent-runs" / f"{run_id}.json"
        if path.exists():
            raise FileExistsError(f"agent run already exists: {run_id}")
        payload = {**run, "recorded_at": self._timestamp()}
        self._write_json(path, payload)
        self._append_event(
            "agent_run_recorded",
            {
                "run_id": run_id,
                "contract_id": run["contract_id"],
                "attempt": run["attempt"],
                "status": run["status"],
            },
        )
        return payload

    def update_agent_run(self, run_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        safe_id = self._safe_id(run_id)
        path = self.control / "agent-runs" / f"{safe_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"unknown agent run: {run_id}")
        current = self._read_json(path)
        recorded_at = current.pop("recorded_at", self._timestamp())
        current.pop("updated_at", None)
        payload = {**current, **updates}
        validate_payload("agentRun", payload)
        stored = {**payload, "recorded_at": recorded_at, "updated_at": self._timestamp()}
        self._write_json(path, stored)
        self._append_event(
            "agent_run_finished",
            {"run_id": safe_id, "contract_id": payload["contract_id"], "status": payload["status"]},
        )
        return stored

    def agent_runs(self, contract_id: str | None = None) -> list[dict[str, Any]]:
        runs = self._json_files("agent-runs")
        if contract_id is None:
            return runs
        return [item for item in runs if item.get("contract_id") == contract_id]

    def latest_agent_run(self, contract_id: str) -> dict[str, Any]:
        matches = self.agent_runs(contract_id)
        if not matches:
            raise FileNotFoundError(f"no agent run for contract: {contract_id}")
        return max(matches, key=lambda item: str(item.get("recorded_at", "")))

    def events(self) -> list[dict[str, Any]]:
        path = self.control / "events.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def record_verification(self, receipt: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        receipt_id = self._safe_id(str(receipt["receipt_id"]))
        receipt_path = self.control / "receipts" / f"{receipt_id}.json"
        verification_path = self.control / "verifications" / f"{receipt_id}.json"
        if receipt_path.exists() or verification_path.exists():
            raise FileExistsError(f"receipt already recorded: {receipt_id}")
        self._write_json(receipt_path, receipt)
        payload = {**verification, "verified_at": self._timestamp()}
        self._write_json(verification_path, payload)
        self._append_event(
            "handoff_verified" if verification["mergeable"] else "handoff_rejected",
            {
                "contract_id": verification["contract_id"],
                "receipt_id": receipt_id,
                "mergeable": verification["mergeable"],
            },
        )
        return payload

    def latest_verification(self, contract_id: str) -> dict[str, Any]:
        matches = [
            item for item in self._json_files("verifications") if item.get("contract_id") == contract_id
        ]
        if not matches:
            raise FileNotFoundError(f"no verification for contract: {contract_id}")
        return max(matches, key=lambda item: str(item.get("verified_at", "")))

    def record_integration(self, integration: dict[str, Any]) -> dict[str, Any]:
        contract_id = self._safe_id(str(integration["contract_id"]))
        path = self.control / "integrations" / f"{contract_id}.json"
        if path.exists():
            raise FileExistsError(f"integration already recorded: {contract_id}")
        payload = {**integration, "integrated_at": self._timestamp()}
        self._write_json(path, payload)
        self._append_event("handoff_integrated", {"contract_id": contract_id, "integrated_commit": payload["integrated_commit"]})
        return payload

    def save_escalation(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = self._safe_id(str(request["request_id"]))
        path = self.control / "escalations" / f"{request_id}.json"
        if path.exists():
            raise FileExistsError(f"escalation already exists: {request_id}")
        self._write_json(path, request)
        self._append_event("escalation_submitted", {"request_id": request_id, "contract_id": request["contract_id"]})
        return request

    def read_escalation(self, request_id: str) -> dict[str, Any]:
        path = self.control / "escalations" / f"{self._safe_id(request_id)}.json"
        if not path.is_file():
            raise FileNotFoundError(f"unknown escalation: {request_id}")
        return self._read_json(path)

    def save_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        request_id = self._safe_id(str(decision["request_id"]))
        path = self.control / "decisions" / f"{request_id}.json"
        if path.exists():
            raise FileExistsError(f"escalation decision already exists: {request_id}")
        self._write_json(path, decision)
        self._append_event("escalation_decided", decision)
        return decision

    def read_decision(self, request_id: str) -> dict[str, Any]:
        path = self.control / "decisions" / f"{self._safe_id(request_id)}.json"
        if not path.is_file():
            raise FileNotFoundError(f"no decision for escalation: {request_id}")
        return self._read_json(path)

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._append_event(event_type, payload)

    def status(self) -> dict[str, Any]:
        mission = self._read_json(self.mission_path) if self.mission_path.is_file() else None
        contracts = self._json_files("contracts")
        verifications = self._json_files("verifications")
        executions = self._json_files("executions")
        integrations = self._json_files("integrations")
        blocking = [
            item
            for item in verifications
            if not item.get("mergeable", False) or any(finding.get("severity") == "block" for finding in item.get("findings", []))
        ]
        return {
            "initialized": mission is not None,
            "workspace": str(self.workspace),
            "schema": self.schema_status(),
            "mission": mission,
            "policy": self.read_policy(),
            "contract_count": len(contracts),
            "receipt_count": len(self._json_files("receipts")),
            "verification_count": len(verifications),
            "mergeable_count": sum(bool(item.get("mergeable")) for item in verifications),
            "blocked_count": len(blocking),
            "execution_count": len(executions),
            "dispatch_count": len(self._json_files("dispatches")),
            "checkpoint_count": len(self.checkpoints()),
            "agent_run_count": len(self.agent_runs()),
            "execution_states": {
                status: sum(item.get("status") == status for item in executions)
                for status in sorted({str(item.get("status")) for item in executions})
            },
            "integration_count": len(integrations),
            "model": "verification never implies automatic integration",
        }

    def _require_mission(self) -> dict[str, Any]:
        if not self.mission_path.is_file():
            raise FileNotFoundError("project is not initialized; create .northline/mission.json first")
        return self._read_json(self.mission_path)

    def _require_current_schema(self) -> None:
        status = self.schema_status()
        if status["state"] != "ready":
            raise ValueError("project schema is not current; run the Northline migration first")

    def _json_files(self, directory: str) -> list[dict[str, Any]]:
        root = self.control / directory
        return [self._read_json(path) for path in sorted(root.glob("*.json"))] if root.is_dir() else []

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.control.mkdir(parents=True, exist_ok=True)
        event = {"timestamp": self._timestamp(), "event_type": event_type, "payload": payload}
        with (self.control / "events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_id(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
            raise ValueError(f"identifier must be one safe path component: {value!r}")
        return value

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object: {path}")
        return value

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
