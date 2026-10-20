# Workflow 1.6 协议规范

> 类型:设计文档。
> 性质:现行文档。
> 归属:`agent/` + `workflow_editor/` + `manager_webui/`。
> 协议版本:workflow 1.6。

## 1. 范围与版本

Workflow 1.6 定义可保存、校验、编译和执行的 Workflow JSON。协议版本由根字段 `schema_version` 表达，值必须严格为字符串 `"1.6"`。Agent、管理端和编辑器均校验该值；缺失或不匹配时拒绝处理，不执行自动转换。

本文件独立完整定义 Workflow 1.6，不引用其他协议文档作为规范来源。随附的 [workflow_1_6.schema.json](workflow_1_6.schema.json) 定义 JSON 结构、字段类型和额外字段限制；本文定义字段语义、节点参数规则及运行时约束。服务端语义校验负责验证节点配置字段、端口关系和执行约束。通过 JSON Schema 校验不代表 Workflow 可执行。

## 2. 根对象

根对象只允许以下字段：

| 字段 | 必需 | 类型 | 语义 |
| --- | --- | --- | --- |
| `schema_version` | 是 | string | 固定为 `"1.6"` |
| `name` | 是 | string | Workflow 名称；管理端要求非空，长度不超过 120 |
| `description` | 否 | string | 描述；管理端最大长度 2000，缺省按空字符串处理 |
| `input_ports` | 是 | port[] | Workflow 输入接口 |
| `output_ports` | 是 | port[] | Workflow 输出接口 |
| `nodes` | 是 | node[] | 节点定义；管理端要求 1 到 200 个 |
| `connections` | 是 | connection[] | 节点连线；管理端最多 1000 条 |
| `workflow_nodes` | 否 | dependency[] | 可调用子 Workflow 的名称与接口快照；缺省为空数组，管理端最多 50 项 |
| `remote_tools` | 否 | dependency[] | 远程工具名称与接口快照；缺省为空数组，管理端最多 100 项 |

未列出的根字段不属于协议。管理端请求模型拒绝额外根字段；Agent 的 JSON Schema 校验不单独限制额外根字段。存储层标识不属于 Workflow JSON 契约。

## 3. 数据类型与接口端口

### 3.1 数据类型

端口和数据连接类型允许以下值：

| 类型 | 含义 |
| --- | --- |
| `content` | 单个文本内容 |
| `message` | `{ "role": "system|user|assistant|tool", "content": string }` |
| `event` | Event 对象；在 Workflow 内按对象传播，不先转为 JSON 字符串 |
| `list-content` | content 列表 |
| `list-message` | Message 列表 |
| `list-event` | Event 列表 |
| `map-content` | 字符串键到字符串值的对象；键必须非空 |

`port` 对象必须恰有 `name`、`type` 两字段。`name` 为非空字符串；接口名按去除首尾空白并忽略大小写的方式检查重复。输入和输出接口数组分别检查重名。

### 3.2 `origin` 输入

`origin` 是 Workflow 输入接口中的保留名称。该端口可选；一旦声明，其类型必须为 `event`。Input 节点对应的输出端口 ID 为 `workflow:origin`。

外部事件通过事件绑定触发 Workflow 时，绑定生成一个新的 `event_type: "workflow"` 事件，并将触发绑定的完整原始 Event 放入该事件的 `payload.origin`。其他 Workflow 输入端口仍按端口名称从内部事件的 `payload` 读取；绑定解析出的 Workflow 名称用于调度。

`payload.origin` 是 Workflow 事件的保留字段，语义是提供 Workflow 的 `origin` 输入值。事件绑定生成的 Workflow 事件会把触发绑定的完整原始 Event 写入该字段；绑定源事件的 payload 若也含有 `origin`，该字段由真实原始 Event 替换。直接发送 `event_type: "workflow"` 的事件也可以提供 `origin`；只要该字段存在，Workflow 就使用它作为 `origin` 输入，否则使用当前完整 Workflow Event。未声明该端口时不要求接收 origin。编辑器新建 Workflow 默认声明 `origin`。

### 3.3 依赖接口

