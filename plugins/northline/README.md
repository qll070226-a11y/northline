<p align="center">
  <img src="./assets/northline-logo.png" width="160" alt="Northline logo">
</p>

<h1 align="center">Northline</h1>

<p align="center"><strong>Verifiable delegation for long-running agent work.</strong></p>

Northline 是一个面向 Codex 的 Skill 与 Plugin。它把根任务、委派范围、仓库状态和交接证据保存为可验证对象，阻止过期、越界或缺少证据的子任务结果直接进入集成。

## 能力

- 持久化根目标、约束、决策、验收标准和基线 commit。
- 将递归委派限制为 `Root -> Worker -> Leaf`，默认最大深度 2。
- 用版本化 `DelegationContract` 限制每个子任务的目标、文件和测试。
- 用 `HandoffReceipt` 记录变更、测试、证据、假设、风险和遗留问题。
- 确定性检查 agent 身份、契约版本、commit 新鲜度、文件范围和测试证据。
- 创建固定基线的隔离 Git worktree，并由父侧重新计算 diff、commit 祖先关系和测试结果。
- 严格区分 `VERIFIED` 与 `INTEGRATED`：验证只授权父智能体继续审查，不会自动合并源代码。
- 自动生成契约与交接凭证中的可观察字段，并给出可执行的任务恢复摘要。
- 用仓库级策略限制隔离、脏工作区、空测试、变更规模和测试超时。
- 生成可直接交给 Worker/Leaf 的版本化任务派发包，不依赖聊天记忆重述范围。
- 记录 Git 支持的执行检查点，并在中断后检查 worktree 是否与检查点一致。
- 输出委派树、事件时间线、验证摘要和协议开销计数，支持完整审计。
- 用显式 schema 版本和迁移命令维护长期兼容性。
- 通过最小权限 Codex CLI 适配器执行任务，持久化 thread、JSONL 轨迹与 token usage。
- 将运行失败转为可恢复检查点，限制最大尝试次数，并安全清理终态 worktree。
- 在五个隔离 Git 场景中组合验证主流程、递归委派、范围漂移、过期状态和失败恢复，并输出协议开销。

## 准备本地运行时

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_plugin.ps1
```

脚本会创建 `.venv-plugin`，安装协议核心和 MCP 依赖，并运行 smoke test。通过 GitHub marketplace 安装时，MCP 启动器也会在首次运行时执行同一准备过程。

## CLI

```powershell
.\.venv-plugin\Scripts\northline.exe init --workspace . `
  --objective "实现功能并保持原有 API" `
  --constraint "不得修改公开接口" `
  --criterion "测试全部通过"

.\.venv-plugin\Scripts\northline.exe resume --workspace .
.\.venv-plugin\Scripts\northline.exe forward-test --output results\product-forward-test.json
```

完整 MCP 与 CLI 流程见 [product-workflow.md](./skills/northline/references/product-workflow.md)。
系统边界、信任模型与数据流见 [architecture.md](./docs/architecture.md)。
前向场景、指标与解释边界见 [product-forward-testing.md](./docs/product-forward-testing.md)。

## 状态目录

```text
.northline/
|-- project.json
|-- mission.json
|-- policy.json
|-- contracts/*.json
|-- contract-history/*/v*.json
|-- dispatches/*.json
|-- checkpoints/<contract-id>/*.json
|-- agent-runs/*.json
|-- run-artifacts/<run-id>/events.jsonl
|-- executions/*.json
|-- receipts/*.json
|-- verifications/*.json
|-- escalations/*.json
|-- decisions/*.json
|-- integrations/*.json
`-- events.jsonl
```

## 开发验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\ruff.exe check .
.\.venv-win\Scripts\northline.exe forward-test --output results\product-forward-test.json
```

完整仓库、研究材料与 issue tracker：<https://github.com/qll070226-a11y/northline>

## License

[MIT](./LICENSE)
