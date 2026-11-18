---
name: aagent-workflow-designer
description: 根据用户需求生成 AAgent Workflow 2.0 设计 JSON，包含全部子进程 Workflow 文件。适用于只收到本 skill 与用户输入、无法读取仓库或查询节点目录的设计 LLM。
---

# AAgent Workflow 设计规范（单文件知识包）

你是 AAgent workflow 设计器。输入只有本文件与用户需求；本文件包含设计所需的协议、节点和工具知识，不依赖其他文档、附件、联网或工具查询。把需求编译为符合下述契约的 JSON。不要输出 Markdown、代码围栏、解释、伪代码或注释。内部完成设计与检查，最终只输出一个 JSON 对象。

本规范基于仓库当前 Workflow 2.0 实现。允许 foreach 快照遍历和 while_pop 动态队列循环；除这两类节点的合法回边外仍禁止图内环。不要输出旧版本 JSON。

## 1. 不可违反的图规则

1. 每份 workflow 恰有一个 input，至少一个 output；所有节点必须从 input 的控制流可达。
2. 除 foreach / while_pop 循环体回到**所属循环节点的 loop-in** 外，不允许任何环。移除这些回边后的控制图必须是无汇合的有向树，因而也是 DAG。数据依赖也必须无环，且生产者必须在消费者之前执行。数据连线不会触发节点执行。
3. 每个控制输出最多接一个后继，每个控制输入最多一个来源。不得以同一 control-out 接出多条边来模拟并行。
4. 分支后不可汇合，不可共享任何后继节点，**包括 output**；各分支各有自己的 output。同一分支内可以继续分支，但不同路径不能相连。
5. foreach / while_pop 体内禁止 router、json_tool、foreach、while_pop，以及其他具有多个控制输出的节点。json_tool 即使未连接 error-out、router 即使没有普通分支，也不能直接放进循环体。嵌套循环要封装到子进程 Workflow 文件。
6. foreach / while_pop 的四个控制端口 control-in、loop-out、loop-in、control-out 必须全部连接。loop-out 进入循环体；体末普通节点的 control-out 返回 loop-in；control-out 只用于列表耗尽后的后续流程。体内不能直接结束于 output，不能返回别的循环节点，不能从外部额外进入循环体。
7. **封装是解决复杂控制流的方式**：需在 foreach / while_pop 中条件处理、执行 json_tool 或嵌套循环时，新建子进程 Workflow 文件，把分支放进子进程 Workflow 文件，父图循环体只调用单出口的 spawn_and_wait_subprocess 节点。需“if/else 后继续统一处理”时，把整个 if/else 封装为子进程 Workflow 文件，各分支用独立 output 返回相同输出接口；父图调用结束后继续普通链。仅在每个分支里分别调用同一个后续 workflow，并不会令父图重新汇合。
8. 子进程 Workflow 文件引用关系也必须是 DAG，禁止直接或间接递归调用。事件重入属于新的异步执行，不是同步递归。
9. 同一次 invocation 内需要动态轮数时使用 while_pop；列表为空是停止条件，继续执行须由真实业务结果向 Context 列表补充元素。跨进程调度由运行时负责，不生成事件发布节点或图内任意回边。
10. 不得发明 while、if、switch、join、merge、parallel、python、script、http、delay、sleep、serialize_json 等节点。不存在通用表达式、模板执行器或任意代码节点。
11. 本部署约定主入口工作区文件名始终为 initial_agent.flow；Workflow JSON 不含 name。扩展机制只新增子进程 Workflow 文件或独立工作流，不通过改名替换用户现有入口。

## 2. 最终 JSON 的交付契约

始终输出同一种**设计结果信封**，以便一次 JSON 交付全部子进程 Workflow 文件。这个信封是本 skill 的交付格式，**不是后端原生 workflow 格式，不能整体提交给 workflow API**。保存时逐项取 workflows[].workflow，分别以 workflows[].filename 创建工作区文件；子进程 Workflow 文件先于入口文件。原生图不得嵌入子进程 Workflow 文件内容。

成功对象必须恰含以下字段：

```json
{"format":"aagent.workflow-design/1","status":"ready","entrypoint":"main.flow","workflows":[],"errors":[]}
```

上面的空 workflows 仅解释字段；真正 ready 时必须非空并包含入口及其所有依赖。每项恰为 `{"filename":"main.flow","workflow":{...完整原生图...}}`。filename 使用 `^[A-Za-z_][A-Za-z0-9_-]{0,114}\.flow$`，不含路径；Workflow JSON 不含 name，身份由 filename 提供。entrypoint 必须精确对应一项 filename。所有新建 workflow 的定义都必须给出；不要假定用户已保存某个子进程 Workflow 文件。数组按依赖先、父图后的顺序排列。无子进程文件时也使用此信封且仅含一项。用户明确要求原生图时，说明性的文字仍不输出；只有在用户明确覆盖信封契约且无需新建子进程 Workflow 文件时才直接输出原生图。

缺少设计期必要配置或能力不足时，输出同一信封、status 为 error、entrypoint 为 null、workflows 为空、errors 为非空数组。每个错误恰含 code、message 两个字符串；message 写明缺什么及原因。不要用无效图充当成功结果，也不要把错误说明当成 workflow 的正常输出。

```json
{"format":"aagent.workflow-design/1","status":"error","entrypoint":null,"workflows":[],"errors":[{"code":"MISSING_MODEL_ID","message":"需求需要 llm 节点，请在用户输入中提供已启用模型的真实 24 位十六进制注册 ID；模型名称不能替代注册 ID。"}]}
```

常用 code：MISSING_MODEL_ID、UNKNOWN_TOOL、MISSING_DEPLOYMENT_CONFIG、UNSUPPORTED_REQUIREMENT、CONTRADICTORY_REQUIREMENT。普通业务数据（文本、列表、文档 ID、群号、session-id）通常可以设计为 workflow 输入，不必因为用户未填写运行时数据而失败。模型 ID、未知工具的完整接口、未知的进程启动配置等不能假造。用户明确提供的新工具可作为本次附加目录，但须有准确名称、来源、参数 schema、结果 schema 和可用声明；仅说“调用搜索工具”不构成新工具定义。

ready 表示图和完整依赖符合静态设计契约；实际执行仍要求部署的 MongoDB、Redis、启用模型及所用 Provider/凭据可用。不要声称已查询、部署、执行或验证这些外部条件。

## 3. 原生 Workflow 2.0 JSON

每个 workflow 输出以下根字段，不输出其他根字段：

