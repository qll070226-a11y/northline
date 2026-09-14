from __future__ import annotations

import json
from pathlib import Path

from northline.detector import DriftDetector
from northline.models import DelegationContract, HandoffReceipt, HandoffStatus, MissionState


def base() -> tuple[MissionState, DelegationContract]:
    mission = MissionState("synthetic", "implement parser", global_constraints=("preserve public API",), acceptance_criteria=("tests pass",))
    contract = DelegationContract(
        objective="implement parser", in_scope=("parser",), out_of_scope=("API redesign",), allowed_files=("src/**/*.py", "tests/**/*.py"), forbidden_files=("pyproject.toml",), acceptance_criteria=("tests pass",), required_tests=("pytest",), base_commit="base", parent_id="root", mission_id=mission.mission_id
    )
    return mission, contract


def cases(contract: DelegationContract) -> dict[str, HandoffReceipt]:
    common = dict(contract_id=contract.contract_id, agent_id="worker_001", status=HandoffStatus.REPORTING, base_commit="base", result_commit="result", diff_summary="implemented parser", tests_run=("pytest",), test_results=("pass",), acceptance_evidence={"tests pass": "pytest: pass"})
    return {
        "clean": HandoffReceipt(changed_files=("src/parser.py",), **common),
        "scope_conflict": HandoffReceipt(changed_files=("pyproject.toml",), **common),
        "stale_commit": HandoffReceipt(changed_files=("src/parser.py",), base_commit="old", **{k: v for k, v in common.items() if k != "base_commit"}),
        "unsupported_completion": HandoffReceipt(changed_files=("src/parser.py",), tests_run=(), test_results=(), **{k: v for k, v in common.items() if k not in {"tests_run", "test_results"}}),
        "ambiguous_goal": HandoffReceipt(changed_files=("src/parser.py",), unresolved_questions=("Should the public API change?",), **common),
    }


def main() -> None:
    mission, contract = base()
    detector = DriftDetector()
    report = {}
    for name, receipt in cases(contract).items():
        findings = detector.inspect(mission, contract, receipt, current_head="base", root_constraints=mission.global_constraints)
        report[name] = {"mergeable": detector.is_mergeable(findings), "finding_codes": [finding.code for finding in findings]}
    output = Path("results/synthetic_faults.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
