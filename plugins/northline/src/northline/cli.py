from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from . import __version__
from .engine import ProtocolEngine
from .models import DelegationContract, MissionState
from .runtime import demo_runtime


def _head(workspace: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "git rev-parse failed"
        raise RuntimeError(f"workspace must be a Git repository with a commit: {detail}")
    return completed.stdout.strip()


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Guard long-horizon agent delegation with verifiable project artifacts")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="run a deterministic Root/Worker verification demo")
    evaluate = sub.add_parser("evaluate", help="write a small reproducible smoke result")
    evaluate.add_argument("--output", type=Path, default=Path("results/demo.json"))

    initialize = sub.add_parser("init", help="initialize .northline mission state in a repository")
    initialize.add_argument("--workspace", type=Path, default=Path.cwd())
    initialize.add_argument("--objective", required=True)
    initialize.add_argument("--constraint", action="append", default=[])
    initialize.add_argument("--criterion", action="append", required=True)
    initialize.add_argument("--mission-id", default=None)
    initialize.add_argument("--max-depth", type=int, default=2)
    initialize.add_argument("--max-children", type=int, default=4)
    initialize.add_argument("--overwrite", action="store_true")

    contract_parser = sub.add_parser("contract", help="save and assign one child delegation contract")
    contract_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    contract_parser.add_argument("--objective", required=True)
    contract_parser.add_argument("--in-scope", action="append", required=True)
    contract_parser.add_argument("--out-of-scope", action="append", default=[])
    contract_parser.add_argument("--allowed-file", action="append", required=True)
    contract_parser.add_argument("--forbidden-file", action="append", default=[])
    contract_parser.add_argument("--criterion", action="append", required=True)
    contract_parser.add_argument("--test", action="append", required=True)
    contract_parser.add_argument("--parent-id", default="root")
    contract_parser.add_argument("--contract-id", default=None)
    contract_parser.add_argument("--agent-budget", default=None)
    contract_parser.add_argument("--agent-id", default=None)
    contract_parser.add_argument("--role", choices=("worker", "leaf"), default=None)
    contract_parser.add_argument("--execution-workspace", type=Path, default=None)

    transition = sub.add_parser("transition", help="advance one persistent handoff state")
    transition.add_argument("--workspace", type=Path, default=Path.cwd())
    transition.add_argument("--contract-id", required=True)
    transition.add_argument("--target", required=True)

    prepare = sub.add_parser("prepare", help="create an isolated worktree for one planned contract")
    prepare.add_argument("--workspace", type=Path, default=Path.cwd())
    prepare.add_argument("--contract-id", required=True)
    prepare.add_argument("--target", type=Path, required=True)

    status_parser = sub.add_parser("status", help="show repository-local mission status")
    status_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    verify = sub.add_parser("verify", help="verify and record a receipt without integrating source")
    verify.add_argument("--workspace", type=Path, default=Path.cwd())
    verify.add_argument("--contract-id", required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--evidence-workspace", type=Path, default=None)
    verify.add_argument("--test-timeout-seconds", type=float, default=600)

    integrate = sub.add_parser("integrate", help="record an observed integration after tests pass")
    integrate.add_argument("--workspace", type=Path, default=Path.cwd())
    integrate.add_argument("--contract-id", required=True)
    integrate.add_argument("--test", action="append", default=[])
    integrate.add_argument("--test-timeout-seconds", type=float, default=600)

    escalation = sub.add_parser("escalate", help="persist a stopped-work escalation request")
    escalation.add_argument("--workspace", type=Path, default=Path.cwd())
    escalation.add_argument("--request", type=Path, required=True)

    decision = sub.add_parser("decide", help="record the Root decision for an escalation")
    decision.add_argument("--workspace", type=Path, default=Path.cwd())
    decision.add_argument("--request-id", required=True)
    decision.add_argument("--approved", action=argparse.BooleanOptionalAction, required=True)
    decision.add_argument("--rationale", required=True)
    decision.add_argument("--user-approved", action="store_true")

    revision = sub.add_parser("revise", help="install an approved contract revision")
    revision.add_argument("--workspace", type=Path, default=Path.cwd())
    revision.add_argument("--request-id", required=True)
    revision.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()

    if args.command in {"demo", "evaluate"}:
        runtime = demo_runtime()
        if args.command == "demo":
            _print({
                "mission": runtime.mission.to_dict(),
                "nodes": [node.__dict__ for node in runtime.nodes.values()],
                "integrated": len(runtime.receipts),
            })
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "protocol": "northline",
                "version": __version__,
                "integrated_receipts": len(runtime.receipts),
                "status": "pass",
            }
            args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(args.output)
        return

    workspace = args.workspace.resolve()
    engine = ProtocolEngine(workspace)
    if args.command == "init":
        mission = MissionState(
            mission_id=args.mission_id or f"mission_{uuid4().hex[:12]}",
            objective=args.objective,
            global_constraints=tuple(args.constraint),
            acceptance_criteria=tuple(args.criterion),
            root_commit=_head(workspace),
            max_depth=args.max_depth,
            max_children=args.max_children,
        )
        _print(engine.initialize(mission.to_dict(), overwrite=args.overwrite))
    elif args.command == "contract":
        mission = engine.status()["mission"]
        if mission is None:
            raise FileNotFoundError("initialize the workspace before saving a contract")
        contract = DelegationContract(
            objective=args.objective,
            in_scope=tuple(args.in_scope),
            out_of_scope=tuple(args.out_of_scope),
            allowed_files=tuple(args.allowed_file),
            forbidden_files=tuple(args.forbidden_file),
            acceptance_criteria=tuple(args.criterion),
            required_tests=tuple(args.test),
            base_commit=_head(workspace),
            parent_id=args.parent_id,
            mission_id=mission["mission_id"],
            deadline_or_budget=args.agent_budget,
            contract_id=args.contract_id or f"contract_{uuid4().hex[:12]}",
        )
        role = args.role or ("worker" if args.parent_id == "root" else "leaf")
        existing = engine.status()["execution_count"]
        agent_id = args.agent_id or f"{role}_{existing + 1:03d}"
        _print(
            engine.delegate(
                contract.to_dict(),
                agent_id=agent_id,
                role=role,
                workspace=str(args.execution_workspace.resolve()) if args.execution_workspace else None,
            )
        )
    elif args.command == "status":
        _print(engine.status())
    elif args.command == "prepare":
        _print(engine.prepare_workspace(args.contract_id, args.target))
    elif args.command == "transition":
        _print(engine.transition(args.contract_id, args.target))
    elif args.command == "verify":
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        _print(
            engine.verify_handoff(
                args.contract_id,
                receipt,
                evidence_workspace=args.evidence_workspace.resolve() if args.evidence_workspace else None,
                test_timeout_seconds=args.test_timeout_seconds,
            )
        )
    elif args.command == "integrate":
        _print(
            engine.record_integration(
                args.contract_id,
                integration_tests=tuple(args.test),
                test_timeout_seconds=args.test_timeout_seconds,
            )
        )
    elif args.command == "escalate":
        _print(engine.submit_escalation(json.loads(args.request.read_text(encoding="utf-8"))))
    elif args.command == "decide":
        _print(
            engine.decide_escalation(
                args.request_id,
                approved=args.approved,
                rationale=args.rationale,
                user_approved=args.user_approved,
            )
        )
    else:
        _print(engine.revise_contract(args.request_id, json.loads(args.contract.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main()
