# Workflow 设计规范

> 本文定义 AAgent Workflow 的全新设计方向。它描述前端编辑器中的节点模型、端口模型、控制流语义、组件结构、交互约束和未来扩展 API。
>
> 本文是独立规范，不继承或解释其他文档中的设计。

## 1. 设计目标

Workflow 是一个可视化的控制流编辑器。用户通过节点和连接描述 Agent 的执行路径，编辑器负责呈现结构、维护连接关系、保存本地草稿，并为未来的运行时执行提供稳定的数据契约。

核心目标：

1. 用统一的节点 UI 表达不同组件。
2. 把节点的显示结构与节点的业务类型解耦。
3. 让输入点和输出点成为一等对象，而不是依赖 CSS 类名或节点类型推断。
6. 让当前的纯前端草稿模型可以平滑演进为后端可执行的 Workflow 定义。
7. 为未来增加节点类型、端口类型、校验器和运行时 API 保留清晰边界。

## 2. 核心概念

### 2.1 Workflow

Workflow 是节点集合和连接集合的有向图：

```text
Workflow = Nodes + Connections + Metadata
```

节点负责定义执行单元和端口，连接负责描述端口之间的数据或控制关系。

编辑器允许用户构建图，但图的运行语义必须满足以下约束：

- 控制流连接是有方向的。
- 一个输入端口最多接收一条连接。
- 一个输出端口可以根据端口能力连接一个或多个目标，但控制流默认只绑定一个后继节点。
- Router/Switch 可以有多个输出分支，但一次运行只选择其中一个分支。
- 未连接的必需输入端口使 Workflow 无法通过校验。
- 连接只能发生在类型兼容的端口之间。

### 2.2 Node

Node 是 Workflow 中可执行或可组合的基本单元。节点包含：

- 稳定的节点 ID。
- 节点类型。
- 用户可见名称。
- 画布位置。
- 输入端口集合。
- 输出端口集合。
- 类型专属配置。

节点不应依赖另一个节点的内部字段来确定自己的端口。节点端口必须由节点自身声明。

### 2.3 Port

Port 是节点与外界连接的唯一接口。端口必须拥有稳定 ID，并明确声明：

- `id`：端口在节点内的唯一标识。
- `direction`：`input` 或 `output`。
- `type`：端口的数据或控制类型。
- `label`：界面显示名称。
- `required`：是否必须连接。
- `multiple`：是否允许多个连接。
- `description`：端口用途描述。

端口 ID 的作用域是节点内部。连接必须同时保存节点 ID 和端口 ID，不能只保存节点 ID。

### 2.4 Connection

Connection 表示一个输出端口到一个输入端口的有向关系：

```text
Connection = fromNode + fromPort + toNode + toPort + type
```

推荐结构：

```js
{
  id: 'connection-001',
  fromId: 'router-1',
  fromPortId: 'branch-1',
  toId: 'llm-1',
  toPortId: 'control-in',
  type: 'control'
}
```

连接的端口类型必须与两端端口声明一致。连接不能通过端口在画布上的位置或 CSS 类名推断。

## 3. 控制流与数据流

### 3.1 控制流

控制流表示“接下来执行哪个节点”。当前控制流类型为：

```text
control / flow
```

控制流的运行规则：

1. 当前节点执行完成后，产生一个控制流结果。
2. 普通节点沿其控制流输出继续执行。
3. Router/Switch 根据条件选择一个输出分支。
4. 选中的分支继续执行，未选中的分支本次运行不执行。
5. 不允许把一个 Router 的多个分支解释成并行执行。

控制流只表达执行顺序，不携带用户文本或模型结果。控制流端口在 UI 上使用绿色标识。

### 3.2 数据流

数据流表示节点之间传递的内容。当前数据流类型为：

```text
content / string
```

数据流的运行规则：

- 数据流可以与控制流同时存在。
- 数据流连接不自动决定节点执行顺序。
- 节点只有在所需控制流到达且必需数据输入满足时才执行。
- 数据流端口在 UI 上使用蓝色标识。
- 当前 `content` 端口的底层类型为 `string`。

控制流与数据流必须保持语义分离：

```text
control: 决定执行路径
content: 携带执行数据
```

