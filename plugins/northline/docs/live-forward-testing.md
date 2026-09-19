# Live Forward Testing

Northline v0.9 adds MCP wrappers around the independently invocable live-test layer and deterministic product suite. The live-test layer remains intentionally separate from the deterministic `forward-test` suite.

## Safety boundary

The command performs a model-free preflight by default:

```powershell
northline live-forward-test --workspace . --contract-id CONTRACT_ID `
  --output results\live-forward-test.json
```

The report returns `status=authorization_required` and `real_model_calls=false`. A Codex CLI process can start only when Root adds `--authorize`:

The MCP equivalent is `preflight_live_forward_test(workspace, contract_id, output, baseline?)`; it is always model-free and cannot authorize a run.

```powershell
northline live-forward-test --workspace . --contract-id CONTRACT_ID `
  --authorize --timeout-seconds 1800 `
  --baseline results\product-forward-test.json `
  --output results\live-forward-test.json
```

The contract must already be in `PLANNED` state and have an isolated, clean worktree at the contract base commit. The normal Northline state machine, attempt limit, checkpoint, and JSONL persistence rules still apply.

## Recorded evidence

Each report includes:

- authorization, Codex-process, and model-exposure flags;
- contract, version, base commit, assigned worktree, and resume mode;
- elapsed time and Codex token usage;
- Codex JSONL event count and Northline checkpoint count; manual intervention remains `null` until supplied by a higher-level evaluator;
- the persisted agent-run record, final message, and execution state;
- an optional deterministic-baseline comparison.

Elapsed time is directly comparable by unit. Codex JSONL events and Northline protocol events are different layers, so the report presents them separately and never computes a misleading event-count delta.

`model_exposure_status=confirmed` requires non-zero token usage in the recorded Codex events. A started process without usage is reported as `not_observed`; it is not silently counted as a paid model call.

## Interpretation boundary

A successful live runtime call means Codex completed its turn and Northline advanced the contract to `REPORTING`. It does not mean the patch is correct or ready to integrate. Root must still draft or inspect the handoff receipt, run deterministic verification, review the diff, and explicitly record integration.
