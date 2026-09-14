# Verifiable Recursive Delegation for Long-Horizon Software Engineering Agents

Artifact note (2026-09-14): the maintained project is product-first. This manuscript and its experiments provide secondary validation for the released Codex Skill and Plugin.

## Abstract

Long-horizon software engineering tasks expose a failure mode that is not captured by final test pass rate alone: an agent can gradually drift from the root objective, modify files outside its mandate, continue from stale repository state, or report completion without verifiable evidence. We present a framework-neutral protocol for bounded recursive delegation in which a Root agent delegates to Workers and Leafs through versioned contracts, isolated workspaces, structured handoff receipts, and parent-controlled verification. Deterministic checks gate integration; language-model judges may explain findings but cannot authorize a merge. We implement the protocol with a LangGraph-compatible runtime and a Codex Skill/Plugin adapter. Our staged empirical study compares five scaffolds during screening, then evaluates a frozen primary comparison on sealed controlled Python repository tasks. Public benchmark tasks are retained as an external sensitivity study rather than treated as uncontaminated ground truth. We evaluate goal adherence, scope violations, stale-state acceptance, unsupported completion claims, regressions, cost, latency, and intervention rate. The artifact is designed to reproduce both successes and failure cases.

## 1. Introduction

Multi-agent coding systems increasingly decompose software engineering tasks into specialized roles. However, delegation adds a control problem: local optimization by child agents can change the effective task, and each handoff can lose constraints or evidence. Existing systems often report a final patch or conversation trace without treating handoff validity as a first-class object.

This work asks whether a bounded delegation protocol can reduce long-horizon task drift while preserving useful parallelism. Our contributions are: (1) a formal model of goal, scope, state, and evidence drift; (2) a versioned contract and handoff receipt protocol; (3) deterministic verification gates over commits, files, tests, and constraints; and (4) an open, reproducible empirical evaluation.

## 2. Research Questions and Hypotheses

- RQ1: Does controlled recursive delegation improve root-goal adherence over single-agent and flat multi-agent baselines?
- RQ2: What is the marginal value of contracts, receipts, parent verification, worktree isolation, and deterministic drift checks?
- RQ3: How do recursion depth, parallelism, and verification strength trade off quality, cost, and latency?
- RQ4: Which failure modes are intercepted by deterministic checks?
- RQ5: Does the protocol transfer across models, repositories, and task types?

H1 predicts lower goal drift; H2 predicts fewer unsupported completion claims; H3 predicts fewer scope violations and merge conflicts; H4 predicts that depth two is a favorable quality-cost point; H5 predicts high recall for deterministic state and scope checks.

## 3. Problem Formulation

Let a mission be `M=(G,C,A,B)` where `G` is the root goal, `C` global constraints, `A` acceptance criteria, and `B` the base commit. A delegation tree `T` contains agents and contracts. A contract `K` defines objective, allowed scope, forbidden scope, dependencies, required tests, and base commit. A receipt `R` is valid only if its contract version and base commit match the parent context and its evidence satisfies local acceptance criteria.

We define goal drift as failure to satisfy `A` while the final patch may still pass unrelated tests. Scope drift is a changed path or behavior outside `K`. State drift is execution from a stale base commit or contract version. Evidence drift is a completion claim unsupported by reproducible test output or a result commit. These dimensions are reported separately rather than collapsed into a single judge score.

### 3.1 Delegation invariants

For every non-root node `v`, exactly one parent owns the contract that created `v`. A receipt can discharge only that contract, must identify the assigned agent, and must reference the same contract version and base commit. Integration is authorized only when all deterministic findings have severity below `BLOCK`. These invariants prevent a valid receipt for one task from advancing another task and prevent a newer natural-language explanation from overriding older machine-verifiable constraints.

### 3.2 Operational measures

Root-goal satisfaction is judged from hidden acceptance tests and a task-specific rubric. Scope drift is observed from the repository diff relative to allowed and forbidden path patterns. State drift is observed from commit and contract-version mismatches. Evidence drift is observed when required test commands, result commits, or criterion-specific evidence are absent. Handoff information loss is the proportion of root constraints relevant to a child task that are absent from its contract or receipt; two annotators label relevance on a preregistered sample.

## 4. Protocol

The protocol uses `PLANNED -> CLAIMED -> EXECUTING -> REPORTING -> VERIFIED -> INTEGRATED`, with explicit blocked, stale, partial, rejected, and parent-decision states. The Root owns final integration. A Worker may create a Leaf only within the mission depth and child-count budget. A parent verifies a receipt before accepting it. A blocked finding is never overridden by an LLM judge. When execution requires a stale base, expanded scope, or a root-constraint exception, the child must stop and emit an `EscalationRequest` rather than disguising the conflict as a completed handoff.

### 4.1 Contracts and receipts

A contract is immutable within one execution attempt. Changing objective, scope, required tests, or base commit increments its version and invalidates earlier receipts. A receipt maps every local acceptance criterion to evidence and reports assumptions, risks, unresolved questions, changed files, and tests. The protocol distinguishes `REPORTING`, an agent claim, from `VERIFIED`, a parent decision, and `INTEGRATED`, a repository state transition.

