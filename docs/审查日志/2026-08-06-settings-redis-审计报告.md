# 2026-08-06 设置落 Redis 单键 JSON 审计报告

> 日期:2026-08-06。
> 类型:审计报告。
> 性质:历史快照。
> 范围:`agent/queue_client.py`、`agent/task_worker.py`、`agent/settings.json`、`agent/prompt/system.txt`(删除)、`webui_py/main.py`、`docker-compose.yml` 及 02/03/04/06/前端API格式 文档。
> 说明:System Prompt 持久化从 `prompt/system.txt` 迁到 `settings.json` 再落为 Redis 单键 JSON 设置对象(`aagent:settings`)的静态审查;审查中发现并修复 1 项 P3(初始化与 GET 未校验 `system_prompt` 字段),修复证据见第 3 节;未做真实 Redis/容器实测,验证边界见第 4 节。

## 1. 结论

通过。设置改为 Redis 单键 JSON 对象(`aagent:settings`,可配 `AGENT_SETTINGS_KEY`)为运行时唯一真源,`settings.json` 仅作首次启动默认种子;agent 与 webui 双侧读取路径、`setting` 事件回环、旧键迁移均正确;审查中发现 1 项 P3(初始化只判对象非空、未校验 `system_prompt` 字段)已在同轮修复,遗留 3 项 P4 边界(见第 3 节),不影响主流程。

## 2. 已核验

1. **Key 三侧一致**:`agent/queue_client.py`、`webui_py/main.py`、`docker-compose.yml` 均以 `AGENT_SETTINGS_KEY`(默认 `aagent:settings`)为设置对象键,默认值一致;
2. **A37 空缓存崩溃已修复**:`initialize_system_prompt` 现为字段级校验(`get_system_prompt() is not None` 即跳过),不再 `apply_system_prompt(None)`;首个无缓存启动走旧键迁移或种子写入;
3. **A39 文件/Redis 不一致窗口已消除**:不再写文件,Redis 为唯一真源,「重启用 Redis 旧值覆盖文件导致设置丢失」路径不复存在;
4. **旧键迁移正确**:有 `system_prompt`→跳过;无值+旧扁平键存在→迁移写入并删除旧键;两者皆无→`settings.json` 种子写入;
5. **缺省回退**:`read_system_prompt()` 在 Redis 键缺失/字段缺失时回退 `settings.json` 默认值,`active` 仍可构造 system 消息;
6. **WebUI 只读语义不变**:`GET /api/settings` 原样返回整个设置对象(前端只消费 `system_prompt`,向后兼容);`POST /api/settings/system-prompt` 仍走 `setting` 事件回环,Agent 保持唯一写入者,`record_history` 审计保留;
7. **占位符链路未变**:种子与旧 `system.txt` 逐字一致,`{{BOT_ID}}`/`{{SYSTEM_DOCUMENTS_PROMPT}}` 仍在 `active` 时替换;
8. **镜像打包**:`agent/Dockerfile` 为 `COPY . .`,`settings.json` 随镜像;`prompt/system.txt` 已删除,现行代码与现行文档无残留引用(审查日志快照保留旧描述,不回写);
9. **文档同步**:02/03/04/06/前端API格式 已按新设计更新;`AGENT_SETTINGS_KEY` 配置项已替换 `AGENT_SYSTEM_PROMPT_KEY`;
10. **修复后边界**:`initialize_system_prompt` 校验 `system_prompt` 字段存在;`GET /api/settings` 对缺字段/非 dict 返回 503「尚未初始化」,语义对齐。

## 3. 问题清单

| 级别 | 问题 | 说明与建议 |
|---|---|---|
| P3 | 初始化只判设置对象非空、未校验 `system_prompt` 字段(已修复) | 初版 `if get_settings(): return`,若对象存在但缺 `system_prompt`(手动编辑或未来先写其他字段)会跳过初始化,`read_system_prompt` 每轮回退默认、WebUI 返回 200 缺字段;已改为 `get_system_prompt() is not None` 字段级校验,WebUI GET 同步要求 `system_prompt` 为 str(缺则 503) |
| P4 | 迁移中断时旧扁平键残留 | 设置对象已存在时 `initialize_system_prompt` 提前返回,不清理旧键;旧键无写入方、仅占一个 Key,可接受;如需彻底清理可在迁移逻辑无条件 `delete` |
| P4 | `AGENT_SYSTEM_PROMPT_KEY` env 若在 `.env` 自定义会使迁移查错键 | 新部署应只配 `AGENT_SETTINGS_KEY`;旧 env 仅影响迁移目标键,默认值已对齐,低风险 |
| P4 | 每次 `active` 一次 Redis GET | 原来读文件,现读 Redis 设置(单 worker 低频,无性能问题);`read_system_prompt` 有本地缓存可进一步优化,暂无必要 |

## 4. 验证方式

- 静态证据:VS Code 对全部改动文件诊断零错误;已核验三侧键一致、迁移三分支、占位符替换链路、WebUI 只读语义、Dockerfile 打包;
- 未验证:会话中功能测试(假 Redis 连接)被用户取消,未取得输出;未在真实 Redis/容器环境实测首次启动种子、旧键迁移与 WebUI 回显。

## 5. 涉及文件

- `agent/queue_client.py`、`agent/task_worker.py`、`agent/settings.json`(新增种子)、`agent/prompt/system.txt`(删除)、`webui_py/main.py`、`docker-compose.yml`;
- 文档:02-事件与队列、03-模块详解、04-配置与部署、06-格式规范、webUI/前端API格式;
- 实现细节见 [实现记录](../日志/2026-08-06-settings-redis-实现记录.md)。

## 6. 建议

- 部署验证:真实环境首次启动(Redis 空)→ 种子写入 → `GET /api/settings` 回显;旧部署(存在旧扁平键)→ 自动迁移 → 旧键删除;
- 后续如需「设置页多字段」扩展,直接向 `aagent:settings` 对象追加字段,`GET /api/settings` 自动透出;
- `initialize_system_prompt` 启动期 Redis 硬依赖(crash loop 风险)仍存在,见 agent 汇总 §5。

## 7. 关联文档

- 领域汇总:[2026-08-05 Agent 问题汇总](2026-08-05-agent-问题汇总.md);
- 实现记录:[2026-08-06 设置落 Redis 单键 JSON 实现记录](../日志/2026-08-06-settings-redis-实现记录.md);
- 接口契约:[前端API格式](../webUI/前端API格式.md);
- 历史快照:[设置页](历史/2026-08-03-设置页-system-prompt-审查报告.md)、[agent 结构封装](历史/2026-08-05-agent结构封装-审查报告.md)。
