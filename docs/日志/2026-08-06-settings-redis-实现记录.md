# 2026-08-06 设置落 Redis 单键 JSON 实现记录

> 日期:2026-08-06。
> 类型:实现记录。
> 性质:历史快照(记录本次功能实现与缺陷修复过程,当前行为以源码为准)。
> 范围:`agent/queue_client.py`、`agent/task_worker.py`、`agent/settings.json`、`agent/prompt/system.txt`(删除)、`webui_py/main.py`、`docker-compose.yml`。
> 说明:System Prompt 持久化从 `prompt/system.txt` → `settings.json` → 最终落为 Redis 单键 JSON 设置对象(`aagent:settings`,可配 `AGENT_SETTINGS_KEY`);`settings.json` 仅作首次启动默认种子。

## 1. 需求与设计取舍

用户分三步提出:① 把 system_prompt 从 `prompt/system.txt` 挪到 `agent/settings.json`;② 更进一步,把整个设置直接存 Redis,并同步改 FastAPI 侧;③ `GET /api/settings` 应把整个设置对象传给前端,给后续扩展留余地。

设计取舍:

- **Redis 单键 JSON 对象**:运行时以 `aagent:settings` 一个 Key 存 `{"system_prompt": ...}`,后续新增字段直接追加,`GET /api/settings` 原样透出;
- **`settings.json` 降级为默认种子**:仅首次启动/无缓存时写入 Redis;版本化兜底默认,避免代码内嵌大段 prompt;
- **Agent 仍是唯一写入者**:WebUI `POST /api/settings/system-prompt` 保持 `setting` 事件回环,由 worker 应用并落 Redis,保留 `record_history` 审计,避免直接写 Key 造成的状态漂移;
- **旧扁平键自动迁移**:兼容既有 `aagent:settings:system_prompt`(纯字符串)部署,首次启动迁移到新对象并删除旧键,用户设置不丢失;
- **消除文件/Redis 不一致窗口**:不再写文件,Redis 为唯一真源,原 A39 场景不复存在。

## 2. 实现内容

### 2.1 `agent/queue_client.py`

- 新增 `AGENT_SETTINGS_KEY`(默认 `aagent:settings`);保留 `AGENT_SYSTEM_PROMPT_KEY`(仅迁移用,不写入);
- 新增 `get_settings()`(读 JSON 对象,缺失/损坏返回 `{}`)、`set_settings()`(写 JSON);
- `get_system_prompt()`/`set_system_prompt()` 改为对设置对象 `system_prompt` 字段的读改写;
- 新增 `get_legacy_system_prompt()`/`clear_legacy_system_prompt()` 供迁移。

### 2.2 `agent/task_worker.py`

- `default_system_prompt()`:读 `settings.json` 种子(校验非空字符串);
- `read_system_prompt()`:读 Redis 设置,字段缺失回退默认种子;
- `apply_system_prompt()`:仅写 Redis,不再写文件;
- `initialize_system_prompt()`(修复 A37 空缓存崩溃 + 字段级校验):`get_system_prompt()` 非 None 即跳过;否则先迁移旧扁平键(写入后删除);再无则种子写入。

### 2.3 `webui_py/main.py`

- `SYSTEM_PROMPT_KEY` → `SETTINGS_KEY`(默认 `aagent:settings`);
- `GET /api/settings`:读整个设置 JSON 对象**原样返回**(`{"system_prompt": ..., ...}`),后续字段自动透出;缺 `system_prompt`/非 dict 返回 503「Agent 尚未初始化设置」;
- `POST /api/settings/system-prompt`:不变,仍 RPUSH `setting` 事件,由 worker 应用。

### 2.4 `docker-compose.yml`

- webui 环境变量 `AGENT_SYSTEM_PROMPT_KEY` → `AGENT_SETTINGS_KEY`(默认 `aagent:settings`)。

### 2.5 `agent/settings.json` / `agent/prompt/system.txt`

- 新增 `agent/settings.json`:`{"system_prompt": "<与旧 system.txt 逐字一致的内容>"}`;
- 删除 `agent/prompt/system.txt`(运行时真源已迁至 Redis,种子在 settings.json)。

### 2.6 缺陷修复:初始化不校验 `system_prompt` 字段

**现象**:初版 `initialize_system_prompt` 用 `if get_settings(): return` 判对象非空,若设置对象存在但缺 `system_prompt` 字段,初始化被跳过,`read_system_prompt` 每轮回退默认、WebUI 返回 200 却缺字段。

**修复**:改为 `get_system_prompt() is not None` 字段级校验(缺失即走迁移/种子);WebUI `GET /api/settings` 同步要求 `system_prompt` 为字符串,否则 503。

## 3. 兼容与迁移

- 新部署(Redis 空):首次启动种子写入 `aagent:settings`;
- 旧部署(存在 `aagent:settings:system_prompt` 扁平键):首次启动迁移到对象并删除旧键;
- WebUI 前端不变:`setting.js` 只读 `settings.system_prompt`,返回整个对象向后兼容。

## 4. 涉及文件

- `agent/queue_client.py`、`agent/task_worker.py`、`agent/settings.json`(新增)、`agent/prompt/system.txt`(删除)、`webui_py/main.py`、`docker-compose.yml`;
- 文档同步:02-事件与队列、03-模块详解、04-配置与部署、06-格式规范、webUI/前端API格式。

## 5. 验证边界(如实说明)

- VS Code 对全部改动文件诊断为零错误;已静态核验:三侧 Key 一致、迁移三分支、占位符替换链路、WebUI 只读语义、Dockerfile `COPY . .` 打包种子;
- 会话中功能测试(假 Redis 连接)被用户取消,未取得输出;
- 真实 Redis/容器环境:首次启动种子、旧键迁移、WebUI 回显未实测。

## 6. 已知边界(详见审查报告)

- `initialize_system_prompt` 启动期仍硬依赖 Redis(Redis 不可达时 crash loop,compose health 门控缓解);
- 迁移中断时旧扁平键可能残留(无写入方,仅占一个 Key);
- 每次 `active` 一次 Redis GET(单 worker 低频,无性能问题)。
