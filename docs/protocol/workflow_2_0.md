# Workflow 2.0 协议规范

> 类型：协议规范。  
> 归属：`agent/`、`manager_webui/`、`workflow_editor/`。  
> Workflow 协议版本：`2.0`。  
> 机器可读结构定义：`workflow_2_0.schema.json`（本文为完整规范；实现本协议不要求查阅其他版本文档）。

## 1. 范围与版本

Workflow 2.0 定义可保存、校验、编译和执行的 Workflow JSON。根字段 `schema_version` 必须是字符串 `2.0`。Agent 和管理端只接受当前版本；缺少版本号、旧版本或未来版本均不能作为 Workflow 2.0 执行或保存。

编辑器可将 1.6 和 1.7 工作流迁移到 2.0；其他版本不自动迁移。迁移保留已有节点及连线，并按本规范第 10 节处理 Router 的保留兜底分支。迁移不会自动创建或选择 Struct 类型。本文完整规定 2.0 的根对象、节点、端口、连线、校验、执行、Context 和 Struct 语义，不依赖其他协议文档补充解释。

Workflow 2.0 新增 Workflow 局部具名 Struct 类型，并允许 Context 保存这些类型的值；增加五种 Struct 节点。Struct 声明位于 Workflow metadata，节点只引用声明 ID。编辑器允许先放置未绑定类型的节点草稿；通过 Agent 或管理端语义校验的 Workflow 必须为这些节点配置有效声明。

## 2. 根对象

根对象包含以下字段。节点配置必须位于节点的 `arguments` 中。

| 字段 | 必需 | 类型 | 含义 |
| --- | --- | --- | --- |
| `schema_version` | 是 | string | 固定为 `2.0` |
| `name` | 是 | string | Workflow 名称 |
| `description` | 否 | string | Workflow 描述 |
| `metadata` | 否 | object | Workflow 局部元数据；`structs` 缺省为空数组 |
| `input_ports` | 是 | port[] | Workflow 输入接口 |
| `output_ports` | 是 | port[] | Workflow 输出接口 |
| `nodes` | 是 | node[] | 节点列表 |
| `connections` | 是* | connection[] | 控制流和数据连线 |
| `workflow_nodes` | 否 | dependency[] | 子 Workflow 名称及接口快照 |
| `remote_tools` | 否 | dependency[] | Remote Tool 名称及接口快照 |

端口对象由 `name` 和 `type` 两个字段组成，例如一个名称为 prompt、类型为 content 的接口端口。节点顶层字段包括必需的 `id`、`type`，可选的字符串 `name` 及数字 `x`、`y`，以及按类型要求的 `arguments`、`workflowPorts`、`dataInputPorts`、`input_ports`、`output_ports`。`id` 在单个 Workflow 中必须唯一。不支持的节点参数和节点顶层字段会被语义校验拒绝。Schema 是本文约束的机器可读镜像；本文逐节定义其语义，不以 Schema 文件替代协议规则。

规范化后持久化的 Workflow 必须包含表中标为必需的字段；`connections` 即使为空也必须显式保存。管理端创建/更新请求允许省略 `connections`、`description`、`metadata`、`workflow_nodes` 和 `remote_tools`，服务端分别补为 `[]`、`""`、`{}`、`[]`、`[]` 后再保存，因此 `connections` 在 API 请求中可省略，但在本规范的规范化 Workflow JSON 中必需（表中 *）。`name` 长度为 1–120；`description` 最大长度 2000。`metadata` 当前只允许 `structs` 一个属性；`metadata.structs` 缺省为空数组。输入和输出接口各最多 50 个端口，每个端口名称长度为 1–80。`nodes` 必须有 1–200 个元素；`connections` 最多 1000 条；`workflow_nodes` 最多 50 项；`remote_tools` 最多 100 项。通过管理端 HTTP API 写入 Workflow 时，请求体上限为 512 KiB。

对根对象的未知字段，管理端请求模型会拒绝；当前 Agent 所用 JSON Schema 没有在根层设置 `additionalProperties: false`，因此 Agent 单独进行 Schema 校验时不拒绝未知根字段。这是接收端行为差异，不改变本协议规定的根字段集合；需要严格互操作的生产者不得发送未知根字段。

## 3. 数据类型与 Struct 声明

### 3.1 Struct 类型标识

Struct 是 Workflow 局部类型，不是全局注册类型。标识形式为 `struct:<id>`，Struct 列表为 `list-struct:<id>`。`<id>` 必须匹配 `^[A-Za-z_][A-Za-z0-9_]*$`，并区分大小写。

