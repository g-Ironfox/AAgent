# Workflow 动态端口改动记录

## 目标

Workflow 管理页中的 Input / Output 字段不再只是描述性元数据。

保存字段后，它们会直接成为 Workflow 编辑器中 Input 和 Output 节点的真实数据端口，并参与连线校验、Workflow 解析和运行时数据传递。

## 管理页

- Workflow 详情支持编辑 Input 字段和 Output 字段。
- 每个字段包含：
  - `name`：字段名。
  - `type`：`content`、`message`、`list-content` 或 `list-message`。
- 已移除“必填”概念及其 `required` 字段。
- 字段名必须非空，且同一侧的字段名不能重复。
- Workflow 的稳定标识仍是 `key`，重命名仅修改展示名称。

## 数据存储

Workflow 文档新增两个元数据字段：

```json
{
  "input_ports": [
    {
      "name": "query",
      "type": "content"
    }
  ],
  "output_ports": [
    {
      "name": "answer",
      "type": "content"
    }
  ]
}
```

保存元数据时，服务端会同步更新所有 Input / Output 节点的 `workflowPorts`。动态端口使用命名空间 ID，避免与历史端口冲突：

```json
{
  "id": "workflow:query",
  "name": "query",
  "type": "content"
}
```

## 编辑器行为

- Input 节点将 `workflowPorts` 渲染为数据输出端口。
- Output 节点将 `workflowPorts` 渲染为数据输入端口。
- 端口显示名称和悬浮提示均使用字段名。
- 端口类型决定可连接的数据类型。
- Input 的 `control-out` 和 Output 的 `control-in` 控制端口不受影响。
- 字段删除、重命名或改变类型时，服务端会自动移除不再有效的数据连接。

## 严格格式

- 顶层 `input_ports` / `output_ports` 是 Input / Output 数据端口的唯一权威定义，两个字段都必须存在且为数组。
- Input / Output 节点的 `workflowPorts` 是由顶层 Meta 生成的标准快照，必须与对应 Meta 完全一致。
- 边界数据端口统一使用 `{id, name, type}`，其中 `id` 固定为 `workflow:<name>`。
- 不再接受 Input 的 `content-out`、`source` 或 Output 的 `content-in` 旧边界端口。
- 独立编辑器导入缺少顶层 Meta 的旧文件时，会生成空边界端口并丢弃旧边界数据连接；控制连接不受影响。

## 校验与运行时

Workflow 校验器会检查：

- `workflowPorts` 必须是数组。
- 每个端口必须包含唯一的名称和 ID。
- ID 必须是 `workflow:<字段名>`。
- 类型必须是支持的数据类型。
- 动态 Input / Output 端口上的连接类型必须与端口类型一致。
- 节点 `workflowPorts` 必须与顶层 Meta 生成结果完全一致。

运行时行为：

- Workflow Input 节点从事件 `payload` 中按字段名读取值，并从对应动态端口向后传播。
- Workflow Output 节点按字段名读取已连接的输入，组合为输出对象。
- 若 Output 存在名为 `content` 的字段，响应仍使用该字段作为 `payload.content`。
- 若没有 `content` 字段，响应的 `payload.content` 为整个输出对象。
- 缺少顶层 Meta、缺少节点端口快照或使用旧边界端口的 Workflow 会被校验器拒绝。

## 涉及文件

- `webui_py/workflows.py`：元数据 API、端口同步和失效连接清理。
- `webui_py/static/workflows.html`、`workflows.js`、`css/workflows.css`：管理页字段编辑。
- `webui_py/static/workflow/model.js`、`view.js`：编辑器端口归一化、渲染和连接过滤。
- `agent/workflow_contract.py`：节点数据端口契约。
- `agent/workflow_validator.py`：动态端口与连接类型校验。
- `agent/workflow_parser.py`：解析时保留端口定义并生成端点。
- `agent/task_worker.py`：动态输入读取和动态输出组装。

## 已完成检查

- 修改后的 Python 文件通过语法检查。
- 管理页和编辑器相关 HTML、CSS、JavaScript 未发现编辑器诊断错误。
- 已验证标准动态端口通过、错误类型和旧边界端口拒绝、Meta 与节点快照不一致拒绝、显式空端口四类场景。
- Validator 独立运行验证已通过；完整回归测试仍需项目运行环境提供 `pymongo` 等依赖。