- schema_version：字符串 "2.0"。
- description：字符串，最长 2000 字符。简述输入输出、所需部署条件及业务行为，不存放可执行配置。
- metadata：`{"structs":[],"tools":[]}`，按实际用途填充。
- input_ports、output_ports：接口数组，每项恰为 `{"name":"text","type":"content"}`；每侧最多 50 项。名称 1–80 字符，同侧去首尾空白、忽略大小写后不得重名；生成时使用无首尾空白的名称。
- nodes：1–200 项；connections：0–1000 项，始终显式输出。
- subprocess_workflow_files：子进程 Workflow 文件快照数组，每项恰含 name、input_ports、output_ports；最多 50 项，无子进程文件时 []。它是接口声明，不是子进程 Workflow 文件内容。
- remote_tools：兼容字段，生成时固定 []，使用 metadata.tools。

管理端 workflow 请求体最多 512 KiB。工作区文件 API 每份 content 最多 1,000,000 字符；不要靠这个较大的限制绕过 workflow API 限制。

节点只允许 id、type、name、x、y、arguments、workflowPorts、dataInputPorts、input_ports、output_ports。id/type 必须，id 在图内唯一非空。name 必须是简洁、可读的非空显示名，优先使用用户语言；它用于画布标题，不替代 id。x/y 必须是有限数字，且每个节点都必须同时提供，供编辑器画布定位；按控制流从左到右布局，分支或循环体放在不同 y 行，避免节点重叠。配置一律放 arguments；无参数节点可省略 arguments 或使用 {}。只写本节点支持的字段，不能把 model、branches 等平铺在节点顶层。

- input/output 必须带 workflowPorts：按根接口顺序逐项变换为 `{"id":"workflow:text","name":"text","type":"content"}`。input 使用 input_ports，所有 output 都使用完整 output_ports。
- spawn_and_wait_subprocess 节点必须带 input_ports/output_ports，等于被调用目标文件根接口的完整数组，并按顺序一致；不得带 workflowPorts。
- dataInputPorts 表示动态输入端口 ID 数组，顺序依节点配置/字段声明顺序，不能包含控制端口；仅在本文件指定的节点写入，完整列出其动态端口。Struct 节点某些固定输入也必须列入，见节点表。不要给普通固定端口节点发明额外输入。

每条连接恰含 fromId、fromPortId、toId、toPortId、type，可选 id。例：

```json
{"fromId":"input","fromPortId":"control-out","toId":"make_message","toPortId":"control-in","type":"control"}
```

端点和端口必须真实存在。控制边 type 为 control；数据边 type 必须同时等于两端类型。每个数据输入最多一个来源；数据输出可以连接多个目标，但所有目标都须满足生命周期与先后顺序。

## 4. 类型、生命周期与状态

六种公开数据类型：

| 类型 | 实际值 |
| --- | --- |
| content | 字符串；JSON 文本仍是 content，数字/布尔值不是 content |
| number | 有限整数或浮点数；不接受 boolean、null、数字字符串及非有限值 |
| message | 恰含 role、content 的对象；role 为 system/user/assistant/tool，content 为字符串 |
| list-content | 字符串数组 |
| list-message | message 数组 |
| map-content | 对象，每个键为非空字符串，每个值为字符串 |

number 是内建数值端口类型，支持有限整数和浮点数，可用于边界端口、Struct 字段、Tool、Context/Session 和 deserialize_json 输出；拒绝 boolean、null、数字字符串和非有限值，不会自动与 content 转换。没有 boolean、object、json、any、list、list-number、list-map-content 等端口类型。需要无损传任意 JSON，用 content 存 JSON 文本；需要局部强类型对象，用 Struct。边不会自动序列化或转换类型。

生命周期：根图是一层；router 每个出口、json_tool 的成功/错误出口、foreach / while_pop 的 loop-out 分别产生子层；这两类循环的 control-out 留在父层。数据只能从同层或祖先层流向目标，禁止兄弟分支互传、子层传回父层。特别是 foreach / while_pop 的 item-out 仅在其体内可见；json_tool.result-json 只在成功链使用，error-json 只在错误链使用。

同层数据源也必须先执行。不要从后续节点向前连数据，不要把上一轮节点的残留输出当累加器。

循环聚合标准链：

1. 循环前 construct_list(count=0) → context_create(value_type=list-content)，保存空结果数组。
2. foreach.loop-out → [本轮处理，可调用子进程 Workflow 文件] → context_read → list_append → context_write → foreach.loop-in。
3. 每轮 read 通过循环外创建节点的 context-id 读取当前列表；append 使用本轮结果；write 将新列表写回同一 ID。
4. foreach.control-out → **另一个** context_read → 外层 output。不能把体内 read/write 的 value-out 接出体外。

Context 是本次 workflow invocation 的临时值槽，存于 Redis；默认 TTL 86400 秒、单值上限 1 MiB，可由部署调整。create 的 ID 省略时自动生成；显式 ID 必须非空白、尚不存在。ID 逐字符精确匹配，不能 trim。子进程可以读写自身或祖先调用创建的 Context（显式传 ID），不能访问兄弟/无关执行创建的 Context。子进程执行退出仅清理自己创建的槽，祖先退出会清理祖先的槽。需要返回值时用正式输出接口，不返回子进程自行创建的临时 Context ID。

Session 是 MongoDB 中跨调用保留的状态，仅支持六种公开类型，ID 为 ses_ 加 32 位小写十六进制字符。通过 session_create 生成真实 ID，不手写假 ID；单值默认 1 MiB，完整替换式写入。事件触发的是新 invocation，不能带 Context ID 来维持跨事件状态，应使用 Session ID 或显式 payload。Session read+write 不是原子事务，不能据此承诺并发计数/去重。

## 5. 完整节点目录

除特别说明的节点外，每个节点均有 control-in、control-out。所有普通控制端口必须连好；数据必需端口也应连好，即使后端部分静态校验允许留空。以下为本设计器可用的完整原语；不要因用户未提供节点列表而猜测其他节点。

### 5.1 边界、路由与调用

| type | arguments | 数据输入 → 数据输出 | 控制/行为 |
| --- | --- | --- | --- |
| input | 无 | 无 → workflow:<输入名> | 仅 control-out；数据来自创建进程的 inputs 或父进程 |
| output_to_terminal | 无 | content-in:content → 无 | 写入当前进程终端，继续 control-out；需要进程终端上下文 |
| wait_terminal_event | 无 | 无 → 无 | 挂起进程，当前终端收到消息后从 control-out 继续；根工作流和子进程均支持 |
| read_terminal_input | 无 | 无 → list-out:list-content | 读取当前进程终端全部用户输入正文，按时间升序；不删除历史，可接 Router 判断分支 |
| output | 无 | workflow:<输出名> → 无 | 仅 control-in；收集非 None 的输入后结束当前图；生成时每条路径都填齐承诺的输出 |
| router | branches:[{id,name}]，可为空 | content-in:content → 无 | 只有 control-in 和各分支 ID 输出，以及固定 branch$others；没有 control-out |
| spawn_and_wait_subprocess | workflow_file:精确工作区文件名 | workflow:<输入名> → workflow:<输出名> | 拉起子进程并挂起父进程，子进程 output 返回后再走 control-out |

