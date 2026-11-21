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
python scripts/build_alfworld_bundle.py --output experiments/alfworld-recovery-scope/workflows
```

The generated bundle is the task/experience substrate. Bind the `decide_action` and experience-review model placeholders to the same enabled model ID for all arms. Install each arm under a unique workspace prefix; do not overwrite an existing prefix. Keep the generated workflow files identical across arms before the injected evolution event.

Run episodes with the existing runner, pointing `--workflow-file-id` at the installed bundle's bootstrap workflow ID:

```powershell
docker compose --profile benchmark run --rm --no-deps --entrypoint python `
  -v ./data/alfworld/results:/results benchmark_worker `
  -m alfworld_runner.main run --workflow-file-id <bootstrap-file-id> `
  --split valid_unseen --episodes <N> --seed 42 --max-steps 50
```

Use separate `--prefix` values and isolated workspaces per arm. Store runner outputs and the experiment ledger outside the workspace so a restore cannot erase evidence. Record the installed file IDs, checkpoint sequence, model ID, Docker image digest, runner arguments, and exact episode IDs in the ledger.

## Permissions

`permissions-hard-paired.json` and `permissions-agentic-granular.json` describe the per-file ACLs for the five-file ALFWorld bundle. `runtime` controls the process launched from a file; `required` controls other processes' access to that file. Checkpoint permissions are capabilities of the process, not ACLs on the file.

The bundle's existing fixed iterator updates only the experience document; it does not expose arbitrary workflow editing to the model. The bootstrap currently has whole-workspace restore capability in the hard-paired ACL and no restore capability in the granular ACL. The existing bootstrap's automatic recovery path, however, restores main-workflow versions only; it does not yet invoke whole-workspace restore or ask an agent to choose workflow-versus-guidance scope. Therefore these ACLs are an experimental boundary/configuration, not by themselves an implementation of the two recovery policies. For a valid policy comparison, implement/enable the policy-specific recovery controller before collecting results and verify the trace shows the required action. Do not treat a no-op permission difference as a treatment.

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
