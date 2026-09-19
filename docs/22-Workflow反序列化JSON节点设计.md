# 22 Workflow 反序列化 JSON 节点设计

## 1. 目标

Workflow 中的 `content` 经常承载一整个 JSON 文本。当前节点可以传递或拼接这段文本，但不能按字段拆成多个有类型的输出，使用者只能为每种响应结构编写专用 Tool。

本方案新增 `deserialize_json` 节点：

- 输入一个 `content`；
- 用户配置要读取的 JSON 顶层键及其 Workflow 数据类型；
- 每个配置项生成一个同名输出 Port；
- 执行时只解析一次输入 JSON，再按声明类型转换并传播各字段值。

首期只支持顶层键，不引入 JSONPath、点号路径、数组下标或默认值。若需要读取子结构，可先将该子结构输出为 `content`，再连接另一个 `deserialize_json` 节点继续拆分。

## 2. 节点契约

节点类型：`deserialize_json`

```json
{
  "id": "deserialize-json-1",
  "type": "deserialize_json",
  "name": "反序列化 JSON",
  "x": 420,
  "y": 220,
  "arguments": {
    "outputs": [
      { "key": "title", "type": "content" },
      { "key": "items", "type": "list-content" },
      { "key": "event", "type": "event" }
    ]
  }
}
```

固定端口：

| 方向 | 端口 ID | 类型 | 说明 |
|------|---------|------|------|
| 输入 | `control-in` | `control` | 触发解析 |
| 输入 | `content-in` | `content` | 必填的 JSON 文本 |
| 输出 | `control-out` | `control` | 全部字段转换成功后继续 |

动态输出端口由 `arguments.outputs` 逐项生成：

| 配置字段 | 说明 |
|----------|------|
| `key` | JSON 顶层键，同时作为输出 Port ID 和显示名称 |
| `type` | 输出 Port 的 Workflow 数据类型 |

`type` 支持现有全部数据类型：

```text
content
message
event
list-content
list-message
event-list
```

`outputs` 必须是非空数组。`key` 必须是非空字符串，区分大小写，不允许重复，也不允许使用同方向已有的 `control-out`。节点不保存 `dataInputPorts`，因为数据输入固定为 `content-in`。

## 3. 转换规则

### 3.1 输入与取值

`content-in` 必须是字符串，并且必须能解析为 JSON 对象。JSON 数组、字符串、数字、布尔值和 `null` 都不能作为根值，因为节点需要按键取值。

每个输出配置只读取对象中完全同名的顶层键。键不存在与键存在但值为 JSON `null` 是两种情况：前者报缺少字段，后者继续按声明类型转换。

### 3.2 `content`

`content` 的运行时值必须始终是字符串：

- JSON 字符串直接使用其字符串内容，不保留外层引号；
- 其他 JSON 值重新序列化为紧凑 JSON 文本；
- 对象和数组的全部子结构原样保留在 JSON 文本中；
- JSON `null` 转为字符串 `null`，不能传播 Python `None`，否则现有 `read_workflow_input` 会将它视为没有输入。

示例：

| JSON 字段值 | `content` 输出 |
|-------------|----------------|
| `"hello"` | `hello` |
| `42` | `42` |
| `true` | `true` |
| `null` | `null` |
| `{"id":1,"meta":{"ok":true}}` | `{"id":1,"meta":{"ok":true}}` |
| `[1,{"id":2}]` | `[1,{"id":2}]` |

序列化使用 UTF-8 语义、保留非 ASCII 字符，并采用紧凑分隔符。对象键顺序沿用 JSON 解析后的顺序，不承诺按键排序。

### 3.3 `list-content`

字段值必须是 JSON 数组。对数组中的每一项独立应用 `content` 转换规则，最终得到字符串列表。

输入：

```json
{
  "items": [
    "plain",
    7,
    { "id": 1, "tags": ["a", "b"] },
    [1, 2],
    null
  ]
}
```

`items: list-content` 的运行时输出等价于：

```json
[
  "plain",
  "7",
  "{\"id\":1,\"tags\":[\"a\",\"b\"]}",
  "[1,2]",
  "null"
]
```

因此数组项即使包含对象、数组等子结构，也只占一个 `list-content` 元素，并以完整 JSON 字符串保存，不会被展开或拍平。

### 3.4 其他类型

其他类型直接保留 JSON 解析后的结构，但必须满足现有 Workflow 类型契约：

