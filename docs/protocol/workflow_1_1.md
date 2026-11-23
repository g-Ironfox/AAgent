# Workflow 1.1 协议规范

> 类型:设计文档。
> 性质:现行文档。
> 归属:`agent_runtime/` + `workflow_editor/` + `manager_webui/`。
> 适用版本:平台 `4.0.6+`。
> 协议版本:workflow 1.1。

本文定义 Workflow 定义的持久化 JSON 契约。版本以仓库根 `version.json.protocol.workflow` 为准。Workflow 不是[Event 1.1](event_1_1.md) 信封；它由编辑器/管理页保存到 MongoDB `workflows`，由 Agent 读取、校验和执行。

## 1. 顶层结构

以下示例把 `content` 从入口透传到出口：

```json
{
  "schema_version": "1.1",
  "name": "echo",
  "input_ports": [{"name": "content", "type": "content"}],
  "output_ports": [{"name": "content", "type": "content"}],
  "nodes": [
    {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:content", "name": "content", "type": "content"}]},
    {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:content", "name": "content", "type": "content"}]}
  ],
  "connections": [
    {"fromId": "input", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
    {"fromId": "input", "fromPortId": "workflow:content", "toId": "output", "toPortId": "workflow:content", "type": "content"}
  ]
}
```

下面是一个多节点示例：将输入的 `question` 加上固定提示词，构造用户消息，组成消息列表交给模型，再把回复写入 `answer` 输出端口：

```json
{
  "schema_version": "1.1",
  "name": "answer_question",
  "input_ports": [{"name": "question", "type": "content"}],
  "output_ports": [{"name": "answer", "type": "content"}],
  "nodes": [
    {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:question", "name": "question", "type": "content"}]},
    {"id": "prompt", "type": "construct_content", "dataInputPorts": ["question"], "arguments": {"append_items": [{"type": "fixed", "value": "请简要回答："}, {"type": "port", "port_id": "question"}]}},
    {"id": "message", "type": "construct_message", "arguments": {"role": "user"}},
    {"id": "messages", "type": "construct_list", "dataInputPorts": ["message-in-0"], "arguments": {"item_type": "message", "initial_value_count": 1}},
    {"id": "model", "type": "llm", "arguments": {"model": "", "think": false, "tool_calls": false, "tools": []}},
    {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:answer", "name": "answer", "type": "content"}]}
  ],
  "connections": [
    {"fromId": "input", "fromPortId": "control-out", "toId": "prompt", "toPortId": "control-in", "type": "control"},
    {"fromId": "prompt", "fromPortId": "control-out", "toId": "message", "toPortId": "control-in", "type": "control"},
    {"fromId": "message", "fromPortId": "control-out", "toId": "messages", "toPortId": "control-in", "type": "control"},
    {"fromId": "messages", "fromPortId": "control-out", "toId": "model", "toPortId": "control-in", "type": "control"},
    {"fromId": "model", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
    {"fromId": "input", "fromPortId": "workflow:question", "toId": "prompt", "toPortId": "question", "type": "content"},
    {"fromId": "prompt", "fromPortId": "content-out", "toId": "message", "toPortId": "content-in", "type": "content"},
    {"fromId": "message", "fromPortId": "message-out", "toId": "messages", "toPortId": "message-in-0", "type": "message"},
    {"fromId": "messages", "fromPortId": "list-out", "toId": "model", "toPortId": "messages-in", "type": "list-message"},
    {"fromId": "model", "fromPortId": "output", "toId": "output", "toPortId": "workflow:answer", "type": "content"}
  ]
}
```

| 字段 | 类型 | 约束 |
|---|---|---|
| `schema_version` | 字符串 | 协议版本，必填，当前只能是 `"1.1"`；缺失或不匹配直接拒绝 |
| `name` | 字符串 | Workflow 名称；要求保留所有空格(空格敏感) ; 接受非null空白名称 |
| `input_ports` / `output_ports` | 数组 | 每项至少含非空 `name` 和受支持的 `type`；名称在各自列表内不重复 |
| `nodes` | 数组 | 恰好一个 `input`、至少一个 `output`；节点 `id` 不重复，`type` 必须受支持 |
| `connections` | 数组 | `fromId`、`fromPortId`、`toId`、`toPortId` 指定端点，`type` 为 `control` 或对应数据类型 |
| `workflow_nodes` | 数组，可选 | 本 Workflow 调用的子 Workflow 声明；每项包含 `name`、`input_ports`、`output_ports`，调用节点须与声明的接口匹配 |
| `remote_tools` | 数组，可选 | 远程 Tool 的名称与输入/输出端口声明；远程 Tool 节点须匹配声明 |

