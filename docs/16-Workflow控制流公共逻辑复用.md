# Workflow 控制流公共逻辑复用

## 1. 背景

Workflow 的控制流采用同步架构：单个 Worker 按事件顺序处理节点，当前节点完成后，由它显式发布下一个控制事件。

在这个模型中，不同控制路径可以指向同一个后续节点。例如 Router 的多个分支在完成各自的分支逻辑后，都继续进入同一个公共节点：

```text
             ┌──> 分支 A ──┐
Router ──────┤              ├──> 公共逻辑
             └──> 分支 B ──┘
```

因此，一个节点拥有多个 `control_predecessors` 是合理且必要的。

## 2. 核心结论

`control_predecessors` 表示：

> 所有可能把控制权交给当前节点的上游节点集合。

它表达的是**控制路径对公共逻辑的复用关系**，不表达：

- 等待多个前驱；
- OR Join；
- AND Join；
- 并行汇合；
- 前驱计数；
- 本次运行需要收集的完成信号。

多个前驱只说明图结构中存在多个可能的进入方向。一次同步运行中，实际只有被上游控制逻辑选中的路径会继续发布事件，因此公共节点仍然按正常顺序执行一次。

## 3. 与 Router 的关系

Router 每次运行只选择一个分支：

```text
Router
  ├── branch-a -> Prepare
  └── branch-b -> Prepare
```

此时 `Prepare` 的解析结果可以是：

```json
{
  "control_predecessors": [1, 2],
  "control_successors": [4]
}
```

这里的 `[1, 2]` 表示 `Prepare` 既可以由 `branch-a` 对应的节点进入，也可以由 `branch-b` 对应的节点进入。它不表示 `Prepare` 必须等节点 `1` 和节点 `2` 都完成。

由于 Router 的一次运行只会选择一个分支，实际执行路径仍然是单线的：

```text
Router -> branch-a -> Prepare
```

或：

```text
Router -> branch-b -> Prepare
```

## 4. 与 foreach 的关系

`foreach` 也可能拥有多个控制入口：

- `control-in`：普通进入循环节点；
- `loop-in`：循环体完成后的再次进入。

这两个端口都把控制权交给同一个 `foreach` 节点，但它们不是两个并行来源，也不要求同时满足。它们只是表示不同控制路径复用同一段 foreach 处理逻辑。

循环进度由运行时的列表状态维护，而不是通过统计控制前驱数量维护。

## 5. Parser 契约

解析器为每个节点创建：

```json
{
  "control_predecessors": [],
  "control_successors": [],
  "control_inputs": {},
  "control_outputs": {}
}
```

处理控制连接时：

```python
_append_unique(linked_nodes[from_index]["control_successors"], to_index)
_append_unique(linked_nodes[to_index]["control_predecessors"], from_index)
```

其中：

- `control_predecessors` 是节点级的可能前驱集合；
- `control_successors` 是节点级的可能后继集合；
- `control_inputs` 保留目标控制端口和来源端点的详细映射；
- `control_outputs` 保留来源控制端口和目标端点的详细映射。

`_append_unique` 只负责避免同一个节点关系在集合中重复出现，不限制一个节点拥有多个不同前驱。

控制输出端口仍然遵守端口级约束：同一个输出端口不能绑定多个后继。Router 可以拥有多个分支输出，但每个分支端口各自最多绑定一个后继。

## 6. Worker 执行契约

运行时由当前节点显式发布控制输出：

```python
publish_workflow_control_output(workflow_map, node)
```

或者由 Router 根据选中的分支直接发布目标节点：

```python
publish_workflow_node(
    workflow_map,
    [control_successors_id, 'control-in'],
)
```

Worker 不读取 `control_predecessors` 来等待或聚合事件。`control_predecessors` 是解析后的图结构信息，不是运行时同步屏障。

## 7. 禁止的误读

以下解释都不符合当前 Workflow 架构：

```text
多个前驱 -> 等待所有前驱 -> 执行当前节点
```

```text
多个前驱 -> 运行时 OR Join 节点
```

```text
多个前驱 -> 并发分支完成后合并
```

正确解释是：

```text
多个上游路径 -> 复用同一个公共后续节点
```

## 8. 设计原则

1. 控制流表示执行顺序，不表示同步屏障。
2. 一个节点可以拥有多个可能的控制前驱。
3. 多前驱的主要用途是复用公共逻辑。
4. Router 的分支选择保证一次运行只沿一条控制路径继续。
5. `foreach` 的不同控制入口复用同一段节点处理逻辑。
6. 不通过前驱数量推断运行时行为。
7. 不为普通公共节点增加 OR/AND Join 语义。
8. 如果未来确实需要并行、等待或合并，必须作为全新的执行模型和节点语义单独设计，不能改变当前控制流字段的含义。

## 9. 一句话定义

> `control_predecessors` 记录的是“哪些控制路径可以进入我”，而不是“我需要等哪些节点完成”；在同步 Workflow 中，多前驱的核心价值是复用公共逻辑。
