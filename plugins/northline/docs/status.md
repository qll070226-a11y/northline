# Research Artifact Status

Date: 2026-09-18

Primary delivery changed on 2026-09-14: the Codex Skill and Plugin are now the product objective. The paper and experiment harness are supporting research artifacts. See `docs/product-roadmap.md`.

## Completed

- Product v0.3 unified `ProtocolEngine`, with CLI and MCP using the same persistent state transitions
- Parent-rebuilt Git ancestry, exact changed-file, workspace-HEAD, and required-test evidence
- Explicit `VERIFIED` versus `INTEGRATED` gates, including post-integration test execution
- Persistent execution, contract history, escalation, decision, integration, and isolated-worktree records
- Product v0.4 contract/receipt drafting, actionable resume summaries, and repository policy enforcement
- Framework-neutral protocol types, bounded Root/Worker/Leaf runtime, and Draft 2020-12 schemas
- Deterministic identity, version, commit, path, test, criterion, dependency, and unresolved-question gates
- Stop-work escalation, contract revision, stale-receipt rejection, append-only event replay, and Git worktree isolation
- LangGraph adapter, MCP 2.x stdio server, Codex Skill, and Codex Plugin package
- Leakage-resistant agent/evaluator manifests and sealed public-task oracle
- Block-randomized paired episode schedules and full run fingerprints
- Exposure-aware failure policy: preflight is retryable, post-exposure failure is an outcome, evaluator retry preserves the patch
- Codex CLI agent backend and official SWE-bench harness evaluator backend
- Deterministic 24-task SWE-bench Verified candidate selection across eight repositories, with 12 medium and 12 long tasks
- Exact paired-binary power analysis, task-cluster bootstrap, permutation tests, McNemar sensitivity analysis, and Holm correction
- Controlled-suite freezer requiring 120 independent task families, pinned commits/images, hidden tests, and sealed oracle separation
- Eight-task controlled pilot builder with visible/hidden baseline validation and isolated evaluator
- Task-level image context builder with sealed-data exclusion, Docker daemon preflight, and digest gate
- Container validation runner with `--network none`, read-only image execution, hidden-test mount, and immutable-digest gate
- Blind two-rater review packet generator with duplicate/missing-rating checks and Cohen's kappa adjudication
- Model-experiment promotion gate requiring validated images, two-rater adjudication, task-count match, and sealed-data proofs
- 32-task blueprint audit requiring four balanced task types, independent families, and repository diversity
- Controlled-task authoring guide and sealed-field/path leakage checks for blueprint inputs
- Non-sensitive pilot episode summary and package-level sealed-artifact scan
- Updated preregistration, literature matrix, benchmark-validity threats, manuscript draft, and learning roadmap

## Environment installed

- Official Windows CPython 3.12 project environment
- LangGraph, MCP, NumPy, SciPy, pandas, statsmodels, jsonschema, pytest, and PyYAML
- SWE-bench 5.0.2, datasets 5.0.1, OpenAI Python SDK 2.x, and Modal client
- Docker Desktop 29.6.2 and Codex CLI 0.153.4
- Dependency consistency check reports no broken requirements
- Ruff static checks are part of the one-command reproduction gate

## Verified locally

- 78 tests pass across the protocol, persistent engine, CLI/MCP, real Git worktrees, product forward workflows, research runner, controlled tasks, review gates, and statistics
- Protocol-engine integration tests cover real commits, detached worktrees, false file claims, false passing-test claims, assigned-workspace enforcement, and integration ancestry
- Ruff syntax, symbol, and import checks pass
- Official Skill and Plugin validators pass
- Synthetic scope, stale-state, evidence, ambiguity, and compound escalation faults are blocked
- Dry-run screening resolves to a deterministic 120-episode schedule without model calls
- Public data checksum matches the pinned SWE-bench Verified revision
- A detached, remote-free exact-base pilot checkout has been prepared
- Exact-power results show why 24 public tasks are a pilot, not a confirmatory sample
- Eight pilot gold patches pass hidden tests and eight empty patches fail in isolated evaluation
- Eight task-level image contexts are reproducibly prepared with `.git`, `.github`, hidden-test, and oracle paths excluded

## Candidate, not frozen

The 24 public tasks remain a candidate sensitivity set. They require container-level reproduction, two independent human annotations plus adjudication, and removal or prespecified treatment of broken/wide-test cases. Public benchmark results will not be presented as uncontaminated frontier-capability estimates.

## External blockers observed

- Codex CLI model preflight fails in this app sandbox because the CLI cannot resolve its home/config directory.
- Docker client is installed, but this app sandbox is denied access to the user Docker config and `docker_engine` named pipe.
- The shell cannot currently reach the model API endpoint, so no paid model episode was started.

These occur before model exposure and are recorded as retryable infrastructure failures. They are not paper outcomes. The pipeline is ready to continue from the same run fingerprint once executed in a normal terminal or a remote evaluator with credentials.

## Current pilot boundary

The controlled pilot is validated on the host interpreter with an immutable base commit and a fixed Python image index digest. It is not yet a container-level result: task-level image builds and digest verification remain required before this pilot can be used as a benchmark claim. The pilot episode JSONL is sealed outside the package because it contains gold patches.

The current task-image manifest records `pending_docker_daemon`: the Docker client is installed, but this app sandbox cannot access the daemon named pipe. The generated contexts are preparation artifacts, not image-build evidence. The review manifest records `pending_two_rater_review` until two independent reviewers complete the supplied ratings template.

The task-image validation report now records the same preflight state and will execute only immutable-digest images with network disabled. It never treats a local tag or a missing digest as a validated image.

The promotion report currently blocks model execution until image validation, two-rater adjudication, and the 32-task blueprint audit are complete.

The 32-task blueprint audit currently blocks expansion because only the eight-task bug-fix pilot blueprints exist. It reports the missing 24 tasks and the missing `api_change`, `test_completion`, and `refactor` strata.

## Next product milestone

Forward-test the updated Skill in fresh Codex tasks, define migration behavior for future `.northline/` schema changes, and measure usability overhead from contracts and evidence rebuilding. The product remains the primary delivery; the research pipeline below supplies evidence rather than blocking ordinary releases.

## Next research milestone

Run the task-image builder in a normal terminal or remote evaluator with Docker access, record immutable task-image digests and container logs, complete the two-rater review and adjudication, then expand the pilot to 32 tasks before building the sealed 120-task suite and two-model, two-condition confirmatory schedule. The public set proceeds in parallel only as an external sensitivity study.
