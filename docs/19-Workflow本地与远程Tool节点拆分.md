# 19 Workflow 本地、远程同步与远程异步 Tool 节点拆分

## 1. 目标

将现有 `tool` 节点拆分为三种执行和控制流语义明确的节点：

- `local_tool`（编辑器显示 `Local Tool`）：调用 Agent 进程内注册的工具；
- `remote_sync_tool`（编辑器显示 `Remote Sync Tool`）：通过 Tool Server 调用 Tool Provider，并等待最终结果；
- `remote_async_tool`（编辑器显示 `Remote Async Tool`）：向 Tool Server 发布任务，取得 `task_id` 后立即继续，之后不再管理该任务。

节点持久化类型使用 snake_case。远程 Tool 先在 Workflow 元数据的 `remote_tools` 中注册名称和输入/输出契约，两种远程节点只选择已注册工具并保存契约快照。不得用单个 `remote_tool` 节点上的 `mode` 字段切换语义。同步结果与异步任务 ID 是不同契约，应由节点类型直接表达。

## 2. 设计动机

这次设计起于一个直接的问题：是否应把当前所有 Tool 都迁入 `tool_provider`，让 Agent 只通过 Tool Server 调用工具。

全部远程化看起来最统一，也能让 Agent 与具体工具实现分离，但会把远程执行的固定成本强加给所有工具：

- 每次调用都需要网络通信和 JSON 序列化；
- Tool Server 需要维护 Task、超时、状态和结果；
- Provider 连接状态会成为新的故障点；
- 长任务需要明确提交边界、任务持久化和独立的结果消费链路；
- 开发、部署和排障需要跨越 Agent、Tool Server 与 Provider。

这些成本适合下载、ASR、外部 API 和独立部署服务，因为它们本身依赖较重、耗时较长或需要独立扩缩容。Documents、Workflow 内部状态访问、终端输出等 Agent 内生能力与 Agent 共享数据、生命周期和一致性边界，强制远程化只会把普通函数调用变成分布式任务调用。

保留单一 `tool` 节点并由运行时判断执行位置也不可取：

- 画布无法表达真实执行位置和故障边界；
- 同名工具、Provider 离线和目录变化会造成隐式路由不稳定；
- 保存校验与运行时可能选择不同来源；
- 用户无法按延迟、可靠性和部署要求选择执行方式；
- 本地与远程的目录、Schema 和错误语义仍然不同，只是差异被藏进运行时。

因此采用第三条路径：统一 Tool 的抽象，但不隐藏执行位置和等待语义。Workflow 在节点层显式区分 `local_tool`、`remote_sync_tool` 与 `remote_async_tool`：

```text
Agent 内生、低延迟、共享一致性边界     -> local_tool
远程执行、当前控制流需要最终结果       -> remote_sync_tool
远程长任务、当前控制流只需要任务 ID    -> remote_async_tool
```

这里的解耦是指工具契约、发现方式、执行器和控制流边界清晰，并不要求所有调用跨进程。Local/Remote 是执行位置；Sync/Async 是当前 Workflow 是否等待最终结果。两者都不是能力等级或任务难度。

## 3. 现状与边界

当前 `tool` 节点只调用 Agent 本地注册表：

```text
Workflow Editor /api/tools
-> Redis Hash aagent:tools
-> WebUI 保存校验
-> workflow_tool()
-> tools.tool.execute_tool()
-> 进程内 handler
```

实施必须基于以下事实：

1. Workflow runner 是同步单次遍历；异步节点只发布任务，不管理发布后的执行和结果；
2. 本地目录使用 OpenAI Function 的 `function.parameters`，Tool Server 使用 `inputSchema`；
3. 节点契约分别存在于 Agent、WebUI、编辑器节点契约和序列化层；
4. Tool Server 已支持 `mode: "wait"` 和 `mode: "async"`；`wait` 仍可能返回 `202`，任务会继续执行且当前没有 cancel API；
5. 服务端等待上限为 `min(timeout_ms, TOOL_MAX_WAIT_MS)`，默认 `TOOL_MAX_WAIT_MS=30000`；
6. `tool_call` 节点已删除，LLM 的 `tools: string[]` 只挂载本地工具；本次不恢复动态工具调用，也不把远程工具加入 LLM 挂载项；
7. `agent/tools/tool.py` 导入时会先执行 `redis_reset_tools()` 再重建目录，读取方必须容忍本地目录短暂为空。

执行边界由节点类型唯一决定，不允许自动降级或跨目录查找：