### 4.2 Escalation and contract revision

An escalation records the active contract version, contract base, workspace merge base, parent HEAD, blocking evidence, requested changes, alternatives, risks, and tests required after revision. Submission requires an explicit stop-work assertion. Stale execution first enters `STALE`; scope or policy changes enter `NEEDS_PARENT_DECISION`. Only Root may record a decision, and a root-constraint conflict additionally requires recorded user approval. Approval creates version `n+1` of the same contract at the current parent HEAD and restarts it from `PLANNED`. Receipts for version `n` remain permanently ineligible for integration. This path makes necessary deviation observable without treating every cross-cutting change as agent error.

### 4.3 Authorization and concurrency

The reference policy allows Root agents to create Workers and Workers to create Leafs. Leafs cannot delegate. A parent may have at most four children, and maximum depth is two. Parallel execution is permitted only when file scopes do not overlap and declared dependencies do not impose an order. File disjointness is necessary but not sufficient: shared APIs, schemas, and migrations require explicit dependencies and serial integration.

### 4.4 Verification order

Verification proceeds from cheap deterministic checks to expensive semantic checks: identity and version, commit freshness, path safety and scope, required tests, criterion evidence, integration tests, and finally optional LLM interpretation. A semantic judge may identify an unmodeled risk and request parent review, but it cannot erase a deterministic block. This asymmetry is intentional because LLM judgments are themselves stochastic and potentially affected by the same long-context drift.

## 5. Implementation

The artifact separates protocol-core, a LangGraph runtime adapter, Git worktree operations, Codex Skill/Plugin packaging, and evaluation utilities. Every transition and finding is serializable. The reference implementation has no mandatory model dependency, enabling deterministic protocol tests and controlled synthetic faults.

The protocol types are distributed as dataclasses plus a Draft 2020-12 JSON Schema. The MCP server exposes `validate_handoff`, `check_transition`, and `check_parallel_safety` over stdio. The LangGraph adapter treats protocol state as data rather than embedding policy in prompts. An append-only JSONL event log records delegation, transitions, escalation decisions, verification findings, and integration decisions. The Git adapter reads commits and diffs and creates detached worktrees; merge authorization remains in the runtime. A provider-neutral episode runner separates the agent backend from the evaluator backend, block-randomizes conditions within task and seed, fingerprints every frozen run configuration, and supports append-only checkpoints. Only failures before model exposure are infrastructure exclusions. Agent failures after exposure remain negative outcomes, while evaluator failures preserve the original patch and retry evaluation alone. Agent and evaluator manifests are distinct: hidden tests, repository mappings, gold patches, and oracle metadata never enter the agent payload.

## 6. Methodology

The screening study uses 24 Python repository tasks across bug fixes, API changes, test completion, and refactoring. The primary confirmatory study uses 120 sealed controlled tasks from 120 independently authored task families across at least eight repositories. It compares flat multi-agent and full-protocol scaffolds for two model families, with a second seed on a frozen 30-task robustness subset. A 24-task audited public set is an external sensitivity analysis because public benchmark contamination prevents a clean absolute-capability interpretation. Baselines during screening are single-agent, flat multi-agent, natural-language recursive, structured-contract recursive, and the full protocol. Ablations remove one gate at a time.

### 6.1 Conditions

All conditions receive the same root task, repository snapshot, model family, tool budget, timeout, and temperature. The single-agent condition has no delegation. The flat condition delegates only from Root. The natural-language recursive condition permits two levels but uses free-form handoffs. The structured-contract condition uses schemas but no deterministic integration gate. The full condition uses schemas, worktree isolation, parent verification, and deterministic drift detection.

### 6.2 Two-stage design

Screening evaluates all five conditions once on 24 tasks and is used only for feasibility, variance estimation, and failure taxonomy refinement. Confirmatory evaluation freezes prompts, schemas, task inclusion criteria, outcomes, model snapshots, and a block-randomized schedule before any comparison is inspected. The primary comparison is full protocol versus flat multi-agent. Ablations run on fault-matched controlled tasks so each removed mechanism is exposed to its corresponding injected fault.

### 6.3 Reproducibility controls

Each episode records repository commit, container digest, model identifier, model/provider revision when available, prompt hash, protocol version, seed, tool calls, token usage, wall-clock time, exit status, full event log, final diff, and tests. Each checkout contains only its detached base commit, has no remote, and excludes future and gold objects. A failed or timed-out episode after model exposure remains in the dataset. Reruns are permitted only for frozen pre-exposure infrastructure failures; evaluator reruns reuse the original patch.

## 7. Metrics and Analysis

The sole primary outcome is root-goal satisfaction. Scope violation, stale-state acceptance, unsupported completion, regression, final patch correctness, token cost, latency, retries, and human interventions are secondary outcomes. We report paired confidence intervals, effect sizes, non-parametric paired tests, multiple-comparison correction for the secondary binary family, and stratified results by task type and model. Failure traces are manually coded with an inter-rater protocol for a sample.

