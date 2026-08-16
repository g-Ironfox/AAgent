# 2026-08-16 Workflow 前端连接交互审查报告

> 日期:2026-08-16。
> 类型:审计报告。
> 性质:历史快照。
> 范围:`webui_py/static/workflow.js`、`webui_py/static/workflow/{model,view,connections}.js`、`webui_py/static/workflow.html`、`webui_py/static/css/workflow/{layout,canvas,inspector}.css`、`docs/11-Workflow设计规范.md` 的 Workflow 前端编辑器。
> 说明:对 Workflow 前端编辑器做独立静态审查(正确性/扩展性/优雅性三维度);审查中发现并修复 1 项 P1(输出端新建连接反向存储)、1 项 P2(分支删除过滤条件过宽)与 2 处文档语义不一致;未做浏览器实测,验证边界见第 4 节。

## 1. 结论

有条件通过。核心交互(数据流扇出、输入端拖拽改接/删除、控制流单端移动、拖到不兼容端点恢复)与用户确认的语义一致,端口模型与文档契约对齐;审查中发现并修复 1 项 P1 数据模型缺陷、1 项 P2 过滤条件缺陷与 2 处文档语义不一致,遗留若干 P3/P4(见第 3 节),不影响主流程。本次未做浏览器实测。

## 2. 已核验

1. **端口模型**:连接始终携带 `fromPortId/toPortId`,端点通过 `dataset` 定位,不依赖 CSS 类名、节点类型或端口顺序(符合规范 §2.3/§6.3);
2. **数据流扇出**:`content-out` 为 `multiple:true`,从输出端拖拽固定输出端、每次新建连接;输入端 `multiple:false`,从输入端拖拽时输出端不变、输入端跟随鼠标;
3. **控制流单连接**:拖输入端移动输入端、拖输出端移动输出端,另一端保持不变;无连接时从被拖端新建;
4. **兼容性**:`compatiblePort` 校验端口类型、方向与自节点排除;拖到不兼容端点只恢复原连接,不产生副作用;
5. **拖拽生命周期**:`pointercancel` 已与 `pointerup` 分离,系统取消只恢复连接不提交/不删除;正常结束与取消均释放 pointer capture;
6. **连接 ID**:使用「时间戳 + 递增序列」,避免同一毫秒连续创建连接的 ID 碰撞;
7. **选择器安全**:`portCenter` 改为 `dataset` 精确比较,不把草稿数据拼接进 `querySelector`,消除非法选择器/注入风险;
8. **删除行为**:`deleteNode` 按 `fromId/toId` 清理;分支删除按 `fromId + fromPortId` 双条件清理(修复后,与规范 §8.6 一致);
9. **锚点方向(修复后)**:六种起点状态(数据流输出扇出、数据流输入有/无连接、控制流输出有/无连接、控制流输入有/无连接)逐案推导,新建/改接连接的 from→to 方向全部正确;
10. **文档一致性(修复后)**:§8.4/§8.5 数据流输入端拖拽落点语义与用户确认语义及实现一致;接口契约、端口标签与端点 DOM 数据属性在 Input/LLM 上一致(Router 分支除外,见 P3)。

## 3. 问题清单

| 级别 | 问题 | 说明与建议 |
| --- | --- | --- |
| P1 | 输出端新建连接反向存储 | 从输出端(数据流扇出、空控制流输出)拖拽新建时,`anchorDirection` 被算成 `input`,连接以「输入→输出」反向写入。视觉正常但后续从目标输入端拖拽找不到该连接(incoming 按 toId 查),会重复建线且删除/改接失效。已修复为无连接时 `anchorDirection = direction`(已修复,见[修复记录](../日志/2026-08-16-webui-workflow连接交互-修复记录.md)第 1 节) |
| P2 | 删除分支过滤条件过宽 | 原按 `fromPortId` 单独过滤,端口 ID 为节点内作用域,理论上可误删其他 Router 同名分支端口的连接。已改为 `fromId + fromPortId` 双条件(已修复,与规范 §8.6 一致) |
| P2 | 文档输入端拖拽落点语义不一致 | 规范 §8.4/§8.5 写「拖到兼容输出端/目标输出端」,与「输出端不变、输入端跟随」矛盾。已改为「兼容输入端/目标输入端」(已修复) |
| P3 | Router 接口契约与动态分支标签不一致 | 契约区静态写死「分支名称」,画布分支端点显示实际分支名(分支 1/分支 2),违反规范 §4.5「契约 label 与 data-port-label 一致」。建议 `renderInspector` 由 `nodePorts(node)` 动态渲染契约,顺带满足 §10 扩展性 |
| P3 | 节点/分支 ID 使用 `Date.now()` | `model.js` 节点 ID 与 `view.js` 分支 ID 同毫秒连续创建可能碰撞,与已修复的连接 ID 同类。建议在 `model.js` 提供共享 `nextId(prefix)` 递增序列 |
| P4 | 初始连接计数文本不符 | `workflow.html` 初始「2 条连接」与初始模型 3 条不符,首次渲染即被 JS 覆盖,仅视觉问题 |
| P4 | 画布不支持纵向滚动 | `.workflow-canvas { overflow-y:hidden }`,节点纵向超出画布高度时无法滚动查看 |
| P4 | 拖输入端释放到节点 body 会删除连接 | 释放点非端口即按「空白」处理删除连接,落在节点 body 上也可能误删;如需要可区分空白画布与节点体 |
| P4 | 草稿连接不做端点校验 | `loadDraft` 不校验连接端点有效性,脏草稿中的无效连接静默跳过渲染但仍计入连接计数 |

## 4. 验证方式

- 静态证据:VS Code 对全部改动文件诊断零错误;锚点方向六种起点状态逐案推导;文档与实现语义逐行核对;连接 ID、pointer capture、选择器注入点均已复查;
- 未验证:浏览器端手工交互(输出端新建/扇出、输入端改接/删除、控制流改接、pointercancel 系统取消、多 Router 分支同名端口共存)未实测;`node --check` 在会话中被取消,未取得输出。

## 5. 涉及文件

- `webui_py/static/workflow.js`、`webui_py/static/workflow/model.js`、`webui_py/static/workflow/view.js`、`webui_py/static/workflow/connections.js`;
- `webui_py/static/workflow.html`、`webui_py/static/css/workflow/layout.css`、`canvas.css`、`inspector.css`;
- `docs/11-Workflow设计规范.md`;
- 实现细节见 [修复记录](../日志/2026-08-16-webui-workflow连接交互-修复记录.md)。

## 6. 建议

- 浏览器实测第 4 节列出的交互项,重点覆盖输出端扇出与输入端删除/改接的完整闭环;
- Router 接口契约改为由 `nodePorts(node)` 动态渲染,消除静态契约与动态分支的漂移;
- 节点/分支 ID 统一走 `model.js` 的 `nextId(prefix)` 序列,消除同毫秒碰撞;
- 画布补纵向滚动,并评估「拖到节点 body 是否删除」的误删风险;
- 落地规范 §9 的 `validateWorkflow` 纯函数与表驱动测试,把六种起点状态固化为可回归用例。

## 7. 关联文档

- 设计规范:[11-Workflow设计规范.md](../11-Workflow设计规范.md);
- 修复记录:[2026-08-16 WebUI Workflow 前端连接交互修复记录](../日志/2026-08-16-webui-workflow连接交互-修复记录.md);
- 权威清单:[审查日志 README](README.md)。