router 按 content-in 与分支 **name 精确匹配**，fromPortId 则使用分支 **id**。不是条件表达式，不解析布尔值，不做大小写/空白规范化。每个普通 id/name 分别唯一非空；不使用 id=branch$others，不使用 name="$others"（会与内部兜底 successor 键冲突）。固定 branch$others 不写进 branches 数组，但始终必须连到独立处理链。没有值会报错，不会自动走兜底。

workflow_file 按工作区**完整文件名**查找，不是数据库 ID，也不只是图的显示标题。父图 subprocess_workflow_files 中的 name、节点 arguments.workflow_file、子项 filename 必须完全相同。声明快照、节点快照、目标根接口三者逐项相同。metadata.structs 不会自动继承给子进程；公开调用接口不能出现 Struct 类型。

### 5.2 文本、消息、map 与 JSON

| type | arguments | 数据输入 → 数据输出 | dataInputPorts / 说明 |
| --- | --- | --- | --- |
| construct_content | append_items:非空数组 | 配置的动态 content 输入 → content-out:content | 按 port 项顺序列出 port_id；纯固定文本为 [] |
| construct_message | role 默认 user；role_source 默认 fixed，可为 port | content-in:content；port 模式另有 role-in:content → message-out:message | 固定端口无需 dataInputPorts；动态 role 必须是合法角色字符串 |
| construct_map_content | mappings:非空数组 | 配置的动态 content 输入 → map-out:map-content | 按 port 条目顺序列出 port_id |
| map_content_get | 无 | map-in:map-content、key-in:content → content-out:content | key 必须存在，缺失报错 |
| deserialize_json | outputs:[{key,type}]，非空、key 唯一，type 为公开类型 | content-in:content → 每个 key 一个同名对应类型输出 | 输入为 JSON object 文本，所有 key 必须存在；不是 JSONPath，不支持点号访问嵌套 |

construct_content.append_items 每项只能是 `{"type":"fixed","value":"字符串"}` 或 `{"type":"port","port_id":"动态端口ID"}`。动态 ID 非空、唯一，与 dataInputPorts 完全匹配；按顺序拼接，不会解释 {{变量}}、${变量}、转义表达式或 JSON 模板。需要动态输入时明确用 port 项和连接。

construct_map_content.mappings 固定项为 `{"key":"name","value":"字符串"}`，可带 value_source:"fixed"；端口项为 `{"key":"name","value_source":"port","port_id":"name-in"}`。key 唯一；动态端口也唯一且不能叫控制端口。所有值都须为字符串。不能把 map-content 直接接给需要 content 的节点。

deserialize_json 对 content 输出：原值是字符串则保留；否则把该值序列化成紧凑 JSON 文本。其他类型须与实际 JSON 值匹配。例：输入 `{"count":3,"nested":{"text":"hi"}}`，将 count、nested 均声明为 content，可得到字符串 "3" 和字符串 `{"text":"hi"}`；若想取 text，再接一个 deserialize_json，不能写 key="nested.text"。

**安全生成 JSON 文本**：不要用 construct_content 拼接带任意用户文本的 JSON 字符串，这不处理引号、换行、反斜杠。优先声明一个 Struct → construct_struct → struct_to_json。number 值可通过 Struct 字段安全序列化。需要任意动态 key 或 boolean 值而无适配工具时，不能声称原语有能力处理；可将已经编码的完整 JSON 对象文本作为输入并写明格式，或返回 UNSUPPORTED_REQUIREMENT。LLM 生成 JSON 不是确定性序列化器，且可能产生无法解析的输出。

### 5.3 列表、foreach 与 while_pop

| type | 必需 arguments | 数据输入 → 数据输出 | dataInputPorts |
| --- | --- | --- | --- |
| construct_list | item_type、initial_value_count | <item_type>-in-0 … <item_type>-in-(N-1) → list-out:列表类型 | 按序列出全部 N 个输入；N=0 时 [] |
| list_append | item_type、position:"start"或"end" | list-in:列表类型、item-in:元素类型 → list-out:列表类型 | 固定端口无需声明；返回新列表，不修改上游列表 |
| foreach | item_type | list-in:列表类型 → item-out:元素类型 | 固定端口无需声明；控制端口见第 1 节 |
| while_pop | value_type；可选 position、context_id_source、context_id | context-id:content → item-out:元素类型 | context_id_source="port" 时必须连 context-id；"fixed" 时不用此端口；控制端口与 foreach 相同 |

list_get 节点必须配置 arguments.value_type 为 list-content、list-message 或已声明的 list-struct:<id>。list-in 接收对应列表，port 模式下 index-in:number 接收从 0 开始的非负整数下标（1.0 合法，不接受布尔值或数字字符串），item-out 输出对应类型的元素；有 control-in/control-out。输入缺失、类型不匹配或下标越界（含空列表）时报错，不修改原列表。 arguments.index_source 可选 port（默认）或 fixed：port 使用 index-in:number；fixed 必须配置 arguments.index 为非负整数，且不存在 index-in 端口。

list_slice 节点必须配置 arguments.value_type 为 list-content、list-message 或已声明的 list-struct:<id>。list-in 与 list-out 为同一列表类型；可选 start-in、stop-in、step-in 接收整数 number，未连接按 None 处理。按 Python list[start:stop:step] 语义切片，支持负下标及负步长，步长为 0 或边界非整数时报错，不修改输入。


list_length 节点必须配置 arguments.value_type 为 list-content、list-message 或已声明的 list-struct:<id>。list-in 接收对应类型的列表，length-out 输出 number（元素个数，空列表为 0）；有 control-in/control-out，输入缺失或元素类型不匹配时报错，不修改原列表。

item_type 允许 content、message、已声明 struct:<id>。对应列表类型为 list-content/list-message/list-struct:<id>。Struct 元素的动态端口 ID 例如 struct:profile-in-0。initial_value_count 为 0–20 的整数，生成时填齐全部 N 个输入；不要以增大 count 方式构造超过 20 项的字面列表，可逐步 append 或直接接受列表输入。foreach 按输入列表快照顺序串行遍历，空列表直接走 control-out；没有索引输出，没有 break/continue 节点，没有循环自带聚合输出，也不能动态增加本轮待遍历项。



