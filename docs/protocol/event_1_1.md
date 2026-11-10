# Event 1.1 协议规范

> 类型:设计文档。
> 性质:现行文档。
> 归属:跨服务。
> 适用版本:平台 `4.0.0+`。
> 协议版本:event 1.1。

本文定义 AAgent 的 Event 数据契约。协议版本值以仓库根 `version.json.protocol.event` 为准；每条 Event 还必须在顶层携带固定的 `version: "1.1"`，Agent 主队列消费者严格校验该值。

## 1. 范围与编码

Event 在 Redis List 中占一个元素，内容是 UTF-8 编码的 JSON 对象。QQ 输入队列和主队列使用同一信封；Tool Server 可向专用 Redis 队列投递同形回调信封，但主 worker 没有回调专用消费者。Workflow 定义、Tool Server HTTP 请求、Provider WebSocket 消息均不属于本协议。

```json
{
  "version": "1.1",
  "event_type": "terminal",
  "payload": {"content": "执行任务", "files": []}
}
```

| 顶层字段 | 要求 | 类型 | 含义 |
|---|---|---|---|
| `version` | 必须 | 固定字符串 `1.1` | 单条 Event 的协议版本；Agent 主队列消费者拒绝缺失或不匹配的版本 |
| `event_type` | 必须 | 非空字符串 | 选择 Workflow 执行或事件绑定 |
| `payload` | 必须 | JSON 对象 | 类型专属数据；绑定路由浅拷贝并覆盖 Workflow 选择字段与 `origin` |
| `time` | 可选 | 字符串 | 终端生产者附加的时间；主 worker 不读取 |

其他顶层字段可随 Event 透传并保存到历史，但没有统一处理语义。`created_at` 和 `_id` 由历史存储生成，不属于队列 Event：worker 校验版本后把 Event 复制并加 UTC `created_at` 写入 MongoDB，数据库生成 `_id`。WebUI 展示不可解析的队列内容时包装出的 `raw` 不是可发送的协议类型。Tool Server 专用回调队列不由主 worker 消费，不在本次主队列版本校验范围内。

## 2. 类型契约

### 2.1 外部输入

`qq` 的消息 payload 形状为：

```json
{
  "version": "1.1",
  "event_type": "qq",
  "payload": {
    "post_type": "message",
    "user_id": 3363336986,
    "group_id": null,
    "raw_message": "执行任务",
    "message": [{"type": "text", "data": {"text": "执行任务"}}]
  }
}
```

QQ listener 也产生 `post_type: "inputing"`、带 `user_id` 的输入状态事件。QQ consumer 仅将 `post_type == "message"`、`group_id` 为空且 `user_id` 匹配目标用户的事件转发至主队列；其他事件只进入 QQ 历史。`message` 为上游 OneBot 消息段列表，具体消息段由上游定义。

`terminal` 由 WebUI 生产：

```json
{
  "version": "1.1",
  "event_type": "terminal",
  "time": "2026-09-18T12:00:00.000Z",
  "payload": {"content": "执行任务", "files": []}
}
```

WebUI 要求去除首尾空白后的 `content` 非空且最多 4000 个字符，`files` 当前必须是空列表；主 worker 不重命名字段。其他外部 `event_type` 也可通过启用的绑定触发 Workflow，其 payload 由生产者与 Workflow 输入端口共同约定。

### 2.2 内部事件

绑定路由产生 `workflow`：

```json
{
  "version": "1.1",
  "event_type": "workflow",
  "payload": {"content": "执行任务", "files": [], "workflow_file_id": "workspace-file-id"}
}
```

`payload.workflow_file_id` 为 Workspace 文件的稳定 ID，由绑定写入。路由移除原始 payload 中的 `workflow_file_id`、`workflow_name` 和 `origin`，写入绑定目标并将原事件设为 `origin`；其他原始 payload 字段保留。执行时从 Workspace 当前 generation 读取文件最新内容并解析为 Workflow JSON，文件改名不影响绑定，恢复检查点后使用恢复的文件内容。兼容已有按 `workflow_name` 从管理库读取的调用；同时提供两个字段时优先使用 `workflow_file_id`，文件读取失败不回退到名称。再按 Workflow Input 端口的 `name` 读取同名字段；缺失的字段传为 `None`。`workflow` 是唯一不查询事件绑定、直接执行的主 worker 类型。

执行成功产生 `response`：

```json
{"version": "1.1", "event_type": "response", "payload": {"content": "Workflow 输出"}}
```

`content` 是 Workflow 最终输出的 `content` 字段（若没有则为整个输出），值不限定为字符串。目标 Workflow 不存在或处理时抛出异常产生 `error`：

```json
{"version": "1.1", "event_type": "error", "payload": {"workflow_file_id": "workspace-file-id", "message": "workflow not found"}}
```

`message` 是错误文本；异常捕获产生的 `error` 保留原 Event payload 中存在的 `workflow_file_id` 和 `workflow_name` 以定位执行目标。当前 worker 对所有非 `workflow` 类型（包括 `response` 和 `error`）都查询绑定：为它们配置绑定会再次触发 Workflow，需避免循环。远景设计目标是“无终态”：让 Agent 自主判断是否继续处理并形成循环，同时权衡循环带来的成本与效果；这并非让这两种事件退出绑定路由，也不意味着当前已具备自主控制循环的机制。该目标不属于 Event 1.1 的已实现行为。

### 2.3 Tool Server 回调

异步工具可配置 `type: "redis"`、专用 `queue`、`event_type` 及 `on` 状态列表。回调的 Event 信封相同，payload 格式如下；字段可以为 `null`：

```json
{
  "event_type": "async_result",
  "payload": {
    "task_id": "01J...",
    "tool": "qq.send_group_msg",
    "status": "completed",
    "result": {"message_id": 123},
    "error": null,
    "progress": null,
    "message": null
  }
}
```

回调状态可为 `working`、`completed`、`failed`，是否投递取决于配置的 `on`。主 worker 没有 `async_result` 专用处理分支，不应将回调投递到主队列；该队列须有自己的消费者。

## 3. 传输与处理语义

QQ 队列用 `LPUSH` / `BLPOP`，后入先出；主队列常规 Event 用 `LPUSH` / `BRPOP`，先入先出；WebUI 终端用 `RPUSH`，会先于已排队的常规 Event 出队。所有投递至主队列的生产者必须携带顶层 `version: "1.1"`。主 worker 出队后先校验该值必须精确匹配 `1.1`，再写历史和处理 Event；缺失或不匹配时拒绝处理且不写入历史。无启用绑定的非 `workflow` Event 仅留在历史。绑定查询出错会报告失败，不当作未绑定。当前队列不提供确认、自动重试或去重协议。

Event 1.1 相较 Event 1.0 将 Workflow 选择字段从 MongoDB ID `workflow_id` 改为唯一名称 `workflow_name`。新建及编辑的事件绑定使用 Workspace `workflow_file_id`，`workflow` Event 优先使用该字段并兼容 `workflow_name`。MongoDB Workflow 文档 `_id` 仅供管理 API 定位，不属于 Event 执行选择契约；不支持 `workflow_id`。

Event 协议按 `MAJOR.MINOR` 独立演进；发布时才同步根版本清单、文档元信息与标签正文。变更字段、事件类型或队列方向时，必须同时检查所有生产者和消费者，不保留旧格式的兼容分支。详细版本规则见[版本与归属规范](../版本与归属规范.md)。
