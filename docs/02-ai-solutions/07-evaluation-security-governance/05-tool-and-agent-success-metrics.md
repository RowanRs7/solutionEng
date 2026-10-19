---
title: 工具调用与 Agent 任务成功率
slug: tool-and-agent-success-metrics
module: ai-solutions
stage: test-and-validate
type: core
difficulty: intermediate
duration: 50m
prerequisites:
  - layered-and-end-to-end-evaluation
outcomes:
  - 用业务终态而不是接口返回码定义 Agent 任务成功率
  - 计算工具选择 F1、平均步数、单任务成本并按失败原因分桶
  - 为带资金影响的工具设计幂等与审批相关的评测用例
last_reviewed: 2026-10-19
---

# 工具调用与 Agent 任务成功率

## 为什么需要学习

售后助手的退款 Agent 上线首周“成功率 99.2%”，因为这个指标统计的是工具接口返回 2xx 的比例。同期财务发现 12 笔订单被重复退款：Agent 在超时重试时再次调用了 `refund.create`，接口每次都返回成功，业务状态却错了两次。指标全绿，事故照发生。

问题的根不在模型，而在指标定义。**“工具调用没有报错”与“业务目标达成”是两件事**：参数可能超出退款上限、可能少调了写工单的步骤、可能在无权限时反复重试、也可能多调了一次不该调的写操作。这些都不会体现在接口返回码里。

> **核心结论：** Agent 的成功必须由外部业务终态定义——订单退款状态、工单字段、金额校验全部核对通过才算成功；工具调用成功率只是过程指标，不能当验收指标。

## 学习目标

完成本课后，你能够：

- 区分过程指标（工具 F1、步数、成本）与结果指标（目标达成率、严格成功率）。
- 为一条 Agent trace 定义期望工具集合，并计算工具调用 F1。
- 按规划、参数、工具、权限、超时、观测六类归因失败。
- 为资金类工具设计幂等、上限与审批相关的评测用例。

## 前置知识

- 回看上一课：[检索、生成与端到端分层评测](04-layered-and-end-to-end-evaluation.md)。
- 理解 Function Calling 的基本机制：模型输出结构化调用意图，由宿主程序执行并回填结果；可回看[工具调用、Workflow 与 Agent](../05-tools-and-agents/00-overview.md)。
- 知道幂等键（idempotency key）的作用。
- 能读懂 JSON、Python 字典与列表推导。

## 业务场景

售后助手的 Agent 环节要完成一条完整任务：

1. 读取订单状态（`order.get`）。
2. 检索适用政策（`policy.search`）。
3. 生成答复与退款建议，交人工确认。
4. 人工确认后调用退款（`refund.create`）。
5. 把处理结果写回工单（`ticket.update`）。

团队要回答：这条链路到底有多可靠？改一版规划 Prompt 之后是变好还是变差？成本与人工介入是否可接受？以及最关键的——出了重复退款这类事故，如何在下一次评测中复现它。

## 核心概念

| 指标 | 定义 | 回答的问题 | 类型 |
| --- | --- | --- | --- |
| *工具选择正确率* | 实际调用的工具集合与期望集合的匹配程度 | 该调的调了吗？不该调的调了吗？ | 过程 |
| *工具调用 F1* | 以期望调用为“正例”，综合精确率与召回率 | 调用序列整体有多接近？ | 过程 |
| *参数正确率* | 调用参数是否通过 schema 与业务校验 | 金额、订单号、类型对吗？ | 过程 |
| *目标达成率*（agent goal accuracy） | 外部状态核对后目标是否真正实现 | 钱真的退对了吗？ | 结果 |
| *严格成功率* | 目标达成且无多余写操作、无越权、无重复 | 可以放心自动化吗？ | 结果 |
| *平均步数* | 每任务的平均工具调用次数 | 是否绕路、是否反复重试？ | 效率 |
| *单任务成本* | token 费 + 工具调用费 + 重试成本 | 规模化后能不能扛住？ | 效率 |
| *人工介入率* | 需要人工修改或接管的任务占比 | Agent 是否真的减轻了负担？ | 体验 |

*Agent trace* 是一次任务执行的完整记录：每一步的输入、工具名、参数、返回、耗时与错误。它是所有 Agent 指标的唯一数据来源。

几个容易混淆的边界：

- *宽松成功率* 只看终态；*严格成功率* 还要求过程合规。生产门禁应看严格口径，对外沟通可以同时给两个数字。
- 工具 F1 对“顺序”不敏感（按集合计），而审批链路通常顺序敏感（必须先确认再退款），因此需要额外的顺序断言。
- 人工确认环节意味着“Agent 建议被采纳率”也是一个独立指标：建议常被改，说明生成侧不可用，而不是工具侧有问题。

