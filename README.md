# AAgent
用OS的思路做Workflow调度。内核隔离!


高可塑性且具备工业级弹性优化(对mcp进行了魔改)的智能体"平台",希望通过这个框架对多个技术进行探索,比如(功能分化的)multiagents支持不同于以往的一问一答交互模式而是由事件驱动架构启发的长程(reAct)与瞬时任务合理调度的零等待自由交互,以及workflow的可塑性支持Agent自演进的探索,未来我也期待从数学的角度探索mcts的规划、上下文压缩、马尔科夫链决策等与llm的结合。  

目前思路(暂时):Agent中的部分操作是模式化可以通过规则(workflow)及其执行器来实现的,而不需要占用宝贵的llm throughput。进一步的,我把Agent建模为大部分的规则操作加上少部分的关键判断。

## 产品介绍

以 **进程调度与 Workflow 画布**为中心的个人 Agent 平台。用户通过 WebUI 创建工作流进程；Agent 调度器从 Redis 就绪列表读取可运行进程，并逐节点执行。Workflow 通过分布式 Tool Server 调用本地或远程工具。

每个工作流进程创建时都会分配独立的终端进程。终端消息按终端 ID 保存在 MongoDB；进程记录和就绪/阻塞状态保存在 Redis。

设计上强调:

- **可扩展** — 进程输入、Workflow 节点与 Tool Provider 分别沿调度、编排和能力三个方向扩展。
- **弹性** — Agent、Tool Server、Provider、WebUI 都是独立进程与容器,可以单独重启或替换实现。
- **灵活编排** — Workflow 不是固定的线性流水线:路由、循环、可变 Context、工具调用和子进程 Workflow 文件可以组合成复杂控制流,包括 ReAct 风格的“思考 → 行动 → 观察 → 再思考”。
- **可自定义** — 业务能力由画布编排,节点、端口和状态都显式可见;多数流程变化不需要修改执行器代码。
- **易于调试** — WebUI 可按进程查看终端消息和工作流运行日志。

> 项目仍在过渡期,架构持续调整中。设计与实现冲突时以源码为准;`docs/废弃旧文档/` 里的方案已不代表当前行为。

## 界面一览

### Workflow 编辑器

画布即契约:节点端口是强类型的,类型不匹配的连接在编辑器里就画不出来。左边是 LLM 节点拼出的最小流程,右边是带 Context、Remote Sync Tool 和 foreach 的复杂编排。

| 基础流程 | Context + 远程工具 + 循环 |
| --- | --- |
| ![基础流程](docs/images/workflow-editor-basic.png) | ![复杂编排](docs/images/workflow-editor-context.png) |

### 为什么是 Workflow

这里的 Workflow 不只是把几个 API 串起来,而是 Agent 的控制流语言。Router 可以按运行结果选择路径,foreach 可以展开任务,Context 可以跨节点积累状态,控制流可以成环,子进程 Workflow 文件可以把一段能力封装后再次组合。节点之间的连接同时表达执行顺序和数据依赖,因此复杂行为仍然可以被追踪、替换和复用。

这些能力可以组合出不少巧妙的模式:

- **ReAct** — 在 Workflow 内使用 while_pop、Context、LLM 和工具节点执行多轮推理，停止条件由业务结果和显式控制流决定。
- **动态计划** — 根据中间结果选择、跳过或重复步骤,而不是在代码里写死一条执行路径。
- **能力组合** — 把不同工具和子进程 Workflow 文件作为独立能力单元,按任务动态选择和编排。
- **Multi-Agent** — 未来可以把不同角色建模为可复用的 Agent Workflow,通过事件、共享 Context 和拉起并等待子进程完成委派、协作、复核与交叉验证。比如与用户对接和长任务的分工。

更重要的是,事件源和 Workflow 解耦后,一次长任务不必表现为“发出请求,等待最终答案”。未来可以把计划变化、阶段结果、工具进度、Agent 间交接和需要用户决策的节点持续转化为事件,让 Terminal、聊天平台或其他客户端呈现可追踪、可介入、可继续的交互过程。这是 AAgent 希望探索的体验:复杂执行发生在后台,但用户始终看得见进度,并能在恰当的时机参与。

