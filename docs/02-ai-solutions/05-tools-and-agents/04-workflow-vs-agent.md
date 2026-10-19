---
title: Workflow 与 Agent 的区别
slug: workflow-vs-agent
module: ai-solutions
stage: design
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - tool-permissions-and-least-privilege
outcomes:
  - 用控制流归属区分 workflow 与 agent，并各给一个适用场景
  - 为一条业务链路选择编排方式并写出判断依据
  - 识别“用 Agent 解决固定流程”造成的成本与可测性问题
last_reviewed: 2026-10-19
---

# Workflow 与 Agent 的区别

## 为什么需要学习

售后助手上线两个月后，团队做了复盘：同样的提问“耳机坏了能退吗”，有时 2 秒返回，有时 18 秒；QA 写不出稳定用例，因为每次工具调用顺序都不一样；而日志聚类显示，82% 的会话其实落在四类固定诉求上——查时效、查订单、算金额、提交退款。

问题不在于模型不够强，而在于把可枚举的流程交给了不可枚举的决策者。Anthropic 在其工程文章里给出的区分很干脆：*workflow* 是用预定义代码路径编排模型与工具的系统；*agent* 是由模型动态决定过程与工具使用的系统。两者都属于 *agentic system*，但控制权归属不同。

> **核心结论：** 默认用 workflow，只有当步骤无法预先枚举、且错误可回滚或可被外部信号验证时，才引入 agent。

## 学习目标

完成本课后，你能够：

- 用“谁决定下一步”区分 workflow 与 agent，并说明这一区分带来的工程后果。
- 为一条具体业务链路选出编排方式，并写出三条以上判断依据。
- 指出把固定流程做成 agent 后，在延迟、成本、可测性上的具体损失。
- 设计“确定性主干 + 受限 agent 节点”的混合方案。

## 前置知识

- 回看上一课：[工具权限、校验与最小授权](03-tool-permissions-and-least-privilege.md)。
- 理解有向无环图（DAG）与顺序执行的基本概念。
- 了解“可枚举步骤”与“探索性任务”的区别，例如按固定模板开票与排查一个陌生线上故障。

## 业务场景

晴空商城售后入口每天处理约 900 张工单。按诉求分布：政策咨询 35%、订单状态 25%、退款资格判断 22%、退款提交 10%、其他 8%。

前四类都能写成明确步骤，且每一步的输入输出已知；只有“其他”分支里混合了投诉、重复退款、跨境售后等长尾情况，步骤难以预先枚举。

团队最初的方案是“一个 agent 全包”，现在的目标是把编排改成与诉求分布匹配的形状。

## 核心概念

| 术语 | 含义 | 谁决定下一步 |
| --- | --- | --- |
| *workflow* | 预定义代码路径串联模型与工具 | 代码 |
| *agent* | 模型在循环中依据反馈自行选择工具与终止 | 模型 |
| *路由*（routing） | 先分类再送入专用处理链 | 代码 + 分类器 |
| *提示链*（prompt chaining） | 上一步输出作为下一步输入，可插入校验门 | 代码 |
| *编排者-工作者* | 中心模型动态拆解任务并分派给工作者 | 模型（限定在子任务层） |
| *自主性预算* | 对 agent 的步数、工具范围、花费设上限 | 代码 |
| *检查点* | 在人可审阅的位置暂停并等待确认 | 代码 |

Anthropic 总结的五种 workflow 模式可以直接当作设计词汇表：

| 模式 | 结构 | 售后场景用法 |
| --- | --- | --- |
| 提示链 | 串行，步间可加校验 | 抽取诉求 → 查时效 → 生成答复 |
| 路由 | 分类后分流 | 四类诉求进不同子流程 |
| 并行 | 同时跑子任务再聚合 | 同时查订单与物流，汇总后判断 |
| 编排者-工作者 | 中心模型动态分派 | 长尾工单先拆解再处理 |
| 评估者-优化器 | 生成 → 评审 → 修订 | 答复草稿的合规性复核 |

## 工作原理

两种编排方式的执行机制差异体现在三个层面：

1. **控制流来源。** workflow 的下一步从图的边上取，是静态的；agent 的下一步来自模型输出，是运行时生成的。前者可以在部署前画出完整路径，后者只能画出“可能的路径”。
2. **状态与恢复。** workflow 的每个节点是幂等函数，失败可从检查点重放；agent 的中间状态包括模型消息历史，恢复需要序列化整个运行态（第 5 课展开）。
3. **终止判定。** workflow 在图的终点结束，可证明不循环；agent 依靠模型输出“我完成了”或应用侧硬上限，两者的可信度不同。

一条推荐的落地路径是混合：

1. 用确定性代码做入口分类（规则 + 小模型），命中已知类别即进入对应 workflow。
2. workflow 中的每个节点仍是可测试函数，工具调用只发生在节点内部。
3. 长尾分支进入受限 agent：限定工具白名单、最大步数、只能用只读工具。
4. 需要写操作时，从 agent 退回 workflow：由代码接管审批与执行。