管理页还保存描述、引用和时间等元数据；MongoDB `_id` 是存储标识，不属于连线或节点字段。协议版本由顶层 `schema_version` 表达，不再有单独的整数版本字段。可执行性的依据是 `agent_runtime/workflow_validator.py` 中的 `validate_workflow`，管理页保存时另有大小、数量和引用限制。不能只检查 JSON 能否解析就认为 Workflow 有效。

## 2. 元数据

Workflow 定义的顶层元数据包括 `name`、`schema_version`、`input_ports`、`output_ports`、`workflow_nodes` 和 `remote_tools`。`name` 是 Workflow 名称；`input_ports` / `output_ports` 声明边界接口；`workflow_nodes` 声明本 Workflow 依赖并调用的子 Workflow 及其接口；`remote_tools` 声明本 Workflow 使用的远程 Tool 及其接口。后两者可省略，省略时按空数组处理。

`workflow_nodes` 的每项包含 `name`、`input_ports`、`output_ports`；`name` 标识被调用的 Workflow，端口列表描述其可调用接口，Workflow 节点引用和端口必须与声明匹配。`remote_tools` 的每项恰含 `name`、`input_ports`、`output_ports`；远程 Tool 节点通过 `arguments.tool` 引用声明，输入参数以及同步 Tool 的输出声明必须与对应端口列表一致。`name` 是 Workflow 名称，平台要求不可重名（包含空格）。

## 3. 节点与连线

节点的基本字段是 `id`、`type`、`name`、`x`、`y` 和 `arguments`；可选的公共顶层字段包括 `workflowPorts`、`dataInputPorts`、`input_ports`、`output_ports`。节点类型相关的可配置参数必须放在 `arguments` 中，不能放到节点顶层；公共字段不能放进 `arguments`。`input` / `output` 节点的 `workflowPorts` 必须与顶层边界端口声明一致，ID 形如 `workflow:<name>`。

数据连接类型包括 `content`、`message`、`event`、`list-content`、`list-message`、`list-event`、`map-content`；控制连接使用 `control`。端点必须存在且类型匹配；同一数据输入只允许一个来源，控制端口按节点规则连接。当前支持的节点类型、每类 `arguments` 和端口规则以 `agent_runtime/workflow_contract.py` 为准；具体校验以 `agent_runtime/workflow_validator.py` 为准。不能把编辑器的视觉坐标或运行时编译后的索引连接当作持久化协议的替代格式。

### 支持的类型与强类型约束

Workflow 是**端口与连线强类型**的：数据连接的 `type` 必须是源端口和目标端口声明的同一种类型，不能把 `content` 直接连接到 `message` 或 `list-content`。需要转换时应通过相应节点（例如 `construct_message`、`construct_list`、`deserialize_json`）。`control` 只连接控制端口，不承载数据。所有支持的连接类型如下：

| 类型 | 数据含义 |
|---|---|
| `control` | 控制流，不是数据值 |
| `content` | 文本内容（字符串） |
| `message` | 消息对象，包含 `role`（`system` / `user` / `assistant` / `tool`）和字符串 `content` |
| `event` | 事件对象，包含非空字符串 `event_type` 和 `payload` |
| `list-content` | `content` 的列表 |
| `list-message` | `message` 的列表 |
| `list-event` | `event` 的列表 |
| `map-content` | 字符串键到字符串内容的映射 |

节点 `type` 支持下列全部取值；节点的具体端口和 `arguments` 随类型而异：