<u>只统计接口返回码，等于把“工具没崩”当成“任务成功”。</u>

## 工作原理

一条可复现的 Agent 评测流程分七步：

1. **定义业务终态**：为每类任务写出可核对的外部状态，例如“订单 `refund_status` 为 `refunded`，退款金额等于应退金额，且 `refund` 表只有一条记录”。
2. **登记期望轨迹**：为每条用例写期望工具集合（必要项）与禁止项（如“已退款订单不得再调 `refund.create`”）。
3. **采集 trace**：记录每步工具名、参数、返回摘要、耗时、错误码，并打上任务 ID 与幂等键。
4. **过程判定**：算工具 F1、参数校验结果、步数是否超出上限、是否触发禁止项。
5. **结果判定**：回查业务系统终态，得出目标达成；同时判定是否重复写入或越权。
6. **失败归因**：按六类分桶（规划错、参数错、工具错、权限拒、超时、观测缺失），每桶单独跟踪趋势。
7. **门禁与看板**：把严格成功率、参数正确率、禁止项触发数设为发布门禁；成本与步数作为观测项，不单独阻断发布。

第 6 步的分桶决定改进方向。典型归因：

- *规划错*：该调未调、顺序颠倒、循环重试。
- *参数错*：金额、订单号、退款类型不符合业务规则。
- *工具错*：下游接口返回业务错误（如订单已关闭）。
- *权限拒*：Agent 身份无权限，或越权访问他人订单。
- *超时*：外部依赖慢，触发重试并放大风险。
- *观测缺失*：日志里没有参数或返回，无法归因——这本身是缺陷。

## 架构与选型

| 判定方式 | 适用 | 成本 | 盲区 |
| --- | --- | --- | --- |
| 轨迹比对（期望工具集合） | 流程固定的 Workflow | 低 | 无法判断业务是否正确 |
| 终态核对（查业务系统） | 有资金或状态变更的任务 | 中 | 需要测试环境与可回滚数据 |
| 人工复核 trace | 高风险、规则不明确 | 高 | 不可每日全量 |
| 线上指标（采纳率、投诉） | 上线后监控 | 低 | 反馈滞后，难归因 |

选型依据是**可逆性**：可逆操作（查询、草稿）用轨迹比对即可；不可逆操作（退款、发货、改价）必须终态核对，并保留人工确认作为最后闸门。

另一个权衡是顺序敏感度：把工具调用当集合计，实现简单、对无关调用宽容，但会漏掉“先退款后确认”这类顺序违规。涉及审批的场景应显式断言顺序，或直接检查“确认动作的时间戳早于资金动作”。

## 最小示例

下面的脚本从一组 trace 计算严格成功率、工具 F1、平均步数、成本与失败分布。环境：Python 3.8+，仅标准库。

```python
from collections import Counter

TRACES = [
    {"id": "t1", "expected": ["order.get", "policy.search", "refund.create"],
     "actual": ["order.get", "policy.search", "refund.create"],
     "params_ok": True, "final_state_ok": True, "steps": 3, "cost": 0.012, "fail": "none"},
    {"id": "t2", "expected": ["order.get", "policy.search", "refund.create"],
     "actual": ["order.get", "policy.search", "refund.create", "refund.create"],
     "params_ok": True, "final_state_ok": False, "steps": 4, "cost": 0.018, "fail": "duplicate_refund"},
    {"id": "t3", "expected": ["order.get", "policy.search"],
     "actual": ["order.get"],
     "params_ok": True, "final_state_ok": False, "steps": 1, "cost": 0.004, "fail": "missing_tool"},
    {"id": "t4", "expected": ["order.get", "refund.create"],
     "actual": ["order.get", "refund.create"],
     "params_ok": False, "final_state_ok": False, "steps": 2, "cost": 0.009, "fail": "bad_params"},
    {"id": "t5", "expected": ["order.get", "refund.create", "ticket.update"],
     "actual": ["order.get", "refund.create", "ticket.update"],
     "params_ok": True, "final_state_ok": True, "steps": 3, "cost": 0.011, "fail": "none"},
    {"id": "t6", "expected": ["order.get", "policy.search", "refund.create", "ticket.update"],
     "actual": ["order.get", "policy.search", "ticket.update"],
     "params_ok": True, "final_state_ok": False, "steps": 3, "cost": 0.010, "fail": "missing_tool"},
    {"id": "t7", "expected": ["order.get", "refund.create"],
     "actual": ["order.get", "refund.create"],
     "params_ok": True, "final_state_ok": False, "steps": 2, "cost": 0.008, "fail": "permission_denied"},
    {"id": "t8", "expected": ["order.get", "policy.search", "ticket.update"],
     "actual": ["order.get", "policy.search", "ticket.update"],
     "params_ok": True, "final_state_ok": True, "steps": 3, "cost": 0.013, "fail": "none"},
]

def tool_f1(expected, actual):
    """按多重集合计算 F1：重复调用会被计入分母，因此重复退款会拉低分数。"""
    e, a = Counter(expected), Counter(actual)
    matched = sum((e & a).values())       # 交集大小 = 正确调用的次数
    if not expected or not actual:
        return 0.0                        # 空轨迹视为失败，避免 0/0 被当成满分
    p = matched / len(actual)             # 精确率：调用的工具里多少是必要的
    r = matched / len(expected)           # 召回率：必要的工具里调了多少
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)

n = len(TRACES)
strict_ok = sum(1 for t in TRACES if t["final_state_ok"] and t["fail"] == "none")  # 终态对且无违规
f1s = [tool_f1(t["expected"], t["actual"]) for t in TRACES]

print(f"任务数: {n}")
print(f"严格成功率: {strict_ok / n:.3f} ({strict_ok}/{n})")
print(f"工具调用 F1 均值: {sum(f1s) / n:.3f}")
print(f"平均步数: {sum(t['steps'] for t in TRACES) / n:.2f}")
print(f"单任务成本均值: {sum(t['cost'] for t in TRACES) / n:.4f} USD")
print("失败分布:", dict(Counter(t["fail"] for t in TRACES if t["fail"] != "none")))
print("低 F1 任务:", [(t["id"], round(f, 3)) for t, f in zip(TRACES, f1s) if f < 0.9])
```