`workflow_nodes` 与 `remote_tools` 的每个元素必须恰有 `name`、`input_ports`、`output_ports`。名称非空，端口数组遵守 3.1 的端口结构及重名规则。每个依赖名称在对应数组中唯一；远程工具名称按去除首尾空白、忽略大小写比较重复。

## 4. 节点对象

节点对象只允许以下顶层字段：

| 字段 | 必需 | 类型 | 说明 |
| --- | --- | --- | --- |
| `id` | 是 | string | 非空，Workflow 内唯一 |
| `type` | 是 | string | 必须是第 5 节列出的类型 |
| `name` | 否 | string | 编辑器显示名称 |
| `x`, `y` | 否 | number | 编辑器画布坐标 |
| `arguments` | 否 | object | 节点配置，字段依节点类型限制 |
| `workflowPorts` | 条件必需 | object[] | Input/Output 边界端口快照 |
| `dataInputPorts` | 否 | string[] | 动态数据输入端口 ID |
| `input_ports`, `output_ports` | 条件必需 | port[] | 可调用 Workflow 节点的接口快照 |

配置必须放在 `arguments` 中，不能放在节点顶层。`workflowPorts`、`dataInputPorts`、`input_ports`、`output_ports` 必须位于顶层。节点顶层字段不支持额外字段。服务端语义校验会拒绝该节点类型不支持的参数字段。

Input 节点必须恰好一个，Output 节点至少一个。Input/Output 的 `workflowPorts` 必须与根接口生成的 `{id: "workflow:<name>", name, type}` 数组一致。`dataInputPorts` 必须是无重复的非空字符串数组；动态端口必须与节点配置完全匹配。

## 5. 节点类型、配置与端口

除特别说明外，执行节点均有 `control-in` 与 `control-out`。Input 只有 `control-out`，Output 只有 `control-in`。数据端口类型必须符合下表及其节点配置。

| `type` | `arguments` | 数据输入 | 数据输出 |
| --- | --- | --- | --- |
| `input` | 无 | 无 | 根 `input_ports` 中的 `workflow:<name>` |
| `output` | 无 | 根 `output_ports` 中的 `workflow:<name>` | 无 |
| `router` | `branches`: 非空数组，每项含唯一非空 `id`、唯一非空 `name` | `content-in: content` | 每个 branch ID 是一个 control 输出；可选一个名称为 `其它` 的兜底分支 |
| `construct_message` | `role`、`role_source`，均可选 | `content-in: content`；`role_source="port"` 时另有 `role-in: content` | `message-out: message` |
| `construct_content` | `append_items` | port 项引用的 content 输入 | `content-out: content` |
| `construct_map_content` | `mappings`: 非空 `{key,value}` 数组，key 非空且唯一，value 为 string | 无 | `map-out: map-content` |
| `map_content_get` | 无 | `map-in: map-content`, `key-in: content` | `content-out: content` |
| `split_event` | 无 | `event-in: event` | `type-out: content`, `payload-out: content` |
| `construct_event` | `event_type`: 非空 string | `payload-in: content`，内容为 JSON object 字符串 | `event-out: event` |
| `publish_event` | 无 | `event-in: event` | 无 |
| `deserialize_json` | `outputs`: 非空 `{key,type}` 数组，key 唯一非空 | `content-in: content`，内容为 JSON object 字符串 | 每个 key 对应声明的类型 |
| `construct_list` | `item_type`: `content`/`message`/`event`；`initial_value_count`: 0–20 整数 | `dataInputPorts` 必须恰为 `<item_type>-in-0` 到 `<item_type>-in-(count-1)` | `list-out: list-<item_type>` |
| `list_append` | `item_type`: `content`/`message`/`event`；`position`: `start`/`end` | `list-in: list-<item_type>`, `item-in: <item_type>` | `list-out: list-<item_type>` |
| `foreach` | `item_type`: `content`/`message`/`event` | `list-in: list-<item_type>`；control `loop-in` | `item-out: <item_type>`；control `loop-out` |
| `history` | `event_types`: 不重复且仅含 `terminal`/`response`；`limit`: 1–1000 整数 | 无 | `events: list-event` |
| `llm` | `model`、`think`、`tool_calls`、`tools` | `messages-in: list-message` | `output: content`；按配置可有 `reasoning: content`、`tool_calls: list-content` |
| `local_tool` | `tool`: 非空 string；`parameters`: 无重复的非空 string 数组 | 每个 parameter 名称一个 content 输入 | `output: content` |
| `remote_sync_tool` | `tool`、`parameters: {name,type}[]`、`outputs: {name,type}[]`、可选 `timeout_ms` | 每个 parameter 名称及类型 | 每个 output 名称及类型 |
| `remote_async_tool` | `tool`、`parameters: {name,type}[]`、可选 `timeout_ms`、可选 `callback` | 每个 parameter 名称及类型 | `task_id: content` |
| `context_create` | `value_type`: 支持的数据类型；可选 `context_id`: 去除首尾空白后非空的字符串 | `initial-value: value_type` | `context-id: content` |
| `context_read` | `value_type`、`context_id_source`、`context_id` | `port` 模式有 `context-id: content`；`fixed` 模式无 ID 输入端口 | `value-out: value_type` |
| `context_write` | `value_type`、`context_id_source`、`context_id` | `port` 模式有 `context-id: content`；另有 `value-in: value_type` | `context-id: content`, `value-out: value_type` |
| `session_create` | `value_type`: 支持的数据类型 | `initial-value: value_type` | `session-id: content` |
| `session_read` | `value_type`: 支持的数据类型 | `session-id: content` | `value-out: value_type` |
| `session_write` | `value_type`: 支持的数据类型 | `session-id: content`, `value-in: value_type` | `session-id: content`, `value-out: value_type` |
| `workflow` | `workflow_name`: 非空 string | `input_ports` 快照生成的 `workflow:<name>` | `output_ports` 快照生成的 `workflow:<name>` |

