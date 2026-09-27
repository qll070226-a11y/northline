# Northline 项目面试讲解与答辩手册

> 适用场景：向导师、评审或技术面试官介绍 Northline 的设计动机、系统架构、工程实现、研究价值和后续计划。
>
> 当前产品定位：Northline 是一个面向 Codex 的 Skill + Plugin，用于约束长程软件工程任务中的递归委派、状态恢复、交接验证和最终集成。论文与实验框架是支撑产品决策的研究性附属产物。
>
> 文档更新时间：2026-09-27。

---

## 1. 先记住这一句话

如果导师只给我一分钟，我会这样介绍：

> Northline 不是一个“让更多 Agent 一起写代码”的多智能体框架，而是位于 Root Agent、执行运行时和 Git 仓库之间的可验证控制层。它把根任务、子任务范围、仓库状态和交接证据保存成结构化对象；子智能体只能在明确契约和隔离 worktree 中执行；父智能体会重新计算 commit、diff、测试和状态证据；只有通过确定性验证并由 Root 复核的结果，才有资格进入集成。因此它主要解决的是长程任务中的目标漂移、范围越界、过期状态和无证据完成声明。

这句话包含了项目的四个核心判断：

1. 主要问题不是“单次回答是否正确”，而是长时间、多轮调试后系统是否还在完成原始目标。
2. 多智能体的关键风险不是并发本身，而是委派边界和交接信息会逐渐失真。
3. 自然语言报告不能单独作为完成证据，必须和 Git、测试、协议状态等可观测事实分开验证。
4. LLM 可以帮助解释和发现风险，但不能单独授权合并；最终集成权必须保留在 Root。

---

## 2. 为什么要做这个项目

### 2.1 长程任务的“慢性失控”

短任务中，Agent 可能只需读取一个文件、修改几行代码、运行一个测试。但是仓库级任务通常包含：

- 理解一个模糊的根目标；
- 拆解为多个子任务；
- 反复调试、重试和修改；
- 在多个分支或 worktree 中并行工作；
- 处理过期 commit、依赖变化和冲突；
- 将局部结果重新合并，并确认没有破坏全局目标。

在这条链路中，系统可能出现几种“看起来完成、实际上已经偏离”的情况：

| 失败类型 | 具体表现 | 为什么普通 Agent 流程容易漏掉 |
| --- | --- | --- |
| 目标偏离 | 子任务解决了局部问题，但不再满足 Root 的最终验收标准 | 子任务只记住最近一条自然语言指令 |
| 范围越界 | 修改了契约之外的文件、配置或接口 | 最终只看测试是否通过，没有重新计算允许范围 |
| 状态漂移 | 基于旧 commit、旧契约版本或已变化的父分支继续工作 | 对话历史不会自动证明仓库状态仍然有效 |
| 证据不足 | Agent 声称“测试通过”，但没有命令、输出或结果 commit | 自然语言报告和实际仓库事实没有分离 |
| 合并错误 | 一个局部结果被直接复制进主分支，绕过父侧审查 | `VERIFIED`、`INTEGRATED` 和“我觉得可以合并”被混为一谈 |

### 2.2 项目的核心问题

Northline 研究和实现的核心问题可以写成：

> 在长程软件工程任务中，带有受约束递归委派、结构化交接凭证、隔离工作区和父智能体验收的控制协议，能否降低目标漂移、范围越界、过期状态接受和未经证据支持的完成声明？

这个问题比“多 Agent 是否比单 Agent 更好”更具体，因为它关注的是可验证的控制机制，而不是单纯增加 Agent 数量。

---

## 3. Northline 不是什么

导师很可能会先问：“这是不是又一个多智能体编排框架？”建议主动说明边界。

Northline **不是**：

- 一个新的基础模型；
- 一个替代 Codex、OpenHands 或 SWE-agent 的执行 Agent；
- 一个只靠 Prompt 约束 Agent 的聊天模板；
- 一个允许任意深度递归和任意自动合并的调度器；
- 一个只根据最终测试通过率判断成功的评测脚本；
- 一个把所有 Agent 都放到同一个共享工作区的协作工具。

Northline **是**：

- 一个框架无关的协议核心；
- 一个保存任务、契约、状态、凭证、验证和集成记录的本地控制面；
- 一个可以通过 Codex Skill、MCP、CLI 和 LangGraph 适配器使用的产品；
- 一个把“是否可以交接”和“是否可以集成”分成不同权限阶段的证据门禁；
- 一个可以通过合成故障、真实 Git 仓库和实验日志进行验证的研究 artifact。

---

## 4. 总体架构怎么讲

仓库中的详细图位于 [`assets/northline-architecture.svg`](../assets/northline-architecture.svg)。面试时可以按从上到下、从控制到执行、再到证据和集成的顺序讲。

