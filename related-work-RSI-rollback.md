# Related Work 调研：Append-Only Substrate / Rollback Amnesia

> 面向 AAAI 2027 Workshop (Trust4RSI) 4 页 Position Paper。
> 本文档只收录**与你的问题同题**的工作（自我改进的 agent 在回滚一个失败的自修改时，如何不丢失"为什么失败"的证据）。
> 每篇给出：真实摘要、它解决的问题、与你的 C1/C2/C3 与 F1/F2/F3 的对应、以及你该怎么写它。

---

## ✦ 三个核心结论（如果只看一段）

1. **你必须处理的不是 RIR 那类"单轨迹反思"，而是四篇正面撞车的工作**：`Exo`（受保护机制层保留执行历史 + 治理策略激活，几乎是你 §5 的机制描述）、`Anti-Persistence`（已提出 "separating experience accumulation from abstraction persistence"，即你的双层分离原则）、`EvoUndo`（可恢复性约束自演化）、`ChronoMem`（记忆的语义版本控制 + 回滚，且以"反事实"为回滚成功判据）。
2. **你的核心新意必须从"双层分离"迁移到"回滚算子的作用域语义"**：`scope(revert) ∩ scope(evidence) = ∅`。双层分离已是公共财产，作用域语义才没人形式化。而且 `ChronoMem` 的"反事实回滚"给了你一个**极强的对照**：同一个回滚算子，对世界事实是对的，对自我事实就是 bug——这一条足以撑起全文洞察。
3. **你有两个免费的实证背书，务必用**：`Can Coding Agents Sustain Continual Evolution without Forgetting?` 实测 harness 跨任务演化导致 SWE-Bench 94.0% → 32.0%（你的 F1）；`Masked Erosion` 证明任何以任务成功率为判据的门都会被侵蚀（你的 Sidecar 必须降级为可用性触发器，信任上移到 substrate）。

---

## 0. 先把问题钉死：你的论文到底在解决什么

### 0.1 一句话

> **回滚的作用域（scope）与学习证据的作用域被错误地绑定了。** 当你为了可用性回滚 `s_t` 时，你把"证明这次修改是错的"的证据一起回滚掉了，于是 `Iter` 在下一轮拿到的上下文和失败前**同构**，同一个失败的 `Δ` 会被重新提出。

这不是"agent 不够聪明"，而是**数据模型层面的可观测性问题**：`Iter` 能看到什么，完全由 substrate 的读写规则决定。

### 0.2 形式化重述（比你的 §3 更锐利的一句）

设 `Iter` 近似是一个确定性函数 `Δ = f(L_t, s_t)`。若回滚同时重置 `s_t → s_{t-k}` **且** `L_t → L_{t-k}`，则 `f(L_{t-k}, s_{t-k})` 与上一轮产生失败 `Δ` 时的输入**逐字节相同**，于是 `Δ` 必然被重新采样。Rollback Amnesia 因此不是"倾向"，而是**输入坍缩导致的确定性循环**。这是全文最值得写死的一句话——它把"信任"从心理学问题变成可达性问题（reachability）。

建议论文里显式写出这个不动点论证，一句话即可，但它是你整篇 position paper 的承重墙。

### 0.3 与四类"看起来像但不是"的相邻问题的边界

定位必须靠**否定**来划清，否则 reviewer 会说你只是在做 reflection / memory / version control。

| 相邻问题 | 代表工作 | 它的目标 | 与你的差别（写进 §2 的一句话） |
|---|---|---|---|
| 单条轨迹内的自我纠错 | Reflexion, RIR, Self-Refine | 在**同一个任务**的多轮 trial 内变好 | 不涉及"agent 修改自己的 harness"，也不涉及跨 episode 的状态版本化；且反射文本本身是 lossy abstraction |
| 执行可靠性 / 快照恢复 | AgentGit | 让多 agent 系统可 commit / revert / branch | 只提供**机制**，不规定 revert 的**作用域**；被 revert 掉的工作区就是 agent 下一轮看到的全部 |
| 经验蒸馏 | ExpeL, AWM, Voyager | 从历史任务中抽取可复用知识 | 只**加**不减，没有失败后必须回滚的约束，因此遇不到你的问题 |
| 工作流搜索 | AFlow, ADAS, DGM | 在 `w` 空间里搜更优配置 | 靠**评估信号**做选择；你的设定里没有 ground truth，选择信号本身不可信 |

你的问题集是这四者的**交集之外**：既要有 `w` 的可变性（排除 1），又要有回滚（排除 3），还要在没有可信奖励的情况下决定回滚（排除 4），并且回滚后不能让证据消失（这是全新的）。

### 0.4 你的新意里，哪几条是真的、哪几条已经被占位

**真正可辩护的（建议作为 contribution 主打的顺序）：**

1. **命名并形式化 Rollback Amnesia**，且给出"输入坍缩 → 确定性重采样"的不动点论证。目前检索范围内，这个失败模式没有被作为独立概念提出过（见 §6 的检索结论）。
2. **回滚作用域原则**：`revert_scope(s) ∩ evidence_scope = ∅`。即"回滚算子只允许作用于解释层"。这是**一条可检查的架构不变量**，而不是一个技巧。
3. **不需要分支/合并的论证**：版本控制之所以需要 branch，是因为被否决的工作没有别处可存；若 `L` 已单调保留每个 `Δ` 及其证据，则 branch 退化为"可重放的记录"。这条对 AgentGit / DGM 的对比是干净的、系统味的论点，很契合 Agent OS workshop。
4. **权限分离 + FSM 不变量 I1**（`APPLY` 只能经由带新证据的 `EXECUTE` 到达）。这是可工程化、可审计、可画图的东西。

**已经被部分占位的（必须主动让位，否则会被指控 incremental）：**

- "把事实与解释分开"这个**原则本身**，Anti-Persistence 已经用另一套语言说过：*"separating experience accumulation from abstraction persistence"*。你若把"双层分离"当作核心新意，会被直接打中。
- "保留执行历史 + 治理策略激活"，Exo 已经有了（`a minimal protected mechanism layer preserves execution history and governs policy activation`）。这几乎是你 §5 的机制描述。

**结论：把卖点从"双层分离"移到"回滚算子的作用域语义"上。** 前者是设计模式（已有），后者是可验证的算子性质（尚无人形式化）。下面 §3 的改写稿就是按这个重心写的。

---

## 1. 第一组：同题正面 —— 自我改进 harness 的状态与回滚

### 1.1 Exo: An Architecture for Self-Improving Systems at Runtime ★最需要处理的一篇

- Krentsel, Ratnasamy, Stoica, Casado, Goyal. arXiv:2611.00463, 2026-10-30.
- https://arxiv.org/abs/2611.00463

**摘要（原文）：**
> Agent harnesses govern how language models act in an environment; designing their policies by hand is difficult, while automated techniques require representative datasets and costly executions. We present Exo, an agent runtime architecture for safe learning during ongoing work that collapses the optimization loop into task execution, allowing agents to revise both their harness and their strategies for further improvement. **A minimal protected mechanism layer preserves execution history and governs policy activation while the harness evolves through inspectable code changes.** On long-running objectives in an open-world game, Exo reduces model cost by 12–53% relative to Codex and Pi in standalone runs and 45–82% in transfer runs, while matching task completion rates. Compared with the same starting policy without the ability to edit policy, Exo reduces held-out model cost by 35–61% on AppWorld and SREGym with comparable correctness, cutting AppWorld's mean task time by 13% and SREGym's median diagnosis time by 35%. On Continual Learning Bench coding tasks, model cost including learning falls by 14%, with both policies resolving every issue.

