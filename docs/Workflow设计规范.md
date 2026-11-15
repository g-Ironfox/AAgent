# Workflow 设计规范（草案）

> 状态：设计与评审规范草案；不是“现有校验器已全部实现”的声明。  
> 基线：本仓库 Workflow 2.0、Event 1.1 及核验时工作区源码，核对日期 2026-11-15。  
> 适用：Workflow 作者、编辑器、管理端、Agent 校验器及运行时。

## 1. 核心原则

**单次 Workflow 是可终止的编排单元：除受控的 `foreach` 循环外，控制流必须为 DAG；跨轮循环通过事件和 workflow_queue 完成；分支不能在同一张图中重新汇合，循环内条件逻辑或分支后的公共续接必须通过独立子 Workflow 封装。**

本规范中的“必须／禁止”是设计硬约束，“建议”是工程建议。现有代码或旧协议文档更宽松时，新建和改造 Workflow 仍以本文的设计约束为准；是否由程序自动拦截，见“实现差距与验收”。

### 1.1 三条强制约束

1. **除 `foreach` 的结构化回边外禁止任何环。** 禁止普通节点自环、Router 回跳、错误分支回跳，以及子 Workflow 的直接或间接递归。业务需要重复运行时，发布事件，经 workflow_queue 触发新的 invocation，不回到当前调用栈。
2. **`foreach` 循环体禁止出现带分支能力的节点。** 不仅包括 Router，也包括具有成功／失败等替代控制出口的节点；不能通过少连一条边规避。需要条件判断时，抽取子 Workflow，在循环体中放置单入单出的 `workflow` 调用节点。
3. **同一个分支节点的不同分支，在同一张 Workflow 图内禁止再次汇合。** 禁止立即汇合、经过任意多步后的汇合，以及共用同一个 Output。需要公共后续处理时，把完整分支逻辑抽为一个新 Workflow，通过依赖引用，在父图调用返回后继续。

### 1.2 workflow_queue 的术语映射

本文用 **workflow_queue** 表示“事件驱动的 Workflow 调度队列”。当前仓库没有独立名为 `workflow_queue` 的队列实现：实际入口是 `MAIN_AGENT_QUEUE_NAME`，默认 Redis key 为 `main_agent_queue`。不得把规范中的逻辑名称直接当成现有配置字段或另建一个无人消费的 Redis 队列。

`publish_event` → `publish_to_queue(MAIN_AGENT_QUEUE_NAME, event)` → `task_worker` 是当前可用链路。若后续正式拆分独立 workflow_queue，需同步改造全部生产者、消费者、环境配置及协议；本文不表示该拆分已经完成。

## 2. 仓库中的实际运行机制

持久化 JSON → 校验 → 编译 → 单控制游标执行 → Output 返回，是一次 invocation 的主链路。事件触发是异步调度，子 Workflow 调用则是当前调用栈内的同步组合，两者不可混用。

| 阶段 | 当前行为 | 主要源码 |
| --- | --- | --- |
| 事件接入 | 校验 Event 1.1、记录历史；非 `workflow` 事件查询启用绑定，再转投 `workflow` 事件 | `agent/task_worker.py::handle_task` |
| 加载定义 | 优先按 `workflow_file_id` 读取 Workspace；否则以 `workflow_name` 精确匹配当前 generation 的 Workspace 文件名 | `agent/task_worker.py`、`agent/workflow_parser.py` |
| 校验 | 校验 2.0 Schema、节点参数、端口类型和连线基数，并检查循环体中的实际控制分叉 | `agent/workflow_validator.py::validate_workflow` |
| 编译 | 把节点 ID 映射为下标，生成 `successors`、`predecessors`、`data_inputs`、`data_outputs` | `agent/workflow_parser.py::parse_workflow` |
| 执行 | 从唯一 Input 出发，每个 handler 返回下一个节点下标；数据输出深拷贝到下游输入槽位 | `agent/workflow_nodes.py::run_workflow_map`、`propagate_workflow_output` |
| 返回 | 首次执行到 Output 即结束当前图；子调用返回父图，根调用产生 `response` 事件 | `agent/workflow_nodes.py::workflow_output`、`workflow_workflow` |
| 清理与记录 | 记录 invocation 与节点轨迹，并在 finally 中清理本次 Context | `agent/workflow_nodes.py::run_workflow_map` |

