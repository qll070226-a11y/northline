# Escalation Reference

Use escalation instead of a handoff receipt when completing the delegated objective requires changing the contract.

## Required request fields

```text
request_id
contract_id
contract_version
agent_id
kinds
contract_base_commit
workspace_merge_base
parent_head
blocking_evidence
requested_changes
alternatives
risks
required_tests
requires_user_decision
stopped_work
```

`kinds` contains one or more of `stale_state`, `scope_change`, `root_constraint_conflict`, and `blocked`. A root-constraint conflict must set `requires_user_decision=true`.

## Compound example

A Worker discovers that the parent branch advanced and that the only known fix changes both a forbidden build file and a public API protected by the mission. The Worker must stop, report all three commit references, explain the compatibility risk, and propose alternatives. Root cannot approve the public-API exception without a recorded user approval. Approval creates contract version `n+1` at the current parent HEAD; every version `n` receipt remains invalid.

## Parent checks

- The requester is assigned to the contract.
- The request targets the active contract version.
- Work stopped before the request was submitted.
- Blocking evidence supports every requested scope or policy change.
- The new contract preserves its mission, parent, and contract ID.
- The new version increments exactly once and uses the current parent HEAD.
- Old receipts cannot reach `VERIFIED` or `INTEGRATED`.