**它解决什么问题：** 在线工作过程中（不停机、不需要代表性数据集）安全地自我改进 harness——把"优化循环"折叠进"任务执行"本身，并用一个受保护的机制层保证执行历史不丢、策略激活受治理。

**与你的关系：** **这是你最直接的竞争工作，也是最能证明你方向正确的工作。** 它已经具备：(a) 可变的 harness（对应你的 `w`）；(b) 受保护的机制层保留执行历史（对应你的 C1）；(c) 策略激活治理（对应你的 C2 的一半）。它没有（或未在摘要层面强调）：把"回滚"作为一个**有明确作用域的算子**来形式化；"回滚后证据必须仍然被 Iter 读到"这一条件；Rollback Amnesia 这个失败模式的命名与分析。

**必须做的动作：** 你不能把它当背景引用，必须**逐点对比**并明确说出二者差异（否则 reviewer 一眼看出你漏引最相关的工作，或指控你 re-invent）。可用的差异点：Exo 的目标函数是 **cost / 效率**，信任是手段；你的目标函数是 **可审计性**，效率不是主张。Exo 的"受保护层"保护的是**机制**（谁能改什么），你保护的是**证据**（改失败之后留下了什么）。这是两个正交的不变量。

**建议的 Related Work 句：**
> Exo keeps a protected mechanism layer that preserves execution history and gates policy activation during runtime harness self-improvement, but its objective is cost reduction rather than auditability, and it does not define the scope of a revert operator: protection is over *what may be edited*, not over *what must survive an undo*.

### 1.2 EvoUndo: Recoverability-Constrained Self-Evolution for LLM Agent Harnesses

- Sah, Sah, Jain, Sah. arXiv:2608.28363 (v2, 2026-09-16).
- https://arxiv.org/abs/2608.28363

**摘要（原文）：**
> LLM agents increasingly modify their own prompts, tools, middleware, resources, and execution harnesses at runtime. Such self-evolution can improve capability, but a successful mutation may leave persistent effects that cannot be safely reversed in states different from the one in which it was created. We introduce EvoUndo, a framework for representing, synthesizing, diagnosing, and independently verifying recoverability of model-generated self-modifications across counterfactual states. Across 600 unseen one-shot self-evolution tasks, we identify 197 capability-improving mutations that fail recoverability verification. Under the original recovery representation, conventional repair strategies recover 0/197 of these natural failures. Deterministic oracle analysis recovers 48/197 under the original recovery language L0, while the extended recovery calculus increases empirical oracle recovery to 191/197. A protocol-locked 2x2 grounding-by-expressivity intervention then separates two bottlenecks: exact state-address grounding increases successful recovery from 0/48 to 38/48 (79.2%) when the original language is sufficient, while extending the recovery language enables recovery on 142/143 (99.3%) failures in the oracle-defined S1 stratum. On the primary gpt-oss-120b backbone, adding exact-address diagnostics to the richer language reduces recovery to 133/143 (93.0%); a Qwen3.8-27B replication preserves the grounding and expressivity effects but not this negative interaction, indicating that the latter is model-dependent. These results indicate that reliable agent self-evolution requires co-designing verification, state grounding, witness semantics, and recovery-language expressivity rather than relying on iterative prompting alone.

**它解决什么问题：** 自修改的**不可逆性**。`w` 被改动后会在"不同于它被创建时的状态"里留下无法安全撤销的持久影响；EvoUndo 提出恢复语言的表达力 + 精确状态寻址 + 独立验证，来判定"这次改动还能不能撤"。

**与你的关系：** 它和你是**同一个问题的两半**，且是绝佳的互补引用：
- 它解决"**能不能撤**"（recoverability of a mutation，事前验证）；
- 你解决"**撤了之后学什么**"（epistemic semantics of a revert，事后学习）。

这是你 Related Work 最有说服力的一句话对比，也是你论文价值最容易被 reviewer 接受的位置：**recoverability ≠ learnability**。一个 mutation 可以完全可恢复，而 agent 依然什么都没学到——因为回滚把证据抹平了。

**注意：** 它明确把"recoverability"当成安全前置条件（pre-conditioned safety），你的 Table 1 原稿写的 "Avoided (by rejection)" 基本正确，但要补上：**它的成功恰恰暴露了你的问题**——197 个"capability-improving 但不可恢复"的 mutation 表明，撤销本身是 agent 自我改进的主要瓶颈，而不是边角情况。

**建议的 Related Work 句：**
> EvoUndo asks whether a mutation *can* be reversed, and shows that most capability-improving mutations fail recoverability verification. We ask the complementary question: given that a mutation is reversed, what does the agent learn from it? Recoverability is a precondition for safety, not for learning.

### 1.3 AgentGit: A Version Control Framework for Reliable and Scalable LLM-Powered Multi-Agent Systems

- Li, Ping, Chen, Qi, Wang, Luo, Zhang. arXiv:2511.00628, 2025-11-01.
- https://arxiv.org/abs/2511.00628

**摘要（原文）：**
> With the rapid progress of large language models (LLMs), LLM-powered multi-agent systems (MAS) are drawing increasing interest across academia and industry. However, many current MAS frameworks struggle with reliability and scalability, especially on complex tasks. We present AgentGit, a framework that brings Git-like rollback and branching to MAS workflows. Built as an infrastructure layer on top of LangGraph, AgentGit supports state commit, revert, and branching, allowing agents to traverse, compare, and explore multiple trajectories efficiently. To evaluate AgentGit, we designed an experiment that optimizes target agents by selecting better prompts. We ran a multi-step A/B test against three baselines — LangGraph, AutoGen, and Agno — on a real-world task: retrieving and analyzing paper abstracts. Results show that AgentGit significantly reduces redundant computation, lowers runtime and token usage, and supports parallel exploration across multiple branches, enhancing both reliability and scalability in MAS development. This work offers a practical path to more robust MAS design and enables error recovery, safe exploration, iterative debugging, and A/B testing in collaborative AI systems.

**它解决什么问题：** 多 agent 系统的**基础设施可靠性**——把 git 语义（commit/revert/branch）加到 LangGraph 上，让开发者能对比、回放、并行探索多条轨迹，减少重复计算。**这是 developer-facing 的工具，不是 self-evolving agent。**

**与你的关系：** 你的 Table 1 原稿说它 "Retained on Failure: Nothing (unless branched)"，**这个说法不严谨、会被打**：git 的 `revert`/`checkout` 并不删除对象，提交仍在 reflog/objects 里。真正的 amnesia 不在存储层，而在**读取层**——被 revert 后 agent 的上下文里没有那次失败的 diff。

**请把论证改成这个版本（这才是站得住的）：**
> AgentGit retains every commit in the object store, so its amnesia is not a storage property but an *observation* property: after a revert, the working tree the agent reads no longer contains the failed attempt, and nothing in the framework obliges the next iteration to consult it. Our C3 makes that consultation a structural requirement rather than a developer's choice.

顺便：你的"不需要 branch"论点**必须**在这篇旁边说，因为 AgentGit 的核心卖点正是 branch。

**建议的 Related Work 句：**
> AgentGit provides Git-like commit, revert, and branching as an infrastructure layer for multi-agent workflows, but it is a developer-facing tool for reliability and A/B exploration; it does not constrain what an agent observes after a revert, which in our setting is precisely where failure evidence is lost.

### 1.4 Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents

- Zhang, Hu, Lu, Lange, Clune. arXiv:2505.22954 (v3, 2026-03-12). ICLR 2026.
- https://arxiv.org/abs/2505.22954

