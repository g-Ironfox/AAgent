# Workflow 设计 LLM 接入说明

本目录中的 [单文件 skill](../skills/workflow-designer/SKILL.md) 是给设计 LLM 的完整规范。将整个文件内容作为设计指令，再附用户需求即可；节点目录、工具目录、协议、错误策略和三个完整示例均已内嵌。不要只发送 frontmatter 或文件路径，也不需要另外提供节点列表。本文是给接入方的说明，不必一并发送给设计 LLM。

规范根据当前工作区源码整理，目标版本为 Workflow 2.0 / Event 1.1。本文同时记录论文机制所需的运行时扩展；旧图仍使用原生 Workflow 2.0 契约。

## 已核实的执行链

1. [processes.py](../webui_py/processes.py) 按工作区文件 ID 创建进程，校验并编译工作流，同时创建专属终端，将进程记录和就绪项写入 Redis。
2. [workflow_validator.py](../agent/workflow_validator.py) 校验 Schema、接口、节点、端口、控制图与生命周期；[workflow_parser.py](../agent/workflow_parser.py) 把持久化 nodes/connections 编译成内部索引图。
3. [workflow_nodes.py](../agent/workflow_nodes.py) 按控制连线逐节点执行，数据连接只传值；output 收集结果后结束当前图。workflow 节点按精确工作区文件名同步调用子图，执行结束才回到父图。
4. [main.py](../agent/main.py) 从 Redis 就绪列表取进程，执行一个节点后保存 Workflow 运行值和当前位置，并根据状态重新调度。

运行时和设计规范的主要边界：

| 事项 | 设计规则与实际含义 |
| --- | --- |
| 循环 | 允许 foreach / while_pop 体末回所属 loop-in；移除合法回边后其余图仍须为 DAG |
| 分支 | 控制树不能汇合，不能共享后继或 output；foreach / while_pop 内不能直接放 router/json_tool/foreach/while_pop |
| 分支后的统一步骤 | 把分支整体封装为子 workflow，各分支独立 output，父图调用后继续单一控制链 |
| 数据生命周期 | 祖先可向子层供值，子层不能向外直连；循环聚合通过 Context 写入，再在外层重新读取 |
| 子图交付 | workflow_nodes 只有名称和接口快照，不能携带子图定义；必须另外保存每份子图 |
| 进程入口 | 创建接口使用真实工作区 workflow_file_id 和 inputs，不依赖事件绑定 |
| 模型 | llm.model 是启用模型的真实 Mongo 注册 ID，没有默认模型或动态模型输入端口 |
| 跨事件状态 | Context 随 invocation 清理；Session 可跨调用持久化，但读写不是原子事务 |
| 异步工具回调 | Tool Server 的独立回调 outbox 保留；Agent 调度器没有自动消费该队列，不能宣称会恢复原图 |

类型和节点语义的主要依据是 [Workflow 2.0 协议](protocol/workflow_2_0.md)、[机器 Schema](../agent/workflow_2_0.schema.json)、[节点契约](../agent/workflow_contract.py)、[Struct 实现](../agent/workflow_structs.py) 与上述校验器/执行器。工具目录分别来自 [Local 注册表](../agent/tools/tool.py)、[工作区 Local 工具](../agent/tools/workspace.py)、[Remote 工具实现](../tool_provider/tools/)；回调限制依据 [Tool Server callback_event/callback_worker](../tool_server/main.py)，不是仅由协议文档推测。

## 输出和落地

为了让一次 JSON 包含全部新建依赖，skill 默认输出固定设计信封：

```json
{
  "format": "aagent.workflow-design/1",
  "status": "ready",
  "entrypoint": "main.flow",
  "workflows": [
    {"filename": "child.flow", "workflow": {}},
    {"filename": "main.flow", "workflow": {}}
  ],
  "errors": []
}
```

这里的空对象仅表示完整原生图的位置，不能作为可执行示例；可执行的完整示例都在 skill 中。这个信封是新增的交付约定，后端不直接接受它。真正提交后端的仍是每一项 workflow 原生对象。用本地脚本完成校验和拆分：

```powershell
python skills/workflow-designer/scripts/validate_design.py result.json
python skills/workflow-designer/scripts/validate_design.py result.json --output-dir tmp/generated-flows
```

输出目录必须尚不存在，以免覆盖文件。脚本不联网、不创建进程、不写入在线工作区。它复用 Agent 原生静态校验器，并额外检查本 skill 的禁止节点、必要数据输入、数据执行顺序、完整依赖、三方接口快照、依赖 DAG、模型 ID 格式、文件名和大小限制；不能证明模型真实启用、工具参数符合在线 schema、Provider 在线或所有运行值均有效。

保存工作区时，按 workflows 顺序依次调用现有 POST /api/files，body 为 {"name": filename, "content": 原生workflow的JSON字符串}，或通过现有工作区界面创建对应文件；全部依赖保存完再运行入口。该 API 返回的 file_id 才是创建进程时应使用的真实 workflow_file_id。本地拆出的文件尚未自动进入 Mongo 工作区。

如果必须只收原生单图 JSON，可以在用户指令中明确覆盖信封格式，但这只适用于无需新建依赖的需求；要交付新建依赖，必须保留多文件交付或由调用方另行接收并保存子图，不能往原生 workflow 根对象里塞未支持的字段。

需要 llm 节点时，用户输入须带真实启用模型注册 ID，或在部署时把该固定 ID 预置进 skill。未配置时设计器返回 status=error、code=MISSING_MODEL_ID；不输出占位图。常规业务值可以声明为运行时接口，不要求用户在设计阶段填写全部值。

## 验证

```powershell
python -m unittest discover -s skills/workflow-designer/scripts -p "test_*.py" -v
```

测试直接提取 skill 中的完整示例，验证它们能通过 Agent 和管理端校验并被编译；使用真实执行器检查子图分支返回、foreach 空/非空列表聚合，以及按进程终端 ID 写入包含引号/换行/反斜杠的文本。Redis、工作区读取与运行日志在执行测试中使用替身，不验证线上部署。

正例覆盖 while_pop 的 Context 输入与合法回边；负例覆盖 foreach 内 JSON Tool、分支共用 Output、缺失依赖、接口快照过期、递归依赖、数据先用后产出、必需输入未连、Router 内部兜底键冲突、模型 ID 缺失、重复 JSON 键、NaN 和导出覆盖保护。

## checkpoint 恢复

工作区 checkpoint 工具保留，可由工作流显式调用。恢复会覆盖整个工作区文件并更新 revision，后续修改须重新读取文件。进程创建与终端均不使用事件绑定；错误不会通过旧事件队列自动启动恢复工作流。
