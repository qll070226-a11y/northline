from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .detector import DriftDetector
from .models import DelegationContract, HandoffReceipt, MissionState
from .schema import validate_payload


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

    def initialize(self, mission: dict[str, Any], *, overwrite: bool = False) -> dict[str, Any]:
        validate_payload("mission", mission)
        if self.mission_path.exists() and not overwrite:
            raise FileExistsError("mission already exists; explicit overwrite is required")
        self._write_json(self.mission_path, mission)
        (self.control / "contracts").mkdir(parents=True, exist_ok=True)
        (self.control / "receipts").mkdir(parents=True, exist_ok=True)
        (self.control / "verifications").mkdir(parents=True, exist_ok=True)
        self._append_event("mission_initialized", {"mission_id": mission["mission_id"]})
        return self.status()

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
        self._write_json(path, contract)
        self._append_event(
            "contract_saved",
            {"contract_id": contract["contract_id"], "version": contract.get("version", 1)},
        )
        return {"saved": True, "path": str(path), "contract_id": contract["contract_id"]}

    def verify_and_record(
        self,
        contract_id: str,
        receipt: dict[str, Any],
        current_head: str,
        expected_agent_id: str | None = None,
    ) -> dict[str, Any]:
        mission = self._require_mission()
        safe_id = self._safe_id(contract_id)
        contract_path = self.control / "contracts" / f"{safe_id}.json"
        if not contract_path.is_file():
            raise FileNotFoundError(f"unknown contract: {contract_id}")
        contract = self._read_json(contract_path)
        if receipt.get("contract_id") != contract_id:
            raise ValueError("receipt contract_id does not match the selected contract")
        mission_model = MissionState.from_dict(mission)
        contract_model = DelegationContract.from_dict(contract)
        receipt_model = HandoffReceipt.from_dict(receipt)
        findings = DriftDetector().inspect(
            mission_model,
            contract_model,
            receipt_model,
            current_head=current_head,
            root_constraints=mission_model.global_constraints,
            expected_agent_id=expected_agent_id,
        )
        result = {
            "mergeable": DriftDetector.is_mergeable(findings),
            "findings": [
                {
                    "code": finding.code,
                    "severity": finding.severity.value,
                    "message": finding.message,
                    "evidence": finding.evidence,
                }
                for finding in findings
            ],
        }
        receipt_id = self._safe_id(str(receipt["receipt_id"]))
        receipt_path = self.control / "receipts" / f"{receipt_id}.json"
        verification_path = self.control / "verifications" / f"{receipt_id}.json"
        if receipt_path.exists() or verification_path.exists():
            raise FileExistsError(f"receipt already recorded: {receipt['receipt_id']}")
        self._write_json(receipt_path, receipt)
        verification = {
            "receipt_id": receipt["receipt_id"],
            "contract_id": contract_id,
            "mergeable": result["mergeable"],
            "findings": result["findings"],
            "verified_at": self._timestamp(),
            "integration_authorized": result["mergeable"],
            "integrated": False,
        }
        self._write_json(verification_path, verification)
        self._append_event(
            "handoff_verified" if result["mergeable"] else "handoff_rejected",
            {"contract_id": contract_id, "receipt_id": receipt["receipt_id"], "mergeable": result["mergeable"]},
        )
        return verification

    def status(self) -> dict[str, Any]:
        mission = self._read_json(self.mission_path) if self.mission_path.is_file() else None
        contracts = self._json_files("contracts")
        verifications = self._json_files("verifications")
        blocking = [
            item
            for item in verifications
            if not item.get("mergeable", False) or any(finding.get("severity") == "block" for finding in item.get("findings", []))
        ]
        return {
            "initialized": mission is not None,
            "workspace": str(self.workspace),
            "mission": mission,
            "contract_count": len(contracts),
            "receipt_count": len(self._json_files("receipts")),
            "verification_count": len(verifications),
            "mergeable_count": sum(bool(item.get("mergeable")) for item in verifications),
            "blocked_count": len(blocking),
            "model": "verification never implies automatic integration",
        }

    def _require_mission(self) -> dict[str, Any]:
        if not self.mission_path.is_file():
            raise FileNotFoundError("project is not initialized; create .northline/mission.json first")
        return self._read_json(self.mission_path)

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
