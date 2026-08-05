# 2026-08-02 webui 事件类型重命名 terminal 审查报告

> 日期:2026-08-02。
> 类型:审查报告。
> 性质:历史快照。
> 范围:`webui` 事件类型 → `terminal` 的重命名改动,涉及 `agent/`、`webui_py/` 与现行文档;本报告记录改动清单、审计核验过程与发现。
> 待办:未解决问题统一登记在[2026-08-02 审查核验汇总](2026-08-02-审查核验汇总.md);当前行为以源码为准。

## 1. 背景与目标

- 用户决定将事件协议中的 `webui` 事件类型统一改称 `terminal`,与 `POST /api/terminal`、终端页语义对齐;
- 明确**不涉及**:`webui_py` 服务名/容器名/端口 8081、"WebUI" 界面叫法;
- 明确约定:**历史快照文档**(`docs/审查日志/*`、`docs/webUI/前端事件流设计.md`、`docs/webUI/前端优化记录.md`)保留原样、不回写。

## 2. 改动清单

### 2.1 代码(4 处 + 1 前端标签)

| 文件 | 改动 |
|------|------|
| `agent/task_worker.py:29` | `event_type == "webui"` → `"terminal"`(分发分支) |
| `agent/task_worker.py:88` | `event_type == 'webui'` → `'terminal'`(LLM 投影) |
| `webui_py/main.py:305` | 终端历史查询 `["webui","response"]` → `["terminal","response"]` |
| `webui_py/main.py:332` | `submit_terminal` 封装 `"event_type": "terminal"` |
| `webui_py/static/terminal.html:37` | 数据源标签 `WEBUI · MONGODB` → `TERMINAL · MONGODB` |

### 2.2 现行文档(10 个文件)

- `README.md`、`docs/00-设计哲学.md`、`docs/01-系统架构.md`、`docs/02-事件与队列.md`、`docs/03-模块详解.md`、`docs/05-路线图与创新.md`、`docs/06-格式规范.md`、`docs/07-事件双重身份与信息回调.md`、`docs/08-终端设计.md`、`docs/webUI/前端API格式.md`;
- 修改内容:事件表 `webui`→`terminal`、JSON 示例的 `event_type`、mermaid 状态机/流程图的节点与边标签(`webui`→`terminal`)、投影规则(`qq`/`terminal`/`response`/`tool_return`)、`active` 产生方"webui 分支"→"terminal 分支"、"WebUI 事件"→"terminal 事件"等。

### 2.3 无需改动(已核对)

- `agent/prompt/system.txt`:本就使用 `Terminal:` 与 `<Command>...</Command>`,与投影格式一致;
- `webui_py/main.py` 事件快照三阶段(`worker_stage`/`pending_stage`/`history_stage`):基于内容指纹与状态字段,无事件类型硬编码;
- `docker-compose*.yml`、`.env.example`、`qqbot/`、`agent/llm.py`、`agent/tool.py`、`agent/history_repository.py`:无 `webui` 事件类型引用。

## 3. 未改动范围(明确保留)

| 项 | 理由 |
|----|------|
| `webui_py` 服务名/容器名/端口 8081 | 用户仅要求改事件类型 |
| logger 名 `aagent.webui`、FastAPI title `AAgent WebUI` | 服务标识,非事件类型 |
| 文档中 "WebUI" 界面叫法 | 界面仍叫 WebUI |
| `docs/审查日志/*`、`docs/webUI/前端事件流设计.md`、`前端优化记录.md` | 用户确认历史快照保留(含优化记录"仍使用 `event_type: "webui"`"的旧表述) |
| `.gitattributes`(旧 Go 路径) | 与事件类型无关的历史遗留 |

## 4. 审计核验

### 4.1 方法

- 全库 grep:`"webui"` / `'webui'` / `` `webui` `` / `webui 事件` / `webui事件` 在代码与现行文档中已无事件类型残留,剩余命中均属服务名 / 界面名 / 历史快照;
- `get_errors` 对 `agent/task_worker.py`、`webui_py/main.py` 无编译错误;
- 逐文件核对 mermaid 图(`docs/01` flowchart、`docs/02` stateDiagram)节点与边标签一致性;
- 交叉核对 `system.txt` 的 `<Command>` 描述与 `task_worker.py` 投影格式一致。

### 4.2 一致性结论

事件全链路闭环一致 ✅:`webui_py` 提交 `terminal` 事件 → worker 命中 `terminal` 分支并发布空 `active` → active 分支投影历史中的 `terminal` 为 `<Command>...</Command>` → 终端页查询 `["terminal","response"]` 展示。

## 5. 发现与注意点

| 级别 | 发现 | 说明 | 建议 |
|------|------|------|------|
| 注意 | **存量数据** | MongoDB 历史中已存在的旧 `webui` 事件不再匹配 `["terminal","response"]` 过滤,旧终端命令从终端页消失(事件本身仍保留在库中) | 接受现状(推荐);如需保留展示可一次性迁移 `update_many({"event_type":"webui"},{"$set":{"event_type":"terminal"}})` |
| P3【新】 | **docs/02 §2 将投影归因于 `llm.py`** | "当前 `llm.py` 将 `qq`、`terminal`、`response` 和 `tool_return` 映射到 prompt"——实际投影在 `task_worker.py` 的 active 分支,与 docs/06 §3.3("事件到消息的映射实现在 task_worker.py 的 active 分支")矛盾;属既有问题,非本次改动引入 | 修正为 task_worker.py;docs/03 §4 同类表述建议一并核对 |

## 6. 部署

- 生产 `docker-compose.yml`:`agent` / `webui_py` 无 volume 挂载 → `docker compose build agent webui_py` 后重启容器;
- dev `docker-compose.dev.yml`:有挂载,直接生效。

## 7. 结论

改动范围完整、代码与现行文档一致、无编译错误;剩余 `webui` 引用均属服务名 / 界面名 / 历史快照,符合约定。核心注意点仅存量数据展示(预期行为),另登记一处既有文档归因不准确(见第 5 节)。
