# Preregistration Draft

Status: design freeze candidate; no comparative model outcome has been inspected.

## Study objective

Test whether bounded recursive delegation with versioned contracts, structured receipts, isolated workspaces, deterministic drift checks, and parent-controlled integration reduces long-horizon task drift in Python repository tasks.

## Evidence tiers

The primary causal evidence comes from sealed controlled repository tasks whose generation parameters, hidden tests, and injected drift opportunities are unavailable to the agent. A 24-task SWE-bench Verified candidate set is retained only for same-model, same-task external sensitivity analysis. It is not used to claim frontier coding ability because benchmark contamination and evaluator defects are now documented. Protocol-only fault injections establish detector correctness but do not establish end-to-end agent effectiveness.

## Confirmatory hypotheses

- H1: Full protocol increases root-goal satisfaction versus flat multi-agent delegation.
- H2: Full protocol reduces unsupported completion claims versus natural-language recursive delegation.
- H3: Worktree isolation plus scope gates reduces scope violations and undetected merge conflicts.
- H4: Depth two provides a better quality-cost tradeoff than depth one or unrestricted recursion.
- H5: Deterministic checks detect all injected stale-state, forbidden-path, and missing-evidence faults in the synthetic set.

Compound cases are successful only when execution stops, the conflict is escalated, approval is recorded where required, a new contract version is issued from the current parent HEAD, and every old-version receipt is rejected.

## Design

- Screening: 24 tasks x five conditions x one seed. It is used for feasibility, variance estimation, and failure taxonomy only.
- Primary confirmation: 120 sealed controlled tasks x two conditions (flat multi-agent and full protocol) x two model families x one frozen seed.
- Robustness subset: a preregistered stratified sample of 30 confirmatory tasks receives a second seed. It is not treated as 30 new inferential units.
- Public sensitivity study: 24 audited public candidates x two core conditions x two model families x one seed, only after container reproduction and task annotation.
- Mechanism ablation: five principal ablations on 24 fault-matched controlled tasks. Ablations are mechanism checks, not substitutes for the primary comparison.

The 120-task target follows an unconditional exact McNemar sensitivity analysis. With 30% discordant pairs and a 75% treatment win share (an implied paired risk difference of 15 percentage points), 24 tasks have about 14% power and 100 tasks about 75% power at alpha 0.05. The generated report records exact values and more conservative multiplicity bounds. If the available budget cannot fund 120 tasks, the study is explicitly relabeled as a pilot and emphasizes intervals rather than confirmatory significance.

## Task construction and independence

Controlled tasks must span at least eight repositories and 120 independently authored task families. Variants from one template are not permitted to inflate the confirmatory task count; any later variant analysis is clustered by family and reported separately. Public tasks are selected without using gold patches, with 12 medium and 12 long official difficulty labels, at least eight repositories, and no more than four tasks per repository.

Public task type and delegation-opportunity labels require two independent human annotators who see only the public problem statement, followed by adjudication. Report Cohen's kappa and disagreements. Automated labels may help prepare the rubric but cannot be reported as human annotation. The public candidate list remains unfrozen until every base image runs, annotations are adjudicated, and known broken or wide-test tasks are handled under the frozen exclusion rule.

## Inclusion, exclusion, and stopping

Include Python tasks with a reproducible environment, deterministic or repeatably bounded tests, a pinned base commit, and machine-checkable hidden tests or an adjudicated rubric. Exclude tasks whose dependencies cannot be redistributed, whose base environment is irreparably failing, or whose task text requires external credentials.

Failures are classified by exposure boundary:

- Environment or task preflight failure before model exposure is analysis-ineligible and retryable.
- Timeout, tool failure, or refusal after model exposure is an unsuccessful agent outcome.
- Evaluator failure preserves the original agent patch and retries only evaluation.
- Missing telemetry is reported and is never imputed as success.

Stop after the planned episode count or declared monetary budget, whichever occurs first. Report incomplete cells rather than silently replacing them. Replacement tasks must follow a frozen deterministic order and the reason for every exclusion must be published.

## Blinding and leakage controls

The agent manifest contains only an opaque task ID, objective, and public constraints. Repository identity, base commit, gold patch, hidden tests, evaluator script, failure-to-pass lists, and hints are stored in a sealed evaluator manifest outside the agent project. Allowed files are defined from the task specification, never inferred from the gold patch. Agent checkouts contain one detached base commit, no remotes, no future branches, and no recoverable gold objects.

Each run starts in a fresh context and fresh checkout. Condition order is SHA-256 block-randomized within task x seed. Resume identity includes task, condition, seed, model/config/prompt hashes, protocol version, budgets, and manifest hash.

## Outcomes

The sole primary outcome is root-goal satisfaction from hidden tests plus the frozen task rubric. Secondary outcomes are scope violation, stale-state acceptance, unsupported completion, conflict miss, regression, final patch correctness, tokens, latency, retries, child count, and human intervention. Handoff information loss is coded on a stratified trace sample by two raters using a frozen codebook.

## Analysis

The task, or task family when variants share a template, is the inferential unit. Average repeated seeds and model strata within task for the primary estimate. Report paired risk or mean differences, cluster-bootstrap 95% confidence intervals, and task-level sign-flip permutation tests. Exact McNemar tests are episode-level sensitivity analyses only. H1 is tested at two-sided alpha 0.05; Holm correction applies to the preregistered secondary binary outcome family. Report effect sizes, intervals, adjusted p-values, missing telemetry, failure cases, counterexamples, and negative results.

## Reproducibility freeze

Record protocol/schema/source hashes, complete eligible and excluded task lists, replacement order, repository commit, container image digest, model identifier and provider revision, prompt hash, temperature, token/tool/time budgets, seed, randomized schedule hash, event log, final diff, and test logs. Official harness run IDs include condition, seed, model/config fingerprint, task ID, and patch hash. Any deviation must be timestamped and explained before inspecting the affected outcome.