**摘要（原文）：**
> Today's AI systems have human-designed, fixed architectures and cannot autonomously and continuously improve themselves. The advance of AI could itself be automated. If done safely, that would accelerate AI development and allow us to reap its benefits much sooner. Meta-learning can automate the discovery of novel algorithms, but is limited by first-order improvements and the human design of a suitable search space. The Gödel machine proposed a theoretical alternative: a self-improving AI that repeatedly modifies itself in a provably beneficial manner. Unfortunately, proving that most changes are net beneficial is impossible in practice. We introduce the Darwin Gödel Machine (DGM), a self-improving system that iteratively modifies its own code (thereby also improving its ability to modify its own codebase) and empirically validates each change using coding benchmarks. Inspired by Darwinian evolution and open-endedness research, the DGM maintains an archive of generated coding agents. It grows the archive by sampling an agent from it and using a foundation model to create a new, interesting, version of the sampled agent. This open-ended exploration forms a growing tree of diverse, high-quality agents and allows the parallel exploration of many different paths through the search space. Empirically, the DGM automatically improves its coding capabilities (e.g., better code editing tools, long-context window management, peer-review mechanisms), increasing performance on SWE-bench from 20.0% to 50.0%, and on Polyglot from 14.2% to 30.7%. Furthermore, the DGM significantly outperforms baselines without self-improvement or open-ended exploration. All experiments were done with safety precautions (e.g., sandboxing, human oversight). The DGM is a significant step toward self-improving AI, capable of gathering its own stepping stones along paths that unfold into endless innovation.

**它解决什么问题：** 自修改代码的 agent 如何**开放式**变好——靠维持一个**只增不减的 archive**、从中采样父代生成新变体、并**保留看似更差的中间产物作为 stepping stones**。它是对"证明有益才可修改"（Gödel machine）的实用替代。

**与你的关系：** 这是你论证的**另一半证据**，而且非常有用：
- 它证明了"**历史只增不减**"（你的 C1）在**性能上**是必要的——stepping stones 恰恰是那些当时看起来更差的变体。这给你的 C1 一个**经验动机**，而不只是审计动机。**强烈建议引这一条来支撑 C1。**
- 但它**没有回滚**：它保留全部变体，避免"删掉"的问题，代价是状态空间爆炸、需要可信的评估信号（benchmark）来做选择。
- **这正好是你在 Discussion 里必须承认的取舍**：你的架构"有回滚、无分支"，DGM"有分支、无回滚"。DGM 的 stepping stone 收益你放弃了。诚实地写这一句，会显著提升论文可信度，并预判 reviewer 的攻击。

**建议的 Related Work 句：**
> The Darwin Gödel Machine shows that retaining seemingly worse variants as stepping stones is empirically load-bearing for open-ended self-improvement, which motivates our append-only constraint from a performance rather than an audit angle. DGM achieves this by an archive without rollback; we achieve it by a log with rollback, at the cost of a single active lineage.

---

### 1.5 ChronoMem: Version Control and Semantic Rollback for Large Language Model Agent Memory ★概念上最有张力的一篇

- Su, Xu, Zuo, Bertino. arXiv:2607.27773 (v2, 2026-08-05).
- https://arxiv.org/abs/2607.27773

**摘要（原文）：**
> LLM agents increasingly rely on long-term memory to support multi-session interaction and personalization. However, existing agent memory systems are designed around forward-only evolution, continuously accumulating, consolidating, and overwriting knowledge, with no principled mechanism to inspect, version, or revert prior states. This makes agents brittle under corrections, concept drift, and memory corruption, particularly after they have already been exposed to subsequent information. We present ChronoMem, a semantic version-control layer for agentic memory integrated into the production-ready, open-source Agent Development Kit by Google. ChronoMem commits whole-memory snapshots at each memory write, maintains structured version histories, and supports natural-language rollback requests by mapping undo intents to concrete historical versions through hybrid lexical and semantic retrieval, rank fusion, and reranking. We further introduce a **post-exposure evaluation protocol that tests whether an agent can behave counterfactually after rollback by answering queries and summarizing history as if future updates had never occurred.** On long-horizon conversational benchmarks augmented with evolving memory states and rollback tasks, ChronoMem substantially improves rollback-consistent question answering and history summarization relative to prompt-only and retrieval-only baselines, while achieving strong performance in semantic version selection. To our knowledge, ChronoMem is the first open-source system and benchmark for systematic semantic global memory rollback in LLM agents.

**它解决什么问题：** agent 长期记忆**只能正向演化**（累积、合并、覆写），没有版本、无法回滚，于是在被纠正、概念漂移、记忆污染时变脆。ChronoMem 给记忆加语义版本控制层，并定义了一个**反事实回滚**的评价协议：回滚后 agent 必须表现得"仿佛未来的更新从未发生"。

**与你的关系：** **这是全篇最有价值的一组对照，因为它把你的立场逼到了边界上，而边界恰好站在你这边。**

- ChronoMem 的回滚目标函数是**反事实的（counterfactual）**：回滚成功的判据是"agent 表现得像那件事没发生过"。这在**世界事实**上完全正确——记错的事实就该被彻底撤销。
- 但把同一个算子用在**自我修改的历史**上，反事实回滚就是**你所说的 Rollback Amnesia**：agent 表现得像那次失败的修改从未发生，于是它再次提出同样的修改。
- 所以你的论文可以提出一条比现在更强、更普适的原则：

> **Rollback semantics are layer-dependent. For world-facts, correct rollback is counterfactual (behave as if it never happened). For self-facts, counterfactual rollback is the bug: the agent must behave as if the failed modification *had* happened, while behaving as if it were still active the same way it did before.**

即：**"回滚状态"与"回滚认知"必须分开**。ChronoMem 是前者的完美实现，也是后者的完美反例。这个"同一算子在两层上语义相反"的观察，足以撑起一篇 position paper 的核心洞察，也把你的 C2 从"设计选择"提升为"语义定理"。

- 另外它给了你一个**可借用的评测范式**：`post-exposure evaluation`。你可以定义一个对称的协议——*post-rollback learning test*：回滚后给 agent 一个同分布的任务，看它是否**不**再提出同一个 `Δ`。这是你目前最缺的"可证伪性"，且已有现成方法学可以照抄结构。

**建议的 Related Work 句：**
> ChronoMem adds semantic version control to agent memory and evaluates rollback counterfactually, requiring the agent to answer as if later updates had never occurred. This is the correct semantics for world-facts and precisely the wrong semantics for self-facts: an agent that behaves as if a failed self-modification never occurred will propose it again. Our C1--C2 exist to make that asymmetry structural.

---

## 2. 第二组：同题的另一半 —— 失败证据在经验记忆中的存续与复现

### 2.1 More Memory, Worse Agents: Error Reproduction and Anti-Persistence in LLM Agents ★第二危险的一篇

- Wang, Panaganti, Zhou. arXiv:2610.27406, 2026-10-19.
- https://arxiv.org/abs/2610.27406

**摘要（原文）：**
> LLM agents can improve across tasks without updating model parameters by storing experience from their own executions in external memory and reusing it to guide later decisions. A central design question is whether to retain only observed trajectories and outcomes or also the rules, summaries, and skills inferred from them. Retaining these abstractions allows agents to reuse strategies without repeatedly deriving them from raw trajectories. However, errors in stored abstractions can propagate to subsequent decisions through retrieval and reuse. They can also shape execution trajectories, which then become the basis for new abstractions that reproduce the original errors. **We term this feedback mechanism error reproduction**: errors are regenerated through a cycle of abstraction, execution, and re-abstraction, extending their persistence beyond direct reuse of the original faulty knowledge. We propose Anti-Persistence, a memory design that accumulates trajectories and outcomes while reconstructing task-specific guidance on demand. An adaptive selector uses prior outcomes to decide whether and how to synthesize guidance, which is discarded after execution. This prevents its direct reuse as a stored object, although indirect feedback through retained trajectories remains possible. Across different benchmarks and backbones, Anti-Persistence achieves higher overall held-out success and the lowest average LLM-call cost among the evaluated memory designs. **These results support separating experience accumulation from abstraction persistence in memory-based self-improvement.**

