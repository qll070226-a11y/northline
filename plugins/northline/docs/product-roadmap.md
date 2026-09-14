# Product-First Roadmap

Date: 2026-09-14

## Primary objective

Ship a useful Codex Skill and Plugin that reduce long-task drift in everyday repository work. The paper and experimental harness are secondary evidence for design decisions and measured effects.

## Product acceptance criteria

1. A user can install the Skill alone or the complete Plugin.
2. The Plugin persists mission, contract, receipt, verification, and event artifacts under `.northline/`.
3. Codex can initialize/resume a mission, save contracts, assess parallel safety, validate handoffs, and report blockers through MCP.
4. The CLI provides the same critical path when MCP is unavailable.
5. Verification never silently modifies source or performs integration.
6. A stale, wrong-agent, out-of-scope, old-version, failing-test, or evidence-free handoff is blocked deterministically.
7. Installation, manifests, MCP startup, and realistic cross-process state recovery are tested.

## Release sequence

- `0.2.0`: product control plane, persistent `.northline/`, seven MCP tools, CLI fallback, personal marketplace installation.
- `0.3.0`: automatic Git diff/test evidence collection and explicit parent integration recording.
- `0.4.0`: ergonomic contract/receipt generation, resume summaries, and configurable policies.
- `1.0.0`: forward-tested workflows, migration policy, cross-platform installer, and measured product evaluation.

## Secondary research track

Retain the paper draft, preregistration, controlled tasks, container gates, and statistical analysis. Use them to validate whether product mechanisms reduce drift. Research blockers must not block ordinary Skill/Plugin releases unless they expose a correctness or safety defect in the product.
