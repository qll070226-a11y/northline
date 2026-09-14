from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from .models import DelegationContract, MissionState
from .project_store import ProjectStore
from .runtime import demo_runtime


def _head(workspace: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unversioned"


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

    contract_parser = sub.add_parser("contract", help="save one child delegation contract")
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

    status_parser = sub.add_parser("status", help="show repository-local mission status")
    status_parser.add_argument("--workspace", type=Path, default=Path.cwd())

    verify = sub.add_parser("verify", help="verify and record a receipt without integrating source")
    verify.add_argument("--workspace", type=Path, default=Path.cwd())
    verify.add_argument("--contract-id", required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--current-head", default=None)
    verify.add_argument("--expected-agent-id", default=None)
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
                "version": "0.2.0",
                "integrated_receipts": len(runtime.receipts),
                "status": "pass",
            }
            args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(args.output)
        return

    workspace = args.workspace.resolve()
    store = ProjectStore(workspace)
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
        _print(store.initialize(mission.to_dict(), overwrite=args.overwrite))
    elif args.command == "contract":
        mission = store.status()["mission"]
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
        _print(store.save_contract(contract.to_dict()))
    elif args.command == "status":
        _print(store.status())
    else:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        _print(
            store.verify_and_record(
                args.contract_id,
                receipt,
                args.current_head or _head(workspace),
                args.expected_agent_id,
            )
        )


if __name__ == "__main__":
    main()