```text
用户
  ↓
Root Agent：理解根目标，保留最终决策和集成权
  ↓
Northline Control Plane
  ├── MissionState：根目标、全局约束、决策、验收标准
  ├── Delegation Engine：契约、权限、依赖、递归深度和子任务上限
  ├── State Machine：PLANNED → ... → VERIFIED → INTEGRATED
  ├── Agent Runtime Adapter：Codex，未来可接 OpenHands / SWE-agent
  ├── Workspace Manager：固定 base_commit，创建隔离 worktree
  ├── Root / Worker / Leaf：受控递归委派树
  ├── Handoff Receipt：子智能体声明的结果与风险
  ├── Evidence：Git、Test、Protocol 三类独立证据
  ├── Deterministic Verifier：重新计算事实并阻断违规结果
  ├── Parent Review：父侧复核剩余风险
  ├── Root-only Integrator：只有 Root 可以记录集成
  ├── Global Tests & Goal Acceptance：全局验收
  └── Research Harness / Event Store：记录轨迹、成本、延迟和失败案例
```

### 4.1 Root Agent

Root 不是普通的“最高权限聊天 Agent”这么简单，它有三个明确职责：

1. 维护 `MissionState`，包括全局目标、不可违反的约束和最终验收标准。
2. 决定是否拆解任务、是否允许并行、是否需要升级或修改契约。
3. 在验证完成后进行父侧审查和最终集成。

Root 可以授权 Worker，但不能把自己的最终决策责任转移出去。

### 4.2 Worker 和 Leaf

v1 采用固定的三层结构：

```text
Root
 ├── Worker
 │    ├── Leaf
 │    └── Leaf
 └── Worker
```

默认最大递归深度为 2，单个父节点最多 4 个子任务。Worker 只有在契约明确授权时才能继续派生 Leaf；Leaf 不得继续委派，也不能修改 Root 的全局目标、全局约束或架构决策。

这样做不是因为无限递归在理论上不可能，而是因为 v1 需要先控制实验变量和权限边界。无限递归会带来更多上下文损失、调度开销、合并冲突和责任归属问题。

### 4.3 Control Plane 和 Runtime 的分离

Northline 将“协议真相”和“Agent 执行”分开：

- ProtocolEngine 负责状态、契约、证据、验证和集成规则；
- Codex CLI、LangGraph 或未来的其他运行时负责执行具体任务；
- GitWorkspace 负责 worktree、commit、diff、祖先关系和测试执行；
- ProjectStore 负责持久化 `.northline/` 下的控制面数据；
- MCP、CLI 和 Skill 只是不同入口，不应该各自实现一套不同的协议逻辑。

这保证了将来替换执行运行时，不需要改变实验中真正被研究的协议核心。

---

## 5. 核心数据对象

### 5.1 MissionState：全局任务状态

`MissionState` 是 Root 级别的任务主线，主要字段包括：

```text
mission_id
objective
global_constraints
decisions
acceptance_criteria
root_commit
max_depth
max_children
```

它回答的是：“整个项目最终要完成什么？”而不是“某个子 Agent 现在要改什么？”

例如：

```json
{
  "mission_id": "mission_api_refactor",
  "objective": "将用户认证模块迁移到新的 token 接口，同时保持旧客户端兼容",
  "global_constraints": [
    "不能删除旧公开 API",
    "必须保留 Python 3.10 支持",
    "所有公开行为变化必须有测试"
  ],
  "acceptance_criteria": [
    "新 token 接口可用",
    "旧客户端测试继续通过",
    "全量测试通过"
  ],
  "root_commit": "abc123...",
  "max_depth": 2,
  "max_children": 4
}
```

### 5.2 ProtocolPolicy：全局治理策略

`ProtocolPolicy` 保存协议的硬性安全要求，例如：

- 是否必须使用隔离 worktree；
- 是否要求证据工作区干净；
- 是否必须重新运行契约要求的测试；
- 最大变更文件数；
- 测试超时时间；
- 单个 Agent 最大尝试次数。

策略的作用是把“项目偏好”变成可执行门禁，避免每轮对话重新解释。

### 5.3 DelegationContract：一个有界子任务

契约是父节点给子节点的机器可读授权，主要字段包括：

```text
contract_id
parent_id
mission_id
version
objective
in_scope
out_of_scope
allowed_files
forbidden_files
dependencies
acceptance_criteria
required_tests
base_commit
deadline_or_budget
```

契约必须回答六个问题：

1. 你要完成什么？
2. 你可以修改什么？
3. 你明确不能修改什么？
4. 你依赖哪些其他任务？
5. 什么结果算完成？
6. 你必须基于哪个 commit 开始？

契约一旦进入执行，不能通过聊天内容静默修改。若目标、范围、测试或基线发生变化，必须生成新版本；旧版本的 receipt 不再有资格进入集成。

### 5.4 AgentTaskPacket：实际派发包

`AgentTaskPacket` 是将 MissionState、Contract、Workspace 状态合并后的执行载荷。它会把 Root 目标、全局约束、子任务范围、工作区、base commit、当前 workspace commit、测试和协议规则一次性传给 Worker 或 Leaf。

它解决一个常见问题：子 Agent 不应该依赖一长串聊天记录来恢复任务范围。

### 5.5 ExecutionState：执行事实

它记录：

- contract id；
- agent id 和角色；
- 当前状态；
- worktree；
- 当前 commit；
- 已运行测试和结果；
- 执行备注。

### 5.6 HandoffReceipt：子 Agent 的声明

Receipt 不是“完成证明”，而是待验证的声明。它通常包含：

