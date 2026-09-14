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
- 验证只授权父智能体继续审查，不会自动修改或合并源代码。

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

.\.venv-plugin\Scripts\northline.exe status --workspace .
```

完整 MCP 与 CLI 流程见 [product-workflow.md](./skills/northline/references/product-workflow.md)。

## 状态目录

```text
.northline/
|-- mission.json
|-- contracts/*.json
|-- receipts/*.json
|-- verifications/*.json
`-- events.jsonl
```

## 开发验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\ruff.exe check .
```

完整仓库、研究材料与 issue tracker：<https://github.com/qll070226-a11y/northline>

## License

[MIT](./LICENSE)
