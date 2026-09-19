# Product Forward Testing

Date: 2026-09-19

Northline ships a deterministic product-level forward suite that exercises complete protocol paths in fresh, isolated Git repositories:

```powershell
northline forward-test --output results/product-forward-test.json
```

The suite covers:

1. verified handoff, Root integration, and safe worktree cleanup;
2. bounded `Root -> Worker -> Leaf` delegation and task packets;
3. forbidden-file drift rejection;
4. stale-parent rejection; and
5. failed runtime checkpointing plus bounded thread resume.

Each scenario records elapsed time, protocol-event count, artifact count, artifact bytes, observed state, and deterministic blocking findings. The report also records `real_model_calls=0`: runtime failure and resume are exercised with a controlled subprocess, so this suite validates product wiring and invariants rather than model quality.

The first v0.7 run passed all five scenarios in 9.23 seconds. It produced 61 protocol events, 55 files, and 42,536 bytes of protocol artifacts. These measurements are environment-specific baselines, not performance guarantees.

## Interpretation boundary

A passing report establishes that the protocol components compose correctly on the current host. It does not establish that a live model follows the Skill, that Northline improves task success, or that the overhead is acceptable on large repositories. Those claims require independently launched Codex tasks, real model traces, repeated runs, and paired baselines.

## Release use

Run the suite after changes to contracts, state transitions, worktree handling, runtime adapters, evidence verification, retry logic, or cleanup. A release candidate fails if any scenario fails. Keep the raw JSON report outside source control; summarize stable findings in `docs/status.md`.
