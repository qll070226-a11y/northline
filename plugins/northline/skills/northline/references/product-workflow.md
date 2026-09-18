# Product Workflow

Use this reference when the plugin MCP tools are available or when falling back to the CLI.

## Persistent layout

The plugin writes only protocol artifacts under the selected repository:

```text
.northline/
|-- mission.json
|-- contracts/*.json
|-- contract-history/*/v*.json
|-- executions/*.json
|-- receipts/*.json
|-- verifications/*.json
|-- escalations/*.json
|-- decisions/*.json
|-- integrations/*.json
`-- events.jsonl
```

Source files are never changed by verification. A verification record contains `integration_authorized`, but always writes `integrated=false`; integration remains a Root action.

## MCP flow

1. `get_project_status(workspace)` to resume existing state.
2. `initialize_project(workspace, mission)` only when uninitialized.
3. `delegate_project_task(workspace, contract, agent_id, role)` to persist the contract and assignment.
4. `prepare_project_workspace(workspace, contract_id, target)` to create a detached worktree at the contract base.
5. `check_parallel_safety(left_contract, right_contract)` before concurrency.
6. `transition_project_handoff` through `claimed`, `executing`, and `reporting` as work advances.
7. `verify_project_handoff(workspace, contract_id, receipt, evidence_workspace)` to rebuild Git/test evidence.
8. Root reviews the verified diff and integrates the result commit with Git.
9. `record_project_integration(workspace, contract_id)` verifies parent HEAD and integration tests before recording completion.
10. `get_project_status(workspace)` to resume state and summarize blockers.

The stateless `validate_handoff` tool is useful for previewing a receipt without recording it. `check_transition` validates protocol state transitions.

## CLI fallback

Initialize a mission:

```powershell
northline init --workspace . --objective "Implement the requested change" --constraint "Preserve public API" --criterion "All tests pass"
```

Create a contract:

```powershell
northline contract --workspace . --objective "Implement parser changes" --in-scope "Parser behavior" --out-of-scope "Public API" --allowed-file "src/**/*.py" --forbidden-file "pyproject.toml" --criterion "Parser tests pass" --test "pytest tests/test_parser.py"
```

Prepare and claim its worktree:

```powershell
northline prepare --workspace . --contract-id contract_123 --target ..\northline-worktrees\contract_123
northline transition --workspace . --contract-id contract_123 --target claimed
northline transition --workspace . --contract-id contract_123 --target executing
```

Verify a receipt and inspect status:

```powershell
northline transition --workspace . --contract-id contract_123 --target reporting
northline verify --workspace . --contract-id contract_123 --receipt receipt.json --evidence-workspace ..\northline-worktrees\contract_123
# Root now reviews and integrates the Git commit.
northline integrate --workspace . --contract-id contract_123
northline status --workspace .
```

Use `submit_project_escalation`, `decide_project_escalation`, and `revise_project_contract` (or CLI `escalate`, `decide`, and `revise`) when a child needs a new base, wider scope, or a root decision. The CLI returns JSON and exits with an error for invalid schemas, illegal transitions, unsafe identifiers, duplicate receipts, or accidental mission overwrite.
