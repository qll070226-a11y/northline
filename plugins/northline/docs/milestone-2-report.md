# 第二阶段报告：可执行实验链与有效性加固

日期：2026-09-12 至 2026-09-13

## 阶段结论

项目已经从“协议原型”进入“可执行研究流水线”阶段。Root/Worker/Leaf 协议、Skill/Plugin、MCP、Git 隔离、漂移检测、模型后端、SWE-bench 评估后端、运行恢复、统计分析和发布打包均已形成可运行代码。

这一阶段最重要的研究修正是：不再把 24 个 SWE-bench Verified 任务作为论文主结论来源。2026 年公开审计显示该基准同时存在污染和评估器缺陷；SWE-bench Pro 也不能未经逐任务审计就视为干净替代品。因此，24 个公开任务仅用于同模型、同任务的外部敏感性比较，主因果证据改为 120 个密封受控仓库任务。

## 新增能力

- 严格区分 agent payload 与 sealed evaluator payload，未知任务字段直接拒绝。
- 在 task x seed 内对条件顺序做确定性分块随机化。
- 使用 manifest、模型、prompt、协议、预算和命令共同生成运行指纹。
- 模型看到任务前的预检失败可重试且不进入分析；模型暴露后的超时或工具失败计为失败结果。
- 评估器失败只重试评估，保留原始模型 patch，避免机会性重跑模型。
- Codex CLI 后端保存 JSONL 轨迹、最终消息、patch、token 和委派次数。
- SWE-bench 后端使用包含条件、seed、运行指纹、任务和 patch hash 的唯一 run ID。
- 新增受控任务冻结器：要求 120 个任务、120 个独立家族、至少 8 个仓库、完整 commit、容器 digest 和隐藏测试。
- 新增精确 McNemar 功效分析和 Ruff 静态质量门禁。

## 功效分析

在 discordant pairs 为 30%、协议条件赢得其中 75% 的中等情景下，对应配对风险差约 15 个百分点：

- 24 个任务：功效约 14.4%
- 50 个任务：功效约 40.7%
- 100 个任务：功效约 74.7%
- 120 个任务：功效约 83.3%

因此，多跑同一批 24 个任务的 seed 不能替代增加独立任务数。120 是中等效应、单一主要结局下的合理目标，并不保证检测到小效应。小效应仍需要约 368 个任务。

## 验证状态

- 47 项自动化测试通过。
- Ruff 静态检查通过。
- Python 字节码编译通过。
- `pip check` 无损坏依赖。
- 官方 Skill 校验通过。
- 官方 Plugin 校验通过。
- 一键复现脚本通过。
- 发布压缩包 SHA-256 已生成并复核。

## 已安装环境

Python 3.12、LangGraph、MCP、NumPy/SciPy/pandas/statsmodels、SWE-bench 5.0.2、Datasets 5.0.1、OpenAI SDK 2.x、Modal、Ruff、Docker Desktop 29.6.2 和 Codex CLI 0.153.4 均已安装。

## 当前外部阻塞

当前 Codex 应用沙箱无法访问用户级 Docker named pipe，并使 Codex CLI 无法解析用户主目录；shell 到模型 API 端点也超时。这些问题发生在模型看到任务之前，所以没有产生或伪造任何模型结果。流水线会在正常终端、可访问 Docker 的执行环境或配置好凭据的远程评估器中从相同运行指纹继续。

## 下一阶段

1. 编写并人工复核 120 个独立受控任务定义，随后用冻结器生成 agent manifest 和外置 sealed oracle。
2. 为每个任务构建、固定并记录容器 image digest，验证基线、可见测试和隐藏测试。
3. 完成 24 任务 x 5 条件筛选，只根据基础设施和失败类型调整 prompt，不查看比较性结论后改规则。
4. 冻结两个模型族、两个核心条件和 120 个任务的确认实验。
5. 公开任务完成双人盲标与仲裁后，仅作为外部敏感性分析运行。

## 本轮实际推进

本轮已经完成八任务 controlled pilot：每个任务都拥有独立 Git 基线、可见测试、密封隐藏测试和标准 gold patch。主机验证结果为 8/8 可见基线通过、8/8 隐藏基线失败、8/8 gold patch 通过双层测试。统一 episode runner 已以 sealed-gold-patch 代理完成 8 个 episode；这只是 runner/evaluator plumbing 验证，不是模型能力结果。原始 episode JSONL 含 gold patch，已留在外部密封目录，发布包只包含不含 patch 的汇总。

本轮新增了 controlled evaluator：评估时从 base commit 临时 clone，先应用 patch，再计算模型变更文件，最后复制隐藏测试并执行可见/隐藏测试。因此隐藏测试文件不会被误记为模型范围越界。新增的 `summarize_validation_episodes.py` 只输出计数、运行指纹和原始记录 hash。

任务级 Docker image digest 尚未真正构建。当前 pilot 使用固定 Python image index digest 作为基础运行约束，状态明确标记为 `validated_on_host_pending_task_image_build`。在 Docker named pipe 权限恢复前，不会把 host 验证升级为容器验证。

## 权威依据

- [Codex CLI 非交互执行与 JSONL 输出](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
- [SWE-bench 官方评估 harness](https://github.com/SWE-bench/SWE-bench/blob/main/docs/reference/harness.md)
- [OpenAI：不再使用 SWE-bench Verified 的审计说明](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
- [OpenAI：coding evaluations 信噪分离审计](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)