### 运行与调试

终端消息保存在 MongoDB 的 `terminal_messages` 集合（可通过 `MONGO_TERMINAL_COLLECTION` 配置），并按进程终端隔离。用户输入仅保存到选定终端；Workflow 执行 `output_to_terminal` 节点时，将 Agent 输出追加到对应终端。

`webui_py` 的 `/logs` 页面按进程展示日志，数据来自 MongoDB 的 `process_logs` 集合（可通过 `MONGO_PROCESS_LOG_COLLECTION` 配置）。每个工作流进程和终端进程都有独立记录，可查看进程 ID、父子关系、当前状态、节点轨迹和进程事件。挂起与唤醒事件包含发生时间、等待原因及关联进程 ID，涵盖终端消息和子进程退出；页面支持按状态、进程类型和关键词筛选。新增事件从更新后的运行时开始记录，旧记录不会补造历史事件。

![进程终端](docs/images/terminal.png)

### 管理

管理 WebUI 提供 Sessions、文档和 LLM 模型注册表管理。Workflow 文件在工作区中管理，并通过 Workflow 编辑器设计和导出。

![模型注册表](docs/images/model-registry.png)

### Tool Server

Provider 在线状态、工具目录和任务流水都在这里看。

![Tool Server 控制台](docs/images/tool-server.png)

Tool Server 的详细介绍、接口配置与调用示例、完整功能演示图,见 [`tool_server/README.md`](tool_server/README.md)。

## 架构

```mermaid
flowchart LR
    WebUI[WebUI 创建进程] -->|写入进程和就绪列表| Redis[(Redis 进程表)]
    Redis --> Scheduler[Agent 调度器]
    Scheduler --> Executor[Workflow 执行器]
    Executor -->|等待终端输入| Blocked[阻塞进程集合]
    Terminal[进程专属终端] --> Messages[(MongoDB 终端消息)]
    Executor -->|sync / async| ToolServer[tool_server]
    ToolServer --> Provider[tool_provider]
    Executor --> Logs[(MongoDB 进程运行日志)]
```

- **进程表** 保存在 Redis；就绪进程由调度器逐个取出执行，阻塞进程等待其 wait_for 指定的进程结束或终端消息。
- **终端** 是进程专属的被动进程。创建工作流进程时同时创建终端；用户从 WebUI 选择终端后可发送和查看消息。当前提交接口只保存消息，自动唤醒仍需单独接入。
- **Workflow** 在进程上下文内执行，output_to_terminal 将输出写入当前进程关联的终端。
- **tool_server** 管理工具注册、调用和异步任务状态。它的独立回调 outbox 不属于 Agent 进程调度队列。

## 服务与端口

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| `webui_py` | 8081 | Agent WebUI:进程终端、进程创建、工作区与运行日志 |
| `workflow_editor` | 8082 | Workflow 可视化编辑器(独立服务,只导出 JSON) |
| `tool_server` | 8083 | 工具注册、调用、任务状态与控制台 |
| `manager_webui` | 8084 | 管理 WebUI:Sessions、文档、模型 |
| `agent` | — | Redis 进程调度器与工作流执行器 |
| `tool_provider` | — | 工具实际执行方,通过 WebSocket 注册到 Tool Server |
| `redis` / `mongodb` | — | 队列与存储,仅在 dev 配置下暴露到宿主机 |

## 快速启动

1. 安装 Docker Desktop 与 Docker Compose;
2. 复制环境变量模板并填写当前启用服务所需的配置;
3. 构建并启动服务。

进程由 Agent WebUI 创建；每个进程拥有独立终端，无需配置全局终端或事件绑定。

```powershell
Copy-Item .env.example .env
# 编辑 .env
docker compose up --build -d
docker compose logs -f agent webui_py
```

启动后 Agent WebUI 在 `http://localhost:8081`,管理 WebUI 在 `http://localhost:8084`。

在 Agent WebUI 工作区保存 Workflow 2.0 文件后，打开终端页创建进程并选择该工作流。创建请求直接携带 workflow_file_id 和输入值；调度器从 Redis 就绪列表执行进程。子进程 Workflow 文件 节点按精确工作区文件名调用。

