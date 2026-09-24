# Northline Architecture

The repository README presents the detailed architecture as a scalable SVG. This document defines the same control-plane boundaries, evidence flow and trust model in prose.

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
| `ProtocolPolicy` | Isolation, clean-evidence, required-test, change-size, and timeout gates | User/Root |
| `DelegationContract` | Versioned objective, scope, files, dependencies, tests, base commit | Parent |
| `ExecutionState` | Agent, role, workspace, current commit, status history | Engine |
| `AgentTaskPacket` | Exact mission/contract/workspace payload dispatched to one child | Parent/Engine |
| `AgentCheckpoint` | Observed commit, dirty files, completed/pending work, blockers | Child/Engine |
| `AgentRunRecord` | Codex thread, attempt, command, JSONL trace, usage, result | Engine |
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
|-- policy.json
|-- project.json
|-- contracts/<contract-id>.json
|-- contract-history/<contract-id>/v<n>.json
|-- dispatches/<packet-id>.json
|-- checkpoints/<contract-id>/<checkpoint-id>.json
|-- agent-runs/<run-id>.json
|-- run-artifacts/<run-id>/events.jsonl
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
resume/init
    -> draft and review contract
    -> delegate contract
    -> prepare isolated worktree
    -> persist and deliver agent task packet
    -> explicitly authorized runtime launch
    -> claimed -> executing
    -> checkpoint before interruption or blocking
    -> child commit + evidence-backed receipt draft
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

## v0.6 constraints

- Python/Git repositories are the supported execution target.
- Integration recognition requires the exact verified result commit to be reachable from parent HEAD; squash and cherry-pick equivalence are not inferred.
- Codex CLI runs require an explicit authorization flag and use `workspace-write`; Northline never selects `danger-full-access`.
- Runtime failure becomes `PARTIAL`, records a technical checkpoint, and can retry only within the configured attempt limit.
- Worktree cleanup is explicit and limited to clean `INTEGRATED` or `REJECTED` executions.
- The Codex CLI adapter is implemented; OpenHands and other runtime adapters remain future work.
- Semantic goal satisfaction remains partly dependent on Root review; deterministic gates cover state, scope, identity, dependency, and evidence claims.
- Multi-machine scheduling, UI, online learning, and unbounded recursive delegation are out of scope.

## Product forward validation

`northline forward-test` creates five fresh Git repositories and exercises integration, nested delegation, forbidden-file rejection, stale-base rejection, and bounded runtime resume. It records latency plus protocol event/file/byte overhead in a JSON report. The runtime scenario uses a controlled subprocess and records zero real model calls; live-model adherence remains a separate evaluation layer.
