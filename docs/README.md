# AAgent 文档

本目录保留当前实现文档、专题设计、审查记录和已归档的旧文档。旧方案统一放在 `废弃旧文档/`，不再代表当前运行行为。

## 文档结构

| 文档 | 内容 |
|------|------|
| [17-Tool Server设计](17-Tool%20Server设计.md) | 分布式 Tool 注册、调用、任务状态与回调协议 |
| [18-Tool Server内核实现](18-Tool%20Server内核实现.md) | Provider 并发、Redis 等待、状态原子性与回调投递 |
| [19-Workflow本地与远程Tool节点拆分](19-Workflow本地与远程Tool节点拆分.md) | Workflow 的本地、远程同步和远程异步 Tool 节点 |
| [20-Event协议与流转](20-Event协议与流转.md) | 当前 Event 类型、JSON 格式、队列方向和运行路径 |
| [废弃旧文档](废弃旧文档/) | 已归档的旧架构和旧协议，只用于追溯 |
| [审查日志](审查日志/) | 特定时间点的代码审查、问题和修复记录 |

## 阅读顺序

| 目标 | 阅读路径 |
|------|----------|
| 理解 Event 与队列 | [20-Event协议与流转](20-Event协议与流转.md) |
| 理解远程 Tool | [17-Tool Server设计](17-Tool%20Server设计.md) → [18-Tool Server内核实现](18-Tool%20Server内核实现.md) |
| 理解 Workflow Tool 节点 | [19-Workflow本地与远程Tool节点拆分](19-Workflow本地与远程Tool节点拆分.md) |
| 启动项目 | 根目录 [README](../README.md) |

发生冲突时，以源码为准。`审查日志/` 和 `废弃旧文档/` 都是历史快照，不能直接作为当前行为依据。