Struct 类型可用于 Workflow 内部数据端口、节点参数和 Context；不得用于 Workflow 输入/输出接口、`workflow_nodes` 或 `remote_tools` 的接口快照。需要跨 Workflow 或服务边界传递时，先用 `struct_to_json` 转成 `content`，接收方再用 `json_to_struct` 校验和恢复。

### 3.2 声明格式

`metadata.structs` 是 Struct 定义数组。每项必须恰含 `id`、`name`、`color`、`fields`；每个字段必须恰含 `name`、`type`、`required`。

例如，以下是可直接解析的 Struct metadata：

```json
{
  "structs": [
    {
      "id": "profile",
      "name": "Profile",
      "color": "#3A7D68",
      "fields": [
        {"name": "display_name", "type": "content", "required": true},
        {"name": "nickname", "type": "content", "required": false}
      ]
    }
  ]
}
```

`id`、`name`、`color`、`fields` 的类型分别为 string、string、string、array；字段 `name`、`type` 为 string，`required` 为 boolean。`id` 和字段名必须符合标识规则；Struct ID 唯一，显示名称非空且不区分大小写唯一，同一 Struct 内字段名不得重复。`color` 必须为 `#RRGGBB` 六位十六进制颜色，仅用于数据类型显示，不决定 Struct 节点类别颜色。字段类型可以是内建数据类型，或引用已声明的 `struct:<id>` / `list-struct:<id>`。引用必须存在，定义之间不得形成直接或间接循环；空字段数组合法。未定义的 Struct/字段属性不允许出现。

### 3.3 Struct 值

Struct 值使用 JSON object 表示，属性名必须来自该 Struct 的字段声明。必填字段必须存在；可选字段可以省略。未声明属性和 `null` 值均非法。字段存在时，其值必须符合字段声明的类型。Struct 列表使用 JSON array 表示，数组中的每一项均须符合对应 Struct 定义。

内建值类型的约束如下：

| 类型 | JSON 值约束 |
| --- | --- |
| `content` | string |
| `message` | object，且仅含 `role` 和 `content`；`role` 为 `system`、`user`、`assistant` 或 `tool`，`content` 为 string |
| `event` | object，`event_type` 为非空 string，且存在 `payload` 属性；具体 Event 构造和发布节点还要求 Event 1.1 格式，见第 9.3 节 |
| `list-content`、`list-message`、`list-event` | 对应值类型的数组 |
| `map-content` | 属性名非空的 object，所有属性值均为 string |

Struct 定义可引用其他已声明 Struct 或其列表，但定义之间不得循环引用。Agent 与管理端在接受 Workflow 时递归检查 Struct 声明；运行时 Struct 节点、Context 存取及 JSON 转换递归验证 Struct 值。一般数据边不会自动对所有内建类型进行全局递归校验。Struct 是结构化值，不等同于任意 JSON object。

## 4. Struct 节点

Struct 节点都是普通控制流节点：每个节点有 `control-in` 和 `control-out`，并按节点配置提供下列数据端口。`dataInputPorts` 用于声明动态输入端口，必须与参数推导出的端口集合一致；例外是 Struct 操作节点的 `struct-in` 固定输入也必须列入该数组（Struct 各节点精确数组见下文）。端口数据类型由 Struct 声明及参数推导，不允许在节点上另行覆盖。节点类别颜色固定；`metadata.structs[].color` 仅用于相应 Struct 数据类型及其列表的画布类型显示。

节点创建与 `metadata.structs` 编辑互相独立。编辑器可以放置尚未绑定 Struct 的节点草稿，草稿的 `struct_id` 或 `value_type` 可为空字符串，创建时不打开 metadata 编辑窗。此类草稿不满足可执行 Workflow 的语义校验；保存或执行前必须绑定已声明的类型并配置有效参数与动态端口。