输出（本机 `python3` 实测）：

```text
任务数: 8
严格成功率: 0.375 (3/8)
工具调用 F1 均值: 0.923
平均步数: 2.62
单任务成本均值: 0.0106 USD
失败分布: {'duplicate_refund': 1, 'missing_tool': 2, 'bad_params': 1, 'permission_denied': 1}
低 F1 任务: [('t2', 0.857), ('t3', 0.667), ('t6', 0.857)]
```

这张表最值得看的是对比：工具 F1 高达 0.923，严格成功率只有 0.375。**过程看起来很像样，结果却有六成任务不合格。** 如果只看 F1，`t7` 会被判为完美（调用序列完全正确），但它在权限层失败；`t4` 序列也对，参数却越过了退款上限。这说明必须把“序列正确”“参数合法”“终态达成”拆开统计，缺一项都会误判。

把 `fail` 字段做成枚举而不是自由文本，是让归因可聚合的关键；否则半年后没人能统计“重复退款占比”。

## 动手实验

前置条件：Python 3.8+；保存脚本为 `/tmp/agent_metrics.py`；建议先准备一张空表记录每次运行的三个核心数字。

步骤：

1. 原样运行，核对输出。
2. 把 `t2` 的 `fail` 改为 `none`、`final_state_ok` 改为 `True`（模拟补上幂等键），观察严格成功率与失败分布变化。
3. 给 `t3` 的 `actual` 补上 `policy.search`，观察其 F1 是否升到 1.0，并判断严格成功率是否回升（应仍不回升，因为终态未达成）。
4. 把 `t7` 的 `fail` 从自由文本改为 `"permission_denied"` 以外的拼写错误（如 `"perm_denied"`），观察失败分布中出现两个相近桶——体会枚举约束的必要性。

预期结果：第 2 步严格成功率升到 0.50，失败分布减少一项；第 3 步 F1 均值上升但严格成功率不变，说明过程指标不能替代结果指标；第 4 步失败分布被拆成两个桶，聚合结论失真。

验证方法：改完对照手算的严格成功数与 F1 均值；若严格成功率上升而终态字段没改，说明判定逻辑被绕过。

清理方法：`rm /tmp/agent_metrics.py`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 成功率很高但业务投诉不断 | 用接口返回码代替业务终态 | 抽 10 条“成功”任务回查订单状态 | 改为终态核对，补禁止项断言 |
| 出现重复退款 | 重试未做幂等，且指标不检查重复写入 | 查 trace 中同一幂等键的调用次数 | 工具侧强制幂等键，评测加“重复即失败” |
| 平均步数逐周上升 | 规划退化为试探式调用 | 对比步数分布与失败桶 | 缩短可用工具列表，明确停止条件 |
| 成本核算与账单差距大 | 只统计了模型 token，漏了工具与重试成本 | 用 trace 汇总调用次数与重试次数 | 把工具成本与重试成本纳入单任务成本 |
| 失败原因无法聚合 | 归因字段是自由文本 | 统计 `fail` 字段的唯一值数量 | 改为受控枚举，未知值单独入桶 |

## 安全与生产注意事项

