# JSON 子流程调用示例

这些 2.0 示例可在 Workflow 编辑器中导入，不需要模型、工具或外部服务。

- [workflow-subprocess-child.flow](workflow-subprocess-child.flow)：接收 name，返回 reply 问候语。
- [workflow-subprocess-parent.flow](workflow-subprocess-parent.flow)：接收目标文件名及参数 JSON，等待子进程，解析返回 JSON。

## 终端交互版本

使用 [workflow-subprocess-terminal.flow](workflow-subprocess-terminal.flow) 和上面的子流程文件。

1. 将两个文件保存到 Agent WebUI 工作区，子流程文件名保留为 workflow-subprocess-child.flow。
2. 创建 workflow-subprocess-terminal.flow 的进程，创建时无需传入接口参数。
3. 父终端显示输入提示并进入等待后，发送一条消息：

```json
{"name":"小明"}
```

4. 父终端打印 `你好，小明！`，随后流程结束。每次运行处理一条消息。

父流程先输出提示，再通过 wait_terminal_event 等待消息。read_terminal_input 返回当前终端的全部用户输入，list_get 使用固定索引 -1 取得最后一条消息，接到调用节点的 arguments-json。固定子流程文件名由 construct_content 输出到 workflow-file。

子流程仍通过 Input 接收 name、通过 Output 返回 reply。父流程用 deserialize_json 取出 reply，再通过 output_to_terminal 打印到父终端，同时保留进程结果。终端消息用于用户交互，父子进程之间通过调用节点的 JSON 端口传递参数和结果。

## 接口传参版本

1. 在 Agent WebUI 的工作区保存这两个文件，保留上述文件名及 .flow 扩展名。可以通过编辑器导入查看或修改节点。
2. 创建 workflow-subprocess-parent.flow 的进程，输入值如下：

```json
{
  "child_file": "workflow-subprocess-child.flow",
  "arguments_json": "{\"name\":\"小明\"}"
}
```

arguments_json 是 content 文本。在输入框中直接填写下面的 JSON 文本；只有把它嵌入上面的整个输入对象时，才需要对内层双引号转义：

```json
{"name":"小明"}
```

3. 查看父进程结果，预期为：

```json
{
  "reply": "你好，小明！",
  "child_result_json": "{\"reply\":\"你好，小明！\"}"
}
```

reply 是解析出的字段，child_result_json 是子流程返回的完整 JSON 文本。本例的输出记录在进程结果中，若需显示到终端，可将 reply 接到 output_to_terminal 节点。

## 节点连接

父流程控制线：Input → 拉起并等待子进程 → deserialize_json → Output。

| 数据来源 | 数据目标 |
| --- | --- |
| Input.child_file | 调用节点.workflow-file |
| Input.arguments_json | 调用节点.arguments-json |
| 调用节点.result-json | deserialize_json.content-in |
| 调用节点.result-json | Output.child_result_json |
| deserialize_json.reply | Output.reply |

子流程控制线：Input → construct_content → Output。construct_content 将固定文本“你好，”、输入 name 和固定文本“！”拼接后，输出到 reply。

目标文件名是工作区中的精确文件名，不填写本仓库的 docs/examples/ 路径。参数 JSON 的键必须对应子流程声明的输入接口。调用节点使用空 arguments，无需任何子 workflow metadata 声明。

父流程等待时保存 pending_call；子流程结束后写入结果并从调用节点的后继继续，不会重新执行调用节点。若不需要拆解返回对象，可以省略 deserialize_json，直接使用 result-json。