| 节点类型 | 参数（位于 `arguments`） | 数据输入端口 | 数据输出端口 | 行为 |
| --- | --- | --- | --- | --- |
| `construct_struct` | `struct_id` | 每个声明字段一个端口，端口 ID 为字段名 | `struct-out`，类型为 `struct:<id>` | 从字段输入组装对象；缺失可选字段省略，缺失必填字段时报错；结果递归校验。 |
| `struct_get` | `struct_id`、`field`、`missing`、`has_fallback` | `struct-in`；仅当 `missing` 为 `fallback` 时还需 `fallback-in` | `value-out`，类型为所选字段类型 | 校验输入对象并取出字段。字段缺失时 `missing: error` 报错；`missing: fallback` 使用并校验 fallback。Fallback 只允许用于可选字段，且 `has_fallback` 必须与模式一致。 |
| `struct_update` | `struct_id`、`updates`、`remove_fields` | `struct-in` 及 `updates` 中每个字段对应的同名端口 | `struct-out`，类型为 `struct:<id>` | 复制并校验输入对象，移除列出的可选字段，再以有值的更新输入覆盖字段，最后递归校验输出。必填字段不可移除；更新和移除集合不得重叠。`struct-in` 和每个 updates 端口都必须连接；若更新端口的运行值为 `None`，保留原字段值。 |
| `struct_to_json` | `value_type`，仅允许已声明的 `struct:<id>` 或 `list-struct:<id>` | `value-in`，类型为 `value_type` | `content-out`，类型为 `content` | 校验 Struct 值后序列化为紧凑 JSON 文本并保留 Unicode 字符。 |
| `json_to_struct` | `value_type`，仅允许已声明的 `struct:<id>` 或 `list-struct:<id>` | `content-in`，类型为 `content` | `value-out`，类型为 `value_type` | 解析 JSON 文本并按目标 Struct 类型递归校验；无效 JSON 或不匹配的值报错。 |

`struct_get.missing` 取值为 `error` 或 `fallback`，`has_fallback` 为 boolean。`struct_update.updates` 和 `remove_fields` 均为字段名数组，元素不可重复且必须是声明字段。`construct_struct.dataInputPorts` 必须恰好包含该 Struct 的全部字段名；`struct_update.dataInputPorts` 必须恰好包含 `struct-in` 和所有更新字段；`struct_get.dataInputPorts` 为 `missing: error` 时恰为 `["struct-in"]`，为 `missing: fallback` 时恰为 `["struct-in", "fallback-in"]`；`struct_to_json` 固定为 `["value-in"]`，`json_to_struct` 固定为 `["content-in"]`。这些节点的端口序列化必须与 metadata 重新推导的结果完全一致。

以下完整 JSON 是一个 Struct 构造、字段读取并输出的 Workflow 示例；其中所有 JSON 字符串均使用双引号，示例可独立解析：

```json
{
  "schema_version": "2.0",
  "name": "profile_example",
  "description": "Construct a profile and read its display name",
  "metadata": {
    "structs": [
      {
        "id": "profile",
        "name": "Profile",
        "color": "#3A7D68",
        "fields": [
          {"name": "display_name", "type": "content", "required": true},
          {"name": "nickname", "type": "content", "required": false}
        ]
      }
    ]
  },
  "input_ports": [{"name": "display_name", "type": "content"}],
  "output_ports": [{"name": "name", "type": "content"}],
  "nodes": [
    {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:display_name", "name": "display_name", "type": "content"}]},
    {"id": "construct", "type": "construct_struct", "arguments": {"struct_id": "profile"}, "dataInputPorts": ["display_name"]},
    {"id": "get_name", "type": "struct_get", "arguments": {"struct_id": "profile", "field": "display_name", "missing": "error", "has_fallback": false}, "dataInputPorts": ["struct-in"]},
    {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:name", "name": "name", "type": "content"}]}
  ],
  "connections": [
    {"fromId": "input", "fromPortId": "control-out", "toId": "construct", "toPortId": "control-in", "type": "control"},
    {"fromId": "construct", "fromPortId": "control-out", "toId": "get_name", "toPortId": "control-in", "type": "control"},
    {"fromId": "get_name", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
    {"fromId": "input", "fromPortId": "workflow:display_name", "toId": "construct", "toPortId": "display_name", "type": "content"},
    {"fromId": "construct", "fromPortId": "struct-out", "toId": "get_name", "toPortId": "struct-in", "type": "struct:profile"},
    {"fromId": "get_name", "fromPortId": "value-out", "toId": "output", "toPortId": "workflow:name", "type": "content"}
  ]
}
```

## 5. Context

`context_create`、`context_read` 和 `context_write` 的 `arguments.value_type` 除既有内建类型外，也可使用当前 Workflow 已声明的 `struct:<id>` 或 `list-struct:<id>`。`session_create`、`session_read` 和 `session_write` 不因此获得 Struct 类型支持。Context 节点数据端口如下：

| 节点 | 输入 | 输出 |
| --- | --- | --- |
| `context_create` | `initial-value`：`value_type` | `context-id`：`content` |
| `context_read` | `context_id_source` 为 `port` 时使用 `context-id`：`content`；为 `fixed` 时无 ID 输入 | `value-out`：`value_type` |
| `context_write` | `context_id_source` 为 `port` 时使用 `context-id`：`content`；另有 `value-in`：`value_type` | `context-id`：`content`、`value-out`：`value_type` |

