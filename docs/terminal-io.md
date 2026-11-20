# 终端 HTTP IO 接口

当前接口由 `webui_py` 提供，ALFWorld 等外部适配器可以直接调用。之后拆分前后端时可沿用这组路径和消息格式。

## 写入 Workflow 输入

`POST /api/terminal`，请求体为 JSON：

```json
{
  "terminal_id": "episode-terminal-id",
  "content": "{\"type\":\"observation\",\"episode_id\":\"e1\",\"step\":0,\"text\":\"...\",\"done\":false}"
}
```

`content` 仍为字符串，适配器自行将结构化消息序列化为 JSON。接口去除首尾空白后检查非空，保存处理后的正文，再将同一正文放入外部事件队列，由内核追加到终端输入队列并唤醒等待中的 Workflow。`files` 可以省略，提供时必须为空列表。

已移除原来的 4000 字符限制，入口请求体上限从 16 KiB 调至 1 MiB（1,048,576 字节，包含 JSON 包装和 UTF-8 编码开销）。终端页面也移除了 4000 字符的输入限制。成功时返回 HTTP 201 和保存的 `message`。

调用前应先创建 Workflow 进程，并使用该进程的 `terminal_id`。HTTP 201 表示消息已保存且事件已入队，不代表 Workflow 已经消费；未知终端也会接受消息，但不会因此创建 Workflow。HTTP 503 若含 `message`，表示历史已经保存而事件入队失败，调用方需要处理这种部分成功。

## 增量读取 Workflow 输出

`GET /api/terminal/output?terminal_id=episode-terminal-id&limit=150`

| 参数 | 含义 |
| --- | --- |
| `terminal_id` | 必填，目标终端 ID |
| `limit` | 每次最多返回的条数，默认 150，范围 1–300 |
| `cursor` | 可选，上次响应的 `next_cursor`；首次读取省略 |

响应示例：

```json
{
  "fetched_at": "2026-11-20T00:00:00Z",
  "items": [
    {
      "id": "6b0000000000000000000001",
      "terminal_id": "episode-terminal-id",
      "role": "assistant",
      "content": "{\"type\":\"action\",\"episode_id\":\"e1\",\"step\":0,\"text\":\"look\"}",
      "created_at": "2026-11-20T00:00:00Z"
    }
  ],
  "next_cursor": "6b0000000000000000000001"
}
```

接口只读取指定终端的 `assistant` 消息，不返回输入回显；按 MongoDB `_id` 升序返回，提供游标时只取 `_id` 大于游标的消息。首次读取从已有输出的开头开始。空结果保留传入的游标，首次读取为空时 `next_cursor` 为 `null`。无效游标或超出范围的 `limit` 返回 HTTP 400；存储不可用返回 HTTP 503。

这是立即返回的轮询接口。读取不会删除历史，也不会在服务端保存消费位置。适配器处理完一批消息后保留 `next_cursor`，下一次原样传回；收到空列表时稍后继续轮询，不能将空列表视为 episode 结束。处理失败时保留旧游标，以便重读。

现有 `GET /api/terminal/history` 保留原有行为，用于页面查看最近的输入和输出；自动测试应使用 `/api/terminal/output` 续读，避免反复读取最后一页历史。WebUI 启动时会创建 `(terminal_id, role, _id)` 复合索引，支持按终端增量查询。

## ALFWorld 适配约定

- 每个 episode 创建独立终端和 Workflow，由一个 Workflow 顺序输出动作。游标顺序按 `_id` 定义，不保证多个并发输出者的实际执行顺序。
- 将环境观察作为 `content` 写入，Workflow 从 `read_terminal_queue` 消费。该节点一次可能返回多条消息，按顺序处理。
- Workflow 通过 `output_to_terminal` 输出 JSON；适配器只执行 `type=action` 的消息，其他输出用于展示或调试。
- 用 `episode_id` 和 `step` 关联动作与观察，适配器记录已经执行的动作；历史游标不提供环境动作的恰好执行一次保证。
- 环境结束时写入 `done=true`，由 Workflow 结束循环。等待动作超时、达到最大步数和统计结果由适配器负责。

ALFWorld 环境初始化、动作执行和评测由独立的 `alfworld` 容器提供，使用方法见 [ALFWorld 接入](../alfworld_runner/README.md)。
