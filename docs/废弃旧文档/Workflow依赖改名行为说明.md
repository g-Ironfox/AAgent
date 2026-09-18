# Workflow 依赖改名行为说明

## 现象

在 Workflow 编辑器中，如果某个 Workflow 被其他 Workflow 的画布节点调用，那么在“元数据与接口”窗口中修改这个依赖 Workflow 的名称并点击“应用”后，画布上已经使用它的节点名称也会自动更新。

这是当前编辑器明确实现的同步行为，不是浏览器或数据库自动推断出来的结果。

## 当前引用方式

Workflow 调用节点使用 `workflow_name` 保存依赖 Workflow 的名称：

```json
{
  "type": "workflow",
  "name": "旧名称",
  "workflow_name": "旧名称",
  "input_ports": [],
  "output_ports": []
}
```

创建调用节点时，节点的显示名称和引用名称都来自依赖 Workflow 的名称：

```js
name: configuration.name,
workflow_name: configuration.name,
```

因此，当前数据模型中没有独立的稳定 `workflow_id` 用来识别依赖 Workflow。依赖 Workflow 的名称同时承担了：

- 调用关系中的引用值；
- 画布节点的默认显示名称；
- 元数据中可调用 Workflow 的识别依据。

## 改名时发生的过程

### 1. 打开元数据窗口时记录旧名称

编辑器渲染每个可调用 Workflow 时，会把当前名称保存到行元素的 `previous_name` 数据中：

```js
row.dataset.previousName = workflow.name || '';
```

这个值代表打开元数据窗口时的旧名称。

### 2. 点击“应用”时读取旧名称和新名称

用户修改名称后，元数据表单会同时提交：

```js
{
  previous_name: "旧名称",
  name: "新名称",
  input_ports: [],
  output_ports: []
}
```

`previous_name` 用来定位原来引用该依赖的节点，`name` 是修改后的新名称。

### 3. 按旧名称查找画布节点

应用元数据时，编辑器会建立一个“旧名称 → 新配置”的映射，然后遍历画布节点：

```js
const nextByPreviousName = new Map(
  nextWorkflows.map((workflow) => [
    workflow.previous_name || workflow.name,
    workflow,
  ])
);

for (const node of state.nodes) {
  if (node.type !== 'workflow') continue;

  const workflow = nextByPreviousName.get(node.workflow_name);
  if (!workflow) continue;

  node.workflow_name = workflow.name;
  node.name = workflow.name;
}
```

也就是说，节点原来的 `workflow_name` 等于某个依赖的 `previous_name` 时，就会被认定为该依赖的使用者。

### 4. 同步名称和接口

找到对应节点后，编辑器会同步更新：

```js
node.workflow_name = workflow.name;
node.name = workflow.name;
node.input_ports = structuredClone(workflow.input_ports);
node.output_ports = structuredClone(workflow.output_ports);
```

所以自动变化的不只有节点名称，还包括该调用节点的输入接口和输出接口。

## 为什么改名不会被当成删除

应用元数据前，编辑器会检查是否有调用中的依赖被删除：

```js
const retainedNames = new Set(
  callableWorkflows.map(
    (workflow) => workflow.previous_name || workflow.name
  )
);
```

检查使用中的节点时，也使用节点当前保存的旧名称进行判断：

```js
const removedInUse = state.nodes.find(
  (node) => node.type === 'workflow'
    && !retainedNames.has(node.workflow_name)
);
```

由于重命名的依赖仍然保留着 `previous_name`，所以它不会被判定为删除。随后同步逻辑会把旧引用迁移到新名称。

## 一个完整例子

原始状态：

```text
可调用 Workflow：文本总结
画布节点：workflow_name = 文本总结
```

用户在元数据窗口中将“文本总结”改为“摘要生成”：

```text
previous_name = 文本总结
name          = 摘要生成
```

点击“应用”后：

```text
可调用 Workflow：摘要生成
画布节点：workflow_name = 摘要生成
画布节点显示名称：摘要生成
```

## 当前实现的边界

这套机制可以在编辑器当前会话中正确完成依赖改名迁移，但它本质上仍然是名称引用模型：

- 节点保存的是 `workflow_name`，不是稳定 ID；
- `previous_name` 只是在编辑元数据时临时用于迁移引用；
- 导出数据后，依赖关系仍然依靠名称表达；
- 如果绕过编辑器直接修改导出 JSON 中的 Workflow 名称，而没有同步修改节点的 `workflow_name`，依赖关系可能无法匹配；
- 如果名称存在大小写、空格或格式差异，是否能匹配取决于当前代码路径的具体处理方式。

## 结论

Workflow 编辑器能够在修改依赖 Workflow 名称后自动更新已使用节点，是因为元数据应用逻辑显式保存了依赖的旧名称，并用它查找所有引用节点，然后批量更新这些节点的：

- `workflow_name`；
- `name`；
- `input_ports`；
- `output_ports`。

因此，当前行为可以概括为：

```text
用旧名称定位依赖使用者
→ 将引用迁移到新名称
→ 同步节点显示名称和接口
```