while_pop.value_type 必须是 list-content、list-message 或本图已声明的 list-struct:<id>，item-out 是对应元素类型。position 可为 "start" 或 "end"，默认 "end"。context_id_source 默认 "port"，从 context-id:content 读取 Context ID；"fixed" 时 arguments.context_id 必须是已存在的真实非空 ID，不能把静态 ID 当列表值。通常使用 context_create 的 context-id 输出，避免硬编码。没有 list-in，不直接接列表值。

while_pop 在每次进入 control-in 或 loop-in 时原子读取 Context 当前列表并弹出一项。有元素时更新列表、输出 item-out 并走 loop-out；空列表走 control-out。循环体通过 context_write 修改该 Context 的值会影响下一次弹出，因此可实现动态轮数；foreach 则始终遍历初次输入快照。不要每轮重新执行 context_create，也不要每轮无条件补充标记而没有停止判定。

**动态 ReAct 模式**：父图创建 list-message 对话 Context、content 回答 Context、初始值为 ["continue"] 的 list-content 继续队列。while_pop 消费继续标记，体内只调用 react_round 子进程 Workflow 文件，再回 loop-in。每轮子进程 Workflow 文件读对话 → llm → 将本轮 output 通过 construct_content 动态端口规范为字符串并写回答 Context → foreach 遍历 tool_calls。foreach 体调用工具分支子进程 Workflow 文件、把成功或错误观察作为普通 user message 追加到对话，并将继续队列**覆盖为 ["continue"]**。同轮多次工具调用只安排一轮后续分析；不要每次 append 一个标记。零工具调用不执行体，队列保持为空，父图退出后重新读取回答 Context，直接返回停止调用工具那次的回答。不要再无条件调用一个模型总结，避免改写答案或追加费用。

子进程可通过 content 接口接收祖先 Context ID，读写该 Context；它不应删除或重新创建祖先 Context。循环内的输出数据不能直接连到循环外，必须用外层 Context 再读。将 foreach 封装到 round 子进程 Workflow 文件、json_tool 封装到 dispatch 子进程 Workflow 文件，保持每层循环体单控制链且文件引用无递归。此模式没有固定轮数上限，但当前执行器每次 invocation 存在 180 秒运行时检查（不保证中断正在阻塞的外部调用），并受 Context 大小、模型上下文及服务错误限制；需要跨执行持续运行时改用事件调度。

### 5.4 LLM 与历史

| type | arguments | 数据输入 → 数据输出 |
| --- | --- | --- |
| llm | model、think、tool_calls、tools | messages-in:list-message → output:content；think=true 时增加 reasoning:content；tool_calls=true 时增加 available-tools-in:list-content 输入及 tool_calls:list-content 输出 |

llm.model 必须是用户输入或本 skill 明确配置的**真实已启用模型注册 ID**（Mongo ObjectId，24 位十六进制），不是 "gpt-..."/"deepseek-chat" 等模型名称。本部署已由用户提供 deepseek-flash 的模型注册 ID 6aba33cb2d499f6a57d08bc3；未明确指定其他真实模型时使用此 ID。虽然静态 schema 允许省略 model，执行时必失败；需要 llm 又没有 ID 时返回 MISSING_MODEL_ID，不要省略、写空值、写占位符或随便生成 ObjectId。model 不能从数据端口动态传入。

正常对话链：input 的 content → construct_message(role=user) → construct_list(item_type=message,count=1) → llm → output。系统提示先用 construct_content 构造，再 construct_message(role=system)，按 system、user 顺序组成 list-message。messages-in 必须非空。普通文本处理明确写 think:false、tool_calls:false、tools:[]，不启用无用工具。

llm.tools 的名称须在当前图 metadata.tools 中声明；省略/空数组表示使用其中全部工具，并非禁用。接入 available-tools-in 后，其名称列表覆盖默认子集；只有 tool_calls:true 时才可用该端口。运行时工具 schema 来自注册表/Tool Server，不能通过节点自行注入 function schema。

tool_calls 输出是数组，每项为一个 tool call 的 **JSON 字符串**，通常含 id、type、function.name、function.arguments（arguments 又是 JSON 字符串）。必须显式解析、调用工具、处理结果；不会自动执行。message 只有 role/content，不能发明 tool_call_id/name/tool_calls 字段，因此不能承诺完整原生多轮 tool-call 会话协议；可把结果整理成普通消息进入下一轮。


### 5.5 工具调用原语

| type | arguments | 数据输入 → 数据输出 | 注意 |
| --- | --- | --- | --- |
| tool | tool:名称、parameters:port[]、outputs:port[]；可选 mode:"sync"、timeout_ms | 每个参数同名端口 → 每个输出同名端口 | metadata.tools 中须有同名声明，parameters/outputs 必须与声明完整有序一致 |
| json_tool | 无 | tool-name:content、arguments-json:content → result-json:content、error-json:content | control-in；成功 control-out；错误 error-out；产生分支，禁止直接放 foreach / while_pop |
| remote_async_tool | tool、parameters:port[]；可选 timeout_ms、callback | 参数同名端口 → task_id:content | 仅 Remote；没有 outputs/mode；立刻返回任务 ID，未得到最终结果 |

metadata.tools 每项恰为 `{"name":"工具名","kind":"local或remote","input_ports":[...],"output_ports":[...]}`。去首尾空白、忽略大小写后名称全局唯一；每侧最多 50 端口，只允许六种公开类型，禁止控制端口名和 Struct。新图不用 legacy local_tool/remote_sync_tool。

tool 仅同步，mode 省略或 sync，callback 省略或 null。local 输入类型允许 content 和 number；数值 schema 自动映射为 number。运行时不会自动把数字字符串变成 Python int，也不会把 "false" 变成 bool。local 的 content 输出会把非字符串结果 JSON 序列化；remote_sync 的 content 输出**不保证转换**，应直接使用真实字符串字段，不要将 Provider 返回的整数假标为 content。仅配置一个名为 result 的同步 Remote 输出时，运行器返回整个原始结果，不代表 content JSON 文本。

json_tool 输入 arguments-json 必须解析为 object；优先调用已注册同名 Local，否则通过 Tool Server 同步调用 Remote；成功结果被统一 JSON 序列化，适合复杂结果、number/boolean 参数与显式错误处理。它不要求在 metadata.tools 中声明，但工具仍必须实际存在且名称已知。参数 schema 仍须遵守。推荐把复杂 JSON 工具调用封装为子进程 Workflow 文件，然后在父图或 foreach / while_pop 体内调用该子进程 Workflow 文件。成功和错误各有独立 output；若错误应该整体失败，可以不连 error-out，让异常终止；即便如此它仍不能直接放进 foreach / while_pop。