```text
contract_id
agent_id
status
base_commit
result_commit
changed_files
diff_summary
tests_run
test_results
evidence_links
assumptions
risks
unresolved_questions
recommended_next_action
```

重要原则：Receipt 可以由子 Agent 提交，但不能被父节点直接信任。

### 5.7 RepositoryEvidence：父侧重建的事实

Verifier 会重新获取：

- commit 是否存在；
- result commit 是否从 base commit 派生；
- 实际变更文件是什么；
- workspace HEAD 是否符合契约；
- required tests 是否真实执行；
- 测试输出和退出码是什么；
- Receipt 的声明是否与实际状态一致。

这就是“声明”和“证据”的分离。

---

## 6. 状态机和权限边界

### 6.1 正常状态

```text
PLANNED
   ↓
CLAIMED
   ↓
EXECUTING
   ↓
REPORTING
   ↓
VERIFIED
   ↓
INTEGRATED
```

各状态含义：

| 状态 | 含义 | 谁可以推动 |
| --- | --- | --- |
| `PLANNED` | 契约已创建，尚未开始执行 | Root/父节点 |
| `CLAIMED` | Agent 已接收任务包 | 执行引擎 |
| `EXECUTING` | Agent 正在工作 | 执行引擎 |
| `REPORTING` | Agent 已提交结果和 Receipt，等待验证 | 子 Agent |
| `VERIFIED` | 父侧独立证据检查通过 | Verifier/父节点 |
| `INTEGRATED` | Root 已将结果纳入父仓库并完成集成测试 | Root/Integrator |

### 6.2 异常状态

```text
PARTIAL                 执行中断或运行时失败
BLOCKED                 当前无法安全继续
STALE                   基线或契约版本过期
NEEDS_PARENT_DECISION   需要父节点决定范围/约束变化
REJECTED                证据或契约检查失败
```

### 6.3 为什么 `VERIFIED` 不等于 `INTEGRATED`

这是导师非常可能问的问题。

`VERIFIED` 只说明：在子 worktree 中，这个结果满足当前契约的局部要求。它并不说明：

- 父仓库已经包含这个 commit；
- 与其他并行任务没有冲突；
- 全局测试通过；
- Root 的整体目标已经满足。

因此，Northline 把权限切成两道门：

```text
局部证据通过：VERIFIED
        ↓ Root 父侧 diff review
父仓库集成 + 全局测试 + 根目标验收
        ↓
INTEGRATED
```

这样可以防止“局部正确”被误认为“全局正确”。

---

## 7. 一次完整执行流程

以下例子假设 Root 要求：“给 Python 仓库增加一个新的 API，同时保持旧 API 兼容。”

### 步骤 1：初始化任务

Root 创建 MissionState，写入目标、约束、验收标准和当前 root commit。

```powershell
northline init `
  --workspace . `
  --objective "增加新 API 并保持旧 API 兼容" `
  --acceptance-criterion "新 API 测试通过" `
  --acceptance-criterion "旧 API 回归测试通过"
```

初始化后，项目目录会出现 `.northline/`，但源代码仍由 Git 管理。

### 步骤 2：设计并保存契约

Root 将任务拆成一个 Worker 子任务，例如只允许修改 `src/api.py` 和 `tests/test_api.py`。

```powershell
northline contract `
  --workspace . `
  --objective "实现兼容的新 API" `
  --in-scope "API 参数转换与兼容逻辑" `
  --out-of-scope "数据库迁移" `
  --allowed-file src/api.py `
  --allowed-file tests/test_api.py `
  --forbidden-file migrations/ `
  --criterion "新 API 返回正确结果" `
  --criterion "旧 API 行为不变" `
  --test "pytest tests/test_api.py -q" `
  --role worker `
  --agent-id worker_api
```

### 步骤 3：检查并发安全

如果同时还有另一个任务修改 `src/models.py`，Root 不能只因为路径不完全重叠就直接并行，还要考虑共享接口、schema 和迁移顺序。

并行判断至少检查：

- 文件范围是否重叠；
- 是否共享 API、schema 或数据库迁移；
- 是否存在显式依赖；
- 是否有必须串行的测试或集成顺序。

### 步骤 4：准备隔离 worktree

每个契约在固定 `base_commit` 上创建独立 worktree。子 Agent 不直接污染 Root 工作区。

```powershell
northline prepare --workspace . --contract-id <contract-id> --target worker_api
northline dispatch --workspace . --contract-id <contract-id>
```

派发包中会包含：

- Root 目标；
- 全局约束；
- 当前契约版本；
- base commit；
- 子 Agent 身份与角色；
- 允许和禁止的文件；
- required tests；
- 发生过期或扩大范围时必须停止并升级的规则。

### 步骤 5：显式授权运行 Agent

Northline 默认不会因为准备了契约就自动启动外部 Codex。启动模型运行必须有明确 Root 授权。

```powershell
northline run-codex `
  --workspace . `
  --contract-id <contract-id> `
  --authorize `
  --timeout-seconds 3600
```

运行时会保存 JSONL 事件、线程信息、token usage、退出码和最终消息。若在模型真正暴露前失败，可作为基础设施失败重试；模型已经开始工作后失败，必须作为一次真实执行结果保留。

### 步骤 6：中断或阻塞时记录 checkpoint