| 类别 | 节点类型 | 用途 |
|---|---|---|
| 边界 | `input`、`output` | Workflow 输入和输出 |
| 控制 | `router`、`foreach` | 分支、遍历列表 |
| 构造与读取 | `construct_content`、`construct_message`、`construct_map_content`、`map_content_get`、`split_event`、`deserialize_json`、`construct_list`、`list_append` | 构造、拆分或转换数据 |
| 能力调用 | `history`、`llm`、`local_tool`、`remote_sync_tool`、`remote_async_tool` | 读取历史、调用模型或工具 |
| 状态 | `context_create`、`context_read`、`context_write`、`session_create`、`session_read`、`session_write` | 操作 Context 或 Session |
| 组合 | `workflow` | 调用另一 Workflow |

这里的强类型指**定义阶段的端口/连线约束**：校验器检查已声明端口的连接类型，编辑器也按端口类型连接。它不等于对所有运行时值做统一的全局类型检查；例如缺失的输入可能为 `None`，具体节点（如 `llm`、`deserialize_json`）在执行时还会校验自己的输入值。自定义或未声明的数据输入端口也不能仅凭连线 `type` 推断出运行时值一定符合表中的形状。

### Python 值与外部输入

端口类型是 Workflow 定义中的字符串标记；传输的值在 Agent 中使用普通 Python 对象，不包装成 `{ "type": ..., "value": ... }`。各类型对应的值如下（`payload` 的内容依具体事件而定）：

| 端口类型 | Python 值 | 外部 JSON 值示例 |
|---|---|---|
| `content` | `str` | `"你好"` |
| `message` | `dict[str, str]`，含 `role` 和 `content` | `{"role":"user","content":"你好"}` |
| `event` | `dict`，含非空字符串 `event_type` 和 `payload` | `{"event_type":"response","payload":{"content":"你好"}}` |
| `list-content` | `list[str]` | `["甲","乙"]` |
| `list-message` | `list[dict]`，每项为 `message` | `[{"role":"user","content":"你好"}]` |
| `list-event` | `list[dict]`，每项为 `event` | `[{"event_type":"response","payload":{}}]` |
| `map-content` | `dict[str, str]` | `{"title":"标题","body":"正文"}` |

`control` 不传递 Python 数据值；编译后控制边仅以节点的整数索引表示。JSON 对象和数组进入 Python 后分别成为 `dict` 和 `list`。以上是端口预期的值形状，不表示所有入口都已做运行时类型检查。

顶层 Workflow 由 Agent 处理 `event_type: "workflow"` 的 Event 时，先按 `payload.workflow_name` 读取并校验定义，再按 Input 端口名称从 Event `payload` 取同名字段。例如上面的 `answer_question` 可接收：

```json
{"event_type":"workflow","payload":{"workflow_name":"answer_question","question":"什么是强类型端口？"}}
```

此时 `question` 的 JSON 字符串成为 Python `str`，写入 Input 节点对应连接目标的 `data_inputs["question"][2]`；未提供的端口值取 `None`。`workflow_name` 用于选择定义，不会自动传入 Workflow；仅在显式声明同名 Input 端口时才按普通字段传入。子 Workflow 则从父节点同名端口传值，不经 Event 队列。

`validate_workflow` 校验的是**定义**（端口声明、连接类型、节点参数等），不是 Event `payload` 的实际值。入口的 `payload.get(...)` 和数据传播不统一验证 `str` / `dict` / `list` 的形状；部分节点在消费时自行检查（如 `llm` 的 `list-message`、`split_event` 的 `event`、`deserialize_json` 的声明输出），Context/Session 存取也校验对应 `value_type`。因此外部调用方应按上表提供值，不能把“定义通过校验”理解为“外部输入已通过类型校验”。

## 4. 解析后的 `workflow_map`

Agent 的 `parse_workflow` 把持久化定义编译成 `workflow_map`（按原始 `nodes` 顺序排列的节点对象列表），供执行器按整数索引访问。以上面的 `echo` 为例，解析后、执行前的结构为：

