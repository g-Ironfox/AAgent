# Workflow 1.2 协议规范

> 类型:设计文档。
> 性质:现行文档。
> 归属:`agent/` + `workflow_editor/` + `manager_webui/`。
> 协议版本:workflow 1.2。

Workflow 1.2 在 1.1 的节点与连接契约上新增 `construct_event` 和 `publish_event` 节点。Workflow 定义必须将 `schema_version` 写为 `"1.2"`；Agent、管理页和编辑器只接受当前版本，不自动迁移 1.1 定义。

## 构造事件节点

`construct_event` 通过 `arguments.event_type` 指定非空事件类型，从 `payload-in` 接收 JSON 对象字符串，并在 `event-out` 输出 `{ "event_type": "...", "payload": { ... } }` Event 对象。Payload 必须能解析为 JSON 对象，可包含嵌套对象、数组和非字符串值。该节点有标准 `control-in` / `control-out`，无其它参数。

## 发布事件节点

`publish_event` 有标准 `control-in` / `control-out` 控制端口，以及一个 `event-in` 数据输入端口，类型必须为 `event`。节点没有可配置 arguments。运行时要求输入是对象，含非空字符串 `event_type` 和对象 `payload`；随后通过 Event 1.1 主队列发布，并沿 `control-out` 继续执行。发布队列使用 `MAIN_AGENT_QUEUE_NAME`，Event 信封的 `version` 由队列客户端设为 `"1.1"`。

示例节点与连接：

```json
{"id":"publish","type":"publish_event","name":"发布 Event","arguments":{}}
```

```json
{"fromId":"input","fromPortId":"workflow:event","toId":"publish","toPortId":"event-in","type":"event"}
```

工作流可把 `publish_event` 的控制后继连到 Router：由 Router 根据当前数据选继续循环的分支或退出分支。控制流中的有向环是允许的，节点不会隐式终止或限制循环次数；需要由 Router/工作流逻辑提供退出条件。每次投递都会进入主 Agent 队列，作为新的 Event 独立启动对应的 Workflow，不会在当前执行栈内递归调用 Workflow。

## 版本与 Schema

Workflow 1.2 使用独立版本号，Event 协议仍为 1.1。当前版本清单和消费端的硬编码版本常量必须保持一致。JSON Schema 见 [workflow_1_2.schema.json](workflow_1_2.schema.json)；端口兼容、控制连接完整性及运行时输入值检查由 Agent/管理页 validator 与节点执行器实施。

完整节点、端口和参数契约以 `agent/workflow_contract.py` 为准。旧 Workflow 1.1 定义需要按 1.2 契约重建或手动调整。