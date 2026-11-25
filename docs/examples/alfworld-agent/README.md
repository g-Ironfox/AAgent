# ALFWorld 三段工作流

基于 [alfworld-react.flow](../alfworld-react.flow) 的原生 ReAct 提示词和历史格式，接入固定引导、固定经验迭代器和文件权限。运行时三个流程均不自改，唯一持续学习的文件是经验文档。

| 文件 | 职责 |
| --- | --- |
| alfworld-agent-bootstrap.flow | 唯一的环境终端所有者；记录观察和动作；调用主流程；执行异常时逐版本恢复；结束后调用迭代器 |
| alfworld-agent-main.flow | 每次处理一条观察，读取固定经验，用原生 reasoning 生成一个 ALFWorld 动作，返回完整对话历史 |
| alfworld-agent-iterator.flow | 根据初始任务、完整轨迹、环境结果和恢复错误总结经验，只写固定经验文件 |
| alfworld-agent-stable-main.flow | 安装时主流程的固定稳定备份，作为恢复底线 |
| alfworld-agent-experience.md | 主流程只读、迭代器可写的跨 episode 经验 |

## 安装与运行

先按 [Benchmark 控制台](../../../benchmark_webui/README.md) 启动后端、Agent 调度器、benchmark_worker 和 benchmark_webui，并准备 ALFWorld 数据。开发 Compose 配置的 Agent 容器默认执行 sleep，需另开终端执行 `docker compose exec agent_runtime python main.py`。已有调度器时无需再启动。

模型管理中启用一个支持原生 reasoning 的模型，然后在仓库根目录执行：

```powershell
# 预览五个文件及权限
python scripts/install_alfworld_workflows.py --model YOUR_MODEL_ID

# 创建文件、绑定实际文件 ID，并建立 baseline checkpoint
python scripts/install_alfworld_workflows.py --model YOUR_MODEL_ID --install
```

默认后端地址为 http://127.0.0.1:8081，可用 --url 修改；--prefix 可用于安装多套隔离的文件。安装器拒绝覆盖同名文件，也不会清空已有经验。模型 ID 与工作区文件 ID 不同。

在 Benchmark 页面选择安装结果中 **bootstrap 的 file_id**，Workflow inputs 使用 **{}**。建议先用 episodes=1、max_steps=2 验证通信，再按需要增加到 50 步；动作和结束后的迭代共用 action_timeout，默认 180 秒，模型较慢或需要多次恢复时可调大。

独立 CLI 同样选择 bootstrap 文件：

```powershell
docker compose --profile benchmark run --rm --no-deps --entrypoint python -v ./data/alfworld/results:/results benchmark_worker -m alfworld_runner.main run --workflow-file-id BOOTSTRAP_FILE_ID --episodes 1 --max-steps 50 --action-timeout 300
```

上述流程无需 task 输入，任务由环境的第一条 observation 给出。仓库中的 .flow 是可编辑模板，含模型和文件 ID 占位符；使用安装器可一次完成绑定与权限设置。只导入单个主流程不能直接连接评测器，因为主流程是由引导调用的逐轮子流程。

修改生成器后执行以下命令更新模板：

```powershell
python scripts/build_alfworld_bundle.py
```

生成器现在会在写入任何文件之前检查整套文件：如果目标文件已经绑定真实模型、文件 ID 或子流程名称，而新生成内容将改掉这些绑定，默认拒绝覆盖。不要用未绑定模板直接覆盖正在使用的工作区副本。可以输出到一个新目录，或显式传入原有绑定：

```powershell
python scripts/build_alfworld_bundle.py --output tmp/alfworld-bound --prefix YOUR_PREFIX --model YOUR_MODEL_ID --experience-id EXPERIENCE_FILE_ID --main-id MAIN_FILE_ID --stable-id STABLE_FILE_ID
```

`--force` 仅用于明确要重置本地模板绑定的情况，不会帮你重新绑定或更新线上文件。在线上修复时应保持文件 ID 和权限不变，并分别核对主流程、稳定备份、经验、迭代器和引导的引用。

## 每轮执行与恢复

引导等待第一条观察，保存初始任务、工作区清单和 checkpoint。每条观察先持久化，再判断 done：未结束时，将当前观察和历史作为 task JSON 交给主流程；主流程返回 action 与 history，引导保存逐轮尝试结果后才发送动作。模型正文只有动作，reasoning 留在原生 assistant 历史中。终端是 ALFWorld 的数据通道：输入为 observation JSON，输出只发送 action/error JSON，不混入进度、推理或结束摘要；这些信息从进程日志和任务记录查看。

正常返回的无效动作、环境反馈 Nothing happens、达到步数上限、解题失败均不会触发文件回退。只有子流程加载/执行异常才进入恢复：先试当前版本，失败后沿当前 checkpoint 祖先分支逐个尝试不同内容的旧版本，最后到 stable。每次失败先写记录，再替换主文件。已处于 stable 时失败即停止，不重复尝试相同 stable。

