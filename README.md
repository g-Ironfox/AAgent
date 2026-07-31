# AAgent

AAgent is a Docker Compose project that connects a QQ bot event listener to an
LLM-powered task worker through Redis. MongoDB stores event history.

## Services

- `qqbot`: receives QQ WebSocket events and publishes tasks to Redis.
- `agent`: processes queued tasks, calls model/search APIs, and sends replies.
- `webui`: queue / worker status / history monitor panel.
- `redis`: task queue.
- `mongodb`: event history storage.

## Documentation

The project documentation is split by responsibility under [`docs/`](docs/README.md):

| Document | Content |
|----------|---------|
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