## 4. 通用节点 UI 组件

### 4.1 结构

所有节点使用相同的 UI 结构：

```text
.flow-node
├── .flow-node-head
│   ├── .node-symbol
│   └── 节点名称与类型
└── .flow-node-body
    └── .node-port*
```

`head` 和 `body` 是节点 UI 的两个稳定区域。

### 4.2 Head 规范

`head` 只负责节点身份展示：

- 类型图标。
- 节点名称。
- 节点类型标识。

`head` 不放置输入点、输出点、配置摘要、执行状态或业务内容。这样可以保证标题区高度稳定，也避免端点标签与节点标题发生重叠。

推荐 DOM：

```html
<span class="flow-node-head">
  <span class="node-symbol">R</span>
  <span>
    <strong>任务路由</strong>
    <small>ROUTER</small>
  </span>
</span>
```

类型标记是 head 中的主要视觉识别元素。默认尺寸为 `29px × 29px`，字母字号为 `10px`，不能缩小到难以辨认的装饰性尺寸。

### 4.3 Body 规范

`body` 只负责端点展示：

- 输入端点位于左侧。
- 输出端点位于右侧。
- 输入和输出各自拥有独立的垂直排列序列。
- body 的高度由两侧端点数量决定。
- body 的第一行从顶部开始。
- 后续端点以固定行高向下排列。

默认端点行高：

```js
const portRowHeight = 28;
const portTopInset = 8;
```

布局公式：

```text
row = directionPorts.indexOf(port)
top = portTopInset + row * portRowHeight
bodyHeight = max(minBodyHeight, portTopInset + max(inputCount, outputCount) * portRowHeight)
```

第一行端点必须与 head 底部的分割线保持视觉间距，不能直接贴在 body 顶部。当前默认顶部内缩为 `8px`。

端点的横向位置由方向决定：

```text
input  -> left: -7px
output -> right: -7px
```

端点中心必须位于节点边界附近，使 SVG 连线可以从端点中心开始或结束。

### 4.4 端点标签

端点标签使用 `data-port-label` 提供，CSS 只负责显示，不负责判断端口类型。
标签表示端口的业务名称，而不是端口类型名称。端口类型已经通过颜色和连接兼容性表达，不应重复显示为标签。

```html
<span
  class="node-port"
  data-port-id="branch-1"
  data-port-direction="output"
  data-port-type="control"
  data-port-label="分支 1"
></span>
```

标签规范：

- 标签必须描述端口在节点中的业务职责，例如“输入内容”“上下文”“触发”“下一步”或具体分支名。
- 标签不能使用“控制流”“string”等类型名代替端口名称。
- 输入标签显示在端点右侧。
- 输出标签显示在端点左侧。
- 标签不能参与连接几何计算。
- 标签不能拦截鼠标事件。
- 标签内容必须通过 DOM 属性设置，不能把用户输入直接拼接进 HTML。

### 4.5 接口契约

节点检查器中的契约区域统一命名为“接口契约”。Input、Router/Switch 和 LLM 不再分别使用“输入契约”或“端点契约”，因为它们都描述同一个概念：节点对外暴露的端口接口。

接口契约是节点端口定义的只读 UI 投影。每个端口契约只展示两个字段：

- `label`：端口的业务名称，例如“输入内容”“上下文”“触发”“下一步”或具体分支名。
- `type`：端口类型，例如 `control` 或 `content`。

端口颜色与 `type` 保持一致，用于快速区分控制流和数据流。颜色已经承担类型识别职责，因此接口契约不再显示“控制流”、`string`、`flow` 等类型别名或解释性描述。

接口契约必须按端口方向拆分为两个区域：

- `输入接口`：只列出 `direction: 'input'` 的端口。
- `输出接口`：只列出 `direction: 'output'` 的端口。

没有端口的一侧也应保留对应区域，并显示“无输入接口”或“无输出接口”，避免不同节点的契约结构发生跳变。

推荐结构：

```html
<section class="inspector-section">
  <div class="section-label"><strong>接口契约</strong><span>只读</span></div>
  <div class="contract-group">
    <div class="contract-group-title">输入接口</div>
    <div class="port-contract">
      <span class="port-swatch content"></span>
      <strong>上下文</strong>
      <code>content</code>
    </div>
  </div>
  <div class="contract-group">
    <div class="contract-group-title">输出接口</div>
    <div class="empty-options">无输出接口</div>
  </div>
</section>
```