这不是拓扑排序驱动的并行 DAG 调度器。`predecessors` 是编译结果，不是“等待所有前驱完成”的 join 屏障；数据连线也不会自动调度生产者。**控制流决定何时执行，数据流决定读到什么。**

## 3. 图结构与控制流约束

### 3.1 定义与作用域

- **控制图**：仅取 `connections[].type == "control"` 的边；DAG、循环体和分支汇合判定主要基于此图。
- **数据依赖图**：其余强类型连线组成的图；不得用反向数据线制造反馈环。一般数据边不是“上一轮值”的声明机制，循环状态应通过 Context 显式读写。
- **分支节点**：能够选择不同后续控制路径的节点，不按实际已连边数判定。当前包括 `router`、`json_tool`；今后新增同类节点同样适用。一个数据输出供多个消费者读取不是控制分支。
- **结构化循环**：`foreach` 是唯一特例，其 `loop-out`／`loop-in` 表示有限遍历，`control-out` 表示遍历结束，不是任意 goto 或通用分支。
- **图边界**：一次子 Workflow 调用对父图是单入单出的黑盒节点；子图必须独立满足本规范，禁止因“被封装”就放宽其内部限制。

### 3.2 DAG 与边界规则

1. 每个 Workflow 必须且只能有一个 Input，至少一个 Output；允许多个**不同 ID** 的 Output 作为互斥分支的独立终点。
2. 每个可执行节点必须从 Input 控制可达；每条正常路径最终到达某个 Output。运行失败可以终止 invocation，但不得把未连接的必要端口当作正常终点。
3. 每个控制输出最多一个后继，每个数据输入最多一个来源；端点和端口类型必须匹配。除合法 `foreach` 的入环结构外，不应通过多个控制前驱复用同一节点。
4. 识别并移除合法 `foreach` 的循环体末端 → 本 foreach.`loop-in` 回边后，控制图必须无环；只有正确闭合的结构化循环可获豁免，不能把所有指向 `loop-in` 的边盲目排除。
5. Workflow 同步依赖图也必须为 DAG：禁止 `A → A`、`A → B → A` 及更长的递归链。发布事件触发 A 的下一次执行不属于同步依赖边。
6. 数据生产者必须在消费者读取前执行；循环内每轮所需值必须本轮产生或显式读取。禁止用反向数据连线、旧槽位、未运行分支的输出代替状态管理。

### 3.3 分支禁止汇合

对每个分支节点，其不同出口的**所有后续控制可达集合必须互不相交**，判定包括 Output 节点，且不限于直接后继。分析时应先将合法 foreach 收缩为单个结构单元，避免把循环自身误判为分支汇合。

以下全部禁止：

```text
Router ── A ──┐                    Router ── A ── X ──┐
              ├── Common                              ├── SameOutput
       ── B ──┘                           ── B ── Y ──┘
```

以下合法：

```text
Input → Router ┬─ case-a → WorkA → OutputA
               ├─ case-b → WorkB → OutputB
               └─ others → Fallback → OutputOther
```

- `OutputA`、`OutputB`、`OutputOther` 是不同节点，但都遵循同一个 Workflow 根级输出接口。
- 两个分支指向**同一个** `workflow` 调用节点，也属于禁止的汇合。
- 不同分支使用不同调用节点引用同一依赖 Workflow 属于实现复用，不等于同图汇合；但分支后有统一续接时，优先按第 5 节封装整个条件单元。
- Router 的普通分支和保留兜底 `branch$others` 均须连接；缺失路由输入属于错误，不是命中兜底。
- 数据从共同前驱向多个分支扇出可以保留；不得把互斥分支的输出接到共同消费者，变相引入 merge／phi 语义。

## 4. Foreach 设计规范

### 4.1 唯一允许的循环形态