Agent 不能只说“下次继续”。它要记录当前 commit、已经完成的工作、待处理工作、阻塞原因和 workspace 状态。

```powershell
northline checkpoint `
  --workspace . `
  --contract-id <contract-id> `
  --completed "完成 API 参数转换" `
  --pending "补充旧 API 回归测试" `
  --blocker "发现父分支新增了共享 schema" `
  --note "需要 Root 决定是否升级契约"
```

### 步骤 7：提交 Receipt

子 Agent 必须先形成结果 commit，再报告。Receipt 需要把每条 acceptance criterion 对应到证据。

```powershell
northline receipt `
  --workspace . `
  --contract-id <contract-id> `
  --summary "完成 API 兼容转换并补充回归测试" `
  --acceptance-evidence "新 API 返回正确结果=pytest tests/test_api.py -q: passed" `
  --acceptance-evidence "旧 API 行为不变=pytest tests/test_legacy_api.py -q: passed" `
  --evidence-workspace <worker-worktree>
```

### 步骤 8：父侧验证

```powershell
northline verify `
  --workspace . `
  --contract-id <contract-id> `
  --receipt receipt.json
```

验证器会重新执行确定性检查，而不是只解析子 Agent 的文本。

### 步骤 9：Root 复核并集成

Root 要检查：

- diff 是否符合原始目标；
- 是否有未披露的假设；
- 是否有与其他任务的冲突；
- 是否需要修改架构决策；
- 全局测试是否通过。

只有 Root 在父仓库实际集成后，才可以记录：

```powershell
northline integrate --workspace . --contract-id <contract-id>
```

---

## 8. 确定性验证器到底检查什么

Northline 的验证器不是一个单一的“LLM judge”，而是多个确定性检查的组合。

### 8.1 身份检查

确认 Receipt 中的 `agent_id`、contract id、parent id 和当前执行记录匹配。防止一个 Agent 的结果被错误地挂到另一个任务上。

### 8.2 契约版本检查

确认 Receipt 使用的契约版本仍然是当前版本。若 Root 已经批准新范围并创建了版本 2，版本 1 的结果不能继续进入集成。

### 8.3 Commit 新鲜度检查

确认：

- base commit 真实存在；
- result commit 真实存在；
- result commit 从 base commit 派生；
- retry 场景符合最近 checkpoint；
- workspace HEAD 和记录一致。

### 8.4 文件范围检查

验证器从 worktree 重新计算实际 diff，而不是相信子 Agent 提交的 `changed_files` 字段。实际变更如果超出 `allowed_files` 或命中 `forbidden_files`，直接阻断。

### 8.5 测试证据检查

测试命令来自 Root 预先写入的契约，而不是子 Agent 临时在 Receipt 中声称的命令。验证器会重新运行 required tests，并记录退出码、输出和超时。

### 8.6 目标条件检查

每个 acceptance criterion 必须有证据映射。对语义性很强的目标，确定性验证器不能完全判断“是否真正满足业务意图”，因此交给 Root 进行最终语义复核；但它可以阻止缺少映射、缺少测试或缺少结果 commit 的完成声明。

### 8.7 依赖和并发检查

两个契约只有在文件、接口、schema、迁移和执行顺序都没有冲突时，才允许并行。Northline 对并行安全采取保守判断：无法证明独立，就按串行处理。

### 8.8 为什么确定性检查优先

LLM 适合解释复杂 diff、提出潜在风险和帮助 Root 发现未建模问题，但它不应该独自授权合并。原因是：

- LLM 判断具有随机性；
- LLM 可能受到长上下文漂移影响；
- LLM 很难可靠地证明 commit 祖先关系和真实文件范围；
- 安全策略需要“可重复地阻断”，而不是“多数情况下感觉没问题”。

---

## 9. `.northline/` 如何保存项目状态

项目控制面数据保存在仓库本地的 `.northline/` 目录：

```text
.northline/
├── mission.json                         # Root 任务主线
├── policy.json                          # 全局治理策略
├── project.json                         # 项目与 schema 信息
├── contracts/<contract-id>.json         # 当前契约
├── contract-history/<id>/v<n>.json      # 契约版本历史
├── dispatches/<packet-id>.json          # Worker/Leaf 派发包
├── checkpoints/<id>/<checkpoint-id>.json# 中断恢复点
├── agent-runs/<run-id>.json             # Agent 运行记录
├── run-artifacts/<run-id>/events.jsonl  # JSONL 事件和运行产物
├── executions/<contract-id>.json        # 执行状态
├── receipts/<receipt-id>.json           # 子 Agent Receipt
├── verifications/<receipt-id>.json      # 父侧验证结果
├── escalations/<request-id>.json        # 停止工作请求
├── decisions/<request-id>.json          # Root 决策
├── integrations/<contract-id>.json      # 集成记录
└── events.jsonl                         # 追加式事件时间线
```

JSON 文件通过临时文件写入再替换，避免中途写入造成损坏；`events.jsonl` 是追加式日志，可以用于恢复委派树、重建状态转换和统计协议开销。源代码改动仍然在 Git worktree 中，不和控制面记录混在一起。

---

## 10. 代码结构：导师问“你具体写了什么”时怎么回答

| 路径 | 作用 | 面试时的重点 |
| --- | --- | --- |
| [`src/northline/models.py`](../src/northline/models.py) | Mission、Contract、Receipt、Execution 等协议对象 | 把自然语言任务变成可序列化对象 |
| [`src/northline/state_machine.py`](../src/northline/state_machine.py) | 状态转移规则 | 防止跳过 `REPORTING`、`VERIFIED` 等门禁 |
| [`src/northline/engine.py`](../src/northline/engine.py) | `ProtocolEngine` 主应用服务 | 所有关键入口统一走一个状态ful service |
| [`src/northline/project_store.py`](../src/northline/project_store.py) | `.northline/` 持久化 | 支持恢复、迁移、事件和版本历史 |
| [`src/northline/workspace.py`](../src/northline/workspace.py) | Git worktree、commit、diff、测试 | 把仓库事实从 Agent 报告中独立出来 |
| [`src/northline/detector.py`](../src/northline/detector.py) | 漂移和证据发现 | 输出确定性 finding 和阻断级别 |
| [`src/northline/schema.py`](../src/northline/schema.py) | Draft 2020-12 schema 校验 | 防止不同入口写入形状不一致的数据 |
| [`src/northline/agent_runtime.py`](../src/northline/agent_runtime.py) | Codex CLI 适配 | 显式授权、JSONL、usage、超时和失败记录 |
| [`src/northline/langgraph_runtime.py`](../src/northline/langgraph_runtime.py) | LangGraph 可选适配 | 让编排层使用协议状态，但不拥有协议真相 |
| [`src/northline/mcp_server.py`](../src/northline/mcp_server.py) | MCP stdio 工具 | 向 Codex 和其他客户端暴露统一协议能力 |
| [`src/northline/cli.py`](../src/northline/cli.py) | CLI 备用入口 | MCP 不可用时仍可执行关键流程 |
| [`src/northline/events.py`](../src/northline/events.py) | 事件与时间线 | 支持审计、恢复和实验数据提取 |
| [`experiments/`](../experiments) | 任务、后端、指标和实验运行器 | 将产品机制转化为可复现实验 |
| [`tests/`](../tests) | 协议、Git、MCP、CLI 和实验测试 | 验证“不能错误集成”这类安全属性 |
| [`skills/northline/SKILL.md`](../skills/northline/SKILL.md) | Codex 使用规则 | 指导何时委派、暂停、验证和集成 |
| [`.codex-plugin/plugin.json`](../.codex-plugin/plugin.json) | Plugin manifest | 声明 Skill、MCP、图标和安装信息 |

最重要的工程设计是：MCP、CLI、Skill 和 LangGraph 不各自复制状态机，而是最终调用同一个 `ProtocolEngine` 或同一套协议核心。这减少了入口之间行为不一致的风险。

---

## 11. 如何安装和运行

### 11.1 本地开发环境

项目使用 Python `>=3.10`。开发依赖包括：

- `jsonschema`：协议对象和 Draft 2020-12 schema 校验；
- `pytest`：测试；
- `ruff`：静态检查；
- `mcp`：MCP stdio server；
- `langgraph`：可选运行时适配；
- `numpy / scipy / pandas / statsmodels`：实验与统计；
- `swebench / datasets`：外部仓库级任务评估；
- `openai`：可选模型后端。

插件自带准备脚本：

```powershell
powershell -ExecutionPolicy Bypass -File plugins\northline\scripts\setup_plugin.ps1
```

### 11.2 最小产品验证

```powershell
cd plugins\northline
..\..\.venv-win\Scripts\python.exe -m northline.cli demo
..\..\.venv-win\Scripts\python.exe -m northline.cli forward-test --output results\product-forward-test.json
..\..\.venv-win\Scripts\python.exe -m northline.cli health --workspace <repo-path> --output results\health.json
```

`forward-test` 会创建隔离的临时 Git 仓库，验证：

1. 正常的提交、验证和集成；
2. Root → Worker → Leaf 的嵌套委派；
3. 禁止文件修改被拒绝；
4. 过期基线被拒绝；
5. 运行中断后的恢复流程。

它不需要调用真实模型，因此适合 CI 和安装后 smoke test。

### 11.3 CLI 命令分组

```text
demo / evaluate / forward-test / health
    产品演示、smoke 结果、确定性前向测试、本机健康检查