```json
[
  {
    "id": "input", "type": "input",
    "workflowPorts": [{"id": "workflow:content", "name": "content", "type": "content"}],
    "predecessors": {}, "successors": {"next": 1},
    "data_inputs": {},
    "data_outputs": {"workflow:content": [[1, "workflow:content"]]}
  },
  {
    "id": "output", "type": "output",
    "workflowPorts": [{"id": "workflow:content", "name": "content", "type": "content"}],
    "predecessors": {"last": [0]}, "successors": {},
    "data_inputs": {"workflow:content": [0, "workflow:content", null]},
    "data_outputs": {}
  }
]
```

每个解析节点保留原节点的 `id`、`type` 及已有的 `name`、`arguments`、`workflowPorts`、`dataInputPorts`、`input_ports`、`output_ports`；`x`、`y` 被移除，顶层 `name`、`connections` 等不进入列表。`input` / `output` 的 `workflowPorts` 从顶层边界端口重新生成。新增的字段含义如下：

| 字段 | 解析后格式 | 含义 |
|---|---|---|
| `predecessors` | `{键: [来源节点索引, ...]}` | 普通控制输入键为 `last`；`foreach` 的 `loop-in` 键为 `continue` |
| `successors` | `{键: 目标节点索引}` | 普通控制输出键为 `next`；`router` 的分支键为 `branch-<分支名称>`，`foreach` 的 `loop-out` 键为 `item` |
| `data_inputs` | `{端口ID: [来源节点索引, 来源端口ID, 当前值]}` | 未连接时为 `[null, null, null]`；已连接但尚未写入时当前值为 `null` |
| `data_outputs` | `{端口ID: [[目标节点索引, 目标端口ID], ...]}` | 一个输出端口可连接多个目标；未连接的端口对应空列表 |

执行时数据输出会写入目标 `data_inputs` 的第三项；执行器还可能向节点暂存以 `_` 开头的状态字段。因此 `workflow_map` 是可变的 Agent 内部结构，不应保存回 MongoDB，也不属于 Workflow 1.1 的持久化 JSON 契约。解析器会过滤无效端点连接；必须先调用 `validate_workflow` 校验原始定义，不能用解析成功代替校验。

## 4. 与 Event 的关系和版本

Agent 从 Event `payload` 中按 Input 端口名称取同名字段，未提供的字段传为 `None`；`workflow_id` 只有在显式声明同名 Input 端口时才成为 Workflow 输入。Workflow 内部 `event` 数据类型可以承载 `event_type` 与 `payload`，不另设协议版本。Workflow 的 Tool 节点直接调用本地执行器或 Tool Server，不由主 Event 队列派发。

Workflow 版本采用独立的 `MAJOR.MINOR`；顶层 `schema_version` 是 1.1 新增的必填字段，值为 `"1.1"`，1.0 顶层没有该字段。**版本值硬编码在各消费方的源码常量中**（Agent 解析器、Agent 校验器、管理页、编辑器各自声明 `1.1`），不运行时读取 `version.json`——这样改协议时必须显式改代码，不会漏掉。

消费边界的版本检查已落地：Agent 的 `parse_workflow` 与 `validate_workflow` 在入口比对 `schema_version`，管理页保存时校验，编辑器载入/导入时校验；缺失或不匹配一律拒绝，不做兼容与数据迁移。

修改节点/端口契约时，需同批核对编辑器、管理页和 Agent 的解析与校验，并同步提升这里写死的常量；版本清单、文档元信息和标签正文在发布时对齐

## 5. JSON Schema

Draft 2020-12 Schema 描述 Workflow 1.1 的持久化 JSON 外形，可用于编辑器、API 客户端和工具的基础结构校验，详见 [workflow_1_1.schema.json](workflow_1_1.schema.json)。节点 `arguments` 保持为对象，由 `type` 决定具体字段；节点参数、动态端口、边界节点数量、端点存在性及连线类型匹配等语义规则仍以 `agent_runtime/workflow_validator.py` 为准，JSON Schema 校验通过不代表 Workflow 可执行。

顶层允许管理页附加描述、引用、时间及存储元数据；这些元数据不改变 Workflow 定义本身。Schema 中 `workflowPorts` 用于边界节点的持久化端口快照，`input_ports` / `output_ports` 在不同节点类型上的语义仍由节点契约解释。