```text
Before → foreach.control-in
           │ loop-out → Body1 → Body2 → foreach.loop-in
           │ item-out ───────→ 本轮所需的数据输入
           └ control-out → After → Output
```

- `list-in` 必须是 `arguments.item_type` 对应的列表；当前支持 content、message、event 和局部 Struct 的列表。
- 循环体必须是单入口、无分支、无旁路的控制链，末端唯一返回当前 foreach 的 `loop-in`。
- 禁止循环体跳到外部节点、提前跳到 Output、跳入其他 foreach、接收外部额外控制入口；外部预先产生的数据可以作为只读输入。
- 不修改待遍历列表来追加新一轮任务。当前实现第一次进入时复制列表，逐项取值；遍历完成清除缓存，空列表直接进入 `control-out`。
- 空循环体可表示为本 foreach.`loop-out → loop-in`；它是唯一允许的 foreach 自回边特例，但无处理意义时建议删去该循环。
- 循环体不得直接放 Router、`json_tool` 等带分支能力的节点；即使 Router 只有兜底，或 json_tool 未连接 `error-out`，也不例外。
- **同图直接嵌套 foreach 不作为支持模式。** 内层 foreach 自带循环／退出两路控制，当前循环体检查也会拒绝；需要嵌套遍历时，把内层循环封装为子 Workflow。

### 4.2 循环中的条件处理

```text
父 Workflow：
Input → foreach ─loop-out→ workflow(ProcessOne) → foreach.loop-in
            └control-out→ Output

ProcessOne：
Input → Router ┬─ A → HandleA → OutputA
               └─ others → HandleOther → OutputOther
```

父图循环体只看到一个无分支调用节点。子图各分支分别返回，不共用 Output，也不在子图内汇合。子调用正常返回后，父节点只沿自身唯一 `control-out` 继续。

### 4.3 累积与状态

需要汇总每项结果时，在循环前初始化 Context，在每轮中按 `context_read → ProcessOne → list_append → context_write` 顺序更新，循环结束后再读取结果。`foreach` 本身只输出当前元素，不自动收集子调用的输出列表。

Context ID 不是跨调用共享内存句柄：Context 受 invocation 所有权校验，父子图具有不同 invocation。把本轮值作为子图输入、将返回值在父图写回；不得把父图 Context ID 传给子图企图直接读写父图状态。

## 5. 子 Workflow 与依赖规范

### 5.1 公共后续处理的正确封装

把“选择路径并产出统一结果”封装成完整子 Workflow，而不是在原图中硬接 join：

```text
父图：Input → workflow(ChooseResult) → Common → Output

ChooseResult：
Input → Router ┬─ A → WorkA → OutputA(result)
               └─ others → WorkB → OutputB(result)
```

这里的“统一”发生在**调用返回接口**，不是子图中的控制连线汇合。每次调用只执行一条分支、返回一次；它不表示等待多个分支完成的并行聚合。

### 5.2 依赖声明与接口

1. 先新建并保存子 Workflow 为 Workspace 文件，定义稳定、尽量小的 `input_ports`／`output_ports`，记录唯一的精确文件名。
2. 在父图 `workflow_nodes` 中声明依赖名及输入输出接口快照；供当前运行时解析的依赖名使用目标 Workspace 文件名。
3. 在父图放置 `type: "workflow"` 节点，用 `arguments.workflow_name` 指向依赖，并保存同样的 `input_ports`／`output_ports`。
4. 数据端口使用 `workflow:<name>`，控制端口仍为 `control-in`／`control-out`。
5. 所有子图正常分支必须返回父图后续所需的同名、同类型输出；当前运行时会略过未提供或为 `None` 的 Output 值，不会自动补齐缺失字段。
6. 接口改变后同步刷新依赖快照和所有调用节点；运行时按数组内容比较实际接口与节点快照，名称、类型或顺序不一致都会失败。
7. 最后核验时，当前工作区已将子调用改为 `_read_workspace_workflow_by_name`：在当前 generation 中按 Workspace **精确文件名**加载唯一文件，不按 JSON 内部 `name` 搜索，也不直接按 `workflow_file_id` 调用。同名文件超过一个、未找到或内容不是有效 Workflow JSON 都会失败。已有管理端记录不等于已有可调用的 Workspace 文件；文件改名必须更新依赖名和调用节点。旧 `_read_workflow` 仍存在于源码，不能据此推断 worker／子调用仍从管理库加载。
8. `struct:<id>`／`list-struct:<id>` 只在当前图内部有效；跨 Workflow 必须先转 JSON `content`，接收端再 `json_to_struct` 校验恢复。