init / contract / prepare / dispatch
    初始化任务、创建契约、创建 worktree、生成任务派发包

transition / checkpoint / receipt / verify / integrate
    推进状态、记录检查点、生成交接凭证、父侧验证、记录集成

status / resume / report / schema / migrate
    查看当前状态、恢复摘要、委派报告、schema 和迁移

run-codex / retry / cleanup
    显式启动 Codex、计划重试、清理终态 worktree

escalate / decide / revise
    提交升级、记录 Root 决策、安装新版本契约
```

### 11.4 MCP 入口

MCP server 通过 stdio 启动：

```powershell
northline-mcp
```

MCP 工具覆盖四类操作：

- 纯协议检查：`check_transition`、`check_parallel_safety`、`validate_handoff`；
- 产品自测：`run_product_forward_test`、`northline_health_check`；
- 项目状态：初始化、契约、worktree、dispatch、checkpoint、report；
- 执行和集成：live preflight、Codex runtime、receipt、verify、escalate、integrate。

### 11.5 Codex Skill 和 Plugin 的区别

- Skill 主要提供行为规则和工作流提示，让 Codex 知道何时创建契约、何时停止、何时验证、何时升级。
- Plugin 提供 manifest、Skill、MCP server、资源、图标和安装入口，适合打包分发。
- 两者共用协议核心；Skill/Plugin 不是两套不同的逻辑。

---

## 12. 参考了哪些开源项目，具体借鉴什么

Northline 采用“一个运行时适配层 + 一个独立协议核心”的策略，不把其他项目直接拼接成一个大框架。

| 项目 | 借鉴内容 | Northline 的边界 |
| --- | --- | --- |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 状态图、节点编排、持久化运行思路 | LangGraph 只是可选 runtime adapter，协议规则仍在 Northline |
| [OpenHands](https://github.com/OpenHands/OpenHands) | 软件工程 Agent 的工具执行环境和仓库交互思路 | 不直接嵌入执行环境，未来通过 adapter 接入 |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | 仓库级任务、Git 修改和 SWE-bench 评估经验 | Northline 负责契约和证据门禁，不复制其 Agent |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 角色分工、软件流程和产物交接 | Northline 把角色交接进一步结构化为 commit/diff/test receipt |
| [ChatDev](https://github.com/OpenBMB/ChatDev) | 多角色沟通、阶段化软件开发流程 | Northline 不把自然语言对话当作唯一交接证据 |
| Microsoft Agent Framework | 多 Agent 运行时标准化方向 | 作为未来跨运行时适配和互操作的参考 |

项目的差异点是：

> 这些项目主要解决“Agent 如何执行和协作”，Northline 重点解决“一个协作结果何时有资格被父节点接受和集成”。

---

## 13. 研究问题和实验设计

产品之外，Northline 还提供一条可复现实验线，用来回答协议是否真的降低漂移。

### 13.1 研究问题

- **RQ1**：受控递归委派是否比单 Agent 和扁平多 Agent 更能保持根目标？
- **RQ2**：契约、Receipt、父验收、worktree 隔离和确定性检测各自贡献多少？
- **RQ3**：递归深度、并发度、验证强度在质量、成本和延迟之间如何权衡？
- **RQ4**：最常见的失败模式是什么，哪些可以被确定性规则提前阻断？
- **RQ5**：协议能否迁移到不同模型、Python 仓库和任务类型？

### 13.2 对照组

至少包含：

1. 单 Agent，无结构化交接；
2. 扁平多 Agent，只允许 Root 委派；
3. 递归多 Agent，但使用普通自然语言交接；
4. 递归多 Agent + 结构化契约；
5. 完整 Northline 协议：契约、Receipt、隔离 worktree、父验证、确定性漂移检测。

### 13.3 消融实验

逐项移除：

- 结构化契约；
- Handoff Receipt；
- 父侧验证；
- Git worktree 隔离；
- 确定性漂移检测；
- 深度限制；
- 测试证据门控。

### 13.4 指标

质量指标：

- 根目标满足率；
- 最终 patch 正确率；
- 测试通过率；
- 回归率；
- 任务完成率。

漂移指标：

- 目标漂移率；
- 契约范围越界率；
- 过期状态接受率；
- 无证据完成声明率；
- 交接信息损失；
- 冲突漏检率；
- 错误合并率。

系统指标：

- token 消耗；
- 总延迟；
- 子任务数量；
- 并发度；
- 人工介入次数；
- 重试次数；
- 验证器拦截率。

### 13.5 为什么不只看最终测试通过

最终测试通过不能证明：

- Agent 没有修改契约之外的文件；
- Agent 没有基于过期状态；
- Agent 没有遗漏根目标中的其他条件；
- Agent 的“测试通过”声明是真实可重现的；
- 合并过程没有绕过 Root 权限。

因此 Northline 把正确性、范围、状态和证据作为不同维度记录，而不是把所有问题压缩成一个 judge 分数。

---

## 14. 当前实现状态和诚实边界

截至 2026-09-27，项目已经具备：

- 可安装的 Codex Skill 与 Plugin；
- 持久化 `.northline/` 控制面；
- Root/Worker/Leaf 最大深度 2 的受控委派；
- 版本化契约和契约历史；
- Git worktree 隔离；
- Receipt、checkpoint、escalation、decision 和 integration 记录；
- 统一 CLI、MCP、Skill 和 LangGraph 适配结构；
- Codex CLI 显式授权、JSONL、token usage 和运行状态记录；
- 确定性 forward suite；
- 合成范围冲突、过期状态、错误证据和复合升级场景；
- 实验任务、统计分析和 controlled-task 研究基础设施；
- 插件校验、打包流程和较完整测试套件。

最近本地验证中，协议、CLI/MCP、Git worktree、实验和运行时测试共 `98 passed`。确定性产品 forward suite 为 `5/5` 通过。

但不能夸大为“已经解决 Agent 幻觉”。目前仍有边界：

1. 语义目标满足仍需要 Root 审查或任务特定 oracle，不能完全由路径和 Git 规则决定。
2. 当前主要支持 Python/Git 仓库，不等于已经覆盖所有语言和构建系统。
3. 最大递归深度固定为 2，尚未验证无限递归或动态深度策略。
4. 尚未完成跨机器分布式调度、Web UI 和在线学习。
5. 公开 benchmark 可能受到污染或测试缺陷影响，不能直接宣称 frontier capability。
6. 完整 controlled confirmatory study 仍需要 Docker 镜像、隐藏测试、双人标注和密封 oracle 的进一步验证。
7. 真实模型运行受 provider、凭据、网络和外部运行时影响；这些需要和协议失败分开报告。

一个重要的研究态度是：**产品可以先发布，研究结论必须等证据完整后再说。**

---

## 15. 导师可能问的问题与建议回答

### Q1：你的项目和普通 Multi-Agent Framework 有什么区别？

普通框架重点解决角色创建、消息传递和任务编排；Northline 重点解决交接是否有效、结果是否过期、是否越界以及谁有权集成。它不是增加 Agent，而是给 Agent 协作增加可验证的控制边界。

### Q2：为什么不直接用 LangGraph 的状态机？

LangGraph 可以表示流程，但流程表示不等于 Git 证据验证和权限治理。Northline 把协议核心独立出来，LangGraph 只作为一个可选运行时适配器，这样同一套契约和验证规则也能通过 CLI、MCP 或未来其他 runtime 使用。

### Q3：为什么需要 Worker 和 Leaf 两层？一个 Agent 直接做完不行吗？

单 Agent 是重要 baseline，而且很多小任务不需要委派。但长程任务中不同子问题可能需要不同上下文、工具或独立工作区。两层结构能引入有限并行，同时把递归深度、责任边界和实验变量控制在可解释范围内。

### Q4：为什么最大深度是 2？

这是 v1 的保守设计。深度越大，委派树越复杂，约束损失、调度延迟和错误合并概率越高。先固定深度 2，能够比较单 Agent、扁平多 Agent、递归自然语言和完整协议；未来再研究动态深度是否值得付出成本。

### Q5：如果子 Agent 发现原任务范围不够，怎么办？

不能直接越界修改。它应该停止工作，提交 `EscalationRequest`，说明当前契约版本、基线、实际阻塞证据、请求扩大的范围和风险。Root 决定后创建新版本契约，旧 Receipt 永远不能自动继续集成。

### Q6：为什么不能让 LLM Judge 直接判断能不能合并？

因为 commit 祖先关系、实际 changed files、测试退出码和工作区 HEAD 都是可以确定性计算的事实，不应交给随机模型判断。LLM Judge 可以辅助发现语义风险，但不能覆盖一个确定性的阻断结果。

### Q7：如何证明 Agent 没有撒谎说测试通过？

required tests 由 Root 写入契约，父侧在证据 worktree 中重新执行。Receipt 里的测试声明只作为待核对信息，最终以父侧执行的命令、输出、退出码和超时结果为准。

### Q8：隔离 worktree 的价值是什么？

它把执行空间和 Root 工作区分开，避免子 Agent 的未提交文件、临时文件或部分修改污染主线；同时每个契约可以记录固定 base commit，使状态新鲜度和 diff 范围可验证。

### Q9：你的系统会不会过度限制 Agent，降低效率？

会有成本，这是必须测量的 trade-off，而不是回避它。Northline 记录 token、延迟、重试、子任务数和人工介入；目标不是让所有任务都走最严格协议，而是找出质量、成本和安全之间的可接受点。

### Q10：如果两个任务改的是不同文件，为什么还不能总是并行？

文件不重叠只是必要条件，不是充分条件。两个任务可能共享 API、schema、数据库迁移或测试顺序。Northline 使用保守的并发安全检查，无法证明独立时就串行。

### Q11：你如何定义“目标漂移”？

我不把所有失败都称为目标漂移，而是分维度记录：目标满足失败、范围越界、状态过期和证据不足。目标漂移需要根据根验收标准、隐藏测试或任务特定 rubric 判断；范围和状态问题则尽量通过 Git 与协议数据确定性识别。

### Q12：为什么要保留自然语言交接 baseline？

因为不能假设结构化协议一定更好。自然语言递归交接是一个合理对照组，可以测量 schema、证据和父验收是否真的降低错误，而不仅是增加了格式。

### Q13：你如何避免实验数据泄漏？

Agent 和 evaluator 使用分离的 manifest。隐藏测试、gold patch、oracle 和未来对象不进入 Agent payload；任务 checkout 使用 detached base commit、无 remote 的环境；只有 evaluator 可以访问隐藏结果。

### Q14：为什么公开 SWE-bench 任务不是你的唯一主要证据？

公开 benchmark 可能存在训练污染、测试缺陷和任务分布偏差。它适合作为外部敏感性分析，但不应直接被解释为无偏的 frontier 能力估计。因此研究主比较需要密封、可控、带隐藏测试的任务集。

### Q15：你的实验单位是什么？为什么不是每个 Agent episode？

任务是主要推断单位，因为同一个任务的多个 seed 不是完全独立的。统计上会先在任务内汇总，再进行 task-cluster bootstrap、配对置换检验和必要的 McNemar 敏感性分析。

### Q16：Northline 能否完全自动判断语义正确？

不能，也不应该做出这种承诺。确定性验证器擅长状态、范围、身份、证据和依赖；语义目标满足仍需要 Root、任务 rubric、隐藏测试或专门 evaluator。系统的目标是让不可避免的语义判断发生在可审计的位置，而不是假装它不存在。

### Q17：如果父 Agent 本身也漂移了怎么办？

这是系统的主要限制之一。Northline 能把 Root 的目标、约束、决策和验收标准持久化，降低漂移，但不能自动保证 Root 的语义理解永远正确。更长期的方向包括用户确认点、目标版本化、独立审计 Agent 和跨轨迹一致性检查。

### Q18：为什么 `REJECTED` 以后还要支持 retry？

拒绝不等于任务永久失败。它说明当前 receipt 或执行尝试不具备集成资格。只有在 checkpoint、基线和契约仍然可追踪的情况下，系统才允许创建新尝试；重试必须留下原因和新的 attempt，不能覆盖历史。

### Q19：这个项目最有研究价值的地方是什么？

研究价值不是提出一个更复杂的 Agent，而是把长程协作中的“目标漂移、交接信息损失、过期状态和证据不足”变成可定义、可注入、可记录和可统计比较的变量。

### Q20：这个项目最可能失败的地方是什么？

第一，严格门禁可能降低有效自主性；第二，语义目标的评估仍然困难；第三，真实模型和 provider 的随机性会影响复现；第四，受控任务可能不完全代表真实软件工程。我的应对方式是明确报告成本、负结果和适用边界，而不是只展示成功案例。

---

## 16. 面试时推荐的 10 分钟讲解顺序

### 第 1 分钟：问题

解释长程任务不是一次回答，而是 Root、Worker、Leaf、多轮调试、多个 worktree 和最终合并的连续过程。指出四类风险：目标、范围、状态、证据。

### 第 2 分钟：核心思想

给出一句话：Northline 是控制层，不是执行 Agent。它用契约定义允许做什么，用 Receipt 描述做了什么，用父侧验证判断是否真的做到了，用 Root-only integration 控制最终合并。

### 第 3–4 分钟：架构

按“Root → Control Plane → Runtime/Workspace/Delegation → Evidence/Verifier → Review/Integration”讲。强调协议核心和运行时分离。

### 第 5 分钟：一次任务流程

从 `init`、`contract`、`prepare`、`dispatch`、`run-codex`、`receipt`、`verify`、`integrate` 走一遍。

### 第 6 分钟：关键差异

重点解释：

- `REPORTING` 不等于 `VERIFIED`；
- `VERIFIED` 不等于 `INTEGRATED`；
- Receipt 不是事实，RepositoryEvidence 才是父侧重建的事实；
- LLM 只能辅助解释，不能覆盖确定性阻断。

### 第 7 分钟：实现

展示 `models.py`、`engine.py`、`workspace.py`、`detector.py`、`mcp_server.py` 和 `.northline/` 数据目录。

### 第 8 分钟：验证和测试

说明 forward suite 如何注入过期状态、禁止文件、嵌套委派和中断恢复；说明本地测试套件和插件验证结果。

### 第 9 分钟：研究设计

介绍五个 baseline、消融实验、指标和为什么公开任务只能作为敏感性分析。

### 第 10 分钟：边界与未来

主动承认语义判断、跨语言、分布式、动态深度和真实 provider 依赖等限制，然后说明下一步如何用实验而不是主观感觉验证。

---

## 17. 后续路线图

### 产品方向

1. 在正常终端完成代表性真实 Codex contract 的完整闭环：运行、Receipt、父侧验证、Root 集成。
2. 增加更清晰的安装诊断、provider 检查和跨平台安装流程。
3. 提供更容易查看委派树、事件时间线和阻断原因的轻量 UI。
4. 继续保持协议核心与运行时解耦，增加 OpenHands 等适配器。

### 研究方向

1. 完成 Docker 不可变镜像和隐藏测试验证。
2. 完成双人任务标注与 adjudication。
3. 扩展四类任务：bug fix、API change、test completion、refactor。
4. 在多模型、不同仓库和不同递归深度下比较质量—成本曲线。
5. 研究动态深度、风险自适应验证强度和跨任务目标一致性。
6. 将实验原始轨迹、统计脚本和失败案例一起发布，报告负结果。

---

## 18. 最后给导师看的项目判断

Northline 当前最合适的定位不是“已经证明多智能体一定更好”，而是：

> 一个把长程 Agent 委派中的责任、范围、状态和证据显式化的工程原型，同时提供了验证这些机制是否有效的实验框架。

它的价值在于把一个通常只能凭感觉讨论的问题，转化为可操作的协议对象和可观测指标：

```text
根目标
  → 版本化契约
  → 隔离执行
  → 结构化交接
  → 父侧独立证据
  → Root 审查
  → 全局验收
  → 可审计集成
```

如果导师继续追问，可以回到三个关键词：

1. **Bounded delegation**：递归是受限的，不是无限扩张的。
2. **Evidence-gated handoff**：交接必须有可重建证据，不靠一句“完成了”。
3. **Root-controlled integration**：验证通过不自动合并，最终集成权仍由 Root 掌握。
