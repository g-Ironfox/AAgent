# Benchmark 控制台

通过两个业务容器运行 ALFWorld 评测。依赖项目现有的 Redis、MongoDB、webui_py 和 Agent 调度器。


数据流：

```text
浏览器 → benchmark_webui:8085 → MongoDB 保存任务 → Redis Stream
                                                    ↓
                                             benchmark_worker
                                                    ↓
                               webui_py /api/processes 创建 Workflow 进程
                                                    ↓
                                现有 Agent 调度器执行 Workflow runtime
                                                    ↕ 终端 HTTP JSON 协议
                                             ALFWorld 环境
                                                    ↓
                                      MongoDB episodes / events / summary
                                                    ↓
                                  benchmark_webui 展示进度、统计和交互轨迹
```

## 启动

在项目根目录执行：

```powershell
docker compose --profile benchmark build benchmark_worker benchmark_webui
docker compose --profile benchmark run --rm --no-deps benchmark_worker download
docker compose --profile benchmark up -d benchmark_worker benchmark_webui
```

打开 http://localhost:8085。端口可通过 `BENCHMARK_WEBUI_PORT` 修改。普通 `docker compose up` 不启动这两个服务；指定服务名或启用 `benchmark` profile 即可启动。

下载命令只获取 ALFWorld 0.4.2 的纯文本数据，并复用既有 `alfworld_data` 命名卷。已有完整下载标记时会跳过下载。数据缺失时 worker 会将测试标记失败，错误信息会提示下载；页面顶部显示在线 worker 和数据准备状态。数据下载不在测试运行时自动进行。

在 Agent WebUI 的工作区导入 `docs/examples/alfworld-look.flow`，回到控制台刷新，在 Workflow 列表中选择它。先发布 episodes=1、每轮步数=2 的测试，验证通信。该示例始终执行 look，正常应达到步数上限，成功率为 0。

最小 ReAct 流程可导入 `docs/examples/alfworld-react.flow`，修改 `decide` 节点的模型 ID 后保存，或先生成绑定模型的版本：

```powershell
python scripts/build_alfworld_workflow.py --react --model-id <模型ID> --output tmp/alfworld-react.flow
```

该流程使用 LLM 原生 `reasoning` 保存推理历史，正文只输出一个动作，收到结束观察后退出。详细说明见 [ALFWorld 最小 ReAct](../docs/examples/alfworld-react.md)。

仅输出动作的模型流程仍可先生成再导入：

```powershell
python scripts/build_alfworld_workflow.py --model-id <模型ID> --output tmp/alfworld-agent.flow
```

模型 ID 来自模型管理；页面选择的是工作区中的 Workflow 文件。模型凭证仍由现有 Agent 使用，benchmark 容器不需要模型凭证。每个 episode 通过 `POST /api/processes` 创建独立的逻辑 runtime 进程，由现有 Agent 调度器执行，不会另起 Agent 服务容器。