**它解决什么问题：** 经验记忆的**错误复现（error reproduction）**——错误经由"抽象 → 执行 → 再抽象"的循环被反复再生，其持久性超过原始的坏知识本身。解法：只累积轨迹与结果，把抽象**按需重建、用完即弃**，从而切断抽象作为存储对象的复用链路。

**与你的关系：** 这是**概念上离你最近、也最容易让你显得 incremental** 的一篇。
- 你已经把它写进 Related Work 并归到"anti-persistence"，方向对，但**力度不够**：它不是"又一个 memory 设计"，它是**你论文的实证前提**。它用实验证明了：**失败/错误如果不被正确地保留在正确的位置，会跨 episode 自我复制。** 这正是 Rollback Amnesia 的孪生现象。
- 它的解法和你的解法**方向相反但同构**：它让**抽象**不持久（保住轨迹）；你让**轨迹**绝对持久（只回滚抽象）。两者都把"事实层"与"解释层"解耦。**所以"双层分离"这个原则是它的，不是你的**——你的新意在"回滚算子只作用于哪一层"。
- 它的摘要最后一句 `separating experience accumulation from abstraction persistence` 几乎是你的 C1/C2 的一句话版本。**如果你不引用并明确区分，reviewer 会认为你在重复造概念。** 引用反而对你有利：你可以说"我们的工作把这个已被观察到需要分离的原则，推进为一个可回滚的算子语义"。

**注意它留下的口子（你的机会）：** 它自己承认 *"indirect feedback through retained trajectories remains possible"* ——即"轨迹保留仍可能间接导致错误复现"。**这就是你的切入点**：光保留轨迹不够，还必须保证 `Iter` 在回滚后**实际读取**到那条失败轨迹（你的 C3），并且这条读取不能被摘要化抹平（你 §4.1 的"关键决策必须回溯原始记录"）。

**建议的 Related Work 句：**
> Anti-Persistence identifies error reproduction — errors regenerated through abstraction, execution, and re-abstraction — and mitigates it by discarding synthesized guidance after each execution, explicitly leaving indirect reproduction through retained trajectories open. We close that remainder from the substrate side: trajectories are append-only, and every self-modification is conditioned on them.

### 2.2 Reflexion: Language Agents with Verbal Reinforcement Learning

- Shinn, Cassano, Berman, Gopinath, Narasimhan, Yao. arXiv:2303.11366 (v4), NeurIPS 2023.
- https://arxiv.org/abs/2303.11366

**摘要（原文）：**
> Large language models (LLMs) have been increasingly used to interact with external environments (e.g., games, compilers, APIs) as goal-driven agents. However, it remains challenging for these language agents to quickly and efficiently learn from trial-and-error as traditional reinforcement learning methods require extensive training samples and expensive model fine-tuning. We propose Reflexion, a novel framework to reinforce language agents not by updating weights, but instead through linguistic feedback. Concretely, Reflexion agents verbally reflect on task feedback signals, then maintain their own reflective text in an episodic memory buffer to induce better decision-making in subsequent trials. Reflexion is flexible enough to incorporate various types (scalar values or free-form language) and sources (external or internally simulated) of feedback signals, and obtains significant improvements over a baseline agent across diverse tasks (sequential decision-making, coding, language reasoning). For example, Reflexion achieves a 91% pass@1 accuracy on the HumanEval coding benchmark, surpassing the previous state-of-the-art GPT-4 that achieves 80%. We also conduct ablation and analysis studies using different feedback signals, feedback incorporation methods, and agent types, and provide insights into how they affect performance.

**它解决什么问题：** 不更新权重的前提下从试错中学习——把失败信号转成**语言化反思**，存进 episodic memory，在后续 trial 中提示自己。

**与你的关系：** 它是你的**思想祖先**，不是竞争对手，必须引，且要引得精准：
- 它证明了"**保留失败证据（而非回滚到失败前的自己）**"确实能带来收益。这是你 C2 的**经验合法性来源**：回滚 ≠ 唯一的安全选择，保留证据也是安全的。
- 但它的作用域是**单任务多 trial**（`task → trials`），没有"agent 修改自己的 harness"，因此**没有版本化的 `s_t`**，也就没有"回滚"这个动作，Rollback Amnesia 在它的设定里根本不可能发生。这就是它和你的边界。
- 它的反思文本是 **lossy abstraction**，正是 Anti-Persistence 批评的对象。你可以在 §4.1 里借用这个批评：**"反思"是解释层，可以被回滚和重写；原始 trace 是事实层，不可以。**

**建议的 Related Work 句：**
> Reflexion shows that retaining verbalized failure evidence in an episodic buffer improves subsequent trials without weight updates, establishing that evidence retention is a viable alternative to reverting. Its scope is a single task's trial sequence, where no self-modified state exists to revert, so the amnesia problem cannot arise.

### 2.3 ExpeL: LLM Agents Are Experiential Learners

- Zhao, Huang, Xu, Lin, Liu, Huang. arXiv:2308.10144 (v3). AAAI-24.
- https://arxiv.org/abs/2308.10144

**摘要（原文）：**
> The recent surge in research interest in applying large language models (LLMs) to decision-making tasks has flourished by leveraging the extensive world knowledge embedded in LLMs. While there is a growing demand to tailor LLMs for custom decision-making tasks, finetuning them for specific tasks is resource-intensive and may diminish the model's generalization capabilities. Moreover, state-of-the-art language models like GPT-4 and Claude are primarily accessible through API calls, with their parametric weights remaining proprietary and unavailable to the public. This scenario emphasizes the growing need for new methodologies that allow learning from agent experiences without requiring parametric updates. To address these problems, we introduce the Experiential Learning (ExpeL) agent. Our agent autonomously gathers experiences and extracts knowledge using natural language from a collection of training tasks. At inference, the agent recalls its extracted insights and past experiences to make informed decisions. Our empirical results highlight the robust learning efficacy of the ExpeL agent, indicating a consistent enhancement in its performance as it accumulates experiences. We further explore the emerging capabilities and transfer learning potential of the ExpeL agent through qualitative observations and additional experiments.

**它解决什么问题：** 跨任务的**经验学习**——在若干训练任务上自主收集经验、用自然语言抽取 insight，推理时召回 insight 与过往经验。核心主张：不更新参数也能"越用越强"。

**与你的关系：** 它是**你要回滚的那个东西的定义者**。你的 `e`（iterative experience）在 ExpeL 里就是 insight 集合；你的 `w` 在 ExpeL 里是策略（它是固定 harness + 可变 insight，不是可变 harness，这是差别）。
- 你需要的论证是：**ExpeL 式经验只增不减 ⇒ 一旦 insight 抽错，就会长期污染。** 这正是 Anti-Persistence 量化的现象。
- 因此 ExpeL 支撑你的 **F2（anecdotal overfitting）**：insight 从近期任务抽取，没有机制保证它在全局历史下仍成立。**你可以用它来论证 C3 的必要性**：ExpeL 的 insight 只对"它见过的那批任务"负责，而不是对 `L_t` 负责。

**建议的 Related Work 句：**
> ExpeL induces natural-language insights from a fixed set of training tasks and recalls them at inference, establishing cross-task experiential learning without parameter updates. Because insights are added and never retired, an incorrectly induced insight persists by construction — the overfitting mode our C3 is designed to prevent.

### 2.4 Continual Learning Bench (CL-Bench)

- Asawa, Glaze, Orlanski, Ramakrishnan, Xu, Biswal, Chen, Sala, Zaharia, Gonzalez. arXiv:2606.05661, 2026-06-04.
- https://arxiv.org/abs/2606.05661