```text
local_tool  -> Local Tool Registry -> 进程内 handler
remote_sync_tool  -> Tool Server API mode=wait  -> Tool Server -> Tool Provider
remote_async_tool -> Tool Server API mode=async -> Tool Server -> Tool Provider
```

同名工具也只在本地或远程各自目录中发现和执行。两种远程节点都不保存 `provider_id`，Provider 选择由 Tool Server 负责。

## 4. 节点契约

### 4.1 Local Tool

```json
{
  "id": "local-tool-1",
  "type": "local_tool",
  "name": "查询文档",
  "x": 320,
  "y": 200,
  "arguments": {
    "tool": "query_document_by_id",
    "parameters": ["doc_id"]
  }
}
```

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `tool` | string | 本地工具稳定名称，必须存在于本地目录 |
| `parameters` | string[] | 必须与当前本地输入 Schema 的一级 properties 完全一致 |

### 4.2 Remote Sync Tool

```json
{
  "id": "remote-sync-tool-1",
  "type": "remote_sync_tool",
  "name": "查询远程数据",
  "x": 580,
  "y": 200,
  "arguments": {
    "tool": "service.query",
    "parameters": [
      { "name": "query", "type": "content" }
    ],
    "outputs": [
      { "name": "answer", "type": "content" },
      { "name": "sources", "type": "list-content" }
    ],
    "timeout_ms": 10000
  }
}
```

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `tool` | string | 非空；不要求保存时在线 |
| `parameters` | object[] | 用户声明的 `{name, type}` 输入端口，不要求与在线目录 Schema 一致 |
| `outputs` | object[] | 用户声明的 `{name, type}` 输出端口，不要求与在线目录 Schema 一致 |
| `timeout_ms` | integer | 同步等待和远程执行时限；正整数；不得超过 `TOOL_CLIENT_MAX_WAIT_MS` |

运行时固定发送 `mode: "wait"`。节点不保存 `mode`、`provider_id` 或 `callback`。

### 4.3 Remote Async Tool

```json
{
  "id": "remote-async-tool-1",
  "type": "remote_async_tool",
  "name": "提交视频转写",
  "x": 580,
  "y": 380,
  "arguments": {
    "tool": "bilibili.gain_content_from_bvid",
    "parameters": [
      { "name": "bvid", "type": "content" }
    ],
    "timeout_ms": 600000,
    "callback": {
      "type": "redis",
      "queue": "main_agent_queue",
      "event_type": "async_result",
      "on": ["completed", "failed"]
    }
  }
}
```

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `tool` | string | 非空；不要求保存时在线 |
| `parameters` | object[] | 与 Remote Sync Tool 相同 |
| `timeout_ms` | integer | Provider 执行 deadline；正整数；不受同步等待上限约束 |
| `callback` | object \| null | 可选 Redis 回调；包含固定 `type: redis`、队列、事件类型和至少一个触发状态 |

运行时固定发送 `mode: "async"`。HTTP `202` 表示提交成功，节点取得 `task_id` 后立即继续。节点不保存 `outputs`、`mode` 或 `provider_id`；配置 `callback` 时由 Tool Server 在 `working`、`completed`、`failed` 中选定的状态变化后向指定 Redis List 发布事件。

两种远程节点参数以及 Remote Sync Tool 输出的 `type` 只能是 `content`、`message`、`list-content` 或 `list-message`。类型约束 Workflow 连线；输入类型不转换发送给 Tool Server 的参数值，输出类型也不隐式转换 Tool Server 返回值。旧的字符串参数数组和旧的固定 `output` 端口不做迁移，直接拒绝。

新增配置：

| 配置 | 默认值 | 约束 |
| --- | --- | --- |
| `TOOL_CLIENT_DEFAULT_WAIT_MS` | `10000` | Remote Sync Tool 未填写 `timeout_ms` 时使用 |
| `TOOL_CLIENT_MAX_WAIT_MS` | `10000` | 仅限制 Remote Sync Tool；必须小于或等于 `TOOL_MAX_WAIT_MS` |
| `TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS` | `600000` | Remote Async Tool 未填写 `timeout_ms` 时使用 |
| `TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS` | `3600000` | 保存时限制异步任务 deadline，避免无界输入 |

远程 Schema 可在一级属性或根输出上使用扩展字段 `x-workflow-port-type`，值只能是 `content`、`message`、`list-content` 或 `list-message`。该字段只辅助编辑器选择端口类型，不参与 Tool Server 的 JSON Schema 校验，也不转换运行时值。

### 4.4 端口

三类节点均使用 `control-in` 和 `control-out`。Local 参数固定为 `content`，两种 Remote 参数使用各自声明的类型。

