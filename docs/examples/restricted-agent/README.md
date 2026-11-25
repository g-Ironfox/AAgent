# 固定工作流与经验迭代

这套 Workflow 2.0 示例包含三个固定工作流，以及一个经验文件和一个固定恢复备份。运行期间不演进工作流定义，只更新经验。

| 文件 | 职责 |
| --- | --- |
| [restricted-agent-bootstrap.flow](restricted-agent-bootstrap.flow) | 无 LLM 的固定引导：记录任务、工作区、结果；调用主流程和迭代器；主流程异常时逐级回退重试，到 stable 为止 |
| [restricted-agent-main.flow](restricted-agent-main.flow) | 读取经验，使用有限轮次的工作区工具完成 task，返回 result |
| [restricted-agent-iterator.flow](restricted-agent-iterator.flow) | 分析本轮记录和旧经验，生成新版经验；固定节点写回唯一的经验文件 |
| [restricted-agent-experience.md](restricted-agent-experience.md) | 唯一随任务迭代的经验文档，主流程只读 |
| [restricted-agent-stable-main.flow](restricted-agent-stable-main.flow) | 安装时确定的最小主流程备份，与初始主流程相同，供引导恢复 |

## 安装与运行

启动仓库中的 WebUI、Agent、Redis 和 MongoDB，确保 Agent 与 WebUI 都包含当前的文件权限和 checkpoint 三项权限实现。先在模型管理界面配置一个支持原生 tool calls 的可用模型，取得其模型 ID。

在仓库根目录预览文件和权限：

```powershell
python scripts/install_restricted_workflows.py --model YOUR_MODEL_ID
```

确认配置后执行安装：

```powershell
python scripts/install_restricted_workflows.py --model YOUR_MODEL_ID --install
```

安装脚本通过工作区 API 新建五个文件，绑定实际文件 ID，写入权限，并创建初始 checkpoint。它不启动任务、不修改已有文件。遇到任意同名文件会在写入前停止，避免覆盖经验或既有工作流。需要另一套实例时指定 `--prefix another-agent`；API 地址可以通过 `--url http://127.0.0.1:8081` 调整。中途失败会保留已创建文件，处理原因后使用新前缀重试。

在 WebUI 创建进程，选择 `restricted-agent-bootstrap.flow`，只填写 `task`，例如：

> 读取工作区的项目说明，整理一份待办清单，保存为 task-notes.md，并报告无法确认的事项。

从引导进程的终端和返回值查看结果。返回字段是 `status`、`result` 和 `record_file_id`。`status` 可为 `completed`、`recovered`、`failed`；调度进程自身正常结束不等于任务一定成功，应检查这三个字段与执行记录。

仓库中的 .flow 文件是可在编辑器检查的模板，含明确的 `REPLACE_WITH_*` 占位符。推荐使用安装脚本，它会同时绑定模型和文件 ID；仅导入 .flow 不会自动设置文件权限。改用手动导入时，需要替换占位符，并按 [permissions.json](permissions.json) 设置各文件的权限。

工具名已确定的操作使用固定 `Tool` 节点，在 `metadata.tools` 声明接口并直接连接参数端口，包括经验读写、任务记录、checkpoint 和主文件恢复。只有主流程中承接模型调用参数的四个白名单分支保留 `JSON Tool`，将工具成功或错误结果写回对话。无工具的模型调用显式使用空工具定义，避免固定工具声明成为模型可调用工具。文件清单和 checkpoint 差异的数组输出使用 `content` 保存 JSON，以保留其中的对象；任务记录格式保持一致。

## 局部函数与画布结构

引导顶层为 `初始化任务记录 → 执行主流程与逐级恢复 → 记录结果并迭代经验`，展开函数后查看具体节点。

| 函数 | 职责 |
| --- | --- |
| initialize_run | 创建初始 checkpoint、文件清单和任务记录 |
| run_with_recovery | 先试当前版本，失败后遍历可回退版本，成功或耗尽时结束 |
| attempt_main | 启动一次主流程，统一返回成功或错误结果 |
| remember_attempt | 累积尝试历史和错误，并在下一次回退前持久化 |
| restore_main_version | 用当前 revision 写回选定的主流程旧版本 |
| retry_version | 回退一次、执行一次、记录一次；成功时清空后续候选 |
| write_record | 读取最新 revision 并更新任务记录，供多个阶段复用 |
| finish_task | 保存结果与文件变化、调用迭代器、创建最终 checkpoint 和输出摘要 |
| call_iterator | 调用迭代器并统一返回其成功或错误状态 |

主流程包含读取经验、执行一轮任务、追加对话、执行白名单工具四个函数。迭代器顶层只有读取经验、总结经验、写回经验三个函数。

生成代码也拆成 [引导构建器](../../../scripts/build_bootstrap_workflow.py)、[经验构建器](../../../scripts/build_experience_workflows.py) 和 [共用画布助手](../../../scripts/restricted_workflow_graph.py)。Agent 需包含新增的只读固定工具 `workspace.get_file_recovery_plan`；升级 Agent 后再运行新版工作流。

## 固定的执行顺序

