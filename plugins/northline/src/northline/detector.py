from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from .models import DelegationContract, HandoffReceipt, HandoffStatus, MissionState


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCK = "block"


@dataclass(frozen=True)
class DriftFinding:
    code: str
    severity: FindingSeverity
    message: str
    evidence: str | None = None


class DriftDetector:
    """Deterministic checks. An LLM judge may annotate findings, never override BLOCK."""

    def inspect(
        self,
        mission: MissionState,
        contract: DelegationContract,
        receipt: HandoffReceipt,
        *,
        current_head: str | None = None,
        root_constraints: tuple[str, ...] | None = None,
        expected_agent_id: str | None = None,
    ) -> list[DriftFinding]:
        findings: list[DriftFinding] = []
        if receipt.contract_id != contract.contract_id:
            findings.append(DriftFinding("CONTRACT_ID_MISMATCH", FindingSeverity.BLOCK, "receipt references a different contract"))
        if receipt.contract_version != contract.version:
            findings.append(DriftFinding("CONTRACT_VERSION_MISMATCH", FindingSeverity.BLOCK, "receipt was produced against an old contract version"))
        if expected_agent_id and receipt.agent_id != expected_agent_id:
            findings.append(DriftFinding("AGENT_ID_MISMATCH", FindingSeverity.BLOCK, "receipt was submitted by an agent not assigned to this contract"))
        if receipt.base_commit != contract.base_commit:
            findings.append(DriftFinding("CONTRACT_BASE_MISMATCH", FindingSeverity.BLOCK, "receipt base commit differs from the delegated contract"))
        if receipt.status != HandoffStatus.REPORTING:
            findings.append(DriftFinding("INVALID_RECEIPT_STATUS", FindingSeverity.BLOCK, "an agent handoff receipt must be in reporting status"))
        if current_head and receipt.base_commit != current_head:
            findings.append(DriftFinding("STALE_BASE", FindingSeverity.BLOCK, "receipt base commit is not the current head", f"expected={current_head}, actual={receipt.base_commit}"))
        forbidden = set(contract.forbidden_files)
        allowed = contract.allowed_files
        for path in receipt.changed_files:
            normalized = path.replace("\\", "/")
            if PurePosixPath(normalized).is_absolute() or ".." in PurePosixPath(normalized).parts:
                findings.append(DriftFinding("UNSAFE_PATH", FindingSeverity.BLOCK, f"changed path is absolute or escapes the workspace: {path}"))
                continue
            if self._matches_any(normalized, forbidden):
                findings.append(DriftFinding("FORBIDDEN_FILE", FindingSeverity.BLOCK, f"changed forbidden file: {path}"))
            elif allowed and not self._matches_any(normalized, allowed):
                findings.append(DriftFinding("OUT_OF_SCOPE_FILE", FindingSeverity.BLOCK, f"changed file outside allowed scope: {path}"))
        if not receipt.result_commit:
            findings.append(DriftFinding("MISSING_RESULT_COMMIT", FindingSeverity.BLOCK, "receipt has no result commit"))
        elif receipt.result_commit == receipt.base_commit:
            findings.append(DriftFinding("UNCHANGED_RESULT_COMMIT", FindingSeverity.BLOCK, "result commit is identical to base commit"))
        if not receipt.tests_run:
            findings.append(DriftFinding("MISSING_TEST_EVIDENCE", FindingSeverity.BLOCK, "no tests were reported"))
        if len(receipt.tests_run) != len(receipt.test_results):
            findings.append(DriftFinding("TEST_RESULT_MISMATCH", FindingSeverity.BLOCK, "test commands and results have different lengths"))
        if any(result.lower() not in {"pass", "passed", "ok", "success"} for result in receipt.test_results):
            findings.append(DriftFinding("FAILING_TEST", FindingSeverity.BLOCK, "at least one reported test did not pass"))
        missing_tests = [test for test in contract.required_tests if test not in receipt.tests_run]
        if missing_tests:
            findings.append(DriftFinding("REQUIRED_TEST_MISSING", FindingSeverity.BLOCK, "contract-required tests were not reported", ", ".join(missing_tests)))
        missing_criteria = [criterion for criterion in contract.acceptance_criteria if not receipt.acceptance_evidence.get(criterion, "").strip()]
        if missing_criteria:
            findings.append(DriftFinding("ACCEPTANCE_EVIDENCE_MISSING", FindingSeverity.BLOCK, "acceptance criteria lack evidence", ", ".join(missing_criteria)))
        if receipt.unresolved_questions:
            findings.append(DriftFinding("UNRESOLVED_QUESTIONS", FindingSeverity.BLOCK, "receipt requires a parent decision before integration"))
        if root_constraints:
            text = " ".join(receipt.assumptions + receipt.risks + (receipt.diff_summary,)).lower()
            for constraint in root_constraints:
                if constraint.lower() in text:
                    findings.append(DriftFinding("ROOT_CONSTRAINT_RISK", FindingSeverity.WARNING, f"receipt mentions root constraint: {constraint}"))
        if not mission.objective.strip():
            findings.append(DriftFinding("EMPTY_MISSION", FindingSeverity.BLOCK, "mission objective is empty"))
        return findings

    @staticmethod
    def _matches_any(path: str, patterns: set[str] | tuple[str, ...]) -> bool:
        """Support ``**`` as zero or more path components, including ``src/**/*.py``."""
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
            if "**/" in pattern:
                collapsed = pattern.replace("**/", "")
                if fnmatch.fnmatch(path, collapsed) or fnmatch.fnmatch(path, pattern.replace("**/", "*/")):
                    return True
        return False

    @staticmethod
    def is_mergeable(findings: list[DriftFinding]) -> bool:
        return not any(f.severity == FindingSeverity.BLOCK for f in findings)