**摘要（原文）：**
> Continual learning, the ability of AI systems to improve through sequential experience, has attracted substantial interest, but no high-quality benchmark exists to evaluate it. We introduce Continual Learning Bench (CL-Bench), the first difficult, expert-validated benchmark designed to measure whether LLM-based systems genuinely improve with experience. CL-Bench spans six diverse domains (software engineering, signal processing, disease outbreak forecasting, database querying, strategic game-playing, and demand forecasting), each validated by domain experts and designed so that tasks share a learnable latent structure (codebase layout, disease outbreak dynamics, opponent strategies) that a stateful system can discover online but a stateless one cannot. We evaluate frontier models across several agent architectures, from naive in-context learning (ICL) to dedicated memory systems, introducing a gain metric to isolate learning from prior capabilities. We find that these systems leave headroom for improved continual learning: agents frequently overfit to immediate observations or fail to reuse knowledge across instances, and dedicated memory systems do not fix this — in fact, naive ICL outperforms systems dedicated to memory management. CL-Bench is the first benchmark to evaluate continual learning across diverse real-world domains with expert-validated tasks and isolate online learning from underlying model capability, showing a need for better continual learning systems.

**它解决什么问题：** 给"是否真的从经验中变好"提供**可测量的基准**，并用 `gain` 指标把"学习"从"底层模型能力"里剥离出来。

**与你的关系：** 你不是 empirical paper，可以不引。但**强烈建议引一句**，因为它给你两个免费的东西：
1. **动机的实证背书**：`agents frequently overfit to immediate observations or fail to reuse knowledge across instances` —— 这句话就是你 F2 的引用来源，比你自己断言有力得多。
2. **未来工作的落点**：你可以在 §6 写"验证 Rollback Amnesia 需要一个能区分'功能未改进'与'认知未改进'的协议，CL-Bench 的 gain metric 是一个起点"。这会让 position paper 显得可执行而非空谈。

**建议的 Related Work 句（放在 F2 的动机处，不放在 §2）：**
> CL-Bench finds that agents "frequently overfit to immediate observations or fail to reuse knowledge across instances," and that dedicated memory systems do not fix this, providing direct empirical support for the overfitting mode we address.

---

### 2.5 Can Coding Agents Sustain Continual Evolution without Forgetting? ★最强的动机引用

- Zhao, Zhang, Li. arXiv:2611.03219, 2026-11-02.
- https://arxiv.org/abs/2611.03219

**摘要（原文）：**
> Recently, harness self-evolution has emerged as an important paradigm for improving agent performance. Prior studies show that evolving the agent harness can effectively enhance agent capabilities without modifying the foundation model's parameters. **We find that existing approaches largely study agent evolution on a single task.** In practice, coding agents may need to handle multiple task types over time. Whether an agent harness can continuously evolve across multiple tasks without suffering from catastrophic forgetting remains an important open question. In this paper, we investigate this open question through a comprehensive empirical study of continual harness self-evolution. We organize three software engineering task datasets into six different evolution directions and apply two representative harness evolution methods to perform continual evolution along these directions. Our experimental results show that **evolution on a subsequent dataset can substantially undermine the performance on previously seen datasets.** For example, with DeepSeek-V4-Flash-0731, Meta-Harness improves its performance on SWE-Bench to 94.0% after evolution. However, after further evolution on FeatureBench, its performance on SWE-Bench drops to 32.0% by the fifth round, corresponding to a 66% relative decrease. Finally, based on our experimental findings, we identify several insights, providing directions for the continual self-evolution of agent harnesses.

**它解决什么问题：** 回答一个此前被认为 open 的问题——**harness 能否跨任务持续自我演化而不发生灾难性遗忘**。答案是不能：在 SWE-Bench 上把 harness 演化到 94.0%，再在 FeatureBench 上继续演化，五轮后 SWE-Bench 掉到 32.0%（相对下降 66%）。并指出既有工作几乎都只在**单一任务**上研究演化。

**与你的关系：** **这是你整篇论文最强的动机证据，没有之一。** 理由：
- 它的研究对象就是 `w`（harness），**和你的解释层完全同构**，不是相邻领域。
- 它**实测了 F1（availability drift）与 F2 的极端形态**：不是"略微变差"，而是 66% 的崩塌。你 §1 里"modifications may introduce fatal execution errors or overfit"这句断言，现在有了一个 94%→32% 的具体数字可以引。
- 它证明"**只前进不回滚的演化**"在跨任务下会自我摧毁——这直接推出"必须有回滚通道"（你的 C2），且这个推论**不需要你假设**，是别人实测的。
- 它同时暴露了你的机会：它只做了**诊断**（发现会遗忘），没有给出**substrate 层的解法**。你的 append-only + 可回滚双层，正是它可以承接的下一步。**把这篇当作"problem statement 的实证背书"，你的 position paper 立刻从"我觉得"变成"已有实测证据表明"。**

**建议的 Related Work 句（放在 §2 第一段或 §1 的动机处）：**
> A recent empirical study of continual harness self-evolution reports that evolving a harness on a new task family can destroy performance on previously mastered ones --- SWE-Bench accuracy falling from 94.0\% to 32.0\% after five rounds of evolution on a different benchmark --- and observes that prior work studies evolution on a single task. This is availability drift measured on exactly the object we roll back, and it establishes that an undo channel is not optional.

**⚠️ 同时它也是一个竞争威胁**：这篇已经在"跨任务 harness 演化"这个 settings 上站住了脚，并且是 THU-Agent 组的实证工作。你的论文必须明确：**它做的是"会不会忘"（诊断），你做的是"如何不忘且可回滚"（机制）**。若写得含糊，reviewer 会问"你为什么不直接在它的设定上做"。

---

## 3. 第三组：回滚修复与门控（你的机制的直接对照）

### 3.1 From Faulty Memories to Corrected Actions: Dependency-Guided Rollback Repair for Memory-Augmented Agents

- Wang, Yu, Zhang, Duan, Zheng, Wu, Shi, Cai. arXiv:2608.10502 (v2, 2026-10-22).
- https://arxiv.org/abs/2608.10502

**摘要（原文）：**
> Persistent memory lets language model agents reuse information across sessions, but it also makes errors durable: a poisoned, stale, or misattributed record can alter reasoning, tool use, answers, and subsequent memory writes. Existing defenses mainly detect or delete suspicious memories, or revise the current response. Deleting the source leaves already propagated claims, actions, and derived memories active, whereas resetting the store or replaying the full trace destroys benign state and repeats unnecessary computation. **We therefore formulate post-failure memory recovery**: given a failed execution and diagnosed faulty memories, regenerate the answer and clean up affected persistent state while retaining unaffected work. Our dependency-guided rollback repair builds a typed memory-to-action graph from runtime provenance, traces explicit downstream dependencies, preserves candidates with independent trusted support, deactivates unsupported memory state, and selectively replays only answer-relevant affected computation. We evaluate this approach on a 150-case controlled benchmark spanning three tool-use domains and four memory failure types, and on a 50-case trajectory-derived stress test adapted from LongMemEval-V2. On the controlled benchmark, it achieves 85.3% immediate recovery versus 77.3% for LLM-judge repair, the strongest baseline, while preserving all benign memories and using 41.8% fewer LLM calls. Selective replay, however, leaves higher recurrence than LLM-judge repair (26.6% vs. 12.1%), exposing a trade-off between targeted repair and broader recomputation.

**它解决什么问题：** **一次失败之后的记忆恢复**——给定失败执行与被诊断出的坏记忆，如何重新生成答案并清理受污染的持久状态，同时保住无辜状态、不重复无谓计算。用 provenance 建 memory-to-action 依赖图，做**细粒度**回滚。