**<u>资金类工具缺少幂等与上限校验，是 AI 应用最常见的不可逆事故。</u>** 重试、并发、人工重复点击都会触发二次执行。工具侧必须要求幂等键、金额上限与状态前置条件（`refund_status` 为可退），评测侧必须有“重复调用即失败”的用例。

**<u>Agent 拥有超出任务所需的工具或权限，等价于把越权风险交给模型判断。</u>** OWASP 在 LLM03:2026 Excessive Agency 中把根因归为功能过多、权限过大、自主性过高三类（2025 版编号为 LLM06），对应缓解是缩小工具集、最小权限、关键动作保留人工审批。评测时应专门构造“无权限任务”用例，验证 Agent 会停下并转人工，而不是尝试绕过。

另外两条生产习惯：为每次任务保留幂等键与 trace ID，事故时才能还原调用序列；对外报告成功率时同时给出口径（严格/宽松）与样本量，避免把过程指标当作验收结论。

## 本课总结

- **Agent 的成功由外部业务终态定义，工具返回码只是过程信息。**
- 过程指标（F1、步数、成本）用于定位与优化，结果指标（目标达成、严格成功率）用于验收。
- 工具调用 F1 高不代表任务成功：参数违规、权限拒绝、终态错误都不会体现在调用序列上。
- 失败必须按受控枚举归因，否则无法聚合并判断改进方向。
- 资金类工具必须评测幂等、上限、状态前置与人工审批，并把“重复执行”直接判为失败。

## 思考题

如果严格成功率只有 0.375，但客服反馈“比以前省事多了”，你会如何解释这个矛盾？应该改指标还是改流程？

参考思路：先分清两种“省事”——Agent 把检索和草稿做完了，人工只需确认与修改，即使终态自动化成功率低，人力节省仍然真实。此时应补充“人工修改率”“建议采纳率”“每单节省分钟数”等指标，同时保留严格成功率作为自动化扩展的前置条件。指标不是二选一，而是分层：体验层看节省，安全层看严格成功，两者同时上报。

## 小测

1. 某 Agent 工具调用 F1 为 1.0，被判定为“任务成功”，这种做法的问题是：

   A. 没有问题　B. 忽略参数与终态校验　C. F1 只适用于检索　D. F1 无法计算

2. 为什么要区分严格成功率与宽松成功率？
3. “重复退款”应该被归入哪一类失败？为什么它必须直接判为失败？
4. 单任务成本除了模型 token，还应包含哪些？
5. 场景题：新版规划 Prompt 把平均步数从 2.6 提到 4.1，严格成功率从 0.62 升到 0.68。你会发布吗？给出判断依据与需要的补充信息。

## 答案与解析

1. **B。**F1 只比较调用集合，`t4` 这类参数越限、`t7` 这类权限失败都能拿到满分。A 错在混淆过程与结果；C 错在 Agent 场景同样适用；D 错在 F1 可计算，只是不足以判定成功。
2. 严格口径要求过程合规（无重复、无越权、无多余写操作），用于自动化门禁；宽松口径只看终态，用于与非技术方沟通。两者并列可避免“数字好看但不安全”。
3. 归入工具/幂等类失败（也可单列“重复执行”桶）。它必须判失败，因为资金操作不可逆，且模型重试行为在同类任务中会重复出现；把它计入成功会掩盖系统性风险。
4. 工具调用费用、重试带来的重复模型调用、人工接管的人力成本、外部 API 与存储成本。漏掉重试成本会系统性低估真实开销。
5. 不能直接发布。依据是：成功率提升 6 个点可能显著，但步数增加 58% 意味着更多工具调用、更高成本与更多不可逆风险敞口。需要补充信息：成本变化、延迟 p95、越权与重复执行次数、失败分布是否转移、样本量与差异是否超出噪声。若成本可控且安全指标不退化，可先灰度小比例。

## 延伸阅读与下一课

- Ragas 的 Agent/工具类指标（Tool Call Accuracy、Tool Call F1、Agent Goal Accuracy）：[List of available metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- promptfoo 的轨迹断言（`tool-call-f1`、`trajectory:tool-sequence`、`trajectory:step-count` 等，可直接用于 CI）：[Deterministic metrics](https://www.promptfoo.dev/docs/configuration/expected-outputs/deterministic/)
- OWASP LLM03:2026 Excessive Agency（功能过多、权限过大、自主性过高的风险与缓解；2025 版编号为 LLM06）：[LLM06:2025 Excessive Agency（2025 版页面）](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- 工具与指标清单复核截至 2026-10；框架的断言名称与参数可能随版本变化。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[检索、生成与端到端分层评测](04-layered-and-end-to-end-evaluation.md)。
- 下一课：[人工评审与 LLM-as-a-Judge](06-human-review-and-llm-as-a-judge.md)。