The task is the inferential unit. Seeds are averaged within task before cluster bootstrap confidence intervals and sign-flip permutation tests are computed. Binary episode-level discordance is also reported with exact McNemar tests as a descriptive sensitivity analysis. Holm correction controls family-wise error across the preregistered binary outcomes. Effect estimates and confidence intervals remain primary; adjusted p-values are secondary. Cost and latency are analyzed as paired differences and shown jointly with quality through Pareto plots.

No claim of improvement is made solely from a judge score. Root-goal satisfaction requires hidden tests or human rubric adjudication, and scope/state/evidence outcomes come from deterministic logs. Missing telemetry is reported, not imputed as success. A prospective exact-power analysis shows that 24 tasks are strongly underpowered for plausible paired effects; the public set is therefore a pilot/sensitivity study, not the confirmatory sample.

## 8. Threats to Validity

Threats include model and prompt dependence, limited Python coverage, controlled-task realism, correlated variants, imperfect goal labels, API variance, public benchmark contamination, faulty benchmark tests, and the possibility that strict verification reduces useful autonomy. We mitigate these with task-family clustering, two model families, an audited public sensitivity set, released prompts and logs, repeated seeds on a frozen subset, negative results, deterministic checks, and explicit artifact limitations.

Construct validity remains the central risk: a patch may satisfy visible tests while violating intent, and a strict path policy may label a necessary cross-cutting edit as drift. We therefore separate correctness, goal adherence, scope, state, and evidence rather than defining drift as any failure. Internal validity is threatened by provider updates and stochastic sampling; frozen prompts, recorded model identifiers, paired tasks, and multiple seeds reduce but do not remove this threat. External validity is limited to Python repository tasks and bounded recursion. Researcher degrees of freedom are reduced through the accompanying preregistration and immutable raw episode logs.

SWE-bench Verified and SWE-bench Pro require additional caution. Public audits published in 2026 report both memorization/contamination evidence and substantial evaluator defects. Consequently, public results in this study compare scaffolds under identical task/model exposure and are not interpreted as unbiased measures of frontier coding ability. The main causal analysis uses sealed controlled tasks; protocol-only injections are reported separately from end-to-end agent outcomes.

## 9. Reproducibility and Artifact

The repository releases schemas, state transitions, prompts, task manifests, synthetic fault generators, raw JSONL episodes, analysis scripts, environment metadata, and a one-command smoke test. No private user code or credentials are required.

## 10. Related Work

The positioning should cite surveys and systems including the ACM TOSEM multi-agent software-engineering survey, ReAcTree, Goal Drift, ReAct, Reflexion, MetaGPT, ChatDev, SWE-agent, and OpenHands. The protocol differs by treating handoff receipts and integration authorization as measurable research objects.

He, Treude, and Lo survey LLM-based multi-agent systems across the software lifecycle and identify trustworthy agent synergy as an open direction [1]. MetaGPT encodes software-process SOPs as role-specific workflows [2], while ChatDev structures communication across design, coding, and testing phases [3]. These systems motivate structured collaboration but do not isolate receipt validity and stale-state acceptance as primary outcomes.

ReAct interleaves reasoning and action [4], and Reflexion stores verbal feedback across attempts [5]. Both improve trajectories but leave authority and repository-state consistency largely to the agent scaffold. SWE-agent demonstrates that the agent-computer interface materially affects repository-level performance [6]. Goal Drift directly evaluates persistent objective adherence under competing pressure [7], while ReAcTree uses recursively expanded agent trees and control-flow nodes for long-horizon planning [8]. Our work connects these threads in software engineering by testing whether explicit delegation contracts and evidence-gated integration reduce measurable drift.

## 11. Conclusion

Bounded recursion, explicit contracts, and evidence-gated parent integration provide a testable control surface for long-horizon coding agents. The artifact is intended as a foundation for future work on adaptive depth, cross-language repositories, and distributed execution.

## References

[1] Junda He, Christoph Treude, and David Lo. 2025. LLM-Based Multi-Agent Systems for Software Engineering: Literature Review, Vision, and the Road Ahead. ACM Transactions on Software Engineering and Methodology 34(5), 1-30. https://doi.org/10.1145/3712003

[2] Sirui Hong et al. 2023. MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework. arXiv:2308.00352.

[3] Chen Qian et al. 2024. ChatDev: Communicative Agents for Software Development. ACL 2024. arXiv:2307.07924.

[4] Shunyu Yao et al. 2023. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023. arXiv:2210.03629.

[5] Noah Shinn et al. 2024. Reflexion: Language Agents with Verbal Reinforcement Learning. Advances in Neural Information Processing Systems 36, 8634-8652.

[6] John Yang et al. 2024. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. arXiv:2405.15793.

[7] Rauno Arike, Elizabeth Donoway, Henning Bartsch, and Marius Hobbhahn. 2025. Technical Report: Evaluating Goal Drift in Language Model Agents. arXiv:2505.02709.

[8] Jae-Woo Choi et al. 2025. ReAcTree: Hierarchical LLM Agent Trees with Control Flow for Long-Horizon Task Planning. arXiv:2511.02424.
