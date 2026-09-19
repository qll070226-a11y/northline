# Product Workflow

Use this reference when the plugin MCP tools are available or when falling back to the CLI.

## Persistent layout

The plugin writes only protocol artifacts under the selected repository:

```text
.northline/
|-- project.json
|-- mission.json
|-- policy.json
|-- contracts/*.json
|-- contract-history/*/v*.json
|-- dispatches/*.json
|-- checkpoints/<contract-id>/*.json
|-- agent-runs/*.json
|-- run-artifacts/<run-id>/events.jsonl
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

1. `get_project_schema(workspace)` and `get_project_resume(workspace)` to recover schema, mission, blockers, stale work, and next actions.
2. Use `migrate_project(workspace)` for a supported legacy schema, or `initialize_project(workspace, mission, policy)` when uninitialized.
3. `draft_project_contract(...)` to fill protocol-owned fields; Root reviews the scope and tests.
4. `delegate_project_task(workspace, contract, agent_id, role)` to persist the reviewed contract and assignment.
5. `prepare_project_workspace(workspace, contract_id, target)` to create a detached worktree at the contract base.
6. For manual dispatch, use `create_agent_task_packet(workspace, contract_id)`. For an explicitly authorized Codex CLI run, use `run_codex_project_agent`; it persists the same packet and runtime evidence.
7. `check_parallel_safety(left_contract, right_contract)` before concurrency.
8. Manual runtimes use `transition_project_handoff` through `claimed` and `executing`. The Codex adapter advances these states itself. Use `record_agent_checkpoint` before interruption or when blocked.
9. Transition to `reporting`, then use `draft_project_receipt(...)` to observe the result commit, diff, and tests while preserving child-authored semantic evidence.
10. `verify_project_handoff(workspace, contract_id, receipt, evidence_workspace)` to independently rebuild Git/test evidence.
11. Root reviews the verified diff and integrates the result commit with Git.
12. `record_project_integration(workspace, contract_id)` verifies parent HEAD and integration tests before recording completion.
13. `get_project_report(workspace)` and `get_project_resume(workspace)` to confirm completion or identify the next blocker.
14. After terminal completion or rejection, call `cleanup_project_workspace` only with Root confirmation and a clean worktree.

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
northline dispatch --workspace . --contract-id contract_123 > dispatch.json
northline transition --workspace . --contract-id contract_123 --target claimed
northline transition --workspace . --contract-id contract_123 --target executing
northline checkpoint --workspace . --contract-id contract_123 --completed "Inspected parser" --pending "Implement fix" --pending "Run tests"
```

Or explicitly authorize a Codex CLI execution:

```powershell
northline run-codex --workspace . --contract-id contract_123 --authorize
# After a checkpointed partial failure:
northline retry --workspace . --contract-id contract_123 --reason "Transient runtime failure"
northline run-codex --workspace . --contract-id contract_123 --authorize --resume-previous
```

Verify a receipt and inspect status:

```powershell
northline transition --workspace . --contract-id contract_123 --target reporting
northline receipt --workspace . --contract-id contract_123 --summary "Implemented parser changes" --acceptance-evidence "Parser tests pass=required parser tests passed" > receipt.json
northline verify --workspace . --contract-id contract_123 --receipt receipt.json --evidence-workspace ..\northline-worktrees\contract_123
# Root now reviews and integrates the Git commit.
northline integrate --workspace . --contract-id contract_123
northline resume --workspace .
northline report --workspace .
northline cleanup --workspace . --contract-id contract_123 --confirm
```

Run `northline schema --workspace .` before resuming an older project. If it reports `legacy` or `migration_required`, run `northline migrate --workspace .`; migrations are deterministic, versioned, and recorded in `events.jsonl`.

The Codex adapter follows the official [non-interactive mode](https://developers.openai.com/zh-Hans/docs/non-interactive-mode): prompts use stdin, execution uses `workspace-write`, and events use JSONL. Never substitute `danger-full-access` or infer authorization from workspace preparation.

After installation or changes to protocol/runtime code, run the deterministic product health check:

```powershell
northline forward-test --output results/product-forward-test.json
```

It uses fresh temporary Git repositories and makes no real model calls. Treat it as wiring and invariant evidence, not as proof that a live model follows the Skill or improves task success.

Use `submit_project_escalation`, `decide_project_escalation`, and `revise_project_contract` (or CLI `escalate`, `decide`, and `revise`) when a child needs a new base, wider scope, or a root decision. The CLI returns JSON and exits with an error for invalid schemas, illegal transitions, unsafe identifiers, duplicate receipts, or accidental mission overwrite.
