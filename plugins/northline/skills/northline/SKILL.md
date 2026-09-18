---
name: northline
description: Keep long-running software work aligned with the user's root goal using bounded Root/Worker/Leaf delegation, versioned task contracts, persistent mission state, structured handoffs, and evidence-gated parent integration. Use for multi-step implementation, repeated debugging, parallel sub-agents, or work likely to drift; skip for small single-step edits.
---

# Northline

Protect the user's root objective across long implementation and debugging chains. The Root owns the mission, decisions, and final integration. A child owns only its explicit contract.

## Start or resume

For a substantial task, inspect project status with `get_project_status`. If no mission exists, initialize one with `initialize_project`, preserving the user's objective, constraints, acceptance criteria, current commit, maximum depth 2, and at most 4 children per parent. If a mission exists, resume it rather than silently replacing it.

Do not create delegation overhead for a small task that one agent can complete directly.

## Delegate

Delegate only work that is independently executable or benefits from separate context. Before a child starts, create and persist a `DelegationContract` with:

- one local objective tied to the root objective;
- explicit in-scope and out-of-scope behavior;
- allowed and forbidden files;
- required tests and acceptance criteria;
- current base commit, parent, dependencies, version, and budget.

Persist the assignment with `delegate_project_task`, then use `prepare_project_workspace` when the child needs an isolated Git worktree. Advance the persistent execution through `claimed`, `executing`, and `reporting`; do not skip states.

Use `check_parallel_safety` before parallel work. File disjointness alone is insufficient when contracts share APIs, schemas, migrations, or ordering dependencies. Root may create Workers; an authorized Worker may create Leafs; Leafs do not delegate.

## Receive and verify

Require a `HandoffReceipt` in `reporting` state. It must disclose result commit, changed files, diff summary, exact tests and results, criterion-to-evidence mappings, assumptions, risks, unresolved questions, and contract version.

Call `verify_project_handoff` with the child's evidence worktree. Northline rebuilds Git ancestry, changed-file, HEAD, and required-test evidence instead of trusting the receipt. Treat every deterministic `block` finding as non-overridable. A mergeable result enters `verified`; it does not mean the source was integrated. Root must still inspect the diff, integrate the result commit, and call `record_project_integration`, which observes parent HEAD and reruns integration tests before entering `integrated`.

Reject or revise work when the receipt is stale, out of scope, assigned to another agent, missing evidence, failing required tests, or based on an old contract version.

## Escalate

When completion requires a newer base, wider scope, or conflict with a root constraint, stop work and use the escalation protocol. Root decides; root-constraint changes also require explicit user approval. Approval creates contract version `n+1` at current parent HEAD, and old receipts remain invalid.

Read [references/escalation.md](references/escalation.md) when an escalation is needed. Read [references/product-workflow.md](references/product-workflow.md) when using the MCP/CLI interfaces or inspecting `.northline/` artifacts.

## Completion rule

Do not claim completion from a child's prose report. Completion requires a verified receipt, parent diff review, required tests, root acceptance criteria, and an observed integration state. Report unresolved risks and blocked work explicitly.