`context_create.context_id` 省略时生成 ID；若显式提供，必须是非空白字符串且该 ID 在 Context 存储中尚不存在。空字符串不是规范化 Workflow 中的生成 ID 表示，Schema 会拒绝它。读写节点的 `context_id_source` 为 `port` 或 `fixed`；固定来源必须给出非空 `context_id`。读写时 Context ID、当前 invocation 和声明类型必须匹配，否则操作失败。写入值在存储前递归验证，读取值在返回前再次验证；读写会刷新存储 TTL。

Context 按 Workflow invocation 隔离，不能被其他 invocation 读取或写入。子 Workflow 调用有独立 invocation，不能使用父 Workflow 的 Context。值以 JSON 序列化存储，默认 TTL 为 86400 秒，单个序列化值默认最大 1048576 字节；部署可分别通过 `WORKFLOW_CONTEXT_TTL_SECONDS` 和 `WORKFLOW_CONTEXT_MAX_VALUE_BYTES` 调整。每次执行创建的 Context 会在该 Workflow 执行结束（成功或失败）时尝试清理；清理失败会记日志，TTL 是兜底。Context ID 是不透明字符串。

Session 与 Context 不同：Session 仅支持七种内建值类型，ID 格式为 `ses_` 加 32 位小写十六进制字符，值存入 MongoDB 且不按 Workflow invocation 自动清理；单值序列化 UTF-8 大小上限默认 1048576 字节，可由 `WORKFLOW_SESSION_MAX_VALUE_BYTES` 配置。Session 读写要求 ID 存在且声明类型精确匹配，写入替换完整值；不得用于 Struct。

## 6. 类型边界与连线

Struct 类型只在当前 Workflow 内有效。Workflow 的 `input_ports` / `output_ports`、`workflow_nodes` 中的子 Workflow 接口快照，以及 `remote_tools` 中的工具接口快照均不得声明 Struct 类型。外部数据若需跨边界传递，必须先使用 `struct_to_json` 转换为 `content`，接收侧再用 `json_to_struct` 按本地声明解析和校验。

数据连线的 `type` 必须与源端口、目标端口的推导类型完全一致。Struct 类型及 Struct 列表只允许连接到同类型端口；不同 Struct ID、Struct 与 Struct 列表、或 Struct 与普通 JSON `content` 之间不得直接连接。JSON 转换节点的 `content` 端口是显式边界，不会自动转换类型。控制连线规则见第 10 节。

## 7. 校验与执行

Workflow 2.0 JSON 必须符合本规范明确规定的字段形状、字段类型、额外字段限制及语义约束。编辑器导出的草稿可以含未绑定 Struct 节点或无效的临时连线，不等同于可执行或管理端已保存的规范化 Workflow。编辑器独立加载/保存 `metadata.structs`，并从 metadata 与节点参数推导动态端口；创建 Struct 节点不要求先声明 metadata，也不弹出 metadata 编辑窗。Struct 节点类别颜色固定，Struct 类型及列表颜色取自用户声明的 `color`。

对应 JSON Schema 是静态约束的机器可读镜像。`struct_to_json`、`json_to_struct` 和 Context 节点的 Schema 均允许 Struct 类型标识；Schema 只验证类型标识格式，Struct ID 是否在当前 Workflow 中声明仍由 Agent 和管理端语义校验负责。Session 节点的 Schema 仍只允许内建类型。Agent 和管理端语义校验器还必须检查 Schema 难以表达的约束，包括 Struct ID/名称/字段唯一性、类型引用存在性、无循环依赖、公开接口边界、节点参数与动态端口一致性，以及数据连线端口和类型匹配。编辑器中的未绑定草稿不豁免服务端校验。

Agent 在执行前验证 Workflow，并将 `metadata.structs` 编译为本次运行可用的定义。运行期间，Struct 构造、读取、更新、JSON 转换及 Context 存取递归检查 Struct 值；List 节点检查容器为数组，但不独立递归验证 Struct 列表元素。一般数据边复制传播值，不保证对所有内建类型进行统一运行时验证。非合规 Struct 值或运行所需输入缺失时相应节点失败。Struct 值按值传递，节点输出传播及更新不会允许下游对上游对象进行隐式原地修改。

## 8. 兼容与迁移

Workflow 2.0 的 `schema_version` 必须精确为字符串 `2.0`。Agent 和管理端只接受当前版本；缺少版本、Workflow 1.x 或其他未来版本均不得作为 2.0 执行或保存。本文第 3 至第 10 节完整定义 Workflow 2.0 的节点与连线语义，不需要借助其他版本文档解释。

