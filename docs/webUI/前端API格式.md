# WebUI 前端 API 格式

> 本文定义 `webui_py`（FastAPI，端口 `8081`）对外提供的全部 HTTP API 的请求 / 响应格式与约定，供前端实现与联调使用。
> 事件流页面行为见[前端事件流设计](前端事件流设计.md)，轮询与 DOM 稳定性见[前端优化记录](前端优化记录.md)，终端语义见[08-终端设计](../08-终端设计.md)。

## 0. 通用约定

- **Base URL**：`http://localhost:8081`（Compose 端口映射，见 [04-配置与部署](../04-配置与部署.md)）；
- **数据格式**：JSON（UTF-8）；时间统一为 UTC ISO 字符串；
- **安全响应头**：`Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:`、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`；
- **错误格式**：统一为 `{"error": "<中文提示>"}`，HTTP 状态码 4xx / 5xx；
- **`limit` 参数**：范围 `1..300`，默认 `150`；越界返回 `400 {"error": "limit must be between 1 and 300"}`；
- **超时**：前端 `api.js` 对每个请求设置超时中断（AbortController），超时按失败处理，页面保留最后一次成功快照。

## 1. GET /api/health

健康检查（探活 / Compose healthcheck 使用）。

- `200`：`{"status": "ok"}`
- `503`（Redis 不可用）：`{"status": "unavailable", "error": "<异常>"}`

## 2. GET /api/events

事件流快照：合并 **Worker 状态 + Redis 队列 + MongoDB 历史**，前端按 `status` 分为“历史 → 正在执行 → 等待”三个区段。

- Query：`limit`（可选，`1..300`，默认 `150`）；
- `200` 响应：

```json
{
  "queue": "agent_tasks",
  "fetched_at": "2026-08-02T11:04:01Z",
  "worker": {
    "state": "idle",
    "event": { "...": "..." },
    "started_at": "2026-08-02T11:04:00Z",
    "updated_at": "2026-08-02T11:04:01Z"
  },
  "summary": { "pending": 0, "running": 0, "history": 0 },
  "sources": {
    "mongodb": "ok",
    "redis": "ok",
    "worker": "ok"
  },
  "items": [],
  "warnings": { "mongodb": "...", "redis": "...", "worker": "..." }
}
```

- `worker.state`：`idle` | `processing` | `unknown`（未上报）| `invalid`（非法）| `unavailable`；`processing` 时带 `event` 与 `started_at`；
- `summary.running`：`processing` 时为 `1`，否则 `0`（单 Worker 布尔计数）；`summary.pending` = Redis 队列长度；`summary.history` = MongoDB 窗口内 done 条数；
- `sources.*`：`ok` | `unavailable` | `missing`（worker 未上报）| `invalid`；
- `warnings`：仅任一数据源异常时出现，全部正常时**省略该字段**；前端据此展示“连接失败 / 数据源不可用”警告。

### 2.1 items 分区与 ID 约定

`items` 是混合数组，顺序为：历史（正序）→ running（如有）→ pending（消费顺序）。前端按 `status` 分区：

| status | source | id 格式 | 含义 |
|--------|--------|---------|------|
| `done` | mongodb | `done-{内容指纹}-{created_at}` | 已执行历史（按 `_id` 倒序取最近窗口，服务端反转为正序） |
| `running` | worker | `running-{内容指纹}` | 当前正在执行（至多 1 条；与 done 按内容指纹去重，隐藏最新匹配历史） |
| `pending` | redis | `pending-{内容指纹}-{弹出顺序计数}` | 队列中等待（按消费顺序） |

- **内容指纹**：对事件 JSON（剔除 `created_at` / `_id`）做 FNV-1a 64 位哈希后 base36 编码；事件在 Go/Python 两侧统一 JSON 序列化（键排序一致），去重可靠；
- **pending ID 不用队列下标**：普通 `LPUSH` 会平移下标导致整表重建重播动画，因此用“指纹 + 弹出顺序计数”；
- 同一事件跨状态迁移（pending → running → done）时 ID 前缀不同，前端创建新节点，不跨区复用 DOM；
- 事件自身的 `event` 字段即 [06-格式规范](../06-格式规范.md) 第 1 节定义的事件结构。

### 2.2 PUT /api/events

修改等待执行或历史事件。执行中的事件不可修改。

- 历史事件请求：`{"status":"done","doc_id":"<ObjectID>","event":{...}}`；
- 等待事件请求：`{"status":"pending","position":1,"fingerprint":"<内容指纹>","event":{...}}`；
- `event` 必须是包含非空字符串 `event_type` 的 JSON 对象，`_id` 与 `created_at` 字段会被忽略，编码后不能超过 256 KB；
- 修改历史事件时保留原 `_id` 与 `created_at`；修改等待事件时以 Lua 脚本原子校验队列位置和原始内容后替换；
- `200`：`{"updated":true,"status":"done|pending","fingerprint":"<新内容指纹>",...}`；
- `400`：请求字段、事件格式或状态无效；`404`：目标已不存在；`409`：等待队列已变化；`503`：对应存储暂时不可用；
- 前端保存前解析 JSON；格式无效时停留在编辑态并显示错误，不发送请求；忽略缩进和对象键顺序后内容未变化时直接退出编辑态，不重复提交；保存成功后从“保存”恢复为“编辑”，取消则丢弃未保存内容；详情展开状态在保存及自动刷新后保持不变。

## 3. GET /api/terminal/history

终端历史：仅 MongoDB 已消费的 `terminal` / `response` 事件（终端不读取 Redis pending 与 Worker running）。

- Query：`limit`（可选，`1..300`，默认 `150`）；
- `200`：

```json
{
  "fetched_at": "2026-08-02T11:04:01Z",
  "items": [
    {
      "id": "688e5c4f...",
      "created_at": "2026-08-02T11:03:58Z",
      "event": {
        "event_type": "terminal",
        "payload": { "message": "检查当前任务", "files": [] }
      }
    },
    {
      "id": "688f0a1d...",
      "created_at": "2026-08-02T11:04:00Z",
      "event": {
        "event_type": "response",
        "payload": { "content": "...", "reasoning": "", "tool_calls": [] }
      }
    }
  ]
}
```

- 查询条件：`event_type in ["terminal", "response"]`，按 `_id` 倒序取最近窗口，服务端反转为正序；
- `id` 是 MongoDB ObjectID 字符串，是前端追加去重的**稳定身份**；`created_at` 是 `record_history()` 的时间，不是浏览器提交时间；
- `503`（MongoDB 不可用）：`{"error": "终端历史暂时不可用"}`。

## 4. POST /api/terminal

提交终端命令（最高权限入口，语义见 [08-终端设计](../08-终端设计.md)）。

- 请求体：

```json
{ "message": "检查当前任务", "files": [] }
```

- 校验规则：
  - `message` 非空且 ≤ 4000 字符；
  - `files` 必须为空数组（暂不支持附件）；
  - 请求体 `Content-Length` 上限 16 KB；
- `201` 成功：

```json
{
  "event": {
    "event_type": "terminal",
    "time": "2026-08-02T11:04:01Z",
    "payload": { "message": "检查当前任务", "files": [] }
  },
  "queue": "agent_tasks"
}
```

- `201` 仅表示事件已 `RPUSH` 入队，**不代表 Worker 已消费或 LLM 已执行**；前端显示“已优先入队，等待消费”，不立即把命令画进历史；
- 错误响应：
  - `400`：`{"error": "消息不能为空"}` / `{"error": "消息不能超过 4000 个字符"}` / `{"error": "暂不支持文件附件"}` / `{"error": "请求体不能超过 16 KB"}`；
  - `503`：`{"error": "消息队列暂时不可用"}`。

## 5. GET /api/settings

读取 **Agent 已应用** 的设置值。WebUI 不读取 Agent 容器文件，也不直接写该 Redis Key。

- `200`：`{"system_prompt": "..."}`；
- `503`：Redis 不可用时返回 `{"error": "设置暂时不可用"}`；Agent 尚未初始化 Key 时返回 `{"error": "Agent 尚未初始化设置"}`。

## 6. POST /api/settings/system-prompt

提交 System Prompt 更新事件。

- 请求体：`{"system_prompt": "..."}`；
- `system_prompt` 去除首尾空白后必须非空，原值最长 100000 字符；请求体上限 512 KB；
- `202`：返回 `setting` 事件及 `queue`，仅表示事件已 `RPUSH` 优先入队；
- Worker 原子覆盖 `prompt/system.txt` 成功后才更新 Redis 当前值；前端轮询 `GET /api/settings`，目标值回显后才报告已应用；
- `400`：空值、超长或请求体过大；`503`：队列不可用。

## 7. 文档管理 API

文档页面（`document.html`）使用的 CRUD 接口。数据直接存入 MongoDB 独立集合（默认 `documents`，可用 `MONGO_DOCUMENT_COLLECTION` 覆盖），**不进入 Agent 事件队列，也不写入 `event_history`**。

文档结构：

```json
{
  "_id": "ObjectId",
  "title": "文档标题",
  "content": "正文",
  "created_at": "UTC datetime",
  "updated_at": "UTC datetime"
}
```

### 7.1 GET /api/documents

文档列表，仅返回左侧列表所需的元数据、不含正文，按 `updated_at` 降序：

```json
{ "items": [ { "id": "...", "title": "...", "created_at": "...", "updated_at": "..." } ] }
```

### 7.2 POST /api/documents

创建文档。请求体 `{"title": "...", "content": "..."}`；标题去除首尾空白后必须非空、最长 200 字符，正文最长 1000000 字符，请求体上限 1 MB；`201` 返回完整文档（含 `content`）。

### 7.3 GET /api/documents/{id}

读取单篇文档完整内容；`id` 为 ObjectID 字符串。非法 ID 返回 `400`，不存在返回 `404`。

### 7.4 PUT /api/documents/{id}

整体更新标题与正文并刷新 `updated_at`；校验同创建，`200` 返回更新后的完整文档。

### 7.5 DELETE /api/documents/{id}

删除文档；`200` 返回 `{"deleted": true, "id": "..."}`。

错误统一为 `{"error": "<中文提示>"}`：`400` 参数或 ID 无效、`404` 文档不存在、`503` MongoDB 不可用。

## 8. 前端消费约定

- **事件页**：按 `status` 分三区段（历史 / 正在执行 / 等待），同区段同 ID 复用 DOM 节点，跨状态迁移创建新节点；
- **文档页**：左侧列表只取 `GET /api/documents` 元数据，点选后再取正文；保存前比较输入与已存内容，无变化不提交；新建与切换前提示未保存修改；预览为纯文本，不解析 Markdown；
- **终端页**：按 `id`（ObjectID）去重追加，只追加不重排；首次加载直接定位底部，后续增量平滑滚动（详见[前端优化记录](前端优化记录.md)）；
- **设置页**：表单初值只取 `GET /api/settings`；提交后区分“已入队”与“Agent 已应用”，30 秒内未回显目标值则提示重新读取确认；
- **轮询**：默认 2s（可选 0.5 / 1 / 3 / 5 / 10s），同一时刻最多一个在途请求；暂停时手动刷新仍可用；同步失败 / 超时显示在“最后同步”位置；
- 接口请求与响应字段以本文件为准，与 [06-格式规范](../06-格式规范.md) 的事件结构保持一致。

## 9. 关联文档

- 事件结构与 payload：[06-格式规范](../06-格式规范.md)；
- 事件流页面设计与验收：[前端事件流设计](前端事件流设计.md)；
- 轮询刷新与 DOM 稳定性：[前端优化记录](前端优化记录.md)；
- 终端的事件语义与安全边界：[08-终端设计](../08-终端设计.md)。
