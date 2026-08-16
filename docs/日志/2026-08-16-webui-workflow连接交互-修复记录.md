# 2026-08-16 WebUI Workflow 前端连接交互修复记录

> 日期:2026-08-16。
> 类型:修复记录。
> 性质:历史快照(记录本次审查触发的缺陷修复过程,当前行为以源码为准)。
> 范围:`webui_py/static/workflow/connections.js`、`webui_py/static/workflow/view.js`、`docs/11-Workflow设计规范.md`。
> 说明:按审计流程对 Workflow 前端编辑器做独立静态审查,审查中发现并修复 1 项 P1(输出端新建连接反向存储)、1 项 P2(分支删除过滤条件过宽)与 2 处文档语义不一致;完整结论见 [审查报告](../审查日志/2026-08-16-webui-workflow连接交互-审查报告.md)。

## 1. 修复 1:输出端新建连接反向存储(P1)

**现象**:从输出端新建连接后,连接以「输入 → 输出」反向写入数据模型。视觉上连线方向对称看不出问题,但后续从该连接的目标输入端拖拽时,`incoming` 按 `toId === node.id && toPortId === portId` 查找不到(该连接实际把目标输入端存在 `fromId/fromPortId`),于是被当作空输入端,再次拖拽会创建一条新的正确连接,导致同一输入端出现两条重叠线,且原反向连接的删除/改接全部失效。

**根因**:`bindConnectionPort` 计算 `anchorDirection` 时,无连接分支写成了 `direction === 'output' ? 'input' : direction`。当从输出端拖拽且端口尚无连接(数据流输出扇出、空控制流输出)时,锚点就是被拖的输出端,锚点方向应为 `'output'`,却被算成 `'input'`。`finishConnectionDrag` 的 else 分支按 `anchorDirection` 决定 from/to,于是把 `target(输入)` 当 from、`anchor(输出)` 当 to,连接被反向写入。

**修复**:无连接分支的 `anchorDirection` 直接取 `direction`(锚点即被拖端口):

```js
const anchorDirection = hasContentInputConnection || (hasControlConnection && direction === 'input')
  ? 'output'
  : hasControlConnection && direction === 'output'
    ? 'input'
    : direction;
```

修复后六种起点状态逐案推导均得到正确的 from→to 方向:

| 起点 | 锚点 | anchorDirection | 落点方向 | 结果 |
| --- | --- | --- | --- | --- |
| 数据流输出(无/有连接) | 被拖输出端 | output | input | 新建扇出,输出端固定 |
| 数据流输入(有连接) | 原输出端 | output | input | 输入端改接,输出端不变 |
| 数据流输入(无连接) | 被拖输入端 | input | output | 新建连接 |
| 控制流输出(有连接) | 原输入端 | input | output | 输出端改接 |
| 控制流输出(无连接) | 被拖输出端 | output | input | 新建连接 |
| 控制流输入(有/无连接) | 原输出端/被拖输入端 | output/input | input/output | 改接或新建 |

## 2. 修复 2:删除分支过滤条件过宽(P2)

**现象**:删除 Router 分支时,连接清理只按 `connection.fromPortId !== removed.id` 过滤,没有同时限定 `fromId === node.id`。端口 ID 的作用域是节点内部(见设计规范 §2.3),仅按端口 ID 过滤理论上可能误删其他 Router 节点上同名分支端口的连接。

**修复**:改为按节点 + 端口双条件过滤,与设计规范 §8.6 删除端口的写法一致:

```js
state.connections = state.connections.filter((connection) => !(connection.fromId === node.id && connection.fromPortId === removed.id));
```

## 3. 修复 3:文档语义与实现不一致(P2)

**现象**:设计规范 §8.4 与 §8.5 中,数据流「已连接输入端」拖拽的落点写为「兼容输出端 / 目标输出端」,与用户确认的语义「输出端不变、输入端跟着鼠标走」及实现(拖输入端时兼容目标只能是输入端)矛盾。

**修复**:

- §8.4 表格行:「数据流 | 已连接输入端 | 兼容输出端 | 输入端跟随拖拽改接到目标输出端…」→「数据流 | 已连接输入端 | 兼容输入端 | 输入端跟随拖拽改接到目标输入端,原输出端保持不变」;
- §8.5 表格行:「…拖到兼容空端口:输入端跟随拖拽改接到目标输出端」→「…改接到目标输入端」。

## 4. 涉及文件

- `webui_py/static/workflow/connections.js`(锚点方向、连接创建);
- `webui_py/static/workflow/view.js`(分支删除连接清理);
- `docs/11-Workflow设计规范.md`(§8.4 / §8.5 语义修正)。