编辑器只自动迁移 Workflow 1.6 和 1.7 到 2.0，保留既有节点及连线，并按 2.0 规则处理 Router 保留兜底分支。迁移不会自动创建 Struct 声明，也不会猜测或绑定 Struct 类型。其他版本不自动迁移。保存前仍须通过本规范定义的静态结构和语义校验。

## 9. 内建数据类型与节点

### 9.1 内建数据类型和端口

除 Struct 类型外，数据端口和数据连线可使用以下类型：

| 类型 | 值语义 |
| --- | --- |
| `content` | 字符串 |
| `message` | 仅含 `role` 和 `content` 的对象；role 为 `system`、`user`、`assistant`、`tool` 之一，content 为字符串 |
| `event` | Workflow 内传播的 Event 对象，不自动转换成 JSON 字符串 |
| `list-content`、`list-message`、`list-event` | 对应元素类型的数组 |
| `map-content` | 非空字符串键到字符串值的对象 |

接口 `port` 必须恰含 `name`、`type`。名称非空；同一输入或输出接口数组内，端口名经去除首尾空白、忽略大小写后不得重复。依赖对象必须恰含 `name`、`input_ports`、`output_ports`；依赖名非空，同一依赖数组内不得重复，Remote Tool 名称比较时去除首尾空白并忽略大小写。

`origin` 是保留的可选 Workflow 输入接口名，若存在，其类型必须为 `event`。Input 节点对应端口 ID 为 `workflow:origin`。外部事件绑定触发 Workflow 时，调度器构造 `event_type` 为 `workflow` 的 Event，并把完整原始事件放入 `payload.origin`；其他 Workflow 输入从该 Event 的 `payload` 按端口名取值。若直接传入的 Workflow Event 已带 `payload.origin`，使用该值；否则以该 Workflow Event 本身作为 origin。未声明 origin 输入时无需提供该值。

### 9.2 节点对象和边界快照

节点顶层只允许 `id`、`type`、`name`、`x`、`y`、`arguments`、`workflowPorts`、`dataInputPorts`、`input_ports`、`output_ports`。id 非空且在 Workflow 内唯一；x/y 为数字；arguments 为对象，且仅可含对应节点类型声明的参数。配置必须放在 arguments 中，不得额外增加未声明的顶层配置字段。

节点 `id` 和 `type` 必需；`id` 是非空字符串且在 Workflow 内唯一，`type` 必须属于本规范列出的节点类型。`name` 若提供必须为字符串，`x`、`y` 若提供必须为数字。连接对象恰含 `fromId`、`fromPortId`、`toId`、`toPortId`、`type`，可选字符串 `id`；不得含其他字段。

`workflowPorts` 仅用于 Input/Output 节点。每项恰含 `id`、`name`、`type` 三个字段，id 必须精确为 `workflow:` 加该项 name；数组须按根接口顺序与根接口生成的端口快照完全相同。`dataInputPorts` 是数据输入端口 ID 数组，元素为非空字符串且不得重复；它必须完整且按节点定义顺序列出配置推导出的输入端口。除一般节点的动态输入外，Struct 操作节点也将 `struct-in` 及固定 JSON 转换输入列入该数组；不得列控制端口。`input_ports`、`output_ports` 仅用于可调用 Workflow 节点的接口快照，格式同根接口端口。共享字段均不得放在 `arguments` 内。

每个 Workflow 必须恰有一个 Input 节点和至少一个 Output 节点。Input/Output 快照不一致、未知节点类型、未知参数、未知节点字段、重复节点 ID 均为非法。

### 9.3 内建节点参数、数据端口和语义

除表中标明的控制端口外，普通执行节点均有 `control-in`、`control-out`。Input 仅有 `control-out`；Output 仅有 `control-in`。Router 和 Foreach 的特殊控制端口见第 10 节。

