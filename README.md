# AAgent

AAgent is a Docker Compose project that connects a QQ bot event listener to an
LLM-powered task worker through Redis. MongoDB stores event history.

## Services

- `qqbot`: receives QQ WebSocket events and publishes tasks to Redis.
- `agent`: processes queued tasks, calls model/search APIs, and sends replies.
- `redis`: task queue.
- `mongodb`: event history storage.

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