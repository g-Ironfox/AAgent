# ReAct + Human-in-the-Loop

`react-human-in-loop.flow` 是可导入的 Workflow 2.0 工作流，复用现有函数、Context、While Pop 和终端节点，不修改协议或运行时规则。

## 使用

1. 将 `.flow` 导入工作区，在编辑器中为 `Reason and propose` 节点选择已启用的模型，替换 `REPLACE_WITH_MODEL_ID`。
2. 创建该工作流的进程，传入 `task`（content），例如“排查这个任务为什么失败，逐步提出检查动作”。
3. 在进程终端查看模型提议。人工执行动作后发送观察结果，或者发送拒绝原因、修正建议，进入下一轮。
4. 在终端显示等待输入后发送准确的 `DONE`，结束进程。无需再调用模型；最后一轮响应保留在终端中。工作流没有数据输出端口。

这个版本由人执行行动、提供观察，模型负责结合历史提出下一步。工作流不会自动调用模型提议的工具。普通回复仅表示反馈，不会被解释为执行工具的授权。每次等待后读取该终端最新一条用户消息；建议一轮发送一条完整反馈。

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
读取历史 → LLM → 保存 assistant 消息 → 终端展示 → 等待人工输入
  → 读取最新回复 → Router
      DONE → function_output
      其他 → 保存 user 观察 → 队列追加一个 token → function_output
```

每轮开始，While Pop 已经取走 token。继续分支补回一个 token；结束分支不补回。两个分支都返回函数，主循环都从同一条 `loop-in` 继续，队列为空时自然结束。循环体中没有 Router、分支汇合或跨作用域数据连线。

对话消息按当前协议保存为 `list-content` 中的 JSON 字符串。历史在等待前写入 Context；等待由进程调度器持久化，保留函数栈，人工回复后继续执行。Context 随进程终态清理。运行时原有的累计执行时间限制仍适用，等待人工输入的时间不计入其中。

## 验证

在 `agent` 目录运行：

```powershell
python -m unittest test_react_workflow test_workflow_functions test_workflow_lifecycles -v
```

测试复用实际调度器及内存 Redis，模拟模型和终端存储，覆盖多轮反馈、拒绝、函数内挂起与恢复、首轮结束，以及结束后不额外请求模型。没有调用真实模型或外部工具。