| 节点 | 输出端口 |
| --- | --- |
| Local Tool | 固定 `output: content`，内容是工具最终结果 |
| Remote Sync Tool | `outputs` 中声明的强类型端口，端口名对应结果字段名 |
| Remote Async Tool | 固定 `task_id: content`，内容是 Tool Server `task_id` |

远程参数名称同时作为输入端口 ID 和调用参数名；同步输出名称同时作为输出端口 ID 和结果字段名。名称必须满足：

1. 名称是非空字符串；
2. 不得重复；
3. 输入名称不得为 `control-in`，输出名称不得为 `control-out`。

保留名限制只处理同方向端口冲突；输入端可以使用 `output`、`control-out`，输出端可以使用 `control-in`、`output` 或 `task_id`。连接合法性按 `(portId, direction, type)` 判断。

Local Tool 切换工具或任一 Remote Tool 删除参数、修改参数类型时，只删除失效或类型不匹配的输入连接。Remote Sync Tool 删除输出、修改输出类型时同样只删除对应的失效输出连接。控制连接始终保留。

## 5. 目录与保存校验

### 5.1 目录 API

Workflow Editor 提供：

```text
GET /api/tools/local
GET /api/tools/remote
```

两者统一返回：

```json
{
  "items": [
    {
      "name": "query_document_by_id",
      "description": "通过文档 id 查询文档",
      "inputSchema": {
        "type": "object",
        "properties": {
          "doc_id": {"type": "string"}
        },
        "required": ["doc_id"]
      },
      "outputSchema": null
    }
  ]
}
```

- `/api/tools/local` 读取 `AGENT_TOOLS_KEY`，将 `function.parameters` 转换为 `inputSchema`；现有 `/api/tools` 直接改名，LLM 挂载项复用此接口；
- `/api/tools/remote` 由编辑器后端代理 Tool Server 的 `GET /api/tools`，完整保留 `inputSchema` 和 `outputSchema`；浏览器不直接访问内部地址或持有凭据；
- 响应不增加 `execution` 字段，来源由端点表达；
- 两个目录不能合并。Local Tool 受本地目录约束；Remote Tool 目录供元数据编辑区辅助注册和填充，也允许手动注册目录外名称；
- Workflow 元数据维护 `remote_tools` 契约表，每项包含 `name`、`input_ports` 和 `output_ports`；它是画布节点的选择来源和离线契约快照，不参与运行时 Provider 路由；
- 元数据中的 Remote Tool 可手动配置，也可按名称从 Tool Server 目录填充。执行时仍以 Tool Server 当前状态为准。

Remote Tool 元数据编辑区同时使用两个 Schema 辅助填充：

- `inputSchema.properties` 生成输入端口候选；
- 对象型 `outputSchema.properties` 生成同名输出端口候选；
- 标量或数组型 `outputSchema` 生成单个默认输出端口 `result`；
- Schema 节点存在合法 `x-workflow-port-type` 时直接采用该类型；
- 未声明扩展类型时，`type: "array"` 默认映射为 `list-content`，其他 JSON Schema 类型默认映射为 `content`；
- `message` 和 `list-message` 不根据 JSON 值形状猜测，必须由 Schema 扩展字段声明或由用户手动选择；
- Schema 只用于填充元数据建议。填充后可在元数据中增删、改名和改类型，不与在线 Schema 保持强绑定。

Remote Async Tool 节点使用元数据的输入契约生成输入端口，但忽略元数据输出契约，因为它固定只输出 `task_id`。同一个注册工具仍可被 Remote Sync Tool 使用其输出契约。

### 5.2 保存校验

`local_tool`：

1. 工具存在于本地目录；
2. `parameters` 与当前 Schema 一级 properties 完全一致；
3. 只包含该类型允许的 arguments；
4. 所有连接端口有效。

本地目录短暂为空时不得据此拒绝保存或清空已有选择。

`remote_sync_tool`：

1. `tool` 是非空字符串，且存在于 Workflow 元数据的 `remote_tools`；
2. `parameters` 与该元数据项的 `input_ports` 完全一致；
3. `outputs` 与该元数据项的 `output_ports` 完全一致；
4. `timeout_ms` 是正整数且不超过 `TOOL_CLIENT_MAX_WAIT_MS`，超限直接拒绝，不截断；
5. 只包含该类型允许的 arguments；
6. 输入和输出连接均指向用户当前声明且类型一致的端口。

`remote_async_tool`：

1. 工具名和输入参数必须与元数据契约一致，输入连接规则与 Remote Sync Tool 相同；
2. `timeout_ms` 是正整数且不超过 `TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS`；
3. 不允许出现 `mode` 或 `callback` arguments；
4. 不允许 `outputs`；节点只提供固定的 `task_id: content` 输出端口。

