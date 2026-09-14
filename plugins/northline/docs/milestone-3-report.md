# 第三阶段报告：受控任务 Pilot 与评估器闭环

日期：2026-09-13

## 阶段结论

这一阶段完成了第一组真正可执行的受控任务，而不是只生成任务元数据。8 个任务覆盖 TTL 边界、配置优先级、CSV 引号、依赖环、事件去重、分页终止、路径包含和重试预算等容易被局部修复掩盖的行为边界。

每个任务均具备：

- 独立 Git base commit
- 可见测试与隐藏测试
- 标准 gold patch
- agent-visible manifest 与外部 sealed oracle
- 可重复的 host-level baseline/gold 验证日志

## 结果

- 8/8 可见 baseline 测试通过
- 8/8 隐藏 baseline 测试失败
- 8/8 gold patch 同时通过可见和隐藏测试
- 8/8 空 patch 被 evaluator 判定为目标失败且 unsupported completion
- 统一 episode runner 运行 8 个 plumbing episode，全部 `completed`
- 原始 episode JSONL 不进入发布包，因为包含 sealed gold patch

这些不是模型能力结果，也不支持 H1-H5。它们只证明任务工厂、密封边界、patch 应用、范围计算、测试执行和结果记录能够闭环。

## 这一步解决的问题

1. 任务不再依赖公共 benchmark 的 gold patch 作为唯一真值。
2. 评估器从 base commit 临时 clone，避免模型工作区残留影响结果。
3. 隐藏测试在计算 diff 后再复制，避免测试本身被误报为范围越界。
4. 空 patch 与 gold patch 双向验证，防止隐藏测试过弱。
5. package script 只复制结果白名单，并拒绝 oracle、gold.patch、raw episodes 和 parquet。

## 尚未解决的问题

- 8 个任务仍是 pilot，不是 120 个确认任务。
- 目前是 host-level 验证，不是 Docker task-image 验证。
- 任务模板由当前研究实现者编写，尚需独立审阅者检查目标歧义、可修复性和隐藏测试泄漏。
- 尚未运行真实模型，因此没有比较条件、token 成本或漂移率结果。
- `conflict_missed` 等并非每个任务适用，后续必须使用 fault-matched task families，而不是强行填零。

## 下一阶段工程任务

1. 为每个 pilot 构建 task-level Docker image，并保存 image digest、Dockerfile hash 和 build log。
2. 用普通终端或远程 evaluator 运行容器级 evaluator，复核 host/container 一致性。
3. 让两名独立审阅者盲审 8 个 pilot，记录任务类型、委派机会、目标清晰度、隐藏测试泄漏和难度。
4. 将任务蓝图扩展到 32 个，优先覆盖 4 个 task type，每类 8 个独立家族。
5. 只有 32-task pilot 的构造和评估稳定后，才批量扩展到 120 个确认任务。

## 需要学习的知识

- 软件测试：测试 oracle、mutation testing、property-based testing、metamorphic testing、test adequacy
- 实验设计：paired design、clustered inference、blocking/randomization、power 与 multiplicity
- 可复现构建：Dockerfile、OCI image digest、SBOM、supply-chain provenance、Hermetic build
- Git 工程：detached checkout、worktree、patch application、merge-base、冲突检测
- Agent 评估：exposure-boundary failure、trajectory logging、cost/latency telemetry、benchmark contamination
- 任务标注：codebook、双人盲标、Cohen's kappa、adjudication、inter-rater disagreement
- 论文写作：construct/internal/external validity、negative results、artifact evaluation、registered report
