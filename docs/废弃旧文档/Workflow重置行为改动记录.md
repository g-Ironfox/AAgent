# Workflow 编辑器重置改动

日期：2026-08-26

## 改动内容

Workflow 编辑器的“重置”不再重新请求或恢复数据库中已保存的画布。

点击重置后，画布会恢复为内置初始模板：

- 一个 `Input` 节点。
- 一个 `Output` 节点。
- 一条 `Input.control-out -> Output.control-in` 控制流连接。
- 不包含 Router、LLM、构造节点或任何数据连接。

重置只改变浏览器内的画布状态，并将编辑状态标记为“未保存”。只有用户随后点击“保存”时，初始模板才会写入数据库。

## 端口元数据

初始模板不定义 Input 和 Output 的数据端口，因为这些端口由当前 Workflow 的元数据决定：

- `input_ports` 会转换为 Input 节点的 `workflowPorts`。
- `output_ports` 会转换为 Output 节点的 `workflowPorts`。
- 动态端口 ID 为 `workflow:<端口名称>`。

重置时，编辑器调用 `resetWorkflow(currentWorkflow)`，将当前已加载 Workflow 的元数据传入快照归一化逻辑。因此，重置后节点会继续显示当前 Workflow 的动态数据端口，但不会自动建立任何数据连接。

这保证不同 Workflow 可以拥有不同的输入和输出契约，内置模板不会错误假设存在 `content`、`source` 或其他固定数据端口。

## 边界

重置不会重新下载数据库数据，使用的是当前编辑页内存中的 `currentWorkflow.input_ports` 和 `currentWorkflow.output_ports`。

若端口元数据在其他标签页或其他客户端被修改，当前页面需重新加载 Workflow 或刷新页面，才能获得外部更新后的端口契约。

## 涉及文件

- `webui_py/static/workflow/model.js`
- `webui_py/static/workflow.js`