| 节点类型 | arguments 字段 | 数据输入 | 数据输出 |
| --- | --- | --- | --- |
| `input` | 无 | 无 | 根 `input_ports` 的 `workflow:<name>` |
| `output` | 无 | 根 `output_ports` 的 `workflow:<name>` | 无 |
| `router` | `branches` | `content-in: content` | 分支控制端口，见第 10 节 |
| `construct_message` | 可选 `role`、`role_source` | `content-in: content`；role_source 为 `port` 时另有 `role-in: content` | `message-out: message` |
| `construct_content` | `append_items` | 每个 port 项对应一个 content 输入 | `content-out: content` |
| `construct_map_content` | `mappings` | 每个 port 条目对应一个 content 输入 | `map-out: map-content` |
| `map_content_get` | 无 | `map-in: map-content`、`key-in: content` | `content-out: content` |
| `split_event` | 无 | `event-in: event` | `type-out: content`、`payload-out: content` |
| `construct_event` | `event_type` | `payload-in: content`，内容为 JSON object 文本 | `event-out: event` |
| `publish_event` | 无 | `event-in: event` | 无 |
| `deserialize_json` | `outputs: [{key,type}]` | `content-in: content`，内容为 JSON object 文本 | 每个 key 一个对应 type 的端口 |
| `construct_list` | `item_type`、`initial_value_count` | `<item_type>-in-0` 至 `<item_type>-in-(count-1)` | `list-out: list-<item_type>` |
| `list_append` | `item_type`、`position` | `list-in: list-<item_type>`、`item-in: <item_type>` | `list-out: list-<item_type>` |
| `foreach` | `item_type` | `list-in: list-<item_type>` | `item-out: <item_type>`；控制端口见第 10 节 |
| `history` | `event_types`、`limit` | 无 | `events: list-event` |
| `llm` | `model`、`think`、`tool_calls`、`tools` | `messages-in: list-message` | `output: content`；配置启用时有 `reasoning: content`、`tool_calls: list-content` |
| `local_tool` | `tool`、`parameters: string[]` | 每个参数名一个 content 输入 | `output: content` |
| `remote_sync_tool` | `tool`、`parameters: port[]`、`outputs: port[]`、可选 `timeout_ms` | 每个 parameters 端口 | 每个 outputs 端口 |
| `remote_async_tool` | `tool`、`parameters: port[]`、可选 `timeout_ms`、`callback` | 每个 parameters 端口 | `task_id: content` |
| `context_create` | `value_type`、可选 `context_id` | `initial-value: value_type` | `context-id: content` |
| `context_read` | `value_type`、可选 `context_id_source`、`context_id` | port 模式下 `context-id: content` | `value-out: value_type` |
| `context_write` | `value_type`、可选 `context_id_source`、`context_id` | port 模式下 `context-id: content`，以及 `value-in: value_type` | `context-id: content`、`value-out: value_type` |
| `session_create` | `value_type` | `initial-value: value_type` | `session-id: content` |
| `session_read` | `value_type` | `session-id: content` | `value-out: value_type` |
| `session_write` | `value_type` | `session-id: content`、`value-in: value_type` | `session-id: content`、`value-out: value_type` |
| `workflow` | `workflow_name` | input_ports 快照对应的 `workflow:<name>` | output_ports 快照对应的 `workflow:<name>` |

参数必需性和缺省值如下。节点 `arguments` 若省略，等价于空对象；必需参数未提供的节点无效。除列明字段外，节点不得携带其他 arguments 属性。

| 节点类型 | 必需参数 | 可选参数（缺省值） |
| --- | --- | --- |
| `input`、`output`、`map_content_get`、`split_event`、`publish_event` | 无 | 无 |
| `router` | `branches` | 无 |
| `construct_message` | 无 | `role` (`user`)、`role_source` (`fixed`) |
| `construct_content` | `append_items` | 无 |
| `construct_map_content` | `mappings` | 无 |
| `construct_event` | `event_type` | 无 |
| `deserialize_json` | `outputs` | 无 |
| `construct_list` | `item_type`、`initial_value_count` | 无 |
| `list_append` | `item_type`、`position` | 无 |
| `foreach` | `item_type` | 无 |
| `history` | `event_types`、`limit` | 无 |
| `llm` | 无 | `model`、`think`、`tool_calls`、`tools` |
| `local_tool` | `tool` | `parameters` (空数组) |
| `remote_sync_tool` | `tool` | `parameters` (空数组)、`outputs` (空数组)、`timeout_ms` |
| `remote_async_tool` | `tool` | `parameters` (空数组)、`timeout_ms`、`callback` |
| `construct_struct` | `struct_id` | 无 |
| `struct_get` | `struct_id`、`field` | `missing` (`error`)、`has_fallback` (false) |
| `struct_update` | `struct_id` | `updates` (空数组)、`remove_fields` (空数组) |
| `struct_to_json`、`json_to_struct` | `value_type` | 无 |
| `context_create` | `value_type` | `context_id` (省略时生成 ID；显式值非空白) |
| `context_read`、`context_write` | `value_type` | `context_id_source` (`port`)、`context_id` (仅 fixed 模式使用) |
| `session_create`、`session_read`、`session_write` | `value_type` | 无 |
| `workflow` | `workflow_name` | 无 |

