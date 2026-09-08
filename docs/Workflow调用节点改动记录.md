# Workflow 调用节点改动记录

## 目标

允许一个 Workflow 在另一个 Workflow 的画布中作为节点被调用。调用方可以从元数据中选择已存在的 Workflow，将其作为 `workflow` 节点加入画布，并通过动态输入/输出 Port 传递数据。

本次实现覆盖管理页、编辑器、保存校验、解析器和任务执行器。

## 元数据与引用

每个 Workflow 增加以下元数据：

```json
{
  "input_ports": [
    {"name": "query", "type": "content"}
  ],
  "output_ports": [
    {"name": "result", "type": "content"}
  ],
  "workflow_nodes": [
    {
      "workflow_id": "目标 Workflow ID",
      "name": "目标 Workflow 名称",
      "input_ports": [{"name": "query", "type": "content"}],
      "output_ports": [{"name": "result", "type": "content"}]
    }
  ]
}
```

`workflow_nodes` 是当前 Workflow 被允许调用的目标列表。保存元数据时，服务端读取目标 Workflow，并快照其名称和端口契约。

引用限制：

- 同一个目标 Workflow 不能重复引入。
- Workflow 不能引入自身。
- 被引用的 Workflow 必须存在。
- 输入 Port 与输出 Port 分别不能重名。
- Port 名称按去首尾空格、忽略大小写比较；例如 `Result`、`result`、` result ` 视为重名。
- 输入和输出可以使用相同名称，因为两者由端口方向区分。

## 画布节点

编辑器节点类型新增 `workflow`：

```json
{
  "id": "workflow-...",
  "type": "workflow",
  "name": "Summary",
  "workflow_id": "目标 Workflow ID",
  "workflow_name": "Summary",
  "input_ports": [{"name": "query", "type": "content"}],
  "output_ports": [{"name": "result", "type": "content"}]
}
```

节点端口规则：

- 固定控制输入：`control-in`
- 固定控制输出：`control-out`
- 每个调用输入：`workflow:<输入 Port 名称>`
- 每个调用输出：`workflow:<输出 Port 名称>`

例如 `query` 输入和 `result` 输出分别映射为 `workflow:query` 与 `workflow:result`。

Workflow 节点仅可使用元数据中已引入 Workflow 的快照契约。保存画布时，后端会校验节点的 `workflow_id`、名称及输入/输出 Port 是否与当前元数据一致。

## 编辑器与 UI

管理页增加“引入 Workflow 为节点”列表。选中的目标会写入 `workflow_nodes` 元数据。

编辑器左侧节点库动态显示已引入的 Workflow。点击条目会创建对应的 `workflow` 节点。

Workflow 节点使用与其他节点相同的布局、默认宽度、标题字体、端口字体和检查器契约样式，仅通过紫色顶边和 `WF` 图标区分类型。

### 同名端口连线

输入和输出可以同名，因此同一个节点可能同时存在两个 `workflow:content` Port。连线坐标定位已改为同时按 Port ID 和方向查找：

- 连线起点固定查找 `output` Port。
- 连线终点固定查找 `input` Port。
- 拖动预览按照当前锚点方向查找。

这样同名的输入/输出 Port 不会互相误选，连线始终吸附到正确一侧。

画布尺寸改为根据节点实际渲染宽高计算，端口数量较多的节点不会被右侧或底部裁切。

## 元数据同步

更新 Workflow 元数据时，服务端会同步现有画布：

- Input 节点的 `workflowPorts` 跟随输入契约更新。
- Output 节点的 `workflowPorts` 跟随输出契约更新。
- 删除或改类型后的元数据 Port 会移除对应失效数据连线。
- 取消引入 Workflow 时，会删除对应的 `workflow` 节点及其所有连线。
- 被引入 Workflow 的名称或 Port 契约变化时，会刷新调用节点的快照，并移除不再有效的连线。

## 校验与解析

`agent/workflow_contract.py` 将 `workflow` 声明为支持的节点类型，并提供动态输入/输出 Port 集合。

`agent/workflow_validator.py` 校验：

- `workflow_id` 存在。
- `input_ports` 和 `output_ports` 为合法列表。
- 每个 Port 有名称和受支持的数据类型。
- 输入与输出分别不存在重复名称。
- Workflow 节点连线的 Port 和数据类型与契约一致。

`agent/workflow_parser.py` 会把动态 Port 编译到 `data_inputs` 和 `data_outputs`，连接关系保持为节点索引与 Port ID。

## 嵌套运行

任务执行器新增 `workflow_workflow` 处理器。

执行步骤：

1. 从父 Workflow 节点读取 `workflow_id`。
2. 加载、校验并解析目标 Workflow。
3. 比对目标 Workflow 当前契约与调用节点快照；不一致时拒绝执行并提示刷新元数据。
4. 将调用节点的数据输入写入子 Workflow 的 Input 节点。
5. 启动子 Workflow 的控制流。
6. 子 Workflow 到达 Output 时，将每个输出按同名 `workflow:<名称>` 写回父节点。
7. 子 Workflow 结束后，发布父节点的 `control-out`，继续父 Workflow。

执行器维护 `_workflow_call_stack`。若目标 Workflow 已在调用栈中，会拒绝本次调用，避免直接或间接递归。

子 Workflow 的 Input / Output 端口只由其顶层 `input_ports` / `output_ports` 生成。运行时不再兼容 `content-out`、`source`、`content-in` 等旧边界端口；缺少 Meta 或标准 `workflowPorts` 快照的子 Workflow 会在执行前校验失败。

## 主要文件

- `webui_py/workflows.py`：元数据 API、引用快照、同步与保存校验。
- `webui_py/static/workflows.html`、`webui_py/static/workflows.js`：引入 Workflow 的管理页 UI。
- `webui_py/static/workflow_edit.html`、`webui_py/static/workflow.js`：动态节点库与检查器模板。
- `webui_py/static/workflow/model.js`：Workflow 节点序列化、读取与连接恢复。
- `webui_py/static/workflow/view.js`：节点端口和检查器渲染。
- `webui_py/static/workflow/connections.js`：同名双向 Port 的连线坐标消歧。
- `agent/workflow_contract.py`：动态 Port 定义。
- `agent/workflow_validator.py`：节点和端口契约校验。
- `agent/workflow_parser.py`：动态 Port 编译。
- `agent/task_worker.py`：子 Workflow 调用、返回和递归保护。
- `agent/test_workflow_node.py`：动态 Port、类型校验、输入/输出重名规则的回归测试。

## 验证状态

已完成：

- 修改文件的 VS Code 静态诊断。
- Python 文件语法检查。
- `git diff --check` 空白检查。
- 回归测试文件已加入，覆盖 Workflow 节点动态 Port 映射、错误数据类型、输入/输出 Port 重名与输入输出同名合法的场景。

未完成：

- `agent/test_workflow_node.py` 完整测试尚未实际运行；Validator 的标准端口、旧端口拒绝和 Meta 不一致拒绝已独立运行验证。
- 未进行浏览器端交互截图或端到端嵌套调用验证。