**与你的关系：** 这篇是**你 §4.4 论证的实证对手**，价值极高：
- 它做了**组件级/细粒度回滚**，并且**量化了你所担心的风险**：`selective replay leaves higher recurrence than LLM-judge repair (26.6% vs 12.1%)`。**这就是"细粒度回滚会导致更高复发率"的直接证据**，你可以用它来支撑"整体回滚优于局部回滚"的判断。这是你目前最有说服力的一个外部证据，务必引。
- 但它的作用域是**单次失败后的会话内修复**（post-failure memory recovery），不是跨 episode 的 `w`/`e` 演化；它也没有 append-only 事实层，所以它靠"依赖图"来做归因，而你直接**放弃归因**（§4.3 的立场）。
- 它的 `recurrence` 指标（错误复发率）**正是你论文缺失的度量**。建议你在 §6 或 §4.1 借用这个词：*"a Rollback Amnesia loop is observable as high recurrence under a fixed task distribution"*。这让你的概念可被测量。

**建议的 Related Work 句：**
> Dependency-Guided Rollback Repair performs fine-grained, provenance-based rollback of a single failed execution and reports that selective replay leaves higher error recurrence than broader recomputation (26.6% vs. 12.1%). This is direct evidence for our position that fine-grained attribution is both unreliable and epistemically costly, motivating holistic rollback.

### 3.2 Masked Erosion: How Acceptance Gates Lose Redundant Safeguards in Self-Improving Agents

- So, Liu, Long. arXiv:2610.38392, 2026-10-28.
- https://arxiv.org/abs/2610.38392

**摘要（原文）：**
> Self-improving LLM agents edit their own harness, the prompts and rules around a fixed model, and keep an edit only if an acceptance gate scores it higher on a batch of tasks. Such a gate sees what the harness does under the current model, not what it would still prevent if one safeguard failed. When safeguards overlap, deleting one is masked: the others still block the harm, so the gate decides on task success alone, and redundancy erodes unseen. We measure harm for every subset of four written safeguards in two agent environments and run 411 improvement loops under ten gate rules, mostly as controlled deletion experiments, plus three runs of the GEPA optimizer. A deletion behind another working safeguard adds almost no observable harm. A paired significance test blocks deletions that pass by chance but not deletions that genuinely raise task success, and a larger evaluation batch lets it delete cheaper safeguards: at the same cost, 20-task batches kept every harness protected while 40-task batches lost all six. Large harm audits prevent exposure but not the loss of depth, which turns into harm when the harness is reused with a weaker model. GEPA kept every safety rule verbatim, yet two of its three final harnesses misused credentials under a weaker model. A statistical model frozen before the runs predicts where each gate's protection breaks as safeguard cost and batch size change, and freezing safety text or auditing one-layer ablations preserves depth.

**它解决什么问题：** **接受门（acceptance gate）本身的失效**——自我改进 agent 只在 gate 打分更高时才保留编辑，但当多个安全措施重叠时，删掉其中一个会被其他措施**掩盖**，gate 看不到伤害，冗余在无人察觉中侵蚀。结论：gate 的分数（任务成功率）不能作为安全的代理。

**与你的关系：** 这篇是**你 Sidecar 设计的最大理论威胁，也是最好的盟友**，你必须正面处理：
- **威胁**：你的 §4.3 主张"Sidecar 读信号不读语义、做硬门控"就能保证 F1。但 Masked Erosion 表明：**任何以"任务表现/信号"为判据的门都会因冗余掩盖而侵蚀**——而你的 `θ_time`/`θ_tok`/`exception` 三个信号，恰恰是**最容易被"绕过"的信号**（agent 可以把一次超时改成多次小调用，把异常吞掉换成返回错误结果）。
- **盟友**：它恰好论证了"**门不能依赖评估信号，必须依赖结构**"——这正是你"trust must be in the substrate, not the model's disposition"的**独立证据**。你可以把它的结论当作你的前提，然后说：正因如此，我们把门控**降级为可用性触发器**，而把信任**上移**到不可回滚的事实层。这是一个非常漂亮的引用：**它的失败模式解释了为什么你的 Sidecar 只做粗粒度整体回滚（不尝试精细判断），以及为什么你的信任不建立在 Sidecar 上。**

**建议的 Related Work 句：**
> Masked Erosion shows that acceptance gates scored on task success silently erode redundant safeguards, because overlapping protections mask the harm of any single deletion. This undermines any architecture that locates trust in a gate, including signal-based supervisors, and motivates our choice to use the Sidecar only as a coarse availability trigger while placing the trust property in the append-only layer, which no gate can erode.

这一条引用会显著提升你的 §4.3 的可信度，也顺手挡掉"你的 Sidecar 阈值不也是启发式吗"这一必问的问题。

---

## 4. 背景（同一大领域，但不是同一问题，各一句话即可）

| 工作 | 一句话 | 为什么不用重点写 |
|---|---|---|
| **AFlow** (Zhang et al., ICLR 2025, arXiv:2410.10762) | 用 MCTS 在代码表示的工作流空间里搜索更优 agentic workflow | 有可信验证集做选择，遇不到"无 ground truth 时如何回滚"；它证明 `w` 可被自动优化，正好是你回滚对象的来源 |
| **Agent Workflow Memory** (Wang et al., arXiv:2409.07429, ICML 2025) | 从历史轨迹中归纳可复用 workflow，离线/在线注入 | 只做归纳与复用，没有失败后必须回滚的约束 |
| **Voyager** (Wang et al., arXiv:2305.16291) | 技能库 + 自验证，只把**验证通过**的技能入库 | 它的"先验证再入库"是**事前**门控；你的是**事后**回滚，二者互补，可在 §4.3 一句话对比 |
| **Gödel Agent** (Yin et al., arXiv:2410.04444) | 运行时可自指修改自身逻辑的 agent 框架 | 关注"能否自改"，不关注"改错了如何不遗忘" |
| **Self-Evolving Agents Survey** (Gao et al., arXiv:2507.21046, TMLR 2026) | 按 what/when/how 组织自演化 agent 全领域 | 用一句 "see survey" 定位你的问题在其中的空缺即可 |

---

## 5. 修正版 Table 1（替换你现在的表）

你原表有三处会被打：AgentGit 的 "Retained: Nothing" 不准确；缺 DGM 与 Exo（最相关的两篇）；"Trust Target" 一列是自评，不可比。换成**可观测的机制维度**：

| Work | Mutable state | Revert operator | What the next edit observes after revert | Scope of revert vs. scope of evidence |
|---|---|---|---|---|
| Reflexion | episodic reflection buffer | none (no revert) | full trial history incl. failures | N/A (no `s_t` versioning) |
| ExpeL | induced insights | none | all past tasks & insights | N/A (append-only, no undo) |
| AgentGit | workflow / agent state | commit-level `revert`, `branch` | working tree at checkpoint; failed commit not in context | **evidence outside scope** → amnesia |
| ChronoMem | long-term memory (world facts) | semantic, whole-memory snapshot rollback | state as if later updates never happened | evidence ⊂ scope **by design** → correct for facts, amnesia for self-facts |
| Darwin Gödel Machine | own codebase | none (archive never pruned) | entire archive incl. failures | evidence ⊃ scope (no undo, no forgetting) |
| EvoUndo | prompts/tools/harness | verified recovery program | recovered state; failure only if recorded in recovery witness | scope = recoverability, not learning |
| Dependency-Guided | memory store | fine-grained, provenance-typed | unaffected state retained, affected replayed | **partial scope** → higher recurrence (26.6%) |
| Exo | harness policy + code | activation governance (no explicit undo) | execution history preserved by protected layer | protects mechanism, not evidence |
| **Ours** | `w`, `e` (interpretation layer) | **holistic, to `s_{t-k}`, `L` untouched** | **entire `L_t`, incl. failed `Δ` and its rationale** | **scope ∩ evidence = ∅ (C1–C3)** |