下面是父图的**局部 JSON 片段**，不是可直接运行的完整 Workflow；应合并到包含 Input、Output 和正确连线的 2.0 定义中：

```json
{
  "workflow_nodes": [
    {
      "name": "ChooseResult.json",
      "input_ports": [{"name": "query", "type": "content"}],
      "output_ports": [{"name": "result", "type": "content"}]
    }
  ],
  "nodes": [
    {
      "id": "choose-result",
      "type": "workflow",
      "arguments": {"workflow_name": "ChooseResult.json"},
      "input_ports": [{"name": "query", "type": "content"}],
      "output_ports": [{"name": "result", "type": "content"}]
    }
  ]
}
```
## 6. 事件循环与 workflow_queue

### 6.1 跨轮循环而不是图内回跳

每一轮都是独立 invocation，有新的执行图、端口槽位、Context 和调用栈：

```text
workflow_queue → Worker → Workflow 第 N 轮
                           ├─ 完成 → OutputDone
                           └─ 继续 → 保存续跑状态 → construct_event
                                    → publish_event → OutputScheduled
                                                     │
                下一次独立调度 ← workflow_queue ←─────┘
```

图中回到队列的是**事件投递关系**，不是 `connections` 中的控制边。`publish_event` 只负责投递，随后继续当前图；它不等待下一轮完成，也不把下一轮结果同步返回当前调用方。

可采用两种入口：

- **显式调度**：发布 `event_type: "workflow"`，payload 指定 `workflow_file_id` 或 `workflow_name`（当前工作区按精确 Workspace 文件名解释），其余字段对应目标 Input 端口。
- **业务事件**：发布例如 `job.continue`，由启用的事件绑定转换成 `workflow` 事件；绑定覆盖目标并保留原事件为 `origin`。没有启用绑定的业务事件只记录历史，不会运行 Workflow。

下面是可投递的 **Event 信封示例**；ID、轮数和上限都是示意业务值，不是引擎默认值。目标 Workflow 需声明 `state: content` 输入，并自行解析和检查其中的状态：

```json
{
  "version": "1.1",
  "event_type": "workflow",
  "payload": {
    "workflow_file_id": "replace-with-real-workspace-file-id",
    "state": "{\"job_id\":\"job-example\",\"iteration\":2,\"max_iterations\":10,\"idempotency_key\":\"job-example:2\"}"
  }
}
```

同时提供两个目标字段时当前 worker 优先使用 `workflow_file_id`，读取失败不回退到名称；新设计应只选定一种目标。`origin` 若作为公开输入，其类型必须为 `event`。

### 6.2 续跑状态和退出策略

以下是业务设计要求，不是现有队列自动提供的能力：

1. 明确继续条件、完成条件、最大轮数／重试次数及总时间或成本预算；达到任一终止条件必须停止发布下一轮。
2. 下一轮事件必须携带可恢复的状态值或持久化状态引用。优先使用已有 Session 或业务存储；Session 支持的类型按现有契约，Struct 状态需先转 JSON content。
3. 禁止跨 invocation 传递 Context ID 作为续跑状态。Context 在 invocation 结束时清理，并受所有权约束。
4. 需要幂等的副作用必须使用稳定业务键；建议携带业务关联 ID、轮次和幂等键。字段放入明确的 Input／序列化状态中，**引擎不会因为字段叫 `idempotency_key` 就自动去重**。
5. 禁止失败即无上限重投，避免事件风暴；有延迟重试或退避需求时必须提供调度机制，当前 Redis List 入口不解释 `delay` 或 `not_before` 字段。
6. 检查 `response`／`error` 绑定是否会意外触发自身。当前根调用成功均产生 `response`，包括“已调度下一轮”的调用；这些事件也经过绑定查询。
7. 保存状态与发布事件不是原子事务。涉及不可重复副作用或可靠续跑时，应设计幂等恢复、持久化待发记录／outbox 等机制；不得声称当前队列保证 exactly-once 或崩溃自动恢复。