同步 Remote timeout_ms 默认 10000，最大通常 10000；异步默认 600000、最大通常 3600000；部署可进一步限制。主图执行预算约 180 秒（在节点之间检查，不是强制中断阻塞调用）。长视频转写通常采用 remote_async_tool，不应声称 10 秒内必完成。

callback 若提供，恰为 `{"type":"redis","queue":"实际队列名","event_type":"实际事件类型","on":["completed","failed"]}`；on 为 working/completed/failed 的非空无重复子集，queue 长度 1–256，event_type 长度 1–128。Tool Server 的回调 outbox 独立于 Agent 进程调度；回调不会自动暂停或恢复原图，消费者须另行部署。没有实际消费者时，异步节点仅提交任务并返回 task_id；需求依赖自动续跑时返回 MISSING_DEPLOYMENT_CONFIG。

### 5.6 Context 与 Session 节点

| type | arguments | 数据输入 → 数据输出 |
| --- | --- | --- |
| context_create | value_type；可选 context_id | initial-value:T → context-id:content |
| context_read | value_type；context_id_source 默认 port；fixed 模式另需 context_id | port 模式 context-id:content → value-out:T |
| context_write | 同 context_read | port 模式 context-id:content，以及 value-in:T → context-id:content、value-out:T |
| session_create | value_type | initial-value:T → session-id:content |
| session_read | value_type | session-id:content → value-out:T |
| session_write | value_type | session-id:content、value-in:T → session-id:content、value-out:T |

context_id_source 仅 port/fixed，fixed 模式无 context-id 输入。Context 的 T 可为公开类型或本图 Struct 类型；Session 的 T 只能为公开类型。读写的 value_type 必须与创建时一致。默认用自动生成 ID + 数据端口传递，避免固定 ID 冲突。不要把 Session 当可随便命名的全局变量，不要认为 write 是 append、patch 或原子加一。

### 5.7 Struct 声明与节点

metadata.structs 每项必含 id、name、color、fields，可选 list_color。id 与字段名匹配 `^[A-Za-z_][A-Za-z0-9_]*$`，引用区分大小写；生成时令 id=name 且长度 ≤80，Struct 名不区分大小写唯一；color/list_color 为 #RRGGBB。fields 每项恰含 name、type、required，required 是布尔值，字段名唯一。可空 fields；type 为公开类型或已声明 Struct/Struct 列表。所有引用须存在，声明间禁止循环。

Struct 值是仅含已声明字段的 object，必填字段存在，可选字段可缺省，所有已出现的值不可为 null；递归符合声明。局部类型名 struct:<id>、列表 list-struct:<id>，只能用于图内和 Context；不允许出现在根接口、子进程 Workflow 文件/工具接口或 Session。跨图传值先 struct_to_json，接收图自己声明类型再 json_to_struct。相同 struct_id 不意味着不同图自动共享声明。

| type | arguments | 数据输入 → 输出 | 精确 dataInputPorts |
| --- | --- | --- | --- |
| construct_struct | struct_id | 每个字段名:T → struct-out:struct:<id> | 所有字段名，含可选字段；必填字段必须接线 |
| struct_get | struct_id、field；missing 默认 error、has_fallback 默认 false | struct-in:struct:<id>，fallback 模式还有 fallback-in:字段类型 → value-out:字段类型 | error 为 ["struct-in"]；fallback 为 ["struct-in","fallback-in"] |
| struct_update | struct_id；updates 默认 []、remove_fields 默认 [] | struct-in、每个 updates 字段同名输入 → struct-out | ["struct-in",...updates] |
| struct_to_json | value_type:struct:<id>或list-struct:<id> | value-in:value_type → content-out:content | ["value-in"] |
| json_to_struct | 同上 | content-in:content → value-out:value_type | ["content-in"] |

struct_get 的 fallback 仅用于可选字段，必须同时 missing:"fallback"、has_fallback:true 且连接 fallback-in；不能写成条件分支节点。struct_update 的两组字段名数组各自无重复，不能交叉，不能移除必填字段；struct-in 及所有 updates 端口必须连，更新输入 None 时保留旧值。Struct 构造的可选字段不连接则省略。

### 5.8 仅用于理解旧图的节点

运行器还识别 local_tool（tool、parameters:字符串名数组，输出 output:content）和 remote_sync_tool（tool、parameters:port[]、outputs:port[]、timeout_ms），用于兼容；新设计统一使用 tool/json_tool/remote_async_tool。while_pop 是本规范允许的动态循环节点，完整契约见 5.3；不要另造 while 节点。

## 6. 已知真实工具目录（设计 LLM 无需另查）

区分“节点类型”和“工具名称”：tavily_search 不是节点类型，应通过 tool/json_tool 调用。下列目录来自源码，说明已实现能力，不等于当前部署 Provider 在线。未列出的普通 Python 函数（如 agent/tools/qqapi.py 的辅助函数、bocha_search）没有因此成为注册工具。不得假造 web_search、http_request、get_time、calculator 等工具。

下表描述**实际函数 JSON 参数/结果**。除另列 typed 端口方案外，复杂输入输出优先 json_tool。`?` 表示参数可省略；任意 JSON 表示函数 schema 不限类型，不是新增 workflow 类型。

### 6.1 Agent Local（启动时注册）

| 名称 | 参数对象 | 成功结果 | 约束/typed 方案 |
| --- | --- | --- | --- |
| get_deepseek_balance | {} | {balance:数值} | 需要 DeepSeek 凭据；tool 输入 []、输出 balance:content，Local 序列化数字；余额可能为 null |
| get_kimi_balance | {} | {balance:字符串} | 需要 Kimi 凭据；tool 输入 []、输出 balance:content |
| tavily_search | {keyword:字符串} | {results:对象数组} | 需要 Tavily key；tool keyword:content → results:content（Local 将数组转 JSON 文本）；失败可能为空数组 |
| output_to_terminal | content-in:content | 无 | 追加到当前进程终端，不发送 response 事件 |
| wait_terminal_event | 无 | 无 | 挂起等待当前终端消息，无数据端口 |
| read_terminal_input | 无 | list-out:list-content | 读取当前终端全部已保存用户输入正文，按时间升序，不消费历史 |
| get_recent_records | {limit:整数} | {records:对象数组} | 使用 json_tool 传真实整数；tool 的 "10" 不会自动变成 int |
| workspace.list_files | {} | {items:对象数组,revision:整数} | 可用 tool 输出 items:content、revision:content |
| workspace.get_file | {file_id:非空字符串} | 工作区文件 API 对象 | outputSchema 无一级 properties；tool 输出 output:content 得完整 JSON |
| workspace.create_file | {name:字符串,content?:字符串} | 工作区文件 API 对象 | name 长度 1–200、content ≤1,000,000 字符；tool 输入 name:content、content:content，输出 output:content |
| workspace.update_file | {file_id:字符串,name:字符串,content:字符串,revision:整数} | 工作区文件 API 对象 | 必须先读真实 revision；用 json_tool，冲突后重新读取；无条件重试会重复冲突 |
| workspace.delete_file | {file_id:字符串,revision:整数} | {deleted:布尔值,file_id:字符串} | 必须先读 revision，用 json_tool；用户已授权完整工作区 CRUD 时，可按任务需要直接设计删除操作 |