接口契约区域的约束：

- 所有节点类型使用相同的标题和行结构。
- 接口契约始终按“输入接口”和“输出接口”分组，不能把两个方向混在同一个列表中。
- 端口顺序与节点端口定义顺序一致。
- 契约区域只读，端口名称的编辑应通过节点专用配置区域完成。
- 端口方向仍由画布中端点所在的左右侧表达，不重复添加方向说明。
- 契约中的 `label` 必须与画布端点的 `data-port-label` 保持一致。
- 契约中的 `type` 必须与端口定义及 `data-port-type` 保持一致。

## 5. 节点类型规范

### 5.1 Input

Input 是 Workflow 的固定入口节点。

端口：

```js
[
  {
    id: 'control-out',
    direction: 'output',
    type: 'control',
    label: '下一步'
  },
  {
    id: 'content-out',
    direction: 'output',
    type: 'content',
    label: '输入内容'
  }
]
```

Input 不允许被删除。它通常是 Workflow 中控制流和初始文本内容的来源。

### 5.2 Router / Switch

Router 是条件分支节点，语义等同于普通编程语言中的 `switch` 或条件分支结构。

固定输入端口：

```js
{
  id: 'control-in',
  direction: 'input',
  type: 'control',
  label: '触发'
}
```

动态输出端口由用户创建的分支决定：

```js
{
  id: 'branch-1',
  direction: 'output',
  type: 'control',
  label: '成功路径'
}
```

Router 分支规则：

- 每个分支都是独立的控制流输出端口。
- 分支名称可编辑。
- 分支可以新增或删除。
- 至少保留一个分支。
- 删除分支时，属于该端口的连接必须同时删除。
- 每次运行只选择一个分支。
- Router 不负责配置“路由到哪个模型”，后续节点由连接关系决定。

### 5.3 LLM

LLM 是模型执行节点。

端口：

```js
[
  {
    id: 'control-in',
    direction: 'input',
    type: 'control',
    label: '触发'
  },
  {
    id: 'content-in',
    direction: 'input',
    type: 'content',
    label: '上下文'
  },
  {
    id: 'control-out',
    direction: 'output',
    type: 'control',
    label: '下一步'
  }
]
```

LLM 的模型、系统指令和 Tools 属于节点配置，不属于节点 body 的端点 UI。

## 6. 前端模块边界

### 6.1 `model.js`

职责：

- 保存 Workflow 状态。
- 管理节点集合。
- 管理连接集合。
- 创建和删除节点。
- 保存、加载和重置本地草稿。
- 维护 Router 分支数据。

不负责：

- 创建 DOM。
- 计算端点像素位置。
- 处理 PointerEvent。
- 绘制 SVG 连线。

### 6.2 `view.js`

职责：

- 定义节点端口集合。
- 创建通用节点 UI。
- 渲染节点 head 和 body。
- 渲染检查器。
- 将 DOM 端点交给连接控制器绑定。
- 响应节点配置变化并重新渲染。

核心抽象：

```js
function createNodeUI(node) {
  // 读取 nodePorts(node)
  // 创建 head
  // 创建 body
  // 按方向排列 ports
  // 绑定端点和节点拖拽
}
```

节点类型差异应集中在 `nodePorts(node)` 和对应的检查器配置中，不应散落在 DOM 拼接、CSS 选择器和连接控制器中。

### 6.3 `connections.js`

职责：

- 根据端口 ID 获取端点 DOM。
- 处理端点 PointerEvent。
- 判断端口类型和方向是否兼容。
- 创建、移动和删除连接。
- 计算端点中心。
- 绘制 SVG 路径。

连接控制器不得通过以下方式寻找端口：

- 节点类型。
- 节点名称。
- CSS 专用类名。
- 端点在节点中的顺序。

唯一可靠的查找方式是：

```js
nodeElement.querySelector(`[data-port-id="${portId}"]`)
```

### 6.4 `workflow.js`

职责：

- 组装页面元素。
- 初始化连接控制器和节点视图。
- 绑定保存、重置和添加节点按钮。
- 管理“未保存 / 已保存”状态。

