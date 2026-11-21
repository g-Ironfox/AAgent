# ALFWorld Recovery-Scope Experiment

This package specifies the first controlled experiment for *Hard Paired or Agentic Rollback? Recovery Scope in Self-Evolving Agents*. It isolates recovery scope at a fixed checkpoint. It is an experiment scaffold, not a claim that the current ALFWorld agent bundle already implements both policies end to end.

## Question

After the same injected evolution defect, does restoring workflow and guidance together reduce residual harm enough to justify losing beneficial changes, compared with an agent selecting a component-level recovery scope?

## Arms

| Arm | Recovery action | Checkpoint target | Expected trade-off |
| --- | --- | --- | --- |
| `hard-paired` | Restore the checkpointed workspace state containing both the task workflow and adopted experience/guidance. No component selection. | A fixed checkpoint immediately before the injected evolution interval. | Lower residual contamination; may discard a useful change made in the same interval. |
| `agentic-granular` | Given the same evidence and fixed target checkpoint, retain or restore workflow and guidance independently. Record the selected scope and rationale. | Same checkpoint as hard-paired. | Can retain useful progress; may leave contaminated descendants or create an incompatible pair. |
| `oracle-selective` (diagnostic) | Restore components labelled as contaminated, including declared descendants. | Same checkpoint as primary arms. | Estimates selective-recovery ceiling, not a deployable policy. |

Do not compare different checkpoints in this first experiment. Run the checkpoint-depth study separately after the scope comparison.

## Controlled ALFWorld Protocol

1. Use `valid_seen` for development and freeze prompts, model ID, workflow, action limit, and injection templates before evaluation. Use `valid_unseen` only for the held-out report.
2. Use the same ordered episode IDs, seed, model settings, initial workflow, initial guidance, evolution opportunities, and failure trigger in every arm. The ALFWorld runner's split selection is seeded, but verify the saved manifest and episode IDs are identical across arms.
3. Make a baseline checkpoint, then create a paired beneficial-plus-harmful evolution interval. Examples: add a valid search heuristic while also adding a mistaken rule; rewrite a condition-bearing rule so a descendant overgeneralizes it; or change a workflow and guidance with a declared version dependency.
4. Freeze the post-evolution workspace as the shared failed state. Clone/replay that exact state for each arm; never let one arm's recovery or learning alter another arm's starting state.
5. Present equal failure evidence and recovery token/tool/time budgets. In the primary comparison the checkpoint is fixed. The granular agent may select any subset, including the full pair; hard-paired must restore both components.
6. After recovery, run the same held-out continuation tasks. Disable cross-arm shared experience stores. Keep the original environment task-world state and evaluation protocol common to both conditions.
7. Record task outcomes and recovery traces outside the workspace being restored. The workspace checkpoint restore replaces the whole workspace, including its files and permissions.

Recommended first sweep: three defect families (local workflow bug, mistaken guidance with a descendant, and workflow-guidance version mismatch), two evidence levels (precise and ambiguous), and at least 3 paired seeds per cell for a pilot. Treat this as a debugging pilot, not a powered result. Determine the confirmatory sample size from pilot variance and a preregistered minimum effect.

## System Setup

Use the existing ALFWorld Docker profile and workflow bundle. From repository root:

```powershell
docker compose --profile benchmark build benchmark_worker benchmark_webui
docker compose --profile benchmark run --rm --no-deps benchmark_worker download
docker compose --profile benchmark run --rm --no-deps benchmark_worker smoke
python experiments/alfworld-recovery-scope/build_evolving_iterator.py --output experiments/alfworld-recovery-scope/evolving-workflows --model <model-id> --prefix alfworld-evolving
```

Bound workflow copies must not be overwritten with raw templates: doing so resets model/file IDs and child-workflow names. The default generator rejects binding resets, but remains experience-only. For this experimental bundle, generate into a fresh directory, install under a fresh prefix, or use the binding-preserving `--from-bundle` upgrade described below. Do not force-reset a deployed bundle.