这张表的好处：每一行都是**可从论文中核实的事实**，而不是作者自评；最后一行才是你的贡献，而且它是唯一满足 `scope ∩ evidence = ∅` 的。

---

## 6. 风险清单（审稿人一定会问的）

1. **"你和 Exo 的区别是什么？"** —— 见 §1.1。准备好一句话：*Exo protects what may be edited; we protect what must survive an undo.* 如果你答不出，这篇会被判 incremental。
2. **"你和 Anti-Persistence 的区别是什么？"** —— 见 §2.1。一句话：*它们让解释层不持久，我们让解释层可回滚、事实层不可回滚；我们补上它们明确留下的"轨迹间接复现"的口子。*
3. **"`rollback amnesia` 这个词是不是你造的？"** —— 需要你确认检索结果（见下文"待核实"）。若无人用过，这是你最大的资产，应在 abstract 第一段就下定义并加脚注；若有人用过，必须引用并说"我们将其形式化为…"。
4. **"Sidecar 的阈值不也是启发式？"** —— 用 Masked Erosion 回答（§3.2）：信任不在 Sidecar 上，Sidecar 只负责可用性；信任在不可回滚的层上，而那一层没有任何门可以侵蚀。
5. **"没有分支会丢失 DGM 的 stepping stone 收益"** —— 主动在 §6 承认（§1.4）。
6. **"没有实验"** —— position paper 可以没有，但**必须**给出可测量协议。建议在 §6 加一句：*Rollback Amnesia is falsifiable: under a fixed task distribution, an amnesiac agent's modification proposal distribution should converge to a fixed point, while ours should not.* 这一句把全文从"主张"变成"可检验命题"，是 position paper 最划算的一行字。

---

## 7. 待核实 / 未完成

- [x] **"rollback amnesia" 术语检索（初步结论）**：在 arXiv / 检索范围内**未发现**同行评议文献使用该术语于同一含义。唯一命中是一个 GitHub release 附件 `system-design-patterns.pdf` 中的一句 "The characteristic failure is rollback amnesia"（非同行评议，且无法确认是否同义）。另有 "Strategic Amnesia in LLM Agents playing the Iterated Prisoner's Dilemma"（CEUR-WS），其 "amnesia" 指**策略性地遗忘历史以改变博弈行为**，与你的含义无关，但建议在脚注中一并排除，防止 reviewer 拿它说你用词重复。
  → **建议**：在 abstract 首次出现处下定义 + 加脚注 "We introduce this term; it is distinct from strategic amnesia, which denotes deliberate forgetting of interaction history." 这会同时完成"造词"和"防御"。
- [x] **"Can Coding Agents Sustain Continual Evolution without Forgetting?"** (arXiv:2611.03219) 已读，见 §2.5。结论：**必须引，且是最强动机引用**；但同时是竞争威胁，需明确"诊断 vs 机制"的分工。
- [ ] **`Exo` 是否实现了显式 `revert` 到历史检查点**：摘要只说 "preserves execution history and governs policy activation"，未提 undo。需读正文 Method §（`arxiv.org/html/2611.00463v1`）确认。**这直接决定 §5 表格里 Exo 那一行怎么写**，也决定你能否说"即使是最接近的系统也没有回滚算子"。
- [ ] **"Gate Presence Is Not a Safety Invariant: Semantic Floors for Self-Editing Agent Harnesses"** (NeurIPS 2026, `neurips.cc/virtual/2026/loc/sydney/168230`)：若为正式论文，与 `Masked Erosion` 一起构成对门控的批判，应一并引用。
- [ ] **"When Should Experience Become Parameters? Selection, Not Volume, Governs Online Experience Consolidation in LLM Agents"** (zenodo 21175566) 与 **"Admission Governs Entry: ..."** (zenodo 23314562)：Zenodo 非同行评议，题目与你的 F2 高度相关但需自行判断质量，**不建议作为主要引用**，最多作脚注。
- [ ] **"Failure-Gated Hierarchical Memory: Preventing Memory Pollution in Long-Horizon LLM Agents via Critic-Guided Write Control"** (IEEE)：写入端门控，可作 §2 补充分支。

---

## 8. 可直接粘贴的 Related Work 英文重写稿（约 640 words，替换你现在的 §2）

> 说明：按"同题正面 → 同题另一半 → 机制对照"三段式组织，末尾一段把差距收束到一句话。所有 `\citep{}` 键对应 §9 的 BibTeX。

```latex
\section{Related Work}

\paragraph{Versioning and rollback for agent state.}
Closest to our concern is a line of work that gives agents a substrate for undoing
their own changes. AgentGit~\citep{li2025agentgit} brings Git-like commit, revert, and
branching to multi-agent workflows, but it is a developer-facing reliability layer:
it does not constrain what an agent \emph{observes} after a revert, and the restored
working tree is precisely where the failed attempt disappears from view.
ChronoMem~\citep{su2026chronomem} goes further and treats rollback of agent memory as a
first-class problem, adding semantic version control over whole-memory snapshots and
defining a post-exposure protocol under which a successful rollback is one where the
agent answers \emph{as if future updates had never occurred}. That criterion is exactly
right for world-facts and exactly wrong for self-facts: an agent that behaves as if a
failed self-modification never occurred is an agent that will propose it again.
EvoUndo~\citep{sah2026evoundo} attacks the complementary half of the problem, showing
that most capability-improving self-modifications fail independent recoverability
verification across counterfactual states, and co-designing a recovery language with
exact state grounding to make undo possible at all. Recoverability, however, is a
precondition for safety rather than for learning: a mutation may be perfectly
reversible and still teach the agent nothing. Exo~\citep{krentsel2026exo} collapses the
optimization loop into task execution and protects a minimal mechanism layer that
preserves execution history and governs policy activation while the harness evolves
through inspectable code changes. It is the closest architectural relative of our
work, but its objective is cost reduction rather than auditability, and its protection
is over \emph{what may be edited} rather than over \emph{what must survive an undo}.
A recent empirical study of continual harness self-evolution~\citep{zhao2026continual}
reports that evolving a harness on a new task family can destroy previously mastered
performance --- SWE-Bench accuracy falling from 94.0\% to 32.0\% after five rounds of
evolution on a different benchmark --- and observes that prior work studies evolution on
a single task. This is availability drift measured on exactly the object we roll back,
and it establishes that an undo channel is not optional.
At the other extreme, the Darwin G\"odel Machine~\citep{zhang2026dgm} never undoes
anything: it maintains a growing archive and deliberately retains worse variants as
stepping stones, which is strong evidence that monotone history is load-bearing for
open-ended improvement. DGM buys this with branching and a trusted benchmark signal;
we buy it with a single lineage and an append-only log.

\paragraph{Failure evidence in experiential memory.}
A parallel literature learns from experience without touching weights.
Reflexion~\citep{shinn2023reflexion} stores verbalized reflections on failure in an
episodic buffer and improves subsequent trials, establishing that retaining evidence is
a viable alternative to reverting; its scope is one task's trial sequence, where no
self-modified state exists to revert. ExpeL~\citep{zhao2024expel} induces natural-language
insights across tasks and recalls them at inference, but insights are only ever added,
so an incorrectly induced one persists by construction. This is the overfitting mode
we target: Continual Learning Bench~\citep{asawa2026clbench} finds that agents
``frequently overfit to immediate observations or fail to reuse knowledge across
instances,'' and that dedicated memory systems do not fix it. Most directly,
\citet{wang2026antipersistence} name \emph{error reproduction}, in which errors are
regenerated through a cycle of abstraction, execution, and re-abstraction, and mitigate
it by discarding synthesized guidance after each execution while retaining trajectories
--- explicitly leaving indirect reproduction through retained trajectories open. We
close that remainder from the substrate side, and we share their premise that
experience accumulation must be separated from abstraction persistence. Our
contribution is not the separation itself but the \emph{operator semantics} it enables:
which layer a revert is permitted to touch.

\paragraph{Gating and fine-grained repair.}
Two recent results explain why we refuse to locate trust in a supervisor.
Dependency-Guided Rollback Repair~\citep{wang2026depguided} performs provenance-typed,
fine-grained rollback of a single failed execution and finds that selective replay
leaves \emph{higher} error recurrence than broader recomputation (26.6\% vs.\ 12.1\%),
direct evidence that fine-grained attribution is both unreliable and epistemically
costly. Masked Erosion~\citep{so2026masked} shows that acceptance gates scored on task
success silently erode redundant safeguards, because overlapping protections mask the
harm of any single deletion. Together they imply that a supervisor reading performance
signals cannot be the seat of trust. We therefore demote our Sidecar to a coarse
availability trigger and place the trust property in a layer no gate can erode.

\paragraph{Position.}
Prior systems either keep everything and never undo (Reflexion, ExpeL, DGM), or undo
and lose the evidence (checkpoint-based runtimes), or make undo verifiable without
asking what is learned afterwards (EvoUndo). None specifies the \emph{scope} of the
revert operator relative to the scope of learning evidence. Our claim is that this
scope relation, not the rollback mechanism, is what makes self-evolution trustworthy.
```