它不应了解 Router 分支的布局细节，也不应直接操作节点端点 DOM。

## 7. 数据结构

### 7.1 Node

```js
{
  id: 'router-1',
  type: 'router',
  name: '任务路由',
  x: 310,
  y: 238,
  config: {
    prompt: '根据输入选择一个分支。'
  },
  branches: [
    {
      id: 'branch-1',
      name: '成功路径'
    },
    {
      id: 'branch-2',
      name: '失败路径'
    }
  ]
}
```

当前代码中部分节点配置仍位于节点顶层。未来建议统一收拢到 `config`，但迁移时必须提供版本号和数据迁移函数。

### 7.2 Port Definition

```js
{
  id: 'content-in',
  direction: 'input',
  type: 'content',
  label: '上下文',
  required: true,
  multiple: false,
  description: '接收需要模型处理的文本内容'
}
```

端口定义可以是静态的，也可以由节点配置动态生成。Router 分支属于动态端口。

### 7.3 Connection

```js
{
  id: 'connection-001',
  fromId: 'input',
  fromPortId: 'content-out',
  toId: 'llm-1',
  toPortId: 'content-in',
  type: 'content'
}
```

建议未来删除冗余的顶层 `type`，改为从端口定义解析并在校验阶段确认两端类型一致。但在当前阶段保留 `type` 有利于调试和快速展示。

### 7.4 Workflow Document

未来建议使用版本化文档：

```js
{
  schemaVersion: 1,
  id: 'workflow-001',
  name: 'Agent 主控制流',
  nodes: [],
  connections: [],
  metadata: {
    createdAt: null,
    updatedAt: null
  }
}
```

## 8. 连接规则

### 8.1 兼容性

两个端口满足以下条件时才允许连接：

```js
source.direction === 'output'
source.type === target.type
 target.direction === 'input'
source.nodeId !== target.nodeId
```

建议实现为纯函数：

```js
function canConnect(sourcePort, targetPort, graph) {}
```

这样可以同时用于：

- 拖拽过程中的高亮。
- 放置时的最终校验。
- Workflow 保存前的校验。
- 未来的自动化测试。

### 8.2 输入端约束

默认情况下，一个输入端口只能有一条连接。新连接替换旧连接，或者由 UI 明确拒绝，二者必须选择一种一致行为。

当前推荐行为：

- 用户将新连接放到已有输入端口时，删除该输入端口的旧连接。
- 其他输出端口的连接不受影响。

### 8.3 输出端约束

控制流输出默认只允许一条连接。Router 的每一个分支是独立输出端口，因此 Router 可以拥有多条控制流连接，但每个分支最多一条。

数据流输出允许多条连接，用于把同一份数据提供给多个输入端。数据流扇出只表示数据可被多个节点读取，不自动表示并行执行。

端口能力示例：

```js
{
  id: 'content-out',
  direction: 'output',
  type: 'content',
  label: '输入内容',
  multiple: true
}
```

输入端仍然保持 `multiple: false`。一个输入端只能保留一条连接；新连接放置到已有输入端时，旧连接被替换。

### 8.4 连接拖拽交互

所有连接编辑都从端点开始。拖拽过程中只高亮类型和方向兼容的端点。拖拽结束时，行为由连接类型、起点状态和落点决定。

| 类型 | 起点状态 | 落点 | 结果 |
| --- | --- | --- | --- |
| 数据流 | 输出端未连接 | 空输入端 | 创建一条数据连接 |
| 数据流 | 输出端未连接 | 已连接输入端 | 删除输入端旧连接，创建新连接 |
| 数据流 | 输出端已有一条或多条连接 | 空输入端 | 固定当前输出端，创建一条新的数据连接 |
| 数据流 | 输出端已有一条或多条连接 | 已连接输入端 | 固定当前输出端，删除目标输入端旧连接后创建新连接 |
| 数据流 | 已连接输入端 | 空白区域 | 输出端保持不变，删除输入端上的当前连接 |
| 数据流 | 已连接输入端 | 兼容输出端 | 输入端跟随拖拽改接到目标输出端，原输出端保持不变 |
| 数据流 | 任意 | 不兼容端点 | 取消本次拖拽，不改变原连接 |
| 控制流 | 空输出端和空输入端 | 兼容空端点 | 创建一条控制流连接 |
| 控制流 | 已连接输出端或输入端 | 空白区域 | 删除当前控制流连接 |
| 控制流 | 已连接端点 | 兼容端点 | 将当前连接改接到目标端点；目标已有连接时先替换目标连接 |
| 控制流 | 任意 | 不兼容端点 | 取消本次拖拽，不改变原连接 |