工作区 checkpoint API 同时注册为 Local Tool，可在工具目录中选择：

| 工具名 | 参数 | 用途 |
| --- | --- | --- |
| `workspace.list_checkpoints` | `before_seq?`、`limit?`（默认 50，范围 1–100）、`file_id?` | 分页列表，返回 `items`、`has_more`、`next_before_seq` |
| `workspace.checkpoint_tree` | 无 | 分支树和当前 `head_seq` |
| `workspace.get_parent_checkpoint` | `seq?`（默认当前 head） | 返回 `seq` 和 `parent_seq`，按分支祖先查询回滚目标 |
| `workspace.checkpoint_diff` | `seq` | 相对于父 checkpoint 的文件差异 |
| `workspace.create_checkpoint` | `name` | 保存当前工作区快照 |
| `workspace.restore_checkpoint` | `seq` | 恢复整个工作区并更新文件 revision |

`seq=0` 表示空工作区，恢复到 0 会清空工作区文件。工具复用 `WORKSPACE_API_URL`（默认 `http://webui_py:8081`）访问现有 API。

回滚一步：先调用 `workspace.get_parent_checkpoint`（参数 `{}`），再将返回的 `parent_seq` 作为 `workspace.restore_checkpoint` 的 `seq`。第一个 checkpoint 的 `parent_seq` 为 `0`，可恢复为空工作区；当前已为空工作区时返回 `parent_seq: null`，此时没有更早的回滚目标。父序号按分支关系确定，恢复后再次查询使用新的当前 head。

### 环境变量

`.env.example` 已按用途分组:

| 分组 | 变量 |
| --- | --- |
| LLM | `DEEPSEEK_*`、`KIMI_*`、`ZAI_API_KEY`、`TAVILY_API_KEYS`、`BOCHA_*` |
| 工具 Provider | QQ_API_BASE_URL、QQ_API_TOKEN（供 QQ 工具调用） |
| 进程调度 | REDIS_*、AGENT_TOOLS_KEY、ProcessTable、ReadyProcesses、BlockedProcesses |
| Tool | `TOOL_SERVER_URL`、`TOOL_MAX_WAIT_MS`、`TOOL_CLIENT_*`、`TOOL_PROVIDER_*`、`TOOL_MODULES` |
| 存储 | `MONGO_*` 及各集合名 |

Redis 使用两个独立数字库，两个编号必须不同：

| 配置 | 默认库 | 数据 |
| --- | --- | --- |
| `REDIS_DB` | 0 | 公共事件队列 `external_events`、终端状态 `terminal_sessions`、工具注册及工具服务数据 |
| `REDIS_KERNEL_DB` | 1 | runtime 进程表、ready / blocked、内部终端索引、Workflow Context |

WebUI 等服务只连接公共库，只有 agent 连接内核库。调度器非阻塞读取内核 ready 队列，每执行一个节点后处理公共库的外部事件；ready 为空时阻塞等待外部事件。当前按单个 runtime 调度循环运行。变更库编号后不自动迁移旧库中的运行状态。

## 开发调试

`docker-compose.dev.yml` 挂载宿主机源码,并让 `agent` 以 `sleep infinity` 启动,改完代码不用重建镜像,手动跑入口即可:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose exec agent python main.py
```

发布时不要叠加这个文件。

注意:生产配置 `docker-compose.yml` 里只有 `redis` / `mongodb` 有 volumes,`webui_py` / `manager_webui` / `workflow_editor` / `tool_server` 的代码都在镜像内,改完要 `docker compose up -d --build <服务>`;dev 配置下这四个服务已挂载源码目录,但静态资源引用形式是 `?v=N`,改动后仍需递增版本号才会绕过浏览器缓存。

## 目录结构

```
agent/              Agent 运行时:Workflow 校验、解析、执行与节点实现
tool_server/        工具注册与调用中心,任务状态、回调投递
tool_provider/      实际执行工具的 Provider(QQ / Bilibili / 文档)
webui_py/           Agent WebUI(8081)
manager_webui/      管理 WebUI(8084)
workflow_editor/    Workflow 编辑器(8082)
docs/               设计文档、审查记录与 README 图片
data/               Redis / MongoDB 持久化数据(不提交)
```
