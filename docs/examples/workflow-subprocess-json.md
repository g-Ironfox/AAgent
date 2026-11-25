# JSON 子流程调用示例

这些 2.0 示例可在 Workflow 编辑器中导入，不需要模型、工具或外部服务。

- [workflow-subprocess-child.flow](workflow-subprocess-child.flow)：接收 name，返回 reply 问候语。
- [workflow-subprocess-parent.flow](workflow-subprocess-parent.flow)：接收目标文件名及参数 JSON，等待子进程，解析返回 JSON。

## 终端交互版本

使用 [workflow-subprocess-terminal.flow](workflow-subprocess-terminal.flow) 和上面的子流程文件。

1. 将两个文件保存到 Agent WebUI 工作区，子流程文件名保留为 workflow-subprocess-child.flow。
2. 创建 workflow-subprocess-terminal.flow 的进程，创建时无需传入接口参数。
3. 向父终端发送一条消息（提前发送也会缓冲）：

```json
{"name":"小明"}
```

4. 父终端打印 `你好，小明！`，随后流程结束。每次运行处理一条消息。

父流程先输出提示，再通过 read_terminal_queue 消费当前终端进程的未读消息；队列为空时挂起，收到消息后重试读取。list_get 使用固定索引 -1 取得本批次最后一条消息，接到调用节点的 arguments-json。固定子流程文件名由 construct_content 输出到 workflow-file。

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

## 子进程报错后由父进程处理

将 [workflow-subprocess-error-parent.flow](workflow-subprocess-error-parent.flow) 和 [workflow-subprocess-error-child.flow](workflow-subprocess-error-child.flow) 保存到工作区，保留文件名。创建父流程进程，无需创建时参数；终端出现提示后发送：

- `{"name":"小明"}`：子流程打印 name 并返回问候语，父终端打印 `你好，小明！`。
- `{"name":""}`：子流程的 output_to_terminal 拒绝空文本并报错退出。父流程被唤醒，从 error-out 继续，提取 error-json 中的 error 字段并在父终端打印；父流程处理后可以正常完成。
- `not json` 或 `[]`：参数不是有效 JSON 对象，父流程直接打印错误，不创建子进程。
- `{"name":123}` 或 `{"unknown":"小明"}`：参数类型或名称不符合子流程输入接口，直接进入错误分支。
- 将父流程中“子流程文件名”的固定文本临时改成工作区不存在的 `Missing.flow`：文件加载失败也会进入错误分支。

每次运行处理一条消息。失败时 error-json 的结构为：

```json
{"workflow_file":"workflow-subprocess-error-child.flow","process_id":"<child-id>","status":"failed","error":"output_to_terminal content-in requires non-empty text"}
```

error-json 和 result-json 都是 content 文本，分别只在错误和成功分支提供。本例用独立 Output 结束各分支；child_result_json 在成功时保留结果 JSON，错误时保留错误 JSON，reply 则保留问候语或错误文本。若不连接 error-out，调用前错误或子进程失败仍会使父进程失败。子进程被终止时也可进入错误分支，status 为 terminated。

调用前错误沿用相同结构，process_id 为 null，status 为 failed。例如参数类型不匹配：

```json
{"workflow_file":"workflow-subprocess-error-child.flow","process_id":null,"status":"failed","error":"$.name: expected content"}
```

调用前错误直接选择错误后继，不创建子进程或 pending_call。已创建的子进程退出时，恢复过程清除 pending_call 并执行选定后继，不会重复创建子进程。