数据流和控制流都支持以下直觉化操作：

- 从空端口拖到兼容端口：创建连接。
- 从已连接端口拖到空白区域：删除当前连接。
- 从已连接端口拖到另一个兼容端口：改接连接。
- 拖到不兼容端口或节点自身：取消操作并恢复原状。

数据流与控制流的关键差异有两项：数据流输出可以保留多个目标，因此无论输出端是否已有连接，从输出端发起拖拽都固定输出端并创建新的扇出连接；从数据流输入端发起拖拽时，输出端保持不变，只有输入端跟随鼠标改接或删除。控制流端口均为单连接，已有连接时拖拽哪一端就移动哪一端，另一端保持不变；无连接时从被拖端创建新连接。

### 8.5 连接交互状态表

| 端口 | 当前连接 | 拖拽起点 | 拖到空白 | 拖到兼容空端口 | 拖到兼容已连接端口 |
| --- | --- | --- | --- | --- | --- |
| 数据流输入 | 无 | 不产生操作 | 不产生操作 | 创建连接 | 替换目标旧连接后创建 |
| 数据流输入 | 有 | 编辑该输入唯一连接，输出端保持不变 | 删除该连接 | 输入端跟随拖拽改接到目标输出端 | 替换目标旧连接后改接，原输出端保持不变 |
| 数据流输出 | 无 | 创建新连接 | 不产生操作 | 创建连接 | 替换目标输入旧连接后创建 |
| 数据流输出 | 有 | 创建新的扇出连接 | 不产生操作 | 创建新的扇出连接 | 替换目标输入旧连接后创建新的扇出连接 |
| 控制流输入 | 无 | 不产生操作 | 不产生操作 | 创建连接 | 替换目标连接后创建 |
| 控制流输入 | 有 | 编辑该输入唯一连接，另一端保持不变 | 删除该连接 | 当前输入端跟随拖拽改接 | 替换目标连接后改接 |
| 控制流输出 | 无 | 创建连接 | 不产生操作 | 创建连接 | 替换目标连接后创建 |
| 控制流输出 | 有 | 编辑该输出唯一连接，另一端保持不变 | 删除该连接 | 当前输出端跟随拖拽改接 | 替换目标连接后改接 |

数据流输出端已有多条连接时，从输出端拖拽仍然只创建新的扇出连接，不编辑既有连接。既有数据流连接只能从对应输入端拖拽编辑；这样可以明确保持输出端不变，并避免从多个扇出连接中猜测用户要编辑哪一条。

### 8.6 删除行为

删除节点时：

```js
connections = connections.filter(
  connection => connection.fromId !== nodeId && connection.toId !== nodeId
)
```

删除端口时：

```js
connections = connections.filter(
  connection =>
    !(connection.fromId === nodeId && connection.fromPortId === portId) &&
    !(connection.toId === nodeId && connection.toPortId === portId)
)
```

## 9. 校验 API

未来应增加独立的 Workflow 校验模块，不把校验逻辑塞进视图或连接拖拽代码。

推荐 API：

```js
validateWorkflow(workflow) => {
  valid: boolean,
  errors: [
    {
      code: 'MISSING_REQUIRED_INPUT',
      nodeId: 'llm-1',
      portId: 'content-in',
      message: '缺少必需的 string 输入'
    }
  ],
  warnings: []
}
```

建议的错误代码：