### 5.1 节点语义

- `construct_message.role` 缺省为 `user`，允许 `system`、`user`、`assistant`、`tool`；`role_source` 缺省为 `fixed`，允许 `fixed` 或 `port`。
- `construct_content.append_items` 是非空数组。每项为 `{type:"fixed", value:string}` 或 `{type:"port", port_id:string}`。port ID 不重复，且与 `dataInputPorts` 集合相同。按配置顺序拼接；非字符串 port 值转成字符串。
- `split_event` 要求对象含非空字符串 `event_type` 和 `payload` 字段；payload 输出为 JSON 文本。
- `construct_event` 的 payload 输入必须可解析为 JSON object，输出 Event 1.1 对象 `{version: "1.1", event_type, payload}`。
- `publish_event` 要求对象的 `version` 固定为 `"1.1"`，且含非空字符串 `event_type` 和 object 类型 `payload`；发布到主 Agent 队列后继续控制流。
- `deserialize_json` 要求根对象包含配置中每个 key，且值符合对应目标类型；不匹配会使执行失败。支持类型为 3.1 节列出的七种类型。
- `history` 的 `event_types` 与 `limit` 必须提供；event_types 为非空数组，limit 为 1–1000 整数。
- Context ID 区分所有字符，首尾空格也是 ID 的一部分；实现不得对 ID 执行去除首尾空白或其他规范化。`context_create.context_id` 未提供或为空字符串时自动生成；提供时必须是非空白字符串。若该 ID 已存在则创建失败，不覆盖已有 Context。Context 仅属于当前 Workflow invocation，并在该次执行结束时清理。
- `context_read.context_id_source` 和 `context_write.context_id_source` 缺省为 `port`，仅允许 `port` 或 `fixed`。`port` 模式从 `context-id` 输入端口读取 ID，`context_id` 不使用；`fixed` 模式必须提供非空白的 `context_id` 字符串，且不生成 ID 输入端口。两种模式均按当前 Workflow invocation 校验 Context 所有权。修改 Context 后输出所用的 Context ID 与新值。
- `llm.tools` 选择已注册的本地工具；`tool_calls` 输出为 JSON 文本组成的 list-content。
- 远程工具的 `parameters` 必须与 `remote_tools` 中同名声明的输入接口一致；sync 工具的 `outputs` 必须与声明的输出接口一致。`control-in` 不能作为工具输入名，`control-out` 不能作为 sync 输出名。
- 远程 `timeout_ms` 必须为正整数。sync 上限由 `TOOL_CLIENT_MAX_WAIT_MS` 控制，缺省 10000 ms；async 上限由 `TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS` 控制，缺省 3600000 ms。
- async `callback` 若提供，必须恰含 `type`、`queue`、`event_type`、`on`。`type` 固定为 `redis`；queue 长度 1–256，event_type 长度 1–128；`on` 是无重复且非空的 `working`/`completed`/`failed` 状态数组。
- sync 工具只有一个名为 `result` 的输出时，完整返回值交给该输出；其他输出配置要求返回对象且包含全部输出名。`map-content` 值必须是字符串 map。
- `foreach` 每次从列表取一个元素，经 `loop-out` 进入循环体；列表耗尽后走 `control-out`，空列表直接结束循环。
- `workflow` 节点的接口快照必须与被调用 Workflow 当前定义一致；递归调用被拒绝。