1. 引导创建任务前 checkpoint，获取文件清单，创建以 checkpoint 序号命名的任务记录。
2. 主流程读取固定经验文件，将经验作为参考数据，执行 task。只开放 `workspace.list_files`、`workspace.get_file`、`workspace.create_file`、`workspace.update_file` 四个工具。模型发出的其他工具名会被固定路由拒绝，不会转发给 Local Tool 或 Remote Tool。
3. 默认最多执行八轮模型工具批次；耗尽后追加明确的结束要求，用一次无工具 LLM 调用输出已有结果和未完成项。安装时可用 `--max-turns 1..20` 调整，此后固化在工作流中。这是轮次上限，不是单个批次的调用数量上限；执行器原有的活跃时间限制仍生效。
4. 先尝试当前主流程；失败后先保存本次尝试，再沿任务前 checkpoint 的祖先分支，按由近到远的顺序尝试不同的主流程旧版本。每回退一次就创建新主进程执行同一个 task，成功立即停止回退。重复内容只尝试一次，其他 checkpoint 分支不会被使用。stable 是恢复底线：历史中遇到 stable 就停止继续向前查找；找不到历史版本时以固定稳定备份兜底。已经运行的是 stable 时，失败就结束，不重复运行同一个 stable。覆盖主文件之前读取当前 revision，并保留其权限；写入冲突会停止恢复。
5. 引导创建任务后 checkpoint，读取其文件差异，记录任务结果、错误、前后文件清单和文件变更内容，再调用迭代器。执行失败的记录也会交给迭代器总结。
6. 迭代器只有一次无工具 LLM 调用。模型只产生经验正文；经验文件 ID、名称、revision 和写入工具由固定节点确定。更新冲突或模型失败交给引导记录，保留已有经验及主任务结果。
7. 引导记录迭代器状态，再创建迭代后的 checkpoint，并输出任务摘要。

这里的“主流程失败”包括文件加载、JSON/工作流校验、执行和未处理工具错误。主流程工具调用已被错误分支处理、或者任务结果质量不好时，不会触发恢复；迭代器会根据结果整理经验。

## 权限配置

| 对象 | 运行读/写 | 读取/写入门槛 | checkpoint read/create/restore |
| --- | --- | --- | --- |
| 引导 | 3 / 3 | 3 / 4 | true / true / false |
| 主流程 | 1 / 1 | 1 / 3 | false / false / false |
| 迭代器 | 2 / 2 | 2 / 4 | false / false / false |
| 经验 | 0 / 0 | 1 / 2 | false / false / false |
| 稳定备份 | 1 / 1 | 3 / 4 | false / false / false |

引导、迭代器和稳定备份的写入门槛为 4，三个进程都不能修改。主文件只能由引导在恢复分支写入。主流程不能写经验，迭代器可以写经验。引导生成的任务记录继承读写等级 3，迭代器通过引导传入的 record 参数分析记录。

“迭代器只写一个文件”由固定执行图落实：没有模型工具调用和任意目标输入，唯一写节点使用安装时固定的经验 ID。现有等级机制本身不提供文件白名单；应用层权限也不是任意代码的强沙箱，参见 [权限说明](../../process-permissions.md)。

自动恢复只替换主流程文件内容：历史版本从 checkpoint 差异中读取，stable 从固定备份读取。引导未获全工作区 restore 权限，因此不会撤销其他任务产物或经验。任务前、任务后、迭代后三个 checkpoint 保存全工作区内容和权限，供管理端检查或手动恢复；文件清单只记录元数据。checkpoint 的范围是共享工作区，并发任务时不能把它理解为单任务事务。

## 记录与恢复边界

每个任务产生一个 `restricted-agent-run-<checkpoint-seq>.json`。运行初期保存 task、工作区文件清单和初始 checkpoint；主流程结果产生后先写入结果，再运行迭代器。最终文件包含 `task_record`（JSON 字符串）、`iterator_status` 和 `iterator_result`；task_record 内保留 task、status、result、累计 error、attempts、前后 checkpoint 序号、文件清单和 workspace_changes（checkpoint 差异，包含可读文件的前后内容）。attempts 按执行顺序保存每次尝试的状态、结果、错误、版本来源（current/checkpoint/stable）及 checkpoint 序号；每项仍为 JSON 字符串。固定 stable 兜底未绑定历史 checkpoint 时，版本序号为 0，仅表示来源未知，不会恢复空工作区。嵌套的 result 和文件清单保留工具/子流程的 JSON 字符串，避免把任意文本当作结构插入。

这是一套面向工作区文件任务的受限起点：没有网络搜索、任意代码执行或主动等待用户输入。缺少必要信息或工具时，主流程应报告限制。经验是参考材料，不能改变 task 或权限。经验内容的事实质量由模型根据记录评估，并不等同于经过外部验证。

引导本身依赖执行器、数据库和文件 API。服务宕机、稳定备份损坏、主文件被管理端删除、记录写入失败等不会被自动修复；首个主流程错误已成功写入时会保留，进一步错误可以从引导进程日志查看。并发迭代器通过 revision 冲突保护经验，失败时保留先完成的版本。初版建议串行提交任务，确保后一轮读取上一轮更新后的经验。

## 重新生成与验证

```powershell
python scripts/build_restricted_workflows.py
```

生成器仅使用标准库和现有的 Graph 构建助手，不改变执行器或 Workflow 协议。回归测试位于 `agent_runtime/test_restricted_workflows.py`，使用真实调度器、文件权限路由和内存 Redis/Mongo 替身，模型响应由 mock 提供。