保存两种 Remote Tool 均不依赖 Tool Server，不校验工具在线状态；节点端口必须与 Workflow 元数据契约一致，但元数据不要求与在线候选 Schema 一致。实际输入缺失、多余或类型不符时，由调用时的 Tool Server Schema 以 `422` 拒绝；同步结果与用户声明输出不匹配时，节点执行失败。

## 6. 运行时语义

### 6.1 Local Tool

`workflow_local_tool()` 复用现有进程内路径：收集参数、调用本地 handler、传播 `output`，成功后沿 `control-out` 继续。它不得访问 Tool Server。

### 6.2 Remote Sync Tool

`workflow_remote_sync_tool()` 通过独立 Tool Server Client 调用：

```http
POST /api/tools/{tool_name}/calls
Content-Type: application/json

{
  "arguments": {},
  "mode": "wait",
  "timeout_ms": 10000
}
```

| HTTP / Task | Workflow 行为 |
| --- | --- |
| `200 + completed` | 按 `outputs` 将 `result` 分发到对应强类型端口，继续控制流 |
| `200 + failed` | 节点失败，不继续控制流 |
| `202 + pending/working` | 节点以“尚未完成”失败，不传播 Task，不继续控制流 |
| `404/503` | 远程工具不可用，节点失败 |
| `422` | 参数不符合在线 Schema，节点失败 |
| 网络错误 | 节点失败 |

收到 `202` 时必须：

1. 在节点错误和结构化日志中记录 `task_id`；
2. 不轮询、不自动取回结果；
3. 明确任务仍会在服务端继续执行，超时不会取消任务，副作用可能已发生。

远程同步等待会阻塞 Agent 单 worker，因此只适合能在 `TOOL_CLIENT_MAX_WAIT_MS` 内稳定完成的工具。

同步结果分发规则：

- `result` 是 object 时，每个输出端口按端口名读取同名字段；字段缺失时节点失败；
- 仅声明一个名为 `result` 的输出端口时，该端口接收完整结果，可承载标量、数组或 object；
- 除上述单 `result` 端口外，非 object 结果无法按名称分发，节点失败；
- 运行时不根据返回值猜测端口，也不执行类型转换；Tool Server 的 `outputSchema` 负责远程结果校验，Workflow 声明类型负责连线强类型校验。

### 6.3 Remote Async Tool

`workflow_remote_async_tool()` 固定提交：

```http
POST /api/tools/{tool_name}/calls
Content-Type: application/json

{
  "arguments": {},
  "mode": "async",
  "timeout_ms": 600000
}
```

| HTTP / Task | Workflow 行为 |
| --- | --- |
| `202 + task_id` | 提交成功；传播到固定 `task_id` 端口，立即继续控制流 |
| `200 + completed` | 违反异步调用契约，节点失败，不把结果伪装成 `task_id` |
| `202` 但缺少 `task_id` | 节点失败 |
| `404/503` | 远程工具不可用，节点失败 |
| `422` | 参数不符合在线 Schema，节点失败 |
| 网络错误 | 节点失败 |

异步节点是发布任务的节点。Tool Server 返回非空 `task_id` 即发布成功；节点从固定 `task_id` 端口输出该值并继续控制流。发布后不再等待、跟踪、取消或接收该任务的结果。

### 6.4 输出与错误

Local Tool 的最终结果统一转换为 `content`：

- string 原样输出；
- number、boolean、array、object 使用 JSON 序列化；
- JSON null 输出文本 `null`；
- 失败抛出节点异常，不把错误文本作为成功结果。

Remote Sync Tool 按 `outputs` 声明分发原始结果字段，不统一压成 `content`。Remote Async Tool 的 `task_id` 端口输出非空字符串，不经过工具结果序列化。

不修改 `read_workflow_input()` 的 `slot[2] is not None` 到达判断。远程错误至少包含 `node_id`、`tool`、`execution: "remote_sync"` 或 `execution: "remote_async"`、可选 `task_id` 和 `message`。

## 7. 旧格式与非目标

旧 `tool` 节点不兼容、不迁移。编辑器导入/打开、WebUI 上传/保存和 Agent 执行均直接拒绝旧节点，已有数据由使用者重建。

本次不实现：

- `remote_tool_call` 或任何动态名称执行节点；
- LLM 远程工具挂载；
- 本地找不到时自动转发远程；
- 对已发布的远程异步任务进行等待、跟踪、取消或结果处理；
- 工具参数类型系统扩展；
- 修复 `workflow_llm()` 仅返回 `tool_calls` 时将 `content=None` 传播到 `output` 的既有问题。

