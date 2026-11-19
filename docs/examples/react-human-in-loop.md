# ReAct + Human-in-the-Loop

`react-human-in-loop.flow` 是可导入的 Workflow 2.0 工作流，复用现有函数、Struct、Context、While Pop、JSON Tool 和终端节点，不修改协议或运行时规则。现在支持模型原生 `tool_calls` 和人工审核后执行工具。

## 使用

1. 将 `.flow` 导入工作区，在编辑器中为 `llm` 节点选择支持工具调用的已启用模型，替换 `REPLACE_WITH_MODEL_ID`。
2. 创建该工作流的进程，传入 `task`（content），例如“排查这个任务为什么失败，逐步提出检查动作”。
3. 在进程终端查看请求。工具请求会展示完整的 `id`、工具名及参数；等待输入后回复准确的 `APPROVE` 才执行当前这一条。每条调用单独审核，包括同一轮的多个调用。
4. 回复其他文字（包括小写 `approve`）会拒绝当前工具调用，并将文字反馈给模型。模型没有请求工具时，普通回复作为 user observation 进入下一轮。
5. 回复准确的 `DONE` 结束进程。当前请求及该轮尚未执行的调用都不会执行，也不会再请求模型。之前已执行的工具操作不会撤销。工作流没有数据输出端口，响应与工具执行结果显示在终端。

示例默认向模型提供两个已存在的 Local Tool：`workspace.list_files` 和 `workspace.get_file`。运行环境需要注册这些工具。可以通过编辑器维护 `metadata.tools`，同时更新 LLM 节点的 `tools` 列表；Remote Tool 也使用已有 JSON Tool / Tool Server 同步调用路径。工具目录和模型调用协议继续由原有节点检查。

`APPROVE` 仅批准终端当前显示的工具名和参数。普通回复不会触发工具执行。每次等待后读取该终端最新一条用户消息；一轮应发送一条完整反馈，等下一条审核提示再提交新的决定。

## 控制流

主流程只初始化一次对话历史和轮次队列，队列初始有一个 token：

```text
初始化历史和队列
  → while_pop
      loop-out → function_call(react_turn) → loop-in
      control-out → output
```

`react_turn` 的两个输入是历史 Context ID 和轮次队列 Context ID。函数内部具有独立的生命周期空间，可以使用 Router：

```text
读取历史 → LLM → 保存完整 assistant 消息 → Router
  无工具 → 展示回答 → 等待人工反馈
      DONE → function_output
      其他 → 保存 user 观察 → 排入下一轮 → function_output
  有工具 → foreach(tool_calls)
      → function_call(review_tool) → loop-in
      → 检查停止状态 → 结束或排入下一轮 → function_output
```

`review_tool` 内部展示调用并等待人工回复；只有 `APPROVE` 分支调用 `execute_reviewed_tool`。执行函数内部用 `json_tool` 的成功/失败出口分别返回结果或错误 JSON。成功、失败、拒绝和取消均由 `record_tool_result` 写为带匹配 `tool_call_id` 的 tool 消息。`DONE` 设置本轮停止标志，剩余调用只记录取消，不再提示或执行。

每轮开始，While Pop 已取走 token。继续时 `queue_turn` 补回一个 token；结束时不补回。各路径都通过函数返回，主循环从同一条 `loop-in` 继续，队列为空时自然结束。主循环及工具 foreach 循环的循环体均只有函数调用，没有直接放 Router、分支汇合或跨作用域数据连线。

对话消息按当前协议保存为 `list-content` 中的 JSON 字符串。`build_assistant` 用 Struct 将调用列表恢复为对象数组，保留调用 ID、原始 JSON 参数和 `reasoning_content`，避免把原生调用错误保存为字符串数组。工具调用常见的 `content: null` 会在工作流中规范化为空字符串；无工具时仍使用普通 assistant 消息。

历史在等待前写入 Context；调度器持久化进程与函数栈，人工回复后从等待节点之后继续执行。Context 随进程终态清理。原有累计执行时间限制仍适用，等待输入时间不计入其中。沿用项目当前的持久化能力，不额外提供运行中的进程崩溃后自动恢复或外部副作用恰好执行一次的保证。

`tool call count`（节点 ID `turn_count`）统计本轮 `tool_calls` 数量，不是对话轮数。长度输出是 `number`，通过 `ToolCallCount` Struct → `struct_to_json` → `deserialize_json` 提取为 `content` 后再交给 Router 判断 `0`。`build_count` 使用同样的转换，避免把 `number` 直接接到 `construct_content` 时被编辑器过滤掉连线。

## 维护定义

该图包含多个复用函数。源码生成器位于 `scripts/build_react_workflow.py`，可修改后重新生成 `.flow`：

```powershell
python scripts/build_react_workflow.py
```

生成器会覆盖示例 `.flow`。在编辑器中定制模型或工具后的文件，应另存为工作区文件，或同步修改生成器。

## 验证

在 `agent` 目录运行：

```powershell
python -m unittest test_react_workflow test_workflow_functions test_workflow_lifecycles -v
```

测试复用实际调度器及内存 Redis，模拟模型、工具和终端存储，覆盖多轮反馈、审核前不执行、准确批准、拒绝、工具失败与错误参数、原生调用历史、函数内挂起与恢复，以及批量调用中途结束。没有调用真实模型或外部工具。

编辑器导入导出回归测试（仓库根目录）：

```powershell
node --test workflow_editor/test_react_workflow.mjs
```

该测试检查示例导入后所有连线保留，且导出后可再次导入。