The generated bundle is the task/experience substrate. Bind the `decide_action` and experience-review model placeholders to the same enabled model ID for all arms. Install each arm under a unique workspace prefix; do not overwrite an existing prefix. Keep the generated workflow files identical across arms before the injected evolution event.

Run episodes with the existing runner, pointing `--workflow-file-id` at the installed bundle's bootstrap workflow ID:

```powershell
docker compose --profile benchmark run --rm --no-deps --entrypoint python `
  -v ./data/alfworld/results:/results benchmark_worker `
  -m alfworld_runner.main run --workflow-file-id <bootstrap-file-id> `
  --split valid_unseen --episodes <N> --seed 42 --max-steps 50
```

Use separate `--prefix` values and isolated workspaces per arm. Store runner outputs and the experiment ledger outside the workspace so a restore cannot erase evidence. Record the installed file IDs, checkpoint sequence, model ID, Docker image digest, runner arguments, and exact episode IDs in the ledger.

## Episode record format

The experimental ALFWorld bundle writes an `alfworld-episode/v2` JSON episode record. `events` is an array of objects: observation events keep the original observation JSON, and turn events keep only the new action, reasoning, and recovery-attempt metadata. Cumulative chat history stays in runtime context and is not copied into every event or passed back as an audit trajectory. Final iterator status is stored in `summary.iterator_status`; the old JSON-string `task_record` wrapper is no longer used.

Checkpoint IDs and workspace metadata remain in the record. Full workspace diffs can be queried by checkpoint rather than embedded in the episode file: embedding a diff of the episode file itself would copy the log back into its own contents. Consumers of the old format must read `summary` for execution status and checkpoint fields, and read the nested object fields and `events` directly. Regenerating these templates does not migrate existing records or update installed/running workflow copies; install a new isolated prefix before a new run.

## Main-workflow evolution iterator

The local `workflows/alfworld-agent-iterator.flow` is now the **experimental main + experience iterator**, not the default experience-only iterator. Its public input remains `record: content`, so the existing bootstrap can invoke it unchanged.

Execution order:

1. Read old experience, summarize the episode and persist the updated experience using its revision. This commit completes before any main-evolution work.
2. Read the current main (including its revision) and the separately bound **workflow reference Markdown** using a fixed `workspace.get_file` node, then ask an LLM for a complete candidate workflow. The reference contains the current runtime node declarations, per-type structural schemas, dynamic port examples, exact semantic-validation excerpts, the experiment-local `workflow-json-runtime` skill checked against the implementation, and experiment-local design notes. Its contents are added to the design system message at runtime, **not inlined in the `.flow`**. The old repository skill is excluded from the reference; current runtime contracts define the language; the fixed capability policy further restricts main changes. The shared `skills/` files are not modified. The reference is distinct from writable ALFWorld experience. Current main, experience, and the episode record remain input data. The design LLM has no tools. Missing/unreadable reference aborts evolution before proposing or writing; there is no silent schema-free fallback.
3. Fixed tool `workspace.prepare_main_update` re-reads main under the caller's normal ACL, rejects stale revisions, validates Workflow 2.0, compiles the graph, and checks capability boundaries. This tool does not execute or save the candidate.
4. For a changed, accepted candidate, create `before main evolution` checkpoint, then use `workspace.update_file` with the checked revision to write **only the bound main file**. A concurrent edit after validation is still protected by the update's revision check. Rejected/unchanged candidates cause no main write or evolution checkpoint.
5. Return the saved experience and main-evolution result. Rejected/unchanged proposals leave main untouched. A tool/model/checkpoint/write exception in evolution fails the iterator and is reported by bootstrap, while the experience already saved in step 1 remains committed. If the experience summary/write fails, evolution is not attempted. These are sequential commits; there is no automatic rollback of the saved experience when evolution fails.

There is one main proposal per episode, not an unbounded repair loop. `unchanged` or `rejected` means that episode did not change main; inspect `main_status` and `main_error` rather than assuming every episode must evolve it.

The model can change prompts, pure data processing, functions and control flow, not just append experience. The validator preserves root input/output ports, concrete model bindings, tool declarations, and the complete data dependency chain of the bound experience reader. It rejects new workspace tools, LLM tool calling, terminal I/O, sessions, and subprocesses. It cannot edit stable-main, bootstrap, iterator, permissions or audit files through the candidate. **Static validation is not behavioral evaluation:** a valid candidate may still perform poorly or fail at runtime, and the existing main-version recovery remains the fallback.

Iterator outputs are `experience`, `main_status` (`updated`, `unchanged`, `rejected`), `main_error`, `main_before_revision`, `main_after_revision`, and `main_checkpoint` (0 when no evolution checkpoint was created). Bootstrap retains these in its existing `iterator_result`; it does not copy the generated workflow into each event.


### 独立节点参考 Markdown（低读、高写）

- 源文档：[workflow-node-reference.md](workflow-node-reference.md)。可上传副本：`workflows/alfworld-agent-workflow-reference.md`。二者由同一个实验内生成器生成，不改仓库公共 skill。
- 当前包含 **40 种运行时节点**的允许参数、schema 引用、声明样例、控制端口、数据连线类型和动态端口变体，并附完整 Workflow 2.0 schema 及实际语义校验源码摘录。Schema 不覆盖的语义检查明确单列，不把 `{}` 假装成完整参数约束。
- 权限：文件 `required.read = 1`、`required.write = 4`；文档不执行代码，`runtime.read/write = 0`。main 和 iterator 都能读；iterator 的 write=3 不能改文档。参考文档列出全部节点不代表 main 获准使用全部节点。
- 读取链路：固定 `evolution_read_reference_file_id` → `workspace.get_file` → 解析 `content` → 设计 system message。不是让模型自己猜文件名，也不是把资料反复转义塞回 `.flow`。
- 更新：高权限维护者更新同一工作区文档后，下轮 iterator 会读到新内容，不必为更新资料重写 `.flow`。本地源码/skill 变更后运行以下命令重新生成；不会自动发布到工作区。

```powershell
python experiments/alfworld-recovery-scope/build_workflow_reference.py
python experiments/alfworld-recovery-scope/build_evolving_iterator.py --from-bundle experiments/alfworld-recovery-scope/workflows
```

权限 JSON 只是安装/配置清单，不是上传 Markdown 就自动生效的权限声明。手动上传时必须在工作区实际设置 ACL。

### Generate, install, and test

Runtime support was added in `agent/workflow_evolution.py` and registered as `workspace.prepare_main_update` in `agent/tools/workspace.py`. Restart/rebuild the agent with these files **before running the new iterator**. Merely importing a `.flow` does not register a tool. For the standard Docker deployment, `docker compose up -d --build agent` rebuilds this service; plan the restart around any active tasks. With the development override, the container starts `sleep infinity` and the scheduler is launched manually; restarting that container alone does not start `python main.py`. Check the live tool registry for `workspace.prepare_main_update` before treating the iterator as ready. This repository change does not by itself replace already installed workspace files or restart services.

Install a **fresh isolated prefix** (six files, including the reference; all main/experience/recovery/reference IDs are bound automatically):

```powershell
python experiments/alfworld-recovery-scope/build_evolving_iterator.py --model <enabled-model-id> --prefix alfworld-evolving --install
```

To regenerate only the iterator and its local ACL in an already bound local bundle, preserving its model, main ID, experience ID and child-workflow prefix:

```powershell
python experiments/alfworld-recovery-scope/build_evolving_iterator.py --from-bundle experiments/alfworld-recovery-scope/workflows
```

This local upgrade refreshes the reference Markdown, iterator and permission manifest. Add `--refresh-recording` to upgrade the local bootstrap record serializers as well; main, stable-main, experience and dependency IDs remain untouched. It does not deploy anything. If no reference binding existed, the generated iterator contains `REPLACE_WITH_WORKFLOW_REFERENCE_FILE_ID`: **do not run it yet**. Upload the standalone `workflows/alfworld-agent-workflow-reference.md`, set its actual workspace ACL to required read=1/write=4, obtain its file ID, then bind it:

```powershell
python experiments/alfworld-recovery-scope/build_evolving_iterator.py --from-bundle experiments/alfworld-recovery-scope/workflows --reference-id <uploaded-reference-file-id>
```

Re-upload/update the iterator with revision checking. Later upgrades preserve the existing reference ID unless explicitly replaced. A fresh `--install` performs reference creation and binding automatically. Do not use the default experience-only bundle generator to regenerate this experimental iterator.

```powershell
python -m unittest discover -s experiments/alfworld-recovery-scope -p "test_*.py" -v
python -m unittest discover -s agent -p test_workspace_tools.py -v
```

Tests use real workflow parsing/scheduling and workspace ACL/revision handling with an in-memory store and mocked LLM. They include an actual graph-node insertion, its adoption and use in the next episode, runtime reference/skill delivery, all runtime node schemas and declaration samples, compiled complete skill examples, obsolete-node rejection, saved experience after missing-tool/model failures, low-read/high-write reference ACLs, missing-reference fail-closed behavior, invalid/no-op proposals, concurrent edits and checkpoint failure. They are not a claim of improved ALFWorld task success.


### 记录 v2 与权限校验（本地修复）

`experiment_recording.py` 在实验版 bootstrap 的持久化边界生成 `alfworld-episode/v2`。示例结构：

```json
{
  "format": "alfworld-episode/v2",
  "summary": {"status": "completed", "error": "", "checkpoint_before": 1, "checkpoint_after": 2, "iterator_status": "completed"},
  "task": {"type": "observation", "step": 0},
  "result": {"type": "observation", "done": true, "success": true},
  "events": [
    {"type": "observation", "observation": {"type": "observation", "step": 0}},
    {"type": "turn", "step": 0, "action": "look", "reasoning": "...", "attempts": []}
  ],
  "workspace_before": {"items": [], "revision": 1},
  "workspace_after": {"items": [], "revision": 2},
  "iterator_result": {"experience": "...", "main_status": "unchanged"}
}
```

`task`、`result`、观察、工作区清单和 iterator 结果直接嵌套为 JSON 对象；action/reasoning/error/experience 保留普通字符串。事件只存新增信息，不包含累计 history 或完整主流程结果。正常文本中的引号、换行、Windows 路径仍需标准 JSON 转义；没有全局去反斜杠操作。初始/中间记录可能没有最终字段。旧日志不自动改写；消费端一次 `json.loads` 后读 `summary.status`、`summary.checkpoint_before` 等。

`experiment_permissions.py` 在生成/升级时检查跨文件 ACL：iterator 的 `runtime.write=3` 满足 main 的 `required.write=3`（比较是 `>=`），而参考文档、stable、bootstrap、iterator 的 `required.write=4` 阻止迭代器改写。不能用降低 main 保护或把 iterator 一律升到 4 来修。若目标权限配置无法同时满足两组约束，生成直接报错。

本地更新命令（不触碰线上工作区）：

```powershell
python experiments/alfworld-recovery-scope/build_evolving_iterator.py --from-bundle experiments/alfworld-recovery-scope/workflows --refresh-recording
```

`.flow` 不携带工作区文件权限，上传内容并不更新文件 ACL；使用实验 installer 会应用清单，手动部署必须同时更新实际 ACL。已运行进程保存的是启动时的权限快照。此次本地修复不替换线上回退后的文件，也不自动修改旧日志或重启进程。

## Permissions

`permissions-hard-paired.json` and `permissions-agentic-granular.json` describe the per-file ACLs for the six-file experimental ALFWorld bundle. `runtime` controls the process launched from a file; `required` controls other processes' access to that file. Checkpoint permissions are capabilities of the process, not ACLs on the file.

The experiment-specific iterator now proposes and validates main-workflow changes as well as updating experience. Its write level is 3 (main requires 3, while iterator/stable/bootstrap require 4), and it can create but not restore checkpoints. The default generator in scripts/build_alfworld_bundle.py remains experience-only; use the experimental builder above for evolution. The bootstrap currently has whole-workspace restore capability in the hard-paired ACL and no restore capability in the granular ACL. The existing bootstrap's automatic recovery path, however, restores main-workflow versions only; it does not yet invoke whole-workspace restore or ask an agent to choose workflow-versus-guidance scope. Therefore these ACLs are an experimental boundary/configuration, not by themselves an implementation of the two recovery policies. For a valid policy comparison, implement/enable the policy-specific recovery controller before collecting results and verify the trace shows the required action. Do not treat a no-op permission difference as a treatment.

## Outcomes

For each recovery event and continuation window, record:

- `residual_harm`: whether the injected defect or any labelled descendant remains active or recurs.
- `compatibility`: whether the retained workflow/guidance versions satisfy the declared dependency and execute without recovery-induced errors.
- `useful_retention`: independent held-out reward attributable to the beneficial change, compared with its pre-change baseline.
- `task_success_rate` and `mean_score`: environment `success`/`score`, never workflow status alone.
- `recurrence_rate`: whether the same defect reappears in later tasks or evolution rounds.
- `recovery_cost`: recovery tokens, model calls, tool calls, wall time, and validation calls.
- `time_to_baseline`: continuation tasks or time until performance returns to pre-failure level.
- `selected_scope`, `checkpoint_seq`, `evidence_level`, `dependency_edges`, and all component revisions before/after.

Report residual harm, useful retention, compatibility, and cost separately before reporting aggregate reward. Estimate `p`, `g`, `h`, and `Delta c` from labelled events as defined in the paper; include uncertainty intervals. Keep oracle-selective diagnostic results separate from the primary comparison.

## Implementation Gap

The current workflow-permission-workspace stack supports workspace checkpoint restore and file-level revision recovery, but the shipped ALFWorld bootstrap only attempts main-workflow revisions before the stable workflow. A faithful implementation of this experiment needs a policy controller that (a) records the paired workflow/guidance state at the fixed checkpoint, (b) replays a common post-evolution state, (c) dispatches hard-paired whole-workspace restore versus agent-selected component restore, and (d) writes the audit record outside the restored workspace. Do not claim the paper's primary comparison is runnable until those four properties are covered by integration tests.

### Implementation-aligned design skill

`workflow-json-runtime/SKILL.md` replaces the old repository skill in the generated reference. The old skill still describes removed terminal nodes and is not included. The generated catalog, schema, validator/compiler excerpts and execution semantics come from the current code. Complete skill examples are validated and compiled during generation and tests. Source fingerprints cover the actual implementation and the experiment-local skill; shared `skills/` content is unchanged.

Experience is saved before main evolution. A missing validation tool or a later evolution failure is still reported as failure, while the saved summary remains. Loading the Python tool into the running scheduler remains a separate deployment step.

### Tool contracts and live verification

The reference also extracts all workspace tool JSON Schemas from the implemented
`@tool` decorators, with the actual registry/dispatcher and workspace wrapper
source excerpts. Reading decorator AST avoids Redis registration side effects.

Run `python -m unittest discover -s experiments/alfworld-recovery-scope -p test_runtime_tools.py -v`
to verify the real decorator, callable lookup, typed node dispatch, HTTP wrapper
and candidate validator. Only HTTP and Redis are substituted; this complements
the workflow tests that intercept tool execution.

Run `python experiments/alfworld-recovery-scope/verify_runtime_tools.py --prefix alfworld-hard-paired`
to verify the loaded scheduler. It creates and removes one temporary read-only
workflow and expects unchanged/ready/rejected, without LLM calls or candidate
writes. It checks main/stable/experience/iterator/bootstrap revisions, content
and permissions are unchanged. `--include-recovery` additionally verifies the
current/stable recovery plan with bootstrap read access and checkpoint_seq=0;
it does not exercise historical checkpoint traversal. Use a fresh `--report-dir`
when retaining evidence from several runs. These probes create workspace file
audit events even though protected files are preserved.
