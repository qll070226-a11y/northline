# Milestone 4 Report: Container and Review Gates

Date: 2026-09-13

## Objective

Convert the validated eight-task controlled pilot into an auditable container-build and human-review workflow without exposing hidden tests, oracle patches, or raw gold episodes.

## Delivered

- `experiments/build_task_images.py` creates one deterministic Docker context per task from the immutable base checkout.
- Context generation excludes `.git`, `.github`, `hidden_tests`, `oracle`, and `gold.patch` paths and records context/Dockerfile SHA-256 digests.
- Docker execution is gated by a server preflight. The current run truthfully records `pending_docker_daemon` because the Codex sandbox cannot access `docker_engine`.
- `experiments/validate_task_images.py` runs visible and hidden baseline tests only for immutable-digest images, using a read-only container, `--network none`, and a read-only hidden-test mount.
- `experiments/review_protocol.py` creates eight opaque review packets containing only objective, public constraints, scope, required tests, and source files.
- Ratings require exactly two distinct raters per packet. The adjudicator computes categorical Cohen's kappa and numeric disagreement metrics.
- Artifact packaging now includes only non-sensitive manifests and excludes raw episode/oracle artifacts.

## Verification

- 57 tests pass.
- Ruff checks pass for all new modules.
- Eight task contexts were prepared; `sealed_data_in_context=false`.
- Eight review packets were prepared; `sealed_data_in_packets=false`.

## Gate status

The pilot is still host-validated, not container-validated. No task-level image is labeled built until `docker image inspect` returns an immutable `RepoDigest`. Human review remains pending until the ratings CSV is completed by two independent reviewers and adjudicated.

## Next stage

1. Execute the builder in a normal Docker-capable terminal or remote evaluator and archive build logs plus image digests.
2. Complete blind ratings and run adjudication; resolve disagreements before promoting task annotations.
3. Expand the controlled suite from 8 to 32 independent task families, repeating visible/hidden baseline and image gates.
4. Only after those gates pass, freeze the 120-task confirmatory manifest.