### 6.3 同步子调用与事件调度的选择

| 需求 | 选用机制 | 状态与返回 |
| --- | --- | --- |
| 当前步骤需要条件处理后的结果 | 子 Workflow | 同步返回接口值，父图继续 |
| foreach 内部需要 Router／错误分支／内层遍历 | 子 Workflow | 每轮调用一次，子图独立终止 |
| 反复思考、阶段续跑、业务重试 | 事件 + workflow_queue | 新 invocation，显式传递持久化状态 |
| 等待长时间外部任务 | 专用回调消费者 + 下一轮事件 | 回调转为标准 workflow 事件，不阻塞当前图 |

长任务不得靠普通控制环轮询。主 worker 不将原始异步回调当成 `workflow` 执行请求；应使用专用回调队列和消费者，转换为明确的业务事件或标准 `workflow` 事件后再入队。

## 7. 运行边界与可观测性

- **超时不是合法循环的替代证明。** 当前 `WORKFLOW_TIMEOUT_SECONDS = 180`，在节点之间检查，不是对正在阻塞的 handler 做硬中断，也不是跨事件轮次的全局预算。同步子调用有自己的计时，业务仍需控制总预算。
- **数据没有 join 语义。** 数据输出深拷贝到目标槽位，后续覆盖前可能保留；多路数据到达不等于控制执行屏障，也不证明本轮生产者执行成功。
- **输出完整性由设计保证。** 每条成功路径都应返回其消费者需要的字段；分支或 foreach 子调用不得依赖未覆盖槽位中的上一轮结果。
- **持久化与临时状态区分。** Context 服务于一次 invocation，Session 服务于显式跨调用状态；并发读改写 Session 不应被假定为原子业务事务。
- **关联记录显式设计。** 当前运行记录已有 invocation、调用栈、输入输出、节点轨迹和错误；跨事件的业务关联 ID 应作为设计输入保留，不能假定 worker 自动传播。
- **交付不改变协议版本。** 本文是设计草案，未修改 `schema_version`。正式收紧兼容行为时需按仓库版本管理流程评估协议、旧图迁移和测试变更，而非悄悄改变 2.0 的接收范围。

## 8. 实现差距与校验落地

### 8.1 当前事实与目标约束

| 主题 | 当前仓库事实 | 本规范目标／待办 |
| --- | --- | --- |
| 普通控制环 | 协议 2.0 第 10.1 节允许有向环；现有校验器无通用 DAG 检查 | 禁止除结构化 foreach 外的一切控制环 |
| 分支汇合 | 协议允许 control 输入多个来源；解析器保存多个 predecessor，不实现 join 屏障 | 拒绝分支立即或间接汇合，包含共享 Output |
| 循环体分支 | `_validate_branches_in_foreach` 检查实际控制出边数大于 1 | 改为按节点分支能力拒绝；单出口 Router／未连接 error-out 的 json_tool 也禁止 |
| 循环结构 | 已检查循环体外部控制入口；未完整证明闭合、出口隔离与全图可终止性 | 增加循环体完整结构和全图可达性检查 |
| 同步递归 | 运行时按 `_workflow_call_stack` 拒绝调用链名称重复；管理端拒绝声明自身依赖 | 保存／发布时还应检查可解析的完整依赖图，包括间接递归 |
| 依赖快照 | 运行时比较调用节点快照与真实子 Workflow 接口 | 声明、调用节点、真实依赖三者一致；发布前尽早发现接口漂移 |
| 目标解析 | 最后核验时 worker 和子调用的按名加载已转向 Workspace 精确文件名；旧协议文档仍描述管理库名称 | 同步接口说明、编辑器依赖选择和管理端契约，防止内部 name 与文件名混用 |
| 队列名称 | `MAIN_AGENT_QUEUE_NAME`，默认 `main_agent_queue` | workflow_queue 先作为逻辑名称使用，不宣称已有独立队列 |
| 队列可靠性 | 常规投递 `LPUSH`、消费 `BRPOP`；当前无确认、自动重试或去重协议 | 按业务需要补充持久化恢复、幂等、预算和重试调度 |

