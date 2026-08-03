# 2026-08-03 WebUI 设置页 / System Prompt 审查报告

> 本报告记录"WebUI 新增设置页 + setting 事件由 Agent 侧落盘落缓存"改动的总结与静态审查结论。
> 审查方式：纯静态核验（VS Code 诊断 + 源码/文档交叉比对），未运行容器、未执行本机 Python/Docker 命令。
> 结论性质：**参考意见**，本次不修改任何代码。

## 1. 改动总结

### 1.1 设计模型（本次核心决策）

- **Agent 是设置的唯一所有者**：`prompt/system.txt` 与 Redis Key `aagent:settings:system_prompt` 都只由 agent 写入；
- WebUI 只做两件事：`GET /api/settings` 读 Redis 当前值用于回显，`POST /api/settings/system-prompt` 把 `setting` 事件 `RPUSH` 插队发布；
- 回显真实性：前端保存后轮询 `GET /api/settings`，**只有 Redis 回显值等于提交值**才显示"Agent 已应用"，否则停留在"已入队 / 待确认"，杜绝假回显；
- 重启持久化：agent 启动时若 Redis 已有值则恢复文件，仅当 Key 不存在时才用镜像内 `system.txt` 初始化，避免重建容器丢失页面设置。

### 1.2 文件级改动

| 文件 | 改动 |
|------|------|
| `agent/queue_client.py` | 新增 `AGENT_SYSTEM_PROMPT_KEY`（默认 `aagent:settings:system_prompt`）、`set_system_prompt()`、`get_system_prompt()` |
| `agent/task_worker.py` | 新增 `SYSTEM_PROMPT_PATH`、`read_system_prompt()`、`apply_system_prompt()`（临时文件 + 原子替换 + 写 Redis）、`initialize_system_prompt()`；`setting` 分支改为 `isinstance(str) 且非空` 才应用；`active` 分支改用 `read_system_prompt()`；`main()` 进入循环前调用 `initialize_system_prompt()` |
| `webui_py/main.py` | 新增 `MAX_SYSTEM_PROMPT_CHARS=100_000`、`MAX_SETTINGS_BODY_BYTES=512*1024`、`SYSTEM_PROMPT_KEY`；`terminal_body_guard` 扩展守卫 settings 端点；新增 `GET /api/settings`、`POST /api/settings/system-prompt`（202） |
| `webui_py/static/api.js` | 新增 `fetchSettings()`、`submitSystemPrompt()` |
| `webui_py/static/setting.html` / `setting.js` / `css/setting.css` | 新增设置页（导航/表单/状态/轮询确认逻辑） |
| `webui_py/static/index.html` / `terminal.html` | 导航新增"设置"入口 |
| `docker-compose.yml` | webui_py 显式传入 `AGENT_SYSTEM_PROMPT_KEY` |
| `docs/06-格式规范.md` | `setting` 事件产生方/消费行为更新，新增 Redis Key 所有权与轮询回显说明 |
| `docs/04-配置与部署.md` | 新增 `AGENT_SYSTEM_PROMPT_KEY` 配置项 |
| `docs/webUI/前端API格式.md` | 新增 §5 `GET /api/settings`、§6 `POST /api/settings/system-prompt`，原"前端消费约定/关联文档"顺延为 §7/§8 |

## 2. 审查通过项（结论：设计正确、实现一致）

1. **所有权边界清晰**：WebUI 不直接写 Redis 缓存，与"回显真实性交给 Agent 侧同步"的诉求一致；文档已明确"该 Key 只由 worker 在成功应用后更新"。
2. **插队语义正确**：WebUI 用 `RPUSH` + 消费端 `BRPOP`，与 `insert_to_queue` 的最高优先级插队语义一致，也复用了 `submit_terminal` 的既有模式。
3. **原子文件替换**：临时文件写同一目录后 `replace`，同文件系统原子替换；写入失败不破坏旧文件。
4. **Key 三侧一致**：agent `queue_client`、webui `main.py`、`docker-compose.yml` 均使用 `AGENT_SYSTEM_PROMPT_KEY` 且默认值相同，无失配。
5. **前端状态机稳健**：首次 GET 成功前锁定编辑器；保存失败保留草稿、可手动"重新读取"；30 秒轮询超时给出明确提示而非假装成功。
6. **容错提升**：`setting` 分支由裸 truthy 改为 `isinstance(str) 且非空`，杜绝非字符串写文件导致的崩溃。
7. **文档同步完整**：事件格式、配置、前端 API 三处文档与本实现一致；API 文档章节编号 0–8 无重复。