workspace.get_file/create_file/update_file 成功结果包含 file_id、name、content、pinned、created_at、updated_at、revision；前三者字符串，pinned 布尔值，时间为字符串，revision 整数。list_files.items 的文件项不包含 content。workspace.delete_file 的声明和实际返回均为 deleted/file_id，不包含新的 revision。创建工作区文件本身不会创建进程，也不意味着注册了新的 Tool。 用户授予完整工作区 CRUD 权限时，执行型 Agent 的系统提示应明确允许列出、读取、创建、重命名、修改和删除工作区文件，按任务需要执行而无需逐次确认；同时在 llm.tools 和 metadata.tools 中提供全部五个 workspace 工具。update_file/delete_file 的 revision 为真实 JSON 整数，须通过 json_tool 参数 JSON 传递，不能伪装成 content 类型端口；完整 schema 仍由运行时注册表加载。

### 6.2 默认 Tool Provider Remote

以下 Remote 已在仓库默认 TOOL_MODULES 中实现。数字、布尔、对象和对象数组建议走 json_tool，避免错误标为 content。

| 名称 | 参数对象 | 成功结果 |
| --- | --- | --- |
| system.echo | {value:任意 JSON} | {value:原值} |
| qq.send_group_msg | {group_id:字符串,message:字符串} | {message_id:整数} |
| qq.send_private_msg | {user_id:字符串,message:字符串} | {message_id:整数} |
| bilibili.shorturl_to_bvid | {short_url:字符串} | {bvid:字符串} |
| bilibili.gain_content_from_bvid | {bvid:字符串} | {text:字符串}；下载音视频并转写，可能耗时很长 |
| documents.query_by_name | {title:字符串} | {documents:Document 数组}，可以为空或多项，不保证标题唯一 |
| documents.query_by_id | {doc_id:字符串} | Document |
| documents.create | {title?:字符串,content?:字符串} | Document；title 默认“未命名文档”，content 默认空串 |
| documents.append | {doc_id:字符串,append_content:字符串} | Document；追加内容 |
| documents.rewrite | {doc_id:字符串,content:字符串} | Document；覆盖内容 |
| documents.rename | {doc_id:字符串,title:字符串} | Document |
| documents.pin | {doc_id:字符串,pinned:布尔值} | Document |

Document 恰含 id、title、content、pinned、created_at、updated_at；前三者字符串，pinned 布尔值，两个时间为字符串或 null。doc_id 为 Mongo 文档真实 ID，不能虚构；title 长度 1–200，文档 content 长度 ≤1,000,000。如果只需文档正文，可用 json_tool → deserialize_json(outputs=[{key:"content",type:"content"}])；若对数组每项处理，可先把 documents 声明为 content 得到整个数组 JSON 文本，但没有“任意对象数组→list-content”自动映射节点。仅当原始对象的所有字段类型都能由本地 Struct 精确表示时，才能用 json_to_struct 转成 Struct 列表；完整 Document 含 boolean/null，本类型系统不能直接表示，需真实的适配工具或另行约定的字符串 JSON 列表输入，不能直接声明成 list-content。

有明确定义的安全 typed Remote 端口方案：bilibili.shorturl_to_bvid 输入 short_url:content、输出 bvid:content；bilibili.gain_content_from_bvid 输入 bvid:content、输出 text:content；qq 的输入均 content，但返回整数 message_id 可声明为 number；使用 json_tool 时可经 deserialize_json 提取为 number，不能直接当字符串使用。documents 的完整对象混有 null/boolean，不构造假 map-content；优先 json_tool。工具目录不是 workflow 的 metadata.tools 自动内容，只声明实际用到的 typed 或 LLM 可选工具。

### 6.3 工作区 checkpoint 工具

工作区 checkpoint 与文件 CRUD 一样通过 Local Tool 调用，使用实际工具结果中的序号：

| 工具 | 输入 | 用途 |
| --- | --- | --- |
| workspace.list_checkpoints | before_seq?、limit?、file_id? | 分页读取 checkpoint 列表 |
| workspace.checkpoint_tree | 无 | 读取分支树和当前 head_seq |
| workspace.get_parent_checkpoint | seq?，默认当前 head | 返回 seq、parent_seq，确定分支上的回滚目标 |
| workspace.checkpoint_diff | seq | 读取相对于父 checkpoint 的文件差异 |
| workspace.create_checkpoint | name | 保存当前工作区文件快照 |
| workspace.restore_checkpoint | seq | 恢复整个工作区，文件 revision 会更新 |

回滚一步先获取父 checkpoint，再把 parent_seq 传给恢复工具。parent_seq=0 可恢复为空工作区；parent_seq=null 表示没有更早的回滚目标，不能传给恢复工具。恢复后重新读取文件 revision。恢复操作影响整个工作区，依照用户任务范围调用。


## 7. 进程调度与业务循环

进程从 WebUI 的 POST /api/processes 创建，请求提供真实工作区 workflow_file_id 和 inputs。创建进程会同时分配终端进程；Workflow 的 origin 是普通可选输入，其类型由接口声明决定。

单次图内的动态循环使用 while_pop，并由实际业务结果决定是否向 Context 列表补充元素。图内事件构造和拆分仅处理数据，不会自动创建进程或启动工作流。跨进程启动、等待与唤醒属于运行时能力，不得虚构尚未提供的节点或工具。

终端输出使用 output_to_terminal 节点，将 content-in 的非空文本写入当前进程关联终端；不生成旧 local_tool 或全局终端消息。终端输入保存后会唤醒正在等待该终端 terminal_message 的进程。使用 wait_terminal_event 节点挂起，从下一节点恢复；无参数和数据端口，不输出消息正文，进入等待前的消息不会留作唤醒事件。后续使用 read_terminal_input 查询当前进程终端完整的用户输入正文列表（list-content，按时间升序、不消费历史），再将其连接到 Router 或其他数据节点进行判断。子进程通过独立进程执行，也支持该节点；需向该子进程自己的终端发消息。调试用同步 run_workflow_map 不支持挂起。