**混合方案的关键不是“都上”，而是把不可逆动作永远留在确定性一侧。**

## 架构与选型

| 维度 | workflow | agent |
| --- | --- | --- |
| 路径可预测性 | 完全可枚举 | 运行时生成，只能约束 |
| 单次延迟 | 稳定，等于各节点之和 | 波动大，取决于轮数 |
| 单次成本 | 可预估 | 上不封顶，需预算控制 |
| 可测试性 | 可按节点写断言与回归集 | 需轨迹级评测与人工抽检 |
| 故障影响 | 局部，易定位 | 可能级联，难复现 |
| 适配条件 | 步骤稳定、合规要求高、需审计 | 步骤开放、需探索、有外部验证信号 |

选型判断可归纳为三个问题：**步骤能不能在部署前写出来？错误代价是否可逆？失败时有没有外部信号告诉我错了？** 三个都肯定，用 workflow；第三个不肯定，说明还缺评测与校验能力，此时上 agent 只是把不确定性推给线上。

## 最小示例

下面用同一句诉求分别跑 workflow 与 agent，比较轨迹。它把一个常见直觉演示得很清楚：agent 可能省步骤，也可能漏掉关键步骤。

```python
# 1) 权威数据：固定输入，便于复现
ORDER = {"order_id": "SO-2026-0001", "status": "delivered", "paid": 399.0, "days_since_sign": 5}
POLICY = {"quality_window_days": 15, "seven_day_no_reason": 7}

# 2) workflow 的每个节点都是纯函数，可以单独测试
def step_classify(text):
    return "quality" if ("坏" in text or "没声音" in text) else "seven_day"

def step_fetch_order(_intent):
    return ORDER

def step_fetch_policy(_order):
    return POLICY

def step_decide(intent, order, policy):
    if intent == "quality":
        return {"refundable": order["days_since_sign"] <= policy["quality_window_days"]}
    return {"refundable": order["days_since_sign"] <= policy["seven_day_no_reason"]}

def step_draft(result):
    return "可退" if result["refundable"] else "超出时效"

def workflow(text):
    """路径在代码里写死：顺序不会因输入而改变。"""
    trace = []
    intent = step_classify(text); trace.append("classify")
    order = step_fetch_order(intent); trace.append("fetch_order")
    policy = step_fetch_policy(order); trace.append("fetch_policy")
    result = step_decide(intent, order, policy); trace.append("decide")
    reply = step_draft(result); trace.append("draft")
    return trace, reply

# 3) 用脚本模拟"模型自己决定顺序"：真实 agent 由模型逐轮选择
AGENT_PLANS = {
    "帮我看看耳机能不能退": ["fetch_policy", "fetch_order", "fetch_policy", "draft"],
    "耳机坏了能退吗": ["fetch_order", "draft"],
}

def agent_loop(text, max_steps=3):
    trace = []
    plan = AGENT_PLANS.get(text, ["fetch_order"])
    for step in plan:
        if len(trace) >= max_steps:            # 4) 自主性预算：没有它，循环可能不收敛
            trace.append("stop:max_steps")
            break
        trace.append(step)
        if step == "draft":                    # 5) 模型自称完成即退出，可靠性低于图的终点
            break
    return trace

for text in ["耳机坏了能退吗", "帮我看看耳机能不能退"]:
    t1, reply = workflow(text)
    t2 = agent_loop(text)
    print(f"{text}\n  workflow({len(t1)} 步): {t1} -> {reply}\n  agent   ({len(t2)} 步): {t2}")
```

预期输出：

```text
耳机坏了能退吗
  workflow(5 步): ['classify', 'fetch_order', 'fetch_policy', 'decide', 'draft'] -> 可退
  agent   (2 步): ['fetch_order', 'draft']
帮我看看耳机能不能退
  workflow(5 步): ['classify', 'fetch_order', 'fetch_policy', 'decide', 'draft'] -> 可退
  agent   (4 步): ['fetch_policy', 'fetch_order', 'fetch_policy', 'stop:max_steps']
```

第一句里 agent 少了两步，也漏掉了政策查询——结论看起来一样，但过程不可审计；如果时效改变，它会给出错误答案。第二句里 agent 重复查询并撞上步数上限。workflow 两次轨迹完全一致，因此回归测试可以按节点断言。

## 动手实验

**前置条件**：Python 3.9+，保存为 `flow_vs_agent.py`。

**步骤**：

1. 运行一次，记录两种方式的步数与输出。
2. 把 `max_steps` 改成 1，观察 agent 的轨迹与失败方式。
3. 在 workflow 的 `step_decide` 前插入一个 `step_guard`（例如检查订单状态），验证插入不影响其他节点。
4. 在 `AGENT_PLANS` 里给第一句补一个“先查政策”的计划，观察轨迹变化但仍不可预测。

**预期结果**：步骤 2 中 agent 在 `max_steps=1` 时仅执行第一步并停下，输出不含结论；步骤 3 只多一步 `guard`，其余节点与输出不变。