| 声明类型 | 字段值要求 | 输出表示 |
|----------|------------|----------|
| `message` | 对象，且恰有 `role`、`content`；`role` 为允许值，`content` 为字符串 | Message 对象 |
| `event` | 对象，`event_type` 为非空字符串且存在 `payload` | Event 对象，`payload` 子结构保持原样 |
| `list-message` | 数组，且每项都是合法 Message | Message 对象列表 |
| `event-list` | 数组，且每项都是合法 Event | Event 对象列表 |

首期不做宽松转换。例如字符串形式的 Message 不会再做第二次 JSON 解析，数字不会自动转成 Message，Message 的非字符串 `content` 也不会自动序列化。需要这类转换时，应先声明为 `content`，再显式连接后续节点处理。

## 4. 执行语义

执行顺序：

1. 读取 `content-in`；
2. 使用标准 JSON 解析器解析一次；
3. 校验根值是对象；
4. 按 `arguments.outputs` 顺序读取并转换全部字段；
5. 全部成功后传播所有动态输出；
6. 进入 `control-out`。

转换采用原子语义。任一字段失败时，节点立即报错，不传播任何动态输出，也不进入 `control-out`。实现时应先将所有转换结果存入局部字典，全部校验成功后再统一调用 `propagate_workflow_output`，避免下游收到部分新值。

错误至少区分以下原因，并包含节点 ID；日志可附带失败键，但不应回显完整输入内容：

- `content-in` 未连接或没有值；
- 输入不是字符串；
- 输入不是合法 JSON；
- JSON 根值不是对象；
- 配置的键不存在；
- 字段值不符合声明类型。

不提供“跳过失败字段”“缺失时输出空字符串”或默认值配置。这些行为会削弱静态端口契约，并让下游难以区分真实空值与解析失败。

## 5. 编辑器交互

节点库增加“反序列化 JSON”。新节点默认包含一个输出配置：

```json
{ "key": "value", "type": "content" }
```

Inspector 中每行配置包含：

- 键名输入框；
- 类型下拉框；
- 删除按钮；
- 末尾的新增输出按钮。

修改键名或类型后立即重建动态输出端口，并调用现有连接协调逻辑：

- 键名变化后，旧 Port ID 对应的数据连接失效并删除；
- 类型变化后，只删除与新类型不兼容的数据连接；
- 所有控制连接必须保留；
- 至少保留一个输出配置；
- 非法或重复键名在 Inspector 中阻止导出，运行时和保存 API 仍执行同等校验。

画布端口顺序与 `arguments.outputs` 顺序一致。拖动配置项排序不在首期范围内，可通过删除后重新添加调整顺序。

## 6. 保存与连接校验

新增节点需要同步进入现有四套契约边界：

1. Agent 的节点类型、参数字段、数据端口和控制端口契约；
2. Agent 的节点配置与连接校验；
3. WebUI Workflow 保存 API 的节点格式、动态端口和连接校验；
4. Workflow Editor 的节点创建、导入归一化、序列化、端口生成和 Inspector。

数据端口契约为：

```text
inputs  = {"content-in": "content"}
outputs = {output.key: output.type for output in arguments.outputs}
```

`arguments` 只允许 `outputs`。动态输出不写入顶层 `output_ports`，该字段继续只用于可调用 Workflow 节点的契约快照。

节点沿用普通单进单出控制流：`control-in` 和 `control-out` 都必须连接。一个动态输出可以连接多个同类型输入；每个目标输入仍只能有一个数据来源。

## 7. 测试范围

### 7.1 Agent

- 字符串、数字、布尔值、`null`、对象和数组正确转换为 `content`；
- `list-content` 逐项字符串化，并保留对象和数组子结构；
- Message、Event 及其列表按现有结构输出；
- 非法 JSON、非对象根值、缺少键和类型不匹配均失败；
- 多输出中后一个字段失败时，前面的字段也没有被传播；
- 动态输出端口的连接类型正确，未知或重复端口被拒绝；
- 节点成功后才进入 `control-out`。

### 7.2 WebUI 与编辑器

- 保存 API 接受合法节点并拒绝非法 `outputs`；
- 新建、导出、重新导入后动态输出配置不变；
- 新增、删除、改名和改类型会刷新 Port；
- 改类型只清理不兼容的数据连接，控制连接保持不变；
- 动态端口只能连接相同数据类型；
- 节点库、画布符号、Inspector 模板和样式均存在。

## 8. 首期不包含

- JSONPath、点号路径和数组下标；
- 对嵌套字符串进行递归 JSON 解析；
- 默认值、可选键和部分成功模式；
- 数字、布尔值、对象等新的 Workflow 一等数据类型；
- JSON Schema 推断或从样例自动生成端口；
- 对输出配置进行拖动排序。

这些能力可以在真实工作流出现需求后独立设计，不影响首期节点契约。
