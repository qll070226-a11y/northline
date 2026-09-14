# Milestone 5 Report: Container Validation Gate

Date: 2026-09-13

## Delivered

- Added `experiments/validate_task_images.py` as an independent validation gate.
- The gate rejects dry-run/local-tag entries and requires an immutable `RepoDigest` for every task.
- Container execution uses `--network none`, a read-only root filesystem, a bounded tmpfs, and a read-only mount containing only hidden tests.
- Visible and hidden test command results are captured with exit codes and bounded stdout/stderr tails.
- The gate emits explicit statuses: `validated_task_images`, `task_image_validation_failed`, `pending_task_image_digests`, or `blocked_docker_daemon`.
- Added regression coverage for missing digest handling and connected the gate to `scripts/run_repro.ps1` and artifact packaging.
- Added `experiments/promote_suite.py`, which prevents model episodes from starting until image validation and two-rater adjudication gates pass.
- Added `experiments/audit_controlled_blueprints.py`, which blocks the 32-task expansion until four balanced task types and independent task families are present.
- Promotion now also requires the blueprint audit report, so an incomplete or unbalanced task suite cannot reach model execution even if later gates are accidentally supplied.

## Current result

The current Codex app sandbox cannot access Docker Desktop's `docker_engine` named pipe. The truthful result is:

- overall status: `blocked_docker_daemon`
- task count: 8
- all task entries: `missing_immutable_digest`
- sealed data in image: `false`

This is an infrastructure preflight result, not a benchmark outcome.

## Verification

- 62 tests pass.
- Ruff checks pass.
- Full reproduction entrypoint completes successfully.
- Artifact sealed-data scan passes.

## Exit criteria for the next environment

Run the existing command in a Docker-capable terminal or remote evaluator. Do not proceed to model episodes unless all eight entries have `status=built`, immutable image digests, and container visible/hidden baseline tests passing.