---

## 9. BibTeX（仅收录已核实的条目；venue 以 arXiv 为准，投稿前按最新状态更新）

```bibtex
@article{li2025agentgit,
  title   = {AgentGit: A Version Control Framework for Reliable and Scalable {LLM}-Powered Multi-Agent Systems},
  author  = {Li, Yang and Ping, Siqi and Chen, Xiyu and Qi, Xiaojian and Wang, Zigan and Luo, Ye and Zhang, Xiaowei},
  journal = {arXiv preprint arXiv:2511.00628},
  year    = {2025}
}

@article{zhao2026continual,
  title   = {Can Coding Agents Sustain Continual Evolution without Forgetting?},
  author  = {Zhao, Shangziqi and Zhang, Yitong and Li, Jia},
  journal = {arXiv preprint arXiv:2611.03219},
  year    = {2026}
}

@article{su2026chronomem,
  title   = {ChronoMem: Version Control and Semantic Rollback for Large Language Model Agent Memory},
  author  = {Su, Yongye and Xu, Wujiang and Zuo, Chaoji and Bertino, Elisa},
  journal = {arXiv preprint arXiv:2607.27773},
  year    = {2026}
}

@article{sah2026evoundo,
  title   = {EvoUndo: Recoverability-Constrained Self-Evolution for {LLM} Agent Harnesses},
  author  = {Sah, Tanmay and Sah, Dolly and Jain, Harshul and Sah, Tanya},
  journal = {arXiv preprint arXiv:2608.28363},
  year    = {2026}
}

@article{krentsel2026exo,
  title   = {Exo: An Architecture for Self-Improving Systems at Runtime},
  author  = {Krentsel, Alexander and Ratnasamy, Sylvia and Stoica, Ion and Casado, Martin and Goyal, Ankur},
  journal = {arXiv preprint arXiv:2611.00463},
  year    = {2026}
}

@article{zhang2026dgm,
  title   = {Darwin G{\"o}del Machine: Open-Ended Evolution of Self-Improving Agents},
  author  = {Zhang, Jenny and Hu, Shengran and Lu, Cong and Lange, Robert and Clune, Jeff},
  journal = {arXiv preprint arXiv:2505.22954},
  year    = {2026}
}

@article{wang2026antipersistence,
  title   = {More Memory, Worse Agents: Error Reproduction and Anti-Persistence in {LLM} Agents},
  author  = {Wang, Ruhan and Panaganti, Kishan and Zhou, Dongruo},
  journal = {arXiv preprint arXiv:2610.27406},
  year    = {2026}
}

@article{wang2026depguided,
  title   = {From Faulty Memories to Corrected Actions: Dependency-Guided Rollback Repair for Memory-Augmented Agents},
  author  = {Wang, Yiqi and Yu, Caili and Zhang, Jiaqi and Duan, Yiqun and Zheng, Mingkai and Wu, Zhangkai and Shi, Kaize and Cai, Taotao},
  journal = {arXiv preprint arXiv:2608.10502},
  year    = {2026}
}

@article{so2026masked,
  title   = {Masked Erosion: How Acceptance Gates Lose Redundant Safeguards in Self-Improving Agents},
  author  = {So, Hau-Sing and Liu, Daixian and Long, Weicai},
  journal = {arXiv preprint arXiv:2610.38392},
  year    = {2026}
}

@article{asawa2026clbench,
  title   = {Continual Learning Bench: Evaluating Frontier {AI} Systems in Real-World Stateful Environments},
  author  = {Asawa, Parth and Glaze, Christopher M. and Orlanski, Gabriel and Ramakrishnan, Ramya and Xu, Benji and Biswal, Asim and Chen, Vincent Sunn and Sala, Frederic and Zaharia, Matei and Gonzalez, Joseph E.},
  journal = {arXiv preprint arXiv:2606.05661},
  year    = {2026}
}

@inproceedings{shinn2023reflexion,
  title     = {Reflexion: Language Agents with Verbal Reinforcement Learning},
  author    = {Shinn, Noah and Cassano, Federico and Berman, Edward and Gopinath, Ashwin and Narasimhan, Karthik and Yao, Shunyu},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  year      = {2023}
}

@inproceedings{zhao2024expel,
  title     = {ExpeL: {LLM} Agents Are Experiential Learners},
  author    = {Zhao, Andrew and Huang, Daniel and Xu, Quentin and Lin, Matthieu and Liu, Yong-Jin and Huang, Gao},
  booktitle = {Proceedings of the AAAI Conference on Artificial Intelligence (AAAI)},
  year      = {2024}
}

@article{gao2026survey,
  title   = {A Survey of Self-Evolving Agents: What, When, How, and Where to Evolve on the Path to Artificial Super Intelligence},
  author  = {Gao, Huan-ang and Geng, Jiayi and Hua, Wenyue and Hu, Mengkang and Juan, Xinzhe and Liu, Hongzhang and Liu, Shilong and Qiu, Jiahao and Qi, Xuan and Wu, Yiran and others},
  journal = {Transactions on Machine Learning Research},
  year    = {2026}
}

@article{wang2024awm,
  title   = {Agent Workflow Memory},
  author  = {Wang, Zora Zhiruo and Mao, Jiayuan and Fried, Daniel and Neubig, Graham},
  journal = {arXiv preprint arXiv:2409.07429},
  year    = {2024}
}

@article{zhang2025aflow,
  title   = {AFlow: Automating Agentic Workflow Generation},
  author  = {Zhang, Jiayi and Xiang, Jinyu and Yu, Zhaoyang and others},
  journal = {International Conference on Learning Representations (ICLR)},
  year    = {2025}
}

@article{wang2023voyager,
  title   = {Voyager: An Open-Ended Embodied Agent with Large Language Models},
  author  = {Wang, Guanzhi and Xie, Yuqi and Jiang, Yunfan and Mandlekar, Ajay and Xiao, Chaowei and Zhu, Yuke and Fan, Linxi and Anandkumar, Anima},
  journal = {arXiv preprint arXiv:2305.16291},
  year    = {2023}
}
```

