# Northline Architecture

## Product boundary

Northline is a repository-local control plane for long-running coding-agent work. It does not replace Codex, an agent runtime, Git, or the test runner. It defines what may be delegated, persists the state of that delegation, rebuilds evidence independently, and prevents an unverified result from being recorded as integrated.

The product has four surfaces around one application service:

```text
Codex Skill -----------+
MCP tools -------------+--> ProtocolEngine --> ProjectStore (.northline/)
CLI -------------------+         |      |
LangGraph adapter -----+         |      +--> deterministic policy/state machine
                                  +---------> GitWorkspace (Git diff/worktree/tests)
```

`ProtocolEngine` is the only stateful application entry point. `ProjectStore` only persists artifacts. Stateless schema, transition, and parallel-safety previews remain available, but they cannot authorize integration.

## Authority model

```text
User
  `-- Root: owns MissionState, architecture decisions, and final integration
        |-- Worker: owns one DelegationContract and may delegate an authorized Leaf
        `-- Worker
              `-- Leaf: owns one bounded contract and cannot delegate
```

Defaults are maximum depth 2 and at most 4 children per parent. A child cannot change the root objective, global constraints, parent identity, or its own scope. A requested scope or root-constraint change stops execution and becomes an escalation.

## Protocol objects

| Object | Purpose | Owner |
| --- | --- | --- |
| `MissionState` | Root objective, constraints, acceptance criteria, root commit, limits | User/Root |
| `DelegationContract` | Versioned objective, scope, files, dependencies, tests, base commit | Parent |
| `ExecutionState` | Agent, role, workspace, current commit, status history | Engine |
| `HandoffReceipt` | Child's claims about commit, diff, tests, evidence, assumptions, risks | Child |
| `RepositoryEvidence` | Git facts and independently executed test results | Verifier |
| `EscalationRequest/Decision` | Stop-work request and parent/user decision | Child/Parent |
| Integration record | Observed parent HEAD and post-integration tests | Root/Integrator |

## State and trust boundary

```text
PLANNED -> CLAIMED -> EXECUTING -> REPORTING -> VERIFIED -> INTEGRATED
                         |              |
                         |              `-> REJECTED
                         +-> PARTIAL / BLOCKED / STALE / NEEDS_PARENT_DECISION
```

`VERIFIED` means the receipt and rebuilt evidence passed the deterministic gates. It only authorizes parent review. `INTEGRATED` is recorded later, after the verified result commit is an ancestor of the parent repository HEAD and integration tests pass. No LLM judgment can bypass a blocking deterministic finding.

## Verification flow

1. Load the active mission, contract, and execution from `.northline/`.
2. Require the execution to be in `REPORTING`.
3. Validate agent identity, contract version, base commit, declared files, required tests, criteria evidence, constraints, and dependencies.
4. Inspect the evidence worktree and recompute commit existence, ancestry, actual changed files, and workspace HEAD.
5. Execute every contract-required test in that worktree with a timeout.
6. Compare the child's receipt with the independently observed evidence.
7. Persist the immutable receipt and verification; transition to `VERIFIED` or `REJECTED`.
8. After the Root integrates the commit, rerun integration tests in the parent repository and record `INTEGRATED`.

Test commands are authority-bearing input from the Root contract and run locally with shell semantics. Northline must not execute tests copied from an untrusted child receipt; it only executes commands already stored in the parent-authored contract or supplied explicitly by Root at integration.

## Repository data

```text
.northline/
|-- mission.json
|-- contracts/<contract-id>.json
|-- contract-history/<contract-id>/v<n>.json
|-- executions/<contract-id>.json
|-- receipts/<receipt-id>.json
|-- verifications/<receipt-id>.json
|-- escalations/<request-id>.json
|-- decisions/<request-id>.json
|-- integrations/<contract-id>.json
`-- events.jsonl
```

JSON files are written through a temporary file and replaced atomically. `events.jsonl` is append-only and reconstructs the control-plane timeline. Source changes remain in Git worktrees, outside `.northline/`.

## Runtime sequence

```text
status/init
    -> delegate contract
    -> prepare isolated worktree
    -> claimed -> executing
    -> child commit + receipt
    -> reporting
    -> verify in child worktree
    -> Root reviews and integrates Git commit
    -> record integration in parent worktree
```

Parallel execution is allowed only when file scopes, interfaces, schemas, migrations, ordering, and dependencies are independent. Otherwise Root serializes the contracts.

## Adapters

- Skill: teaches Codex when to create contracts, stop, escalate, verify, and integrate.
- MCP: exposes the complete persistent protocol to Codex and other clients.
- CLI: provides the same critical path for debugging and automation.
- LangGraph: optional orchestration adapter; it does not own protocol truth.
- GitWorkspace: prepares detached worktrees and rebuilds repository evidence.

OpenHands, SWE-agent, MetaGPT, and ChatDev are reference implementations for execution environments, repository interaction, and role workflows. Northline does not embed their runtimes. This keeps the protocol measurable and lets future adapters use them without changing the trust model.

## v0.3 constraints

- Python/Git repositories are the supported execution target.
- Integration recognition requires the exact verified result commit to be reachable from parent HEAD; squash and cherry-pick equivalence are not inferred.
- Worktrees are prepared but not automatically deleted.
- Semantic goal satisfaction remains partly dependent on Root review; deterministic gates cover state, scope, identity, dependency, and evidence claims.
- Multi-machine scheduling, UI, online learning, and unbounded recursive delegation are out of scope.