恢复后使用同一观察和相同历史重试，尚未向环境发送动作，因此环境不会多走一步。成功恢复后推进恢复游标，后续异常只继续向更旧版本回退。恢复只写主流程文件的内容，不恢复整个工作区，也不重置 ALFWorld 内存环境。stable 是已知流程定义的备份，模型服务故障等外部问题仍可能使它失败。

没有可用版本时，引导发出 type=error 的终端消息，runner 立即记录错误；不会等满动作超时。引导仍保存轨迹并尝试更新经验。后端或 runner 中断、动作已经执行后进程崩溃，不提供环境事务或断点续跑。

结束观察 done=true 不会调用主模型或再发动作。引导记录最后的 success/score/done/truncated/reason，调用迭代器并保存其状态。runner 等待引导终端关闭后才开始下一个 episode，让下一轮读到本轮经验。迭代器异常会留在记录中，并保留已有经验与环境结果；引导正常完成时 runner 可继续。

## 权限与记录

| 对象 | 运行读/写 | 读取/写入门槛 | checkpoint read/create/restore |
| --- | --- | --- | --- |
| 引导 | 3 / 3 | 3 / 4 | true / true / true |
| 主流程 | 1 / 1 | 1 / 3 | false / false / false |
| 迭代器 | 2 / 2 | 2 / 4 | false / false / false |
| 经验 | 0 / 0 | 1 / 2 | false / false / false |
| stable | 1 / 1 | 3 / 4 | false / false / false |

所有已知工具均为固定 Tool 节点；模型节点没有工具调用。主流程只能通过固定节点读经验；迭代器只能写安装时绑定的经验 ID；引导能在恢复路径替换主流程，三个进程都不能修改引导、迭代器或 stable。等级机制本身不提供文件白名单，固定目标由执行图保证，详见 [权限机制](../../process-permissions.md)。

每个 episode 产生 `alfworld-agent-run-<checkpoint-seq>.json`，保存为一个普通 JSON 对象：

- `task` / `result`：初始 / 最后环境观察的 JSON 字符串，保留完整原始字段。
- `status` / `error`：流程状态和恢复错误，不替代环境的成功判定。
- `events`：按时间排列的**对象数组**，不是 JSON 字符串数组。
  - `type=observation`：`observation` 保存这一条环境观察。
  - `type=turn`：`step`、`action`、`reasoning` 保存本轮新增动作和推理；`attempts` 是恢复摘要对象数组，包含 `status`、`error`、`checkpoint_seq`、`source`。失败轮次没有动作或推理。
- `checkpoint_before` / `checkpoint_after`、`workspace_before` / `workspace_after`：工作区元数据快照。完整变更内容按需通过 checkpoint 查询，不嵌入日志自身，避免把日志递归复制进日志。
- `iterator_status` / `iterator_result`：经验迭代完成后补充的结果，直接位于顶层。

完整聊天历史只供主流程继续决策，不在每一轮的记录里重复保存；下一轮输入也不再带上完整审计轨迹。所有观察、动作、原生 reasoning 和恢复来源仍可从 `events` 按顺序还原。记录体积随新增内容增长，不再因反复保存完整历史而快速膨胀。普通引号、换行和路径仍会按 JSON 规则正常转义；不应手动删除反斜杠。

这是 ALFWorld 的新记录格式，不再使用旧版 `task_record` 字符串包装。旧文件不会自动迁移；消费记录的脚本应改读顶层字段和 `events`。仓库模板变更不会自动更新已安装的工作区文件或正在运行的进程：建议使用新的 `--prefix` 重新安装整套工作流（先按需备份或迁移经验），然后选择新 bootstrap 的文件 ID 开始新 episode。安装器仍拒绝覆盖旧文件。

status=completed/recovered 只说明流程执行状态，**解题成功以环境 success=true（infos.won）为准**。迭代器据此区分已验证方法与待验证建议，不跨任务照搬物品编号和房间地图。经验在顺序 episode 之间累积，会改变评测条件；比较模型或工作流时应使用新的 --prefix 并保持相同的经验起点。多 worker 并行使用同一套文件可能遇到经验 revision 冲突或主流程恢复竞争，应为各自安装独立的 prefix。

## 验证

```powershell
python -m unittest discover -s agent_runtime -p test_alfworld_bundle.py
python -m unittest discover -s agent_runtime -p test_alfworld_generation.py
python -m unittest discover -s alfworld_runner -p test_runner.py
node --test workflow_editor/test_alfworld_bundle.mjs
```

集成测试使用真实调度器和文件权限 API，Redis/Mongo 与模型使用内存替身，检查多轮历史、结束信号、真实结果记录、逐级恢复、stable 失败和迭代器错误。测试不代表真实模型的 ALFWorld 解题成功率。
