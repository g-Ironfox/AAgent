# AAgent

AAgent 是一个受 CPU 取指、执行与写回循环启发的**事件脉冲驱动 Agent 运行时**。
系统把消息、模型响应、工具调用和工具结果统一表示为事件,由单个 worker
一次执行一个事件,再通过后续事件持续推进任务。Redis 保存待执行事件,
MongoDB 保存事件历史与运行上下文。

> 事件是指令,队列是控制流,Agent 按脉冲执行。

当前 `qqbot` 是唯一的外部事件源,但它只是过渡阶段的消息渠道适配器,
并不是 AAgent 的产品边界。未来将以 `webui` 作为主要交互界面和事件入口,
用于提交任务、管理会话、观察执行过程并触发主动任务;QQ 则保留为可选接入渠道。

系统目前由事件到达触发下一步,队列为空时进入等待。未来计划加入空闲时钟事件,
让 Agent 在没有用户消息时也能执行检查、计划、提醒和后台任务。

## Execution Model

- **串行执行**:同一时刻只处理一个事件,保证工具链和状态写回顺序确定。
- **事件脉冲**:上一步产生后续事件时立即继续;无事件时阻塞等待。
- **统一入口**:QQ、WebUI、HTTP API、Webhook 和时钟最终都转换为统一事件。
- **演进方向**:会话之间并行,会话内部串行;WebUI 从监控面板演进为主要工作台。

## Services

- `agent`:串行消费事件,调用模型与工具,并产生后续事件。
- `webui`:当前用于队列、worker 状态与历史监控;未来作为主要交互和事件入口。
- `qqbot`:当前的 QQ WebSocket 事件适配器;未来作为可选消息渠道。
- `redis`:事件队列与调度顺序。
- `mongodb`:事件历史与运行上下文。

## Documentation

The project documentation is split by responsibility under [`docs/`](docs/README.md):

| Document | Content |
|----------|---------|
| [00-设计哲学](docs/00-设计哲学.md) | CPU-inspired execution model, event pulses, WebUI-first direction |
| [01-系统架构](docs/01-系统架构.md) | Service topology, event-driven design, data storage |
| [02-事件与队列](docs/02-事件与队列.md) | Event types, state machine, queue priority, typical flow |
| [03-模块详解](docs/03-模块详解.md) | Per-module responsibilities and interfaces |
| [04-配置与部署](docs/04-配置与部署.md) | Env vars, Docker Compose, directory layout, security |
| [05-已知问题](docs/05-已知问题.md) | Known issues and improvement suggestions |

## Setup

1. Install Docker Desktop with Docker Compose.
2. Copy `.env.example` to `.env`.
3. Replace every `replace-me` value with your own credentials and IDs.
4. Start the services:

   ```powershell
   docker compose up --build -d
   ```

5. Follow application logs:

   ```powershell
   docker compose logs -f agent qqbot
   ```

Stop the project with `docker compose down`. Runtime database files are stored
under `data/` and are intentionally excluded from Git.

## Security

Never commit `.env`, API keys, access tokens, or the contents of `data/`.
Credentials that have appeared in source code or Git history must be revoked
and replaced at the provider before publishing the repository.