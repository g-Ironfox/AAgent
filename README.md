# AAgent

AAgent 是一个持续存在、统一认知并统一决策的 Agent 运行时,而不是多会话聊天服务。

> 一个决策中心,一个全局认知,一条连续时间线。

## 核心约束

- MongoDB 已提交事件历史是唯一权威上下文;
- `agent` 单 worker 串行推进 LLM 与工具链;
- 外部事件只能进入 Redis 队列,不能并发修改上下文;
- QQ 是当前主要事件源,WebUI 当前主要用于监控。

完整设计依据见[设计哲学](docs/00-设计哲学.md),未实现能力见[路线图与创新](docs/06-路线图与创新.md)。

## 快速启动

1. 安装 Docker Desktop 与 Docker Compose;
2. 复制环境变量模板并填写所有 `replace-me`;
3. 构建并启动服务;
4. 查看核心日志。

```powershell
Copy-Item .env.example .env
# 编辑 .env
docker compose up --build -d
docker compose logs -f agent qqbot
```

WebUI 地址:`http://localhost:8080`。完整变量说明、端口和安全检查见[配置与部署](docs/04-配置与部署.md)。

## 服务

| 服务 | 职责 |
|------|------|
| `agent` | 串行消费事件,调用 LLM 与工具 |
| `qqbot` | 接收 QQ WebSocket 事件并写入队列 |
| `webui` | 展示健康状态、队列、worker 状态与历史 |
| `redis` | 编排事件顺序并缓冲入口流量 |
| `mongodb` | 保存全局事件历史与权威上下文 |

## 文档

从[文档导航](docs/README.md)按任务选择阅读路径:

- 理解运行方式:[系统架构](docs/01-系统架构.md) → [事件与队列](docs/02-事件与队列.md);
- 修改代码:[模块详解](docs/03-模块详解.md);
- 排查风险:[已知问题](docs/05-已知问题.md);
- 查看未来计划:[路线图与创新](docs/06-路线图与创新.md)。

## 安全

不要提交 `.env`、API Key、访问 Token 或 `data/`。曾出现在源码或 Git 历史中的凭据必须先吊销,再从服务商处生成新凭据。