## 3. 参考意见（不修改代码，按优先级排列）

### P2 启动期 Redis 硬依赖可能造成崩溃循环
`main()` 中 `initialize_system_prompt()` 位于 `while True` 的 `try/except` 之外。若启动时 Redis 不可达，`get_system_prompt()` 抛 `ConnectionError`，worker 直接退出，`restart: unless-stopped` 会反复重启形成 crash loop。
- 缓解因素：compose 中 agent 有 `depends_on: redis condition: service_healthy`，正常编排下 Redis 先就绪，风险被大幅压低；但 dev 模式（agent `sleep infinity` 后手动 exec 运行 `task_worker.py`）或 Redis 恰好抖动时仍会暴露。
- 参考改法（供后续评估）：把初始化移入循环内 try，或包一层 try/except（失败时先按文件初始化并延迟重试），保持与循环内 `set_worker_status` 相同的容错风格。

### P3 文件已改、Redis 写失败的不一致窗口
`apply_system_prompt()` 先写文件、后写 Redis。若 Redis 写失败（超时/断连），文件已是新值而 Redis 是旧值：`active()` 读文件会用新值，WebUI 回显旧值，且下次重启 `initialize_system_prompt()` 会用 Redis 旧值覆盖文件，**新设置丢失**。
- 属罕见故障路径，可接受；建议至少记录异常日志便于排查。

### P3 `initialize_system_prompt()` 不防空值
用 `cached_prompt is None` 判断，若 Key 存在但为空串（外部 redis-cli 误写），会把文件清空。`setting` 分支有非空保护，但初始化路径没有。参考改法：`if cached_prompt:` 而非 `is not None`。

### P3 dev 工作流陷阱（建议文档提示）
`docker-compose.dev.yml` 挂载 `./agent` 源码。本地直接改 `prompt/system.txt` 后重启容器，会被 Redis 旧缓存覆盖（`initialize_system_prompt()` 恢复缓存值）。要回退默认值需先删 Redis Key。建议在 `docs/04` 或 dev 说明中加一句提示。

### P4 命名与接口语义
- `terminal_body_guard` 中间件现在同时守卫 settings 端点，函数名有误导，纯命名问题；
- `GET /api/settings` 用 503 表达"Agent 尚未初始化设置"，与"服务不可用"语义混淆；前端按错误锁定编辑，可接受，但 404/409 或 200 + null 更精确（参考意见）。

### P4 并发与信息暴露（可接受，提示即可）
- 多标签页并发保存时，轮询比较"等于我提交的值"，若另一页先应用别的值，本页会超时误报——极端场景；
- `setting` 事件经 `record_history` 落 MongoDB，事件流页会显示含完整 system_prompt 明文的事件；属可审计特性，但 prompt 内容会以明文进入 MongoDB 历史与 WebUI；
- 设置接口同 `/api/terminal` 一样无鉴权，能改 system prompt 即能注入 LLM 指令；与既有内网威胁模型一致，仅提示。

## 4. 工作区杂项（与本次功能无关）

- `agent/prompt/system.txt` 存在未提交的手动改动（新增"好友列表"段），疑似测试期间手动编辑，非本次功能产生；提交时注意与本次功能改动区分。
- 建议确认 `system.txt` 为 UTF-8 编码：`read_system_prompt()` 固定 `encoding="utf-8"` 读取，若文件被以 GBK 保存会抛 `UnicodeDecodeError`（此前 `active` 分支同样按 UTF-8 读，非本次引入）。

## 5. 部署提醒

- `webui_py` 无 volume 挂载，需 `docker compose build webui_py`；`agent` 需 `docker compose build agent`（dev compose 挂载源码则直接生效）；
- 若部署时 Redis 中已存在旧值/脏值，首次启动会以该值覆盖文件；如需重置默认 prompt，先删除 Key `aagent:settings:system_prompt` 再重启 agent。

## 6. 结论

本次改动设计正确、实现与文档一致，静态审查未发现阻断性问题。核心风险点是 **P2 启动期 Redis 硬依赖**（受 compose health 门控缓解），以及 P3 的两处一致性/空值边界，均为参考意见，暂未改代码、未登记入"审查核验汇总"。
