# 2026-09-12 WebUI Workflow 管理页只读化审查报告

> 日期:2026-09-12。
> 类型:审查报告。
> 性质:历史快照。
> 范围:提交 `bf6e225`(workflow管理页ui优化)相对 `201e9e4` 的改动,即 `webui_py/static/workflows.html`、`webui_py/static/workflows.js`、`webui_py/static/css/workflows.css`;同时交叉核对 `webui_py/workflows.py` 的元数据契约与 `docs/11-Workflow设计规范.md` §4.5。
> 说明:管理页由"可编辑数据端口与可调用 Workflow"改为"只读展示 + 上传写入";本次为纯静态审查,未修改任何代码,验证边界见第 4 节。
> 待办:未解决问题按领域登记在[权威清单](README.md#权威清单)对应汇总;当前行为以源码为准。

## 1. 结论

有条件通过。只读化方向与 `docs/11-Workflow设计规范.md` §4.5「接口契约只读」一致,契约数据与后端保存校验同源,删除面(旧编辑表单、按钮、样式、事件绑定)无残留;遗留 1 项 P2(两份改动记录文档仍描述已删除的管理页编辑能力)、2 项 P3(依赖契约快照语义、编辑入口无引导)与 4 项 P4,均不影响当前主流程。

## 2. 已核验

1. **只读化与规范一致**:`只读` 徽标、每行仅 `name` + `type`、按 Input/Output 分区、无端口时保留区域并显示"暂无字段",对应规范 §4.5 对接口契约的约束;
2. **数据来源无需新接口**:`GET /api/workflows` 自上一提交起已返回 `workflow_nodes`(含 `name`/`input_ports`/`output_ports`),本次仅消费既有字段,`webui_py/workflows.py` 未改动;
3. **契约即服务端权威**:`PUT /api/workflows/{id}` 校验 workflow 节点端口与 `workflow_nodes` 快照严格相等、未引入的 workflow 节点直接 400,页面展示与运行期约束同源;
4. **删除面干净**:`metadataForm`/`metadataSubmit`/`metadataStatus`/`addInputPort`/`addOutputPort`/`.metadata-save-state`/`.metadata-workflow-*` 在 `webui_py` 内已无引用(同名 ID 仅存在于独立编辑器 `workflow_editor/static/workflow_edit.html`,互不影响);
5. **无死导入**:`updateWorkflowMetadata` 仍由上传流程 `confirmWorkflowUpload` 使用;
6. **样式完整**:新增 class 均在 `css/workflows.css` 有定义,`--green-soft` 等变量来自 `css/base.css`;`.workflow-metadata[hidden]` 规则保留,`hidden` 属性生效;
7. **DOM 安全**:端口与依赖全部经 `createElement` + `textContent` 构造,无 `innerHTML` 拼接,符合规范 §4.4;
8. **空数据路径**:未选中 Workflow 时清空端口/依赖/计数;无依赖时显示"无 Workflow 依赖";依赖项缺 `ports` 时回退 `[]`,与后端 `.get(..., [])` 默认一致;
9. **资源版本**:`workflows.js?v=8 → ?v=11`,与既有缓存策略一致;
10. **响应式补齐**:≤1100px 断点补 `.dependency-contracts` 单列与相邻边框处理,≤700px 断点补新块间距。

## 3. 问题清单

| 级别 | 问题 | 说明与建议 |
| --- | --- | --- |
| P2 | 文档漂移:管理页编辑能力已删除 | `docs/Workflow动态端口改动记录.md` 仍写「Workflow 详情支持编辑 Input 字段和 Output 字段」,并在"涉及文件"标注"管理页字段编辑";`docs/Workflow调用节点改动记录.md` 第 72 行仍写「管理页增加"引入 Workflow 为节点"列表」。建议改述为:管理页只读展示接口契约与依赖,编辑在 `workflow_editor`(导出 JSON → 管理页上传),写入路径只有上传 |
| P3 | 依赖契约是保存时的快照 | `workflow_nodes[*].name/input_ports/output_ports` 为元数据保存时的快照;`PATCH /api/workflows/{id}` 只更新自身 `name`,不回写引用方快照。被引用 Workflow 改名或改端口后本页仍显示旧值,而保存父 Workflow 会因"Workflow 节点端口与元数据契约不一致"失败。建议依赖项加"快照"标记与说明,或提供重新冻结契约的入口 |
| P3 | 编辑入口无引导 | 管理页现在只能"上传(新建)",改端口或依赖需到独立编辑器导出 JSON 再上传,但页面只有"只读"徽标,没有任何指向编辑器的说明。建议在徽标旁补一句提示或链接 |
| P4 | `submitRename` 的 `finally` 无条件解锁 | `finally` 中 `elements.renameSubmit.disabled = false` 绕过 `validateRenameName()`;重命名失败(如列表过期导致的 409 同名)后按钮恢复可点。建议改为调用 `validateRenameName()` |
| P4 | 空态负外边距在小屏溢出 | `.workflow-dependency-list > .metadata-port-empty { margin:-14px }` 与 ≤700px 断点的 `padding:10px` 不匹配,空态白块左右各溢出 4px。建议断点内同步为 `margin:-10px`,或改用 `grid-column:1/-1` 去掉负边距 |
| P4 | 依赖契约标题层级跳级 | `.dependency-contract h5` 的父级标题是 `h3`(Workflow 依赖与契约),跳过 `h4`。建议改为 `h4` |
| P4 | 计数语义模糊 | `dependencyCount` 统计的是"声明的可调用 Workflow 数",同一 Workflow 可被多个画布节点调用、也可能声明后未使用,与画布实际调用节点数不等。建议措辞改为"N 个引入"之类 |

## 4. 验证方式

- 静态证据:`git status` 工作区干净,审查边界为 `bf6e225`(相对 `201e9e4`);通读 `workflows.html`/`workflows.js`/`css/workflows.css` 全文件与提交 diff;交叉核对 `webui_py/workflows.py` 的列表、重命名、元数据、保存四类端点;全文检索确认被删除标识符无残留;`--green-soft` 等变量定位到 `css/base.css`;
- 未验证:浏览器实测(只读面板渲染、空态、700px 断点、依赖契约展示)未跑;未在真实 MongoDB 数据上核对快照陈旧的实际影响,P3 第 1 项为按代码路径推断;
- 附带观察:`webui_py/static/workflow/` 本地为空目录且未被 git 跟踪(编辑器迁出后的残留),可删除,不属于本提交。

## 5. 涉及文件

- `webui_py/static/workflows.html`、`webui_py/static/workflows.js`、`webui_py/static/css/workflows.css`(提交改动);
- 核对:`webui_py/workflows.py`、`webui_py/static/api.js`、`workflow_editor/static/workflow.js`、`workflow_editor/static/workflow/model.js`;
- 文档:`docs/11-Workflow设计规范.md`、`docs/Workflow动态端口改动记录.md`、`docs/Workflow调用节点改动记录.md`。

## 6. 建议

- 先修 P2:同步两份改动记录文档,把"管理页编辑"改述为"管理页只读 + 上传写入";
- 再定 P3:依赖契约面板补"快照"语义说明(低风险);刷新或重新冻结契约的入口是否实现待定;
- P4 四项可在下次触碰该页面时一并清理;
- 有条件时做一次浏览器实测,覆盖只读面板空态与窄屏断点。

## 7. 关联文档

- 设计规范:[11-Workflow设计规范.md](../11-Workflow设计规范.md) §4.5 接口契约;
- 改动记录:[Workflow动态端口改动记录.md](../Workflow动态端口改动记录.md)、[Workflow调用节点改动记录.md](../Workflow调用节点改动记录.md);
- 权威清单:[审查日志 README](README.md);
- 目录登记:[索引.md](索引.md)。