| 代码 | 含义 |
| --- | --- |
| `DUPLICATE_NODE_ID` | 节点 ID 重复 |
| `DUPLICATE_PORT_ID` | 节点内端口 ID 重复 |
| `UNKNOWN_NODE` | 连接引用了不存在的节点 |
| `UNKNOWN_PORT` | 连接引用了不存在的端口 |
| `PORT_DIRECTION_MISMATCH` | 端口方向不兼容 |
| `PORT_TYPE_MISMATCH` | 端口类型不兼容 |
| `MULTIPLE_INPUT_CONNECTIONS` | 输入端口存在多条连接 |
| `MISSING_REQUIRED_INPUT` | 必需输入未连接 |
| `NO_ENTRY_NODE` | 没有 Workflow 入口 |
| `UNREACHABLE_NODE` | 节点无法从入口到达 |
| `CONTROL_FLOW_CYCLE` | 控制流存在不允许的循环 |
| `EMPTY_ROUTER_BRANCHES` | Router 没有有效分支 |

## 10. 节点注册 API

当节点种类增加时，不应继续在 `view.js` 中堆叠 `if (node.type === ...)`。未来可以引入节点注册表：

```js
registerNodeType({
  type: 'llm',
  symbol: 'L',
  label: 'LLM',
  createDefault: () => ({
    model: 'gpt-5',
    prompt: '',
    tools: []
  }),
  getPorts: (node) => [
    {
      id: 'control-in',
      direction: 'input',
      type: 'control',
      label: '触发',
      required: true
    },
    {
      id: 'content-in',
      direction: 'input',
      type: 'content',
      label: '上下文',
      required: true
    },
    {
      id: 'control-out',
      direction: 'output',
      type: 'control',
      label: '下一步'
    }
  ],
  renderInspector: (context) => {},
  validate: (node, context) => []
});
```

节点注册项建议包含：

- 类型 ID。
- 显示名称。
- 图标或符号。
- 默认配置生成器。
- 端口生成器。
- 检查器渲染器。
- 节点配置校验器。
- 运行时执行器引用。

## 11. 动态端口 API

Router 的分支是动态端口。未来可以把动态端口抽象为统一 API：

```js
addPort(nodeId, {
  id: 'branch-3',
  direction: 'output',
  type: 'control',
  label: '其他路径'
});

renamePort(nodeId, 'branch-3', '兜底路径');

removePort(nodeId, 'branch-3');
```

API 必须保证：

1. 端口 ID 在节点内唯一。
2. 删除端口会清理相关连接。
3. 修改标签不会改变端口 ID。
4. 修改端口类型必须重新校验相关连接。
5. 端口排序变化不影响连接，因为连接只依赖端口 ID。

## 12. 运行时 API

当前 Workflow 只负责编辑和本地保存。未来接入执行引擎时，建议保持编辑模型与运行模型分离。

编辑器侧：

```js
compileWorkflow(workflow) => ExecutionPlan
```

运行时：

```js
runWorkflow(plan, input) => RunHandle
```

运行句柄：

```js
{
  id: 'run-001',
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled',
  startedAt: null,
  finishedAt: null
}
```

运行事件：

```js
{
  type: 'node.started',
  runId: 'run-001',
  nodeId: 'llm-1',
  timestamp: 0
}
```

建议的运行事件类型：

- `workflow.started`
- `workflow.completed`
- `workflow.failed`
- `node.started`
- `node.completed`
- `node.failed`
- `router.branch.selected`
- `port.value.emitted`
- `connection.followed`

Router 运行时必须发出分支选择事件：

```js
{
  type: 'router.branch.selected',
  nodeId: 'router-1',
  portId: 'branch-2',
  reason: '用户输入符合失败处理条件'
}
```

这个事件可以用于运行轨迹、调试面板和审计日志，但不应改变图本身。

## 13. 版本化与迁移

Workflow 草稿必须带 schema 版本。未来结构变化时使用显式迁移函数：

```js
migrateWorkflow(document, fromVersion, toVersion) => document
```

迁移原则：

- 迁移函数是纯函数。
- 每次只负责一个相邻版本。
- 不在渲染阶段隐式修改持久化数据。
- 迁移失败时保留原始数据并提示用户。
- 新版本保存前统一写入最新 schema 版本。

建议迁移链：

```text
v1 -> v2 -> v3 -> latest
```

不建议直接维护大量互相独立的版本转换函数。

## 14. UI 交互规范

### 14.1 端点连接