内建节点额外语义：

- `construct_message.role` 缺省为 `user`，只允许 `system`、`user`、`assistant`、`tool`；`role_source` 缺省为 `fixed`，只允许 `fixed` 或 `port`。
- `construct_content.append_items` 必须为非空数组。每项是 object，`type` 必须为 `fixed` 或 `port`。固定项恰含 `type`、`value`，且 value 为字符串；端口项恰含 `type`、`port_id`，且 port_id 为非空字符串。端口 ID 不重复，且端口项 ID 集合与 `dataInputPorts` 一致。按条目顺序拼接；运行时缺失的端口值跳过，非字符串值转换为字符串。
- `construct_map_content.mappings` 必须为非空数组。每项必须包含非空字符串 `key` 且 key 唯一。固定值项含 `key`、`value`，可以附 `value_source` 且其值必须为 `fixed`；value 为字符串。端口项恰含 `key`、`value_source`、`port_id`，其中 value_source 固定为 `port`，port_id 非空且唯一，不得为控制端口，并与 `dataInputPorts` 一致。端口运行值必须为已提供的字符串；输出保留条目顺序。
- `map_content_get` 按 key 查值；查不到时执行失败。
- `split_event` 要求 Event 含非空字符串 `event_type` 和 `payload`；字符串 payload 原样输出，非字符串 payload 输出为紧凑 JSON 文本。
- `construct_event` 要求非空 event_type，且 payload-in 可解析为 JSON object；输出 Event 1.1 对象，version 固定为字符串 `1.1`。
- `publish_event` 只接受 version 为字符串 `1.1`、event_type 为非空字符串且 payload 为 object 的 Event；发布到 Agent 队列并继续当前控制流。
- `deserialize_json.outputs` 必须为非空数组，key 非空且唯一，type 为七种内建数据类型之一。输入必须解析为 object，且包含每个配置 key。除 `content` 外，值须符合声明类型；`content` 保持字符串原值，非字符串值（包括 null）紧凑 JSON 序列化为字符串；`list-content` 对每个元素执行相同转换。其余内建类型严格按类型验证。
- `construct_list.item_type` 允许 `content`、`message`、`event`，或已声明的 `struct:<id>`；`initial_value_count` 为 0 到 20 的整数。`dataInputPorts` 必须恰为该数量的 `<item_type>-in-N` 端口。输出列表类型为 `list-content`、`list-message`、`list-event` 或 `list-struct:<id>`。
- `list_append.item_type` 允许 `content`、`message`、`event`，或已声明的 `struct:<id>`；`position` 只允许 `start` 或 `end`，输入和输出列表类型为对应的 `list-<item_type>`。
- `foreach.item_type` 允许 `content`、`message`、`event`，或已声明的 `struct:<id>`。逐项输出列表元素，列表耗尽后退出循环；空列表直接退出。
- `history.event_types` 必须为非空、不重复的 `terminal`/`response` 子集；limit 必须为 1 到 1000 的整数。
- `llm.model` 在管理端保存及执行时必须为有效且已启用模型标识；通用静态契约校验器不保证验证模型存在。`llm.tools` 缺省为空数组并选择已注册的本地工具；`think`、`tool_calls` 布尔值控制 reasoning、tool_calls 输出端口是否存在，不表示发送给模型的推理开关。tool_calls 输出为 JSON 文本组成的 list-content。
- `local_tool.parameters` 是无重复的非空参数名数组；工具参数和输出均为 content。
- Remote Tool 参数必须与 `remote_tools` 中同名声明的输入端口完全一致；sync 的 outputs 必须与输出声明完全一致。工具接口不能使用保留控制端口名。timeout_ms 若省略，同步默认 10000 ms、异步默认 600000 ms；同步最大值 10000 ms、异步最大值 3600000 ms，运行时还受部署配置限制。
- async callback 若提供，必须恰含 `type`、`queue`、`event_type`、`on`；type 固定为 `redis`，queue 长度 1–256，event_type 长度 1–128，on 为不重复且非空的 `working`/`completed`/`failed` 数组。
- sync 工具仅配置一个名为 `result` 的输出时，将完整工具返回值赋给该端口；其他输出配置要求工具返回包含所有输出名的对象。map-content 输出必须是字符串 map。
- `context_create`、`context_read`、`context_write` 的 value_type 可以为内建数据类型或本 Workflow Struct 类型；Session 节点只允许内建数据类型。
- Context ID 按原字符串逐字符区分，包括首尾空格，不得规范化。`context_create.context_id` 省略时自动生成，显式值必须非空白且在 Context 存储中不存在；空字符串不合法。context_id_source 缺省为 `port`，仅允许 `port`、`fixed`；port 模式读取 context-id，fixed 模式要求非空白 context_id 且不生成 ID 输入端口。详情见第 5 节。
- 子 Workflow 快照必须与目标 Workflow 当前接口一致；递归调用失败。Struct 类型不得出现在任何公开接口快照。

