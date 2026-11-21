# ALFWorld 最小 ReAct Workflow

[alfworld-react.flow](alfworld-react.flow) 可直接导入工作流编辑器，基于 [alfworld-look.flow](alfworld-look.flow) 的终端协议实现。每条有效观察触发一次模型调用，形成 Observation → Reasoning + Action → 环境执行 → 下一条 Observation 的循环。

## 使用

1. 在 Agent WebUI 工作区导入 `docs/examples/alfworld-react.flow`。
2. 打开 `decide` LLM 节点，将 `REPLACE_WITH_MODEL_ID` 换成模型管理中已启用的模型 ID，然后保存。
3. 在 Benchmark 控制台选择保存的 Workflow，发布 ALFWorld 测试。Workflow inputs 保持 `{}`；观察由执行器写入终端。

也可以生成已绑定模型的文件，再导入：

```powershell
python scripts/build_alfworld_workflow.py --react --model-id <模型ID> --output tmp/alfworld-react.flow
```

不传模型 ID 时会生成带占位符的示例。以下命令重新生成仓库中的默认 ReAct 示例：

```powershell
python scripts/build_alfworld_workflow.py --react
```

原来的不带 `--react` 的生成方式继续支持固定 look 和仅输出动作的模型流程。

## 每轮行为

主流程初始化系统提示词、对话历史 Context 和单个循环 token。每轮在函数 `alfworld_turn` 中执行：

```text
read_terminal_queue → 取最新观察 → 解析 episode_id / step / done
  done=true  → 返回，不补回 token，主循环结束
  done=false → 添加 user 观察 → LLM（think=true）
             → 保存 assistant 的 content 和 reasoning_content
             → 将 content 封装为动作 JSON → output_to_terminal → 补回 token
```

直接使用 LLM 节点现有的两个输出端口：

- `decide.output`：模型最终回复，只包含一条 ALFWorld 命令，例如 `open cabinet 1`。连接到 assistant 的 `content-in` 和动作 Struct 的 `text` 字段。
- `decide.reasoning`：模型返回的推理内容，连接到 assistant 的 `reasoning-in`，以 `reasoning_content` 随历史保留，不发送给环境。

例如，保存到历史的 assistant 消息为：

```json
{"role":"assistant","content":"open cabinet 1","reasoning_content":"The mug may be inside cabinet 1; inspect it."}
```

环境只收到由 Struct 节点序列化的动作：

```json
{"type":"action","episode_id":"e1","step":0,"text":"open cabinet 1"}
```

模型正文无需输出 JSON，也不需要自行输出 `thought` 字段。旧版的 `parse_decision` 节点已经移除，避免把普通命令或额外文字作为 JSON 解析导致失败。模型正文仍应遵守系统提示词，只返回一条命令；此版本未加入命令格式修复或自动重试。

`episode_id` 和 `step` 回传当前观察值，下一条观察作为 user 消息继续推理。收到 `done=true` 时，不再调用模型或输出动作，包括执行器因步数上限或错误而发送的结束观察。

`think=true` 使用仓库现有的模型推理调用路径；实际是否返回 reasoning 取决于模型及其配置。模型返回空 reasoning 时流程仍能执行并保留动作历史。每轮只执行一个动作，保留完整历史，没有历史裁剪。终端协议与启动方式见 [ALFWorld 执行器](../../alfworld_runner/README.md)。

## 验证

```powershell
python -m unittest discover -s agent -p test_alfworld_workflow.py -v
node --test workflow_editor/test_alfworld_workflow.mjs
```

测试使用真实工作流调度器、内存 Redis 和模拟模型，覆盖原生 reasoning 的多轮历史、动作封装、等待观察、结束信号和空 reasoning，并检查编辑器导入导出保留全部连线。测试不代表真实 ALFWorld 解题成功率。


## 三段工作流与经验迭代

需要固定引导、异常时逐版本回退和跨 episode 经验学习时，可使用 [ALFWorld 三段工作流](alfworld-agent/README.md)。执行 `python scripts/install_alfworld_workflows.py --model YOUR_MODEL_ID --install` 一次安装并绑定权限，在 Benchmark 中选择返回的 bootstrap 文件 ID，inputs 填 `{}`。引导负责终端收发，主流程逐轮返回动作；runner 会等待结束后的经验迭代完成再开始下一轮。