## 8. 改动范围

| 模块 | 修改内容 |
| --- | --- |
| `agent/workflow_contract.py` | 注册三种节点类型、arguments 和端口 |
| `agent/workflow_validator.py` | 校验本地 Schema、远程字段、端口名和超时 |
| `agent/workflow_nodes.py` | 拆分本地、远程同步和远程异步 handler，规范化输出 |
| `agent/workflow_parser.py` | 编译三种节点的端口形状 |
| `agent/` 新 Tool Server Client | 调用 API，映射 Task 状态和网络错误 |
| `webui_py/workflows.py` | 保存格式和三种节点校验；以 `NODE_ARGUMENT_FIELDS_BY_TYPE` 作为唯一类型白名单来源 |
| `workflow_editor/main.py` | 本地目录 API 改名并新增远程代理 API |
| `workflow_editor/static/workflow/domain/node-contract.js` | 节点类型、创建逻辑和端口 |
| `workflow_editor/static/workflow/domain/serialization.js` | arguments 白名单和规范化 |
| `workflow_editor/static/workflow/inspector/integrations.js` | 本地受约束选择；远程从元数据契约选择并生成端口快照 |
| `workflow_editor/static/workflow_edit.html` | 三个节点入口和 Inspector 模板 |
| `docker-compose.yml` | Tool Server 地址、同步等待与异步 deadline 配置 |

节点契约存在多份手工副本，实施时增加契约一致性测试；单一 Schema 或代码生成不属于本次改造。

## 9. 验收要求

### 9.1 契约与编辑器

- 三种节点均能保存、校验和解析，未知 arguments 被拒绝；
- 旧 `tool`、`tool_call` 和 `remote_tool` 均被直接拒绝；
- Local Tool 只显示本地目录；Remote Tool 先在元数据中注册，节点只显示已注册项；
- LLM 挂载项仍只显示本地工具；
- Tool Server 不可用不影响编辑和保存，只影响远程候选与执行；
- Local Tool 和 LLM 挂载项只保留当前本地目录中存在的工具，目录为空时清空选择且拒绝保存 Local Tool 节点；
- Remote Tool 元数据的输入输出端口可自由增删并指定四种数据端口类型，节点端口只读并跟随元数据契约；
- Remote API 的 `inputSchema` 辅助填充元数据输入端口，`outputSchema` 辅助填充元数据输出端口，填充后不强制绑定在线 Schema；
- 输入端口拒绝空值、重复和 `control-in`；同步输出端口拒绝空值、重复和 `control-out`；
- 旧 Remote Tool 字符串参数数组直接拒绝，不做迁移或默认类型补全；
- `timeout_ms` 缺失时使用各自默认值；同步超等待上限、异步超 deadline 上限或非正整数时拒绝保存；
- 输入或同步输出配置变化只删除对应的失效或类型不匹配连接，保留其他数据连接和控制连接。

### 9.2 运行时

- Local Tool 不访问 Tool Server，两种 Remote Tool 不访问本地 handler，同名工具不跨目录执行；
- Remote Sync Tool 仅在 `completed` 时传播最终结果；`202`、`failed`、`404/503`、`422` 和网络错误阻止控制流；
- Remote Sync Tool 按用户配置的端口名分发对象字段，端口类型参与强类型连线校验；
- Remote Async Tool 仅在 `202 + task_id` 时传播任务 ID 并继续，不传播最终结果；
- Remote Async Tool 发布成功后不再管理任务；
- JSON 结果按约定序列化，JSON null 输出文本 `null` 且下游可识别为已到达；
- Schema 改变造成的参数不兼容在执行时明确返回 `422`。

## 10. 实施顺序

1. 增加本地与远程目录 API；
2. 在四份节点契约中加入三种类型并删除旧 `tool` 和 `remote_tool`；
3. 完成三节点、三 Inspector 和参数连接清理；
4. 完成 WebUI 的本地强校验、远程同步和远程异步结构校验；
5. 将现有 `workflow_tool()` 迁移为 `workflow_local_tool()`；
6. 接入同步等待和异步 deadline 配置；
7. 增加 Tool Server Client、`workflow_remote_sync_tool()` 和 `workflow_remote_async_tool()`；
8. 覆盖同步 completed/`202`、异步 `202 + task_id`、failed、断线、`422` 和 Schema 变化测试；
9. 由使用者重建包含旧 `tool` 的 Workflow；
10. 验证 Remote Async Tool 发布成功后不会继续管理任务。