## 10. 连线、控制流和执行模型

### 10.1 连线对象与连接基数

连线对象必须含非空字符串 `fromId`、`fromPortId`、`toId`、`toPortId`、`type`，可选字符串 `id`。端点节点及端口必须存在。type 为 `control` 或本规范定义的数据类型，包括当前 Workflow 的 Struct 类型。控制连线只能连接合法控制端口；数据连线类型必须同时等于源输出和目标输入端口推导类型。每个 control 输出最多一个后继；control 输入可汇合多个来源；每个数据输入最多一个来源。

Input 的 control-out、普通执行节点的 control-in/control-out、Output 的 control-in 必须连接。Router 的每个分支输出必须连接。Foreach 的 control-in、loop-in、loop-out、control-out 必须连接。允许控制流有向环，由 Workflow 自身提供退出条件。数据输入可以不连；运行时读取必要值而无值时失败。运行时 `None` 视为未提供。

### 10.2 Router

`router.arguments.branches` 必须提供数组，可为空。每项恰含唯一非空 `id`、唯一非空 `name`，普通分支 ID 不得为 `branch$others`。每个普通分支 ID 是一个控制输出端口；另有固定保留控制输出 `branch$others`，不写入 branches，也没有通用 `control-out`。执行时要求 `content-in` 有字符串值，先与普通分支 name 精确匹配，匹配时走对应分支 ID；否则走 `branch$others`。名称 `others`、`branch$others` 或“其它”均可作为普通分支名称，与保留兜底端口身份无关。

普通分支 ID 用作连线 fromPortId；内部编译时普通分支 successor 键由 `branch-<name>` 构成，兜底键为 `branch$others`。不同普通分支 name 不得造成内部键冲突。无普通分支时所有已提供值都走兜底；缺失输入时报错，不走兜底。

从 1.6/1.7 迁移时，按 ID 恰为 `branch$others` 识别并移除旧 branches 项，不按显示名称猜测；原连线保留。迁移后 Router 始终具有固定兜底端口，旧 Workflow 若缺少兜底连线，必须由编辑者补齐才能通过服务端校验。迁移保留其他节点与有效连线，不创建 Struct 声明或自动绑定 Struct 节点。

### 10.3 Foreach 和图执行

Foreach 每轮从 list-in 取一个值，经 loop-out 控制端口进入循环体；循环体以 loop-in 回到 Foreach。所有元素处理完后走 control-out；空数组直接走 control-out。list-in 类型必须是 arguments.item_type 对应的 list 类型。

Agent 的通用结构校验不证明节点从 Input 可达，也不保证其运行前置数据生产者已执行。每个 Workflow invocation 中，端口槽位的值在被覆盖前可能保留；生产者未运行时不得把槽位是否存在误认为当前轮次已成功生成值。Agent 校验后将持久化的 nodes/connections 编译为内部执行图。控制连接决定执行顺序，数据连接在输出时传播值；编译图及运行状态不属于持久化 JSON。执行从唯一 Input 开始，Input 根据触发事件/调用方提供的值填充接口输出并进入 control-out；Output 收集已提供且非 None 的接口输入作为结果并结束当前图。必要控制后继缺失、必要输入缺失、运行值类型不符、子 Workflow 快照过期或递归调用均使执行失败。

子 Workflow 在当前调用栈内执行，并使用自身 Input/Output 边界。Workflow 节点接口快照必须等于实际 Workflow 接口。调用链出现重复 Workflow 名称时拒绝递归。Struct 不能跨子 Workflow 接口传递，须显式 JSON 转换。

`construct_event` 产生的 Event 以及 `publish_event` 接受的 Event 遵循 Event 1.1：JSON 对象含 `version` 字符串 `1.1`、非空字符串 `event_type` 和 object `payload`。作为 Struct 字段值或 Context 值递归校验的 `event` 还必须含非空字符串 `event_type` 和 `payload` 属性，但不额外要求 `version`。Event 节点之间按对象传值；只有显式 JSON 转换节点或规定的 payload 文本端口执行序列化/反序列化。`publish_event` 将事件发布到主 Agent 队列，由独立消费者调度，不在当前 Workflow 调用栈内递归启动。