README 中“控制流可以成环”的说明、`docs/protocol/workflow_2_0.md` 第 10 节及使用旧拓扑的测试夹具，正式落地时需要一并调整。本次只增加设计文档，不擅自修改运行时代码、历史协议或已有 Workflow。

### 8.2 建议的静态校验顺序

1. **基础契约**：保留现有 Schema、节点类型、端口类型、连接基数及 Input／Output 校验。
2. **结构化 foreach 识别**：沿 `loop-out` 追踪无分支控制链；验证归属于本循环、入口唯一、禁止带分支节点，直到唯一 `loop-in` 回边。遇到非法回边、越界或提前终止立即报错。空循环体单独识别。
3. **无环检查**：仅去掉第 2 步确认的回边，对整个控制图进行拓扑排序或 DFS；不可达区域的非法环也必须拒绝。数据依赖环另行检测，不自动继承控制回边豁免。
4. **可达性与出口检查**：所有可执行节点从 Input 可达；收缩合法 foreach 后，每条路径到达某个 Output，不允许无出口分量。
5. **分支不汇合检查**：在收缩图中，计算每个分支出口的后继可达集合，两两交集必须为空；输出具体分支、首个共同节点及相关边。仅检查直接后继或节点入度不足以提供完整诊断。
6. **依赖一致性**：检查依赖声明和调用节点快照；在能加载真实依赖的保存／发布边界验证接口及依赖 DAG，运行时保留递归和快照防线。建议统一使用稳定文件身份检查依赖环；当前 file_id 入口的调用栈根使用 JSON 内部 name、子调用使用文件名，不能把混合字符串标识当作静态无递归证明。
7. **路径数据检查**：所有读取在对应路径上都有生产者；重点验证每个 Output 的约定必返字段，以及循环体中每轮都需要更新的数据。

编辑器用于即时反馈，管理端保存和 Agent 执行前用于权威检查，三处必须保持相同接受规则。Agent 与管理端目前分别维护 `workflow_validator.py`、`workflow_contract.py` 等文件，落地时必须同步或抽取共享实现，不能只禁用画布连线。

建议错误码（**尚未实现**）：`WF_CONTROL_CYCLE`、`WF_FOREACH_BRANCH_NODE`、`WF_FOREACH_BOUNDARY`、`WF_BRANCH_RECONVERGENCE`、`WF_DEPENDENCY_CYCLE`、`WF_INTERFACE_MISMATCH`、`WF_UNREACHABLE_NODE`。错误信息应包含 Workflow、节点 ID、端口及违规路径，避免只报“非法 DAG”。

## 9. 评审与验收清单

| 场景 | 目标结果 |
| --- | --- |
| Input → 普通节点 → Output | 通过 |
| 普通节点自环／A → B → A／Router 错误后回跳 | 拒绝 |
| 正常 foreach 单链循环／空列表／空循环体 | 通过；分别验证逐项执行、零次执行、无处理结束 |
| foreach 体内 Router，包括只配置兜底的 Router | 拒绝 |
| foreach 体内 json_tool，无论 error-out 是否连接 | 拒绝 |
| foreach 内直接放另一 foreach | 拒绝；改为子 Workflow 封装 |
| foreach 内调用含 Router 的子 Workflow，各分支分别 Output | 通过 |
| foreach 体外闯入／体内提前退出／回到别的循环 | 拒绝 |
| 两分支立即汇合／多步后汇合／共用一个 Output／共用一个调用节点 | 全部拒绝 |
| 两分支终止于不同 Output，遵循同一输出接口 | 通过 |
| 父图调用分支子 Workflow 返回后接 Common | 通过，不视为同图汇合 |
| 同步 Workflow 直接／间接递归 | 拒绝；运行时仍保留防线 |
| 子 Workflow 接口漂移／必返值在某个分支缺失 | 拒绝发布或明确失败，不依赖旧槽位 |
| 事件续跑同一 Workflow | 允许新 invocation；验证轮次上限与完成后不再投递 |
| 重复事件／发送失败／保存后未发送／消费后崩溃 | 验证幂等与恢复方案，不假定队列自动恢复 |
| response/error 绑定再次触发／无绑定业务事件 | 验证不形成无界重投；无绑定事件不应误判为已调度 |
| Context 跨父子图或跨事件使用 | 拒绝共享 ID；改为值传递或 Session |