开发时叠加 `docker-compose.dev.yml` 可挂载源码，benchmark_webui 自动重载。这个覆盖配置将现有 Agent 设为 `sleep infinity`，必须另开终端运行调度器：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile benchmark up -d --build benchmark_worker benchmark_webui
docker compose exec agent python main.py
```

## 页面与接口

页面支持发布任务、按状态筛选、复用配置、查看实时进度、成功率、耗时、每轮步数图，以及逐步 observation/action/result 轨迹。任务和 episode 列表可翻页，轨迹按游标增量读取。页面最多保留当前 episode 最近 1000 条记录，MongoDB 保留完整数据。成功率分母为已处理的 episode 数（包含错误）；请同时查看错误数和已处理/总数，未完成的测试不能视为完整成绩。

| 接口 | 用途 |
| --- | --- |
| GET /api/health | 检查 MongoDB 和 Redis |
| GET /api/options | Workflow 选项、worker 心跳与数据状态 |
| POST /api/jobs | 校验配置并持久化测试，返回 202 |
| GET /api/jobs?status=running&limit=30&before=ID | 按创建时间倒序列出任务 |
| GET /api/jobs/{id} | 配置、状态、摘要、版本、游戏文件列表、错误 |
| GET /api/jobs/{id}/episodes?after=-1&limit=100 | 按 episode index 升序翻页 |
| GET /api/jobs/{id}/events?after=0&episode=0&limit=100 | 按全任务 seq 升序读取轨迹；episode 可省略 |

事件查询返回 `next_cursor` 和 `has_more`；空页保留传入游标。episode 翻页返回最后的 index 作为 `next_cursor`，末页为 null。所有时间保存为 UTC。交互式 API 文档位于 `/docs`。

发布请求示例：

```json
{
  "name": "ALFWorld unseen",
  "workflow_file_id": "工作区文件ID",
  "split": "valid_unseen",
  "episodes": 10,
  "max_steps": 50,
  "seed": 42,
  "action_timeout": 180,
  "startup_timeout": 60,
  "admissible_commands": false,
  "inputs": {}
}
```

合法动作列表默认关闭，开启会改变测试条件。Workflow inputs 必须是最多 64 KiB 的 JSON 对象。评测协议和自定义 Workflow 要求见 [ALFWorld 执行器](../alfworld_runner/README.md)。

## 状态、恢复与存储

状态为 `queued → running → completed/failed`。达到步数上限属于正常的环境结果，任务可正常 completed；动作超时、协议错误、环境或存储错误会将测试 failed，并停止后续 episode。

MongoDB 是任务状态来源；Redis Stream `aagent:benchmark:jobs` 只传递 job_id。可用 `BENCHMARK_QUEUE` 修改队列名，两项服务必须一致。consumer group 为 `benchmark_workers`。公共 Redis DB 与项目的 `REDIS_DB` 一致，benchmark 不访问 runtime 内核库。

提交任务先写入 MongoDB，再投递 Redis。投递失败仍返回 202，任务保持 queued，页面显示投递错误；后台每 5 秒检查，约 30 秒后重试。排队期间通知丢失也会重新投递。重复投递通过 MongoDB 原子领取过滤，不重复执行测试。worker 每 5 秒续约，租约 60 秒；worker 被中断后，已有轨迹保留，租约到期由在线服务将任务标记 failed。中途任务不会自动重跑，也不恢复 ALFWorld 内存环境。页面“复用配置”会填入表单，重新发布才创建新任务。

一个 benchmark_worker 容器默认开 4 个执行子进程，同时执行最多 4 个测试任务。同一测试内部仍顺序执行 episodes；超出并发上限的测试保留在 Redis/MongoDB 队列中，不预先积压到本地进程。

在 `.env` 中设置 `BENCHMARK_WORKER_CONCURRENCY=4`（范围 1–32），然后更新单个 worker 容器：

```powershell
docker compose --profile benchmark up -d --build --no-deps benchmark_worker
```

也可在直接运行入口时指定 `python -m benchmark_worker.main work --concurrency 4`，命令行优先于环境变量。并发数 1 恢复串行执行。

每个执行子进程通过 Python `spawn` 启动，独立创建 Mongo/Redis 客户端、领取身份、当前任务和租约状态；每个测试创建独立的 ALFWorld 环境及终端 HTTP 客户端。TextWorld 的全局环境注册表和 PDDL 解析器由进程隔离，环境操作不再使用跨任务的全局锁。每个子进程内的心跳线程只负责续约和队列维护，不操作环境。单个测试失败不影响其他测试；执行进程意外退出会让主进程报错并停止其他进程，由容器重启策略恢复服务。容器收到停止信号后各进程停止领取任务，当前任务尽力写入失败状态、发送结束消息并关闭资源；主进程最多等待 20 秒，再终止未退出的进程（必要时强制结束），已有轨迹保留，未能正常收尾的任务通过租约到期标记失败。页面顶部按实例聚合，显示 worker 数、运行中的执行进程数和就绪进程数；心跳记录包含 PID，便于核对进程隔离。实际吞吐也取决于模型服务与现有 Agent 调度器。

集合均在 `MONGO_DATABASE` 中，与 runtime 数据分开命名：

| 集合 | 内容 |
| --- | --- |
| benchmark_jobs | 配置、状态、租约、摘要、环境版本和游戏清单 |
| benchmark_episodes | 每轮进度、terminal_id、得分、结束原因、耗时 |
| benchmark_events | 带 seq 和时间戳的 observation、action、result |
| benchmark_workers | 每个执行子进程的心跳、任务、容器实例、slot、PID、并发数和数据状态 |

完整观测与动作保存在 benchmark_events；Workflow 额外输出仍在现有终端消息集合。日志没有自动删除策略。Workflow 文件在每轮创建进程时由 webui_py 读取，运行期间请保持文件和模型配置稳定；这版不提供不可变的 Workflow/模型快照。现有 API 没有强制取消 runtime 的接口，异常时只会尽力发 done 让流程退出；自定义 Workflow 需要处理结束消息。

保留的独立 CLI 可继续运行，结果输出为文件：

```powershell
docker compose --profile benchmark run --rm --no-deps --entrypoint python -v ./data/alfworld/results:/results benchmark_worker -m alfworld_runner.main run --workflow-file-id <工作区文件ID> --episodes 1 --max-steps 2
```

## 验证

快速单元测试：

```powershell
python -m unittest discover -s tests/benchmark -p "test_*.py"
python -m unittest discover -s alfworld_runner -p test_runner.py
```

隔离的完整验收使用单独的 Redis/MongoDB/Agent/WebUI，并复用只读的文本数据卷。验收配置只启动一个 worker 容器，使用 2 个执行子进程，验证同时执行、并发上限、排队和随机种子隔离。请先构建项目的 Agent 与 WebUI 镜像，以及上述两项 benchmark 镜像：

```powershell
docker compose build agent webui_py
docker compose -p aagent-benchmark-smoke -f tests/benchmark/docker-compose.yml up -d benchmark_worker benchmark_webui
docker compose -p aagent-benchmark-smoke -f tests/benchmark/docker-compose.yml run --rm --no-deps verify
docker compose -p aagent-benchmark-smoke -f tests/benchmark/docker-compose.yml down --volumes
```

默认数据卷为 `aagent_alfworld_data`，其他 Compose 项目名请设置 `ALFWORLD_TEST_DATA_VOLUME`。验收页面映射到 http://localhost:18085。清理仅删除验收项目的临时容器和数据库卷，保留外部 ALFWorld 数据卷。


## 三段工作流与经验迭代

需要固定引导、异常时逐版本回退和跨 episode 经验学习时，可使用 [ALFWorld 三段工作流](../docs/examples/alfworld-agent/README.md)。执行 `python scripts/install_alfworld_workflows.py --model YOUR_MODEL_ID --install` 一次安装并绑定权限，在 Benchmark 中选择返回的 bootstrap 文件 ID，inputs 填 `{}`。引导负责终端收发，主流程逐轮返回动作；runner 会等待结束后的经验迭代完成再开始下一轮。
