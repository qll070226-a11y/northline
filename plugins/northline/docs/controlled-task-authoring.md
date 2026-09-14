# Controlled Task Authoring Guide

This guide is for the 24 additional tasks needed to reach the 32-task pilot. A task is not eligible merely because its gold patch passes. It must also be independently authored, reproducible, and auditable without exposing evaluator-only information.

## Required distribution

- 32 tasks total for the pilot expansion.
- Exactly 8 tasks each: `bug_fix`, `api_change`, `test_completion`, and `refactor`.
- At least 8 repositories.
- Every task has a unique `source_id` and a unique `task_family_id`.
- A task family represents one underlying behavior; variants of the same behavior must not be counted as independent families.

## Required blueprint fields

Each JSON task must contain:

`source_id`, `task_family_id`, `repository`, `task_type`, `objective`, `public_constraints`, `base_files`, `gold_files`, and `hidden_test_files`.

`base_files` must fail at least one hidden test while passing the visible tests. `gold_files` must pass visible and hidden tests. `hidden_test_files` must contain only evaluator tests and must not be copied to agent-visible manifests.

## Authoring rules

- Write the objective and constraints before writing the gold solution.
- Keep the public task solvable from the visible repository and specification alone.
- Preserve a small, reviewable diff; avoid unrelated formatting or dependency changes.
- Make hidden tests target behavior not explicitly asserted by visible tests.
- Use deterministic tests and standard-library dependencies whenever practical.
- Record why the task is independent from every other task in the same repository.
- Never include `gold_patch`, `oracle`, `evaluator_context`, `result_commit`, or `hidden_tests` fields in the authoring blueprint.
- Never place `hidden_tests`, `oracle`, or `gold.patch` paths inside `base_files` or `gold_files`.

## Per-task acceptance checklist

1. Base checkout has a reproducible commit and no remote.
2. Visible base tests pass.
3. Hidden base tests fail for the intended reason.
4. Gold files pass both visible and hidden tests.
5. Gold diff is limited to the declared allowed scope.
6. The task has one clear root objective and explicit non-goals.
7. A second reviewer can understand the task without seeing hidden tests or the gold patch.
8. The task is not a template duplicate of another family.

## Commands

Run the audit before building any workspace:

```powershell
.venv-win\Scripts\python.exe experiments\audit_controlled_blueprints.py ..\benchmark-data\controlled_32_blueprints.json --expected-count 32 --output results\controlled-blueprint-audit.json
```

The audit must report `ready_for_controlled_build`. The audit is a design gate; it does not replace visible/hidden test execution, task-image validation, or human review.