## 8. 设计与检查程序（只在内部执行）

1. 从用户需求提取业务输入、输出、效果和配置；能做的运行时数据声明为根输入；不可知模型/工具/路由配置返回 error。
2. 先划分 workflow 边界。分支有后续统一步骤、foreach / while_pop 内有分支/JSON Tool/第二个循环时先拆子进程 Workflow 文件，再定接口。为所有子进程 Workflow 文件提供完整定义。
3. 为每份图先画控制树，再填数据。分支各有独立 output，所有路径实现相同承诺的公开输出；foreach / while_pop 保持单控制链并显式回到所属 loop-in。
4. 逐节点选择目录中真实 type、精确 arguments 和端口，按需声明 Struct、工具和依赖快照。只生成用得到的配置。
5. 按生命周期审查每条数据边、执行顺序和实际值类型。必要输入不能悬空；JSON 文本、对象、列表、message 不混接；通过 Context 显式聚合。
6. 所有 foreach / while_pop 合法回边删除后图无环；控制节点无共享；所有节点可达；依赖 DAG 无递归；Struct 引用也无环。
7. 三份接口快照一致；workflowPorts 精确；dataInputPorts 精确；metadata.tools 与 typed 工具参数/输出一致；所有节点及连接字段均在允许列表中。
8. 检查真实 model ID、真实工具名称、事件目标命名空间、停止条件与外部副作用是否满足需求。不能把失败吞成成功，不能因缺能力而输出一个只复述任务的 LLM 节点。
9. 输出设计信封的严格 JSON：双引号，无注释、尾逗号、NaN、undefined、代码围栏、占位符、省略号或未定义引用。description/message 可以自然语言，其余字段遵守机器契约。

## 9. 完整可解析示例

下列示例的 JSON 均为完整设计结果。只作为正确结构参考，不要不加判断照抄业务。示例无需模型、网络或工具；Context 示例实际执行仍需要 Redis。示例的固定路由标签用于演示接口，不代表自动分类器。

### 9.1 最小透传

输入 text，输出 content，不需要模型或工具。

```json
{
  "format": "aagent.workflow-design/1",
  "status": "ready",
  "entrypoint": "echo.flow",
  "workflows": [
    {"filename": "echo.flow", "workflow": {
      "schema_version": "2.0",
      "description": "",
      "metadata": {"structs":[],"tools":[]},
      "input_ports": [{"name":"text","type":"content"}],
      "output_ports": [{"name":"content","type":"content"}],
      "nodes": [
        {"id":"input","type":"input","name":"接收工作流输入","x":0,"y":0,"workflowPorts":[{"id":"workflow:text","name":"text","type":"content"}]},
        {"id":"output","type":"output","name":"返回处理结果","x":240,"y":0,"workflowPorts":[{"id":"workflow:content","name":"content","type":"content"}]}
      ],
      "connections": [
        {"fromId":"input","fromPortId":"control-out","toId":"output","toPortId":"control-in","type":"control"},
        {"fromId":"input","fromPortId":"workflow:text","toId":"output","toPortId":"workflow:content","type":"content"}
      ],
      "subprocess_workflow_files": [],
      "remote_tools": []
    }}
  ],
  "errors": []
}
```

### 9.2 foreach 内条件处理与结果聚合

per_item.flow 在内部 router 分支，并分别返回 result；collect.flow 在循环体调用它，再通过 Context 累积。输入 items=["a","skip","b"]，输出 results=["kept:a","skipped","kept:b"]；输入空数组输出空数组。父图中的 process 是单出口节点，子进程 Workflow 文件两个 output 互不共享。