- 按住端点开始连接。
- 兼容目标端点高亮。
- 不兼容目标端点不高亮。
- 松开鼠标完成连接。
- 连接预览线使用与端口类型一致的颜色。
- 控制流使用实线。
- 数据流使用蓝色虚线。

### 14.2 节点拖拽

- 拖拽节点整体移动。
- 在端点上按下时优先处理连接，不触发节点拖拽。
- 节点拖拽完成后更新位置并标记草稿未保存。
- 节点位置不能超出画布有效范围。

### 14.3 Router 分支管理

- 分支名称输入框直接编辑。
- 分支端点标签实时同步。
- 新增分支后立即创建对应输出端点。
- 删除分支前清理对应连接。
- 至少保留一个分支。
- 分支顺序变化只影响显示顺序，不影响连接关系。

## 15. 样式规范

### 15.1 端点颜色

| 类型 | 颜色用途 |
| --- | --- |
| `control` | 绿色 |
| `content` | 蓝色 |
| 未知类型 | 中性灰色 |

CSS 应优先使用数据属性选择器：

```css
.node-port[data-port-type="control"] { background: var(--green); }
.node-port[data-port-type="content"] { background: var(--blue); }
```

颜色用于区分端口类型，标签用于说明端口名称；两者职责不可互换。

不要为每种节点类型创建一套端点定位 CSS。

### 15.2 稳定尺寸

节点的 head 高度、端点行高和端点尺寸必须稳定。端点标签过长时：

- 优先使用省略号。
- 不允许改变端点圆点的位置。
- 不允许标签撑大节点宽度。
- 必要时使用 title 或完整信息检查器展示。

### 15.3 层级

推荐层级：

```text
connection layer: z-index 1
node layer:       z-index 2
active node:      z-index 3
canvas overlays:  z-index 4
```

端点必须位于节点层之上，并且标签不能阻挡端点交互。

## 16. 测试规范

### 16.1 单元测试

至少覆盖：

- 节点端口定义完整性。
- 端口 ID 唯一性。
- Router 分支新增、重命名、删除。
- 删除分支时连接清理。
- 控制流和数据流类型兼容性。
- 输入端口单连接约束。
- 连接保存和重新加载。
- 旧数据迁移到最新 schema。

### 16.2 UI 测试

至少覆盖：

- Input、Router、LLM 都具有相同的 head/body 结构。
- 输入点均在 body 左侧。
- 输出点均在 body 右侧。
- 多个 Router 分支从 body 顶部开始按固定行距排列。
- 端点标签不会与 head 重叠。
- 连接从正确的端点中心开始和结束。
- 新增分支后输出点数量增加。
- 删除分支后输出点和连接同时消失。

### 16.3 运行语义测试

Router 必须测试：

```text
给定三个分支，运行一次只能收到一个 branch.selected 事件。
未被选择的分支不产生 node.started 事件。
```

## 17. 当前实现与未来方向

当前实现阶段重点是前端编辑器：

- 节点在浏览器中渲染。
- 连接通过 SVG 绘制。
- 草稿保存在浏览器本地。
- Router 分支由用户维护。
- 控制流与数据流已经在端口层分离。

未来阶段可以按以下顺序扩展：

1. 引入统一的 Workflow schema 版本。
2. 增加 `validateWorkflow`。
3. 增加节点注册表。
4. 增加动态端口 API。
5. 增加撤销与重做历史。
6. 增加 Workflow 导入导出。
7. 增加执行计划编译器。
8. 接入后端运行时。
9. 增加运行轨迹和节点级调试。
10. 增加子 Workflow 和复合节点。

## 18. 设计决策摘要

最终的核心决策如下：

- 节点 UI 统一为 `head + body`。
- `head` 只展示类型和名称。
- `body` 只展示输入点和输出点。
- 端点是有稳定 ID 的一等对象。
- 连接必须保存源端口和目标端口。
- 输入端点在左，输出端点在右。
- 端点从 body 顶部开始，按固定行距向下排列。
- Router 是 switch，不是模型候选列表。
- Router 的每个分支都是独立控制流输出端点。
- 一次运行只走一条控制流分支。
- UI、数据模型、连接控制和未来运行时保持独立。
- 未来扩展优先通过节点注册、端口定义和校验 API 完成，而不是继续增加节点类型特判。
