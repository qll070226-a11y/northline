# Product Workflow

Use this reference when the plugin MCP tools are available or when falling back to the CLI.

## Persistent layout

The plugin writes only protocol artifacts under the selected repository:

```text
.northline/
|-- mission.json
|-- contracts/*.json
|-- receipts/*.json
|-- verifications/*.json
`-- events.jsonl
```

Source files are never changed by verification. A verification record contains `integration_authorized`, but always writes `integrated=false`; integration remains a Root action.

## MCP flow

1. `get_project_status(workspace)` to resume existing state.
2. `initialize_project(workspace, mission)` only when uninitialized.
3. `save_project_contract(workspace, contract)` before delegating.
4. `check_parallel_safety(left_contract, right_contract)` before concurrency.
5. `verify_project_handoff(workspace, contract_id, receipt, current_head, expected_agent_id)` before integration.
6. `get_project_status(workspace)` after verification to summarize counts and blockers.

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

Verify a receipt and inspect status:

```powershell
northline verify --workspace . --contract-id contract_123 --receipt receipt.json --expected-agent-id worker_001
northline status --workspace .
```

The CLI returns JSON and exits with an error for invalid schemas, unsafe identifiers, duplicate receipts, or accidental mission overwrite.