**验证方法**：为 `step_decide` 写参数化用例（签收 3/5/8/20 天），确认结果与时效表一致；对 agent 轨迹做“必须包含 fetch_policy”的断言。

**清理方法**：删除脚本；示例无网络调用、无持久化。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 同一问题响应时间波动 10 倍 | 固定流程跑在 agent 里，轮数不定 | 统计每会话模型调用次数分布 | 把已知类别改回 workflow，限制 agent 步数 |
| 回答偶尔漏掉政策依据 | agent 自行跳过检索步骤 | 对轨迹做“必须包含某工具”断言 | 把检索设为 workflow 必经节点 |
| 发布前无法评估影响 | 没有可枚举路径 | 尝试画出完整流程图，若画不出即不可枚举 | 先补路径枚举，再谈自主性 |
| agent 越权或误调用写工具 | 工具白名单过宽 | 检查该节点可用工具列表 | 长尾节点只给只读工具，写操作回 workflow |
| 成本随使用量线性失控 | 没有自主性预算 | 看 token 与调用次数的 P95 | 加步数、预算、超时三重上限 |

## 安全与生产注意事项

**<u>自主性本身就是攻击面：每多一个可选工具，注入成功后的破坏范围就扩大一圈。</u>** 长尾分支应使用最小工具集，并保持人在环上的确认；OWASP 将“过度自主性”列为 Excessive Agency 的根因之一，并建议对高后果、不可逆动作强制人工审批。

**<u>不要用 agent 处理有资金或合规影响的主干流程。</u>** 主干用 workflow 的价值不只是稳定，更是可审计：审批、参数快照、幂等键都能挂在确定的节点上；把这些散落在模型自由选择里，出事时无法复现。

## 本课总结

- **区分标准是控制流归属**：代码决定路径是 workflow，模型决定路径是 agent。
- 先算诉求分布，再选编排：占比高且步骤固定的部分适合 workflow。
- agent 换来灵活性，代价是延迟、成本、可测性与故障可复现性。
- 混合方案把长尾交给受限 agent，把不可逆动作留在确定性一侧。
- 没有外部验证信号时，agent 的“自我完成”不是可靠终止条件。

## 思考题

如果业务方坚持“全流程都要 agent，因为听起来更先进”，你会用哪三个可量化的实验说服对方？请写出实验设计、指标，以及你愿意接受的结论反转条件。

参考思路：选同一批工单做 A/B——指标取任务成功率、P95 延迟、单会话成本、人工返工率；实验需固定工具集与权限。若 agent 在长尾类别的成功率显著更高且返工更低，就接受在长尾上扩大 agent 范围；反转条件是主干类别的可测性下降或成本超预算。

## 小测

1. workflow 与 agent 的核心区别是什么？
2. 下列任务最适合 agent 的是：  
   A. 按模板开具增值税发票　B. 处理规则固定、需审计的退款审批　C. 排查一个从未见过的线上故障　D. 每日固定时间导出报表
3. 为什么 agent 更难写回归测试？
4. “确定性主干 + 受限 agent 节点”中，写操作应放在哪一侧，为什么？
5. 场景题：四类诉求占 82%，团队仍用单一 agent 处理。请给出改造顺序，并说明每一步如何验证。

## 答案与解析

1. 控制流归属：workflow 的路径由代码预先定义，agent 由模型在运行时决定工具与顺序。由此派生出延迟、成本、可测性与可审计性的全部差异。
2. **C。** 步骤无法预先枚举，需要边探测边调整，且有外部信号（报错、日志）验证对错。A、B、D 都是步骤稳定、要求可审计的流程，更适合 workflow。
3. 因为测试要断言“给定输入产生什么行为”，而 agent 的中间路径每次可能不同，断言对象从确定性输出变成轨迹分布。可测性下降意味着必须用轨迹级评测与抽检补偿，成本更高。
4. 放在确定性一侧。写操作不可逆，需要参数快照、审批令牌与幂等键，这些都要求执行点稳定可复现；放在模型自由选择的路径里，出事后难以定位与补偿。
5. 顺序：先按诉求分类统计真实占比，再把四类主干改写成 workflow 节点（保留原提示与工具），然后给长尾配只读工具与步数上限，最后加轨迹断言与成本面板。每步验证：分类准确率、主干回归集通过率、P95 延迟与单会话成本、人工返工率。

## 延伸阅读与下一课

- Anthropic Engineering：[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)（2024-12-19；workflow 与 agent 的权威定义、五种 workflow 模式、何时不该用 agent；截至 2026-10-19 复核可访问，文中提示工具生态已变化）。
- Microsoft Learn：[How to use function calling with Microsoft Foundry Models](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/function-calling)（`tool_choice` 可用于收窄模型选择，对应“受控自主性”的实现手段）。
- OWASP GenAI：[LLM03:2026 Excessive Agency](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/)（过度自主性的定义与控制建议）。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[工具权限、校验与最小授权](03-tool-permissions-and-least-privilege.md)。
- 下一课：[状态机、分支、循环与人工审批](05-state-machines-branches-and-approval.md)。