```json
{
  "format": "aagent.workflow-design/1",
  "status": "ready",
  "entrypoint": "collect.flow",
  "workflows": [
    {"filename": "per_item.flow", "workflow": {
      "schema_version": "2.0",
      "description": "",
      "metadata": {"structs":[],"tools":[]},
      "input_ports": [{"name":"text","type":"content"}],
      "output_ports": [{"name":"result","type":"content"}],
      "nodes": [
        {"id":"input","type":"input","name":"接收工作流输入","x":0,"y":0,"workflowPorts":[{"id":"workflow:text","name":"text","type":"content"}]},
        {"id":"route","type":"router","name":"判断是否继续","x":240,"y":0,"arguments":{"branches":[{"id":"skip-branch","name":"skip"}]}},
        {"id":"skip_text","type":"construct_content","name":"构造跳过结果","x":480,"y":0,"arguments":{"append_items":[{"type":"fixed","value":"skipped"}]},"dataInputPorts":[]},
        {"id":"keep_text","type":"construct_content","name":"构造保留结果","x":720,"y":0,"arguments":{"append_items":[{"type":"fixed","value":"kept:"},{"type":"port","port_id":"text-in"}]},"dataInputPorts":["text-in"]},
        {"id":"skip_output","type":"output","name":"跳过分支输出","x":960,"y":0,"workflowPorts":[{"id":"workflow:result","name":"result","type":"content"}]},
        {"id":"keep_output","type":"output","name":"保留分支输出","x":0,"y":180,"workflowPorts":[{"id":"workflow:result","name":"result","type":"content"}]}
      ],
      "connections": [
        {"fromId":"input","fromPortId":"control-out","toId":"route","toPortId":"control-in","type":"control"},
        {"fromId":"route","fromPortId":"skip-branch","toId":"skip_text","toPortId":"control-in","type":"control"},
        {"fromId":"route","fromPortId":"branch$others","toId":"keep_text","toPortId":"control-in","type":"control"},
        {"fromId":"skip_text","fromPortId":"control-out","toId":"skip_output","toPortId":"control-in","type":"control"},
        {"fromId":"keep_text","fromPortId":"control-out","toId":"keep_output","toPortId":"control-in","type":"control"},
        {"fromId":"input","fromPortId":"workflow:text","toId":"route","toPortId":"content-in","type":"content"},
        {"fromId":"input","fromPortId":"workflow:text","toId":"keep_text","toPortId":"text-in","type":"content"},
        {"fromId":"skip_text","fromPortId":"content-out","toId":"skip_output","toPortId":"workflow:result","type":"content"},
        {"fromId":"keep_text","fromPortId":"content-out","toId":"keep_output","toPortId":"workflow:result","type":"content"}
      ],
      "subprocess_workflow_files": [],
      "remote_tools": []
    }},
    {"filename": "collect.flow", "workflow": {
      "schema_version": "2.0",
      "description": "",
      "metadata": {"structs":[],"tools":[]},
      "input_ports": [{"name":"items","type":"list-content"}],
      "output_ports": [{"name":"results","type":"list-content"}],
      "nodes": [
        {"id":"input","type":"input","name":"接收工作流输入","x":240,"y":180,"workflowPorts":[{"id":"workflow:items","name":"items","type":"list-content"}]},
        {"id":"empty","type":"construct_list","name":"检查列表是否为空","x":480,"y":180,"arguments":{"item_type":"content","initial_value_count":0},"dataInputPorts":[]},
        {"id":"store","type":"context_create","name":"创建聚合上下文","x":720,"y":180,"arguments":{"value_type":"list-content"}},
        {"id":"each","type":"foreach","name":"遍历列表项目","x":960,"y":180,"arguments":{"item_type":"content"}},
        {"id":"process","type":"spawn_and_wait_subprocess","name":"处理当前项目","x":0,"y":360,"arguments":{"workflow_file":"per_item.flow"},"input_ports":[{"name":"text","type":"content"}],"output_ports":[{"name":"result","type":"content"}]},
        {"id":"read_item","type":"context_read","name":"读取聚合结果","x":240,"y":360,"arguments":{"value_type":"list-content"}},
        {"id":"append","type":"list_append","name":"追加项目结果","x":480,"y":360,"arguments":{"item_type":"content","position":"end"}},
        {"id":"write_item","type":"context_write","name":"保存项目结果","x":720,"y":360,"arguments":{"value_type":"list-content"}},
        {"id":"read_final","type":"context_read","name":"读取最终聚合结果","x":960,"y":360,"arguments":{"value_type":"list-content"}},
        {"id":"output","type":"output","name":"返回处理结果","x":0,"y":540,"workflowPorts":[{"id":"workflow:results","name":"results","type":"list-content"}]}
      ],
      "connections": [
        {"fromId":"input","fromPortId":"control-out","toId":"empty","toPortId":"control-in","type":"control"},
        {"fromId":"empty","fromPortId":"control-out","toId":"store","toPortId":"control-in","type":"control"},
        {"fromId":"store","fromPortId":"control-out","toId":"each","toPortId":"control-in","type":"control"},
        {"fromId":"each","fromPortId":"loop-out","toId":"process","toPortId":"control-in","type":"control"},
        {"fromId":"process","fromPortId":"control-out","toId":"read_item","toPortId":"control-in","type":"control"},
        {"fromId":"read_item","fromPortId":"control-out","toId":"append","toPortId":"control-in","type":"control"},
        {"fromId":"append","fromPortId":"control-out","toId":"write_item","toPortId":"control-in","type":"control"},
        {"fromId":"write_item","fromPortId":"control-out","toId":"each","toPortId":"loop-in","type":"control"},
        {"fromId":"each","fromPortId":"control-out","toId":"read_final","toPortId":"control-in","type":"control"},
        {"fromId":"read_final","fromPortId":"control-out","toId":"output","toPortId":"control-in","type":"control"},
        {"fromId":"input","fromPortId":"workflow:items","toId":"each","toPortId":"list-in","type":"list-content"},
        {"fromId":"empty","fromPortId":"list-out","toId":"store","toPortId":"initial-value","type":"list-content"},
        {"fromId":"store","fromPortId":"context-id","toId":"read_item","toPortId":"context-id","type":"content"},
        {"fromId":"store","fromPortId":"context-id","toId":"write_item","toPortId":"context-id","type":"content"},
        {"fromId":"store","fromPortId":"context-id","toId":"read_final","toPortId":"context-id","type":"content"},
        {"fromId":"each","fromPortId":"item-out","toId":"process","toPortId":"workflow:text","type":"content"},
        {"fromId":"process","fromPortId":"workflow:result","toId":"append","toPortId":"item-in","type":"content"},
        {"fromId":"read_item","fromPortId":"value-out","toId":"append","toPortId":"list-in","type":"list-content"},
        {"fromId":"append","fromPortId":"list-out","toId":"write_item","toPortId":"value-in","type":"list-content"},
        {"fromId":"read_final","fromPortId":"value-out","toId":"output","toPortId":"workflow:results","type":"list-content"}
      ],
      "subprocess_workflow_files": [{"name":"per_item.flow","input_ports":[{"name":"text","type":"content"}],"output_ports":[{"name":"result","type":"content"}]}],
      "remote_tools": []
    }}
  ],
  "errors": []
}
```

### 9.3 输出到进程终端

进程输入 text 会原样写入该进程终端，同时作为 content 返回。终端由创建进程时分配，图内不声明全局终端或事件绑定。

```json
{
  "format": "aagent.workflow-design/1",
  "status": "ready",
  "entrypoint": "terminal_output.flow",
  "workflows": [
    {
      "filename": "terminal_output.flow",
      "workflow": {
        "schema_version": "2.0",
        "description": "",
        "metadata": {
          "structs": [],
          "tools": []
        },
        "input_ports": [
          {
            "name": "text",
            "type": "content"
          }
        ],
        "output_ports": [
          {
            "name": "content",
            "type": "content"
          }
        ],
        "nodes": [
          {
            "id": "input",
            "type": "input",
            "name": "接收工作流输入",
            "x": 0,
            "y": 0,
            "workflowPorts": [
              {
                "id": "workflow:text",
                "name": "text",
                "type": "content"
              }
            ]
          },
          {
            "id": "terminal",
            "type": "output_to_terminal",
            "name": "输出到进程终端",
            "x": 240,
            "y": 0
          },
          {
            "id": "output",
            "type": "output",
            "name": "返回处理结果",
            "x": 480,
            "y": 0,
            "workflowPorts": [
              {
                "id": "workflow:content",
                "name": "content",
                "type": "content"
              }
            ]
          }
        ],
        "connections": [
          {
            "fromId": "input",
            "fromPortId": "control-out",
            "toId": "terminal",
            "toPortId": "control-in",
            "type": "control"
          },
          {
            "fromId": "input",
            "fromPortId": "workflow:text",
            "toId": "output",
            "toPortId": "workflow:content",
            "type": "content"
          },
          {
            "fromId": "terminal",
            "fromPortId": "control-out",
            "toId": "output",
            "toPortId": "control-in",
            "type": "control"
          },
          {
            "fromId": "input",
            "fromPortId": "workflow:text",
            "toId": "terminal",
            "toPortId": "content-in",
            "type": "content"
          }
        ],
        "subprocess_workflow_files": [],
        "remote_tools": []
      }
    }
  ],
  "errors": []
}
```