## 6. 连线

每条连线必须含 `fromId`、`fromPortId`、`toId`、`toPortId`、`type`，可选 `id`。端点和端口 ID 必须是非空字符串，引用的节点必须存在，端口必须由对应节点类型及配置定义。

`type` 只能是 `control` 或 3.1 节列出的数据类型。control 连线只能连接合法控制端口；数据连线类型必须同时匹配源输出和目标输入。边界、Workflow 调用、Tool、Context/Session、Event、列表、LLM、Map、JSON 转换节点还须满足第 5 节的专属类型规则。

每个 control 输入最多一个来源，每个 control 输出最多一个后继；每个数据输入最多一个来源。Input 的 `control-out`、普通节点的 `control-in`/`control-out`、Output 的 `control-in` 必须连接。Router 每个分支输出必须连接；可选名称 `其它` 的分支在输入值没有精确匹配名称时执行，精确匹配优先，且此类分支最多一个。兜底分支使用保留 ID `branch$others`，且其名称必须为 `其它`；普通分支不得使用该 ID 或名称。编译后的内部 successor 键中，普通 Router 分支使用 `branch-<名称>`，兜底分支使用保留键 `branch$others`。Foreach 的 `loop-in`、`loop-out`、`control-in`、`control-out` 必须连接。控制流允许有向环；退出条件由 Workflow 自身提供。

数据输入可以不连接；节点执行时读取必需输入而没有值会失败。运行时将 `None` 视为未提供。未声明的端口不可连线。

## 7. 执行模型

Agent 校验 Workflow 后将节点和连线编译为内部执行图。控制连接决定执行顺序；数据连接在节点输出时传播值。内部执行图不是持久化 JSON 的一部分。

执行从唯一 Input 节点开始。Input 沿 `control-out` 继续；Output 收集已提供且非 `None` 的接口输入字段作为结果并结束当前图。缺少控制后继、必需数据输入或节点运行时类型不符会导致执行失败。

子 Workflow 在当前调用中执行，使用自身 Input/Output 边界；接口快照与实际定义不一致或发生递归调用时执行失败。

`publish_event` 把新事件发布到主 Agent 队列，由队列消费者独立调度，不在当前 Workflow 调用栈内递归启动。

## 8. Event 对象

`event` 是 Workflow 数据类型，格式固定为 Event 1.1：`{version: "1.1", event_type, payload}`。`construct_event` 输出完整格式；`publish_event` 仅接受该版本并发布至 Agent 队列。队列发布器也会将信封版本设置为 `"1.1"`。

当 Workflow 声明 `origin` 输入端口时，其值为完整 Event；来源与映射规则见本规范 3.2 节。

## 9. 校验职责

Draft 2020-12 JSON Schema 定义根字段、节点/端口/连线基本形状、字段类型及额外字段限制。Agent 与管理端语义校验负责管理端请求约束、Workflow 名称和接口规则、`origin` 类型、依赖名称唯一、节点参数及动态端口、Input/Output 数量、边界快照一致性、节点 ID 唯一、连接端点/端口/类型/连接基数、必需控制连接，以及远程工具接口快照、timeout 和 callback 约束。管理端拒绝额外根字段；Agent 不单独拒绝额外根字段。

编辑器负责生成符合本协议的 JSON；服务端仍须独立校验，编辑器校验不能代替 Agent 或管理端校验。