提交前逐项确认：

- [ ] 去掉合法 foreach 回边后无控制环，数据依赖无反馈环，同步依赖图无递归。
- [ ] foreach 只有单链循环体，没有分支能力节点、直接嵌套、越界入口或旁路出口。
- [ ] 每组互斥分支的下游集合不相交，Output 不共用；公共后续通过子 Workflow 调用返回实现。
- [ ] 依赖声明和调用快照一致，子图已保存为可按精确文件名加载的 Workspace 文件，接口漂移已处理。
- [ ] 所需输入按路径先生产后消费，所有正常输出路径均返回消费者需要的字段。
- [ ] 事件续跑状态持久化、退出预算、幂等与失败恢复都有明确责任方。
- [ ] 编辑器、保存端、执行端验证规则一致；旧图迁移与既有夹具已纳入版本计划。

## 10. 源码阅读索引

- `agent/task_worker.py::handle_task`：事件绑定路由、目标选择、Input 注入、根调用 response。
- `agent/queue_client.py`：队列命名、Event 版本补齐、Redis 入队出队。
- `agent/workflow_parser.py::parse_workflow`：JSON 到执行图的编译、Router/foreach 端口映射。
- `agent/workflow_contract.py::control_ports_for_node`：控制端口与分支能力的当前来源。
- `agent/workflow_validator.py::validate_workflow`、`_validate_branches_in_foreach`：现有结构校验与循环体检查边界。
- `agent/workflow_nodes.py::run_workflow_map`、`workflow_foreach`、`workflow_workflow`、`workflow_publish_event`：同步执行、有限遍历、子调用与事件投递。
- `agent/workflow_context_repository.py`、`agent/workflow_session_repository.py`：状态作用域和持久化边界。
- `manager_webui/workflows.py`、`manager_webui/workflow_validator.py`：管理端保存、依赖元数据与服务端校验。
- `docs/protocol/workflow_2_0.md`、`docs/protocol/event_1_1.md`：现有协议文档；普通环、汇合及按名加载来源的描述与本草案／最终工作区源码存在明确差异。
- `agent/test_tool_nodes.py::ForeachBranchValidationTest`、`agent/test_workflow_node.py`、`agent/test_task_worker.py`：现有行为测试入口；不能把现有测试通过当作新约束已实现。

## 11. 本次核验记录

- 阅读范围覆盖事件入口、队列、编译器、节点执行器、Context／Session、管理端与现有协议。
- 运行 `test_workflow_node`、`test_tool_nodes`、`test_task_worker`、`test_workspace_workflow`，共 **141 项既有单元测试通过**。测试期间额外 mock 运行日志持久化，不依赖真实运行记录数据库；这不是端到端队列测试。
- 使用只在内存构造的最小图核实：当前完整校验器仍接受普通控制环、两个 Router 分支共享 Output；当前 foreach 检查仍接受只连接成功出口的 json_tool。这些均是本规范要求收紧的缺口，不是认可该设计。
- 写作期间工作区出现了按 Workspace 文件名加载的并行代码改动；本文已按最终读取到的实现修正，并保留这些改动。本任务仅写入本文，没有改动校验器、执行器或协议版本，也未把目标约束冒充已实现能力。

