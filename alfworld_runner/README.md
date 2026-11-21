# ALFWorld 执行器

`environment.py` 管理 ALFWorld 0.4.2 / TextWorld 1.7.0 的纯文本环境和数据下载，`runner.py` 执行逐轮评测，`client.py` 使用现有 webui_py 的 HTTP 终端接口与 Workflow 通信。`benchmark_worker` 复用这些模块，并将轨迹写入 MongoDB。

现在使用 `benchmark_worker` 和 `benchmark_webui` 两个 Compose 服务，启动步骤、页面、队列与存储说明见 [Benchmark 控制台](../benchmark_webui/README.md)。原先的 `alfworld` 服务已替换，命名数据卷 `alfworld_data` 继续复用。

```text
ALFWorld reset/step → POST /api/terminal → Workflow read_terminal_queue
ALFWorld step      ← GET /api/terminal/output ← Workflow output_to_terminal
```

## 数据与流程

```powershell
docker compose --profile benchmark build benchmark_worker benchmark_webui
docker compose --profile benchmark run --rm --no-deps benchmark_worker download
docker compose --profile benchmark run --rm --no-deps benchmark_worker smoke
```

`download` 只下载 JSON、PDDL 和预生成的 TextWorld 文件，跳过视觉检测器和预训练模型，后续复用数据卷。`smoke` 执行一次真实 reset 和 look，无需模型或后端。

`docs/examples/alfworld-look.flow` 为固定执行 look 的通信示例。模型流程可用以下脚本生成，再导入 WebUI 工作区：

```powershell
python scripts/build_alfworld_workflow.py --model-id <模型ID> --output tmp/alfworld-agent.flow
```

模型 ID 与工作区 Workflow 文件 ID 不同。模型凭证仍由现有 Agent 使用。生成流程保留完整多轮 Context，收到 done 时退出。

最小 ReAct 示例可直接导入 `docs/examples/alfworld-react.flow`，将 `decide` 节点的模型占位符替换为已启用的模型 ID；也可以生成已绑定模型的版本：

```powershell
python scripts/build_alfworld_workflow.py --react --model-id <模型ID> --output tmp/alfworld-react.flow
```

该流程启用 LLM 节点的原生 `reasoning`，将推理与动作一并保存到历史，模型正文只输出一条 ALFWorld 命令并封装后发送给环境。使用说明和限制见 [ALFWorld 最小 ReAct](../docs/examples/alfworld-react.md)。

## 独立 CLI

`main.py` 保留 download / smoke / run 子命令。以下命令绕过 benchmark 队列，直接调用已有后端，结果写到宿主机文件：

```powershell
docker compose --profile benchmark run --rm --no-deps --entrypoint python -v ./data/alfworld/results:/results benchmark_worker -m alfworld_runner.main run --workflow-file-id <工作区文件ID> --episodes 1 --max-steps 2
```

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| --split | valid_unseen | train / valid_seen / valid_unseen |
| --episodes | 1 | 顺序运行的 episode 数，不能超过 split 游戏数量 |
| --max-steps | 50 | 每轮动作上限 |
| --seed | 42 | 随机种子，输入游戏文件先排序 |
| --action-timeout | 180 | 每次等待动作的秒数 |
| --startup-timeout | 60 | 等待终端建立的秒数 |
| --poll-interval | 0.5 | 输出轮询间隔，秒 |
| --admissible-commands | 关闭 | 提供合法动作列表，会改变测试条件 |
| --inputs | {} | Workflow 创建输入 JSON 对象 |
| --api-url | http://webui_py:8081 | 后端地址 |
| --results-dir | /results | 结果文件目录 |

独立 CLI 保存 manifest.json（配置、版本、游戏、结果）、episode-0000.jsonl（逐条观察和动作）、summary.json。网页发布的测试保存到 MongoDB，不会另外生成这些本地文件。

成功使用 infos["won"][0] 判断，达到上限为 max_steps，环境主动结束为 environment_done；通信或协议异常为 error，停止后续 episode。独立 CLI 在 error 时以非零状态退出。

## 自定义 Workflow 协议

输入 `content` 是 JSON 字符串：

```json
{"type":"observation","episode_id":"e1","step":0,"text":"任务和房间观察","score":0.0,"done":false,"success":false,"truncated":false,"reason":null}
```

Workflow 必须通过 `output_to_terminal` 返回：

```json
{"type":"action","episode_id":"e1","step":0,"text":"look"}
```

`episode_id` 与 `step` 必须回传当前观察的值。非 JSON 的普通终端输出和 `type` 不是 `action` 的输出会被跳过，格式错误的动作会终止评测。每执行一次环境动作，下一条观察的步号加一。输入队列一次可能返回多条消息；当前运行器每次只等待一个动作，示例按单个待处理观察工作。

每个 episode 使用独立终端，输出按游标顺序读取。自定义流程应由单个 Workflow 顺序写出动作，并在收到 `done=true` 时退出。异常时运行器会尽力发送 `reason=runner_error` 的结束观察；现有 HTTP API 没有强制取消进程接口，无法保证错误流程会主动退出。

## 测试

```powershell
python -m unittest discover -s alfworld_runner -p test_runner.py
python -m unittest discover -s agent -p test_alfworld_workflow.py
```

数据缓存与真实环境已验证 valid_unseen 包含 134 个可运行任务。固定 look 示例可验证终端通信与正常结束，不代表模型解题能力。


## 三段工作流与经验迭代

需要固定引导、异常时逐版本回退和跨 episode 经验学习时，可使用 [ALFWorld 三段工作流](../docs/examples/alfworld-agent/README.md)。执行 `python scripts/install_alfworld_workflows.py --model YOUR_MODEL_ID --install` 一次安装并绑定权限，在 Benchmark 中选择返回的 bootstrap 文件 ID，inputs 填 `{}`。引导负责终端收发，主流程逐轮返回动作；runner 会等待结束后的经验迭代完成再开始下一轮。
