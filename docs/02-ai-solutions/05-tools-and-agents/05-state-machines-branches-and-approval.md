---
title: 状态机、分支、循环与人工审批
slug: state-machines-branches-and-approval
module: ai-solutions
stage: design
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - workflow-vs-agent
outcomes:
  - 为一条退款链路画出状态、事件与守卫条件
  - 实现审批断点：持久化、超时、参数绑定与恢复
  - 设计循环与重试的上限，避免无进展空转
last_reviewed: 2026-10-19
---

# 状态机、分支、循环与人工审批

## 为什么需要学习

“客服说可以退”是售后团队最怕的一句话。它不在系统里，无法证明；三天后客服点了“同意”，订单状态已经变成“已退款”，于是重复退了一次；模型重试超时的那次请求，其实已经成功，只是响应丢了。

这些事故的共同点不是模型不聪明，而是**流程状态没有被显式记录**：谁在等什么、等多久、等到的批准覆盖哪些参数，全散落在对话与人的记忆里。

> **核心结论：** 把人机协作写成显式状态机——状态可查、转移由代码判定、审批绑定参数与时限，恢复时才能不重不漏。

## 学习目标

完成本课后，你能够：

- 为退款链路列出状态、允许事件与守卫条件，并说明非法转移的处理方式。
- 实现一个带超时的审批断点：挂起、序列化、恢复、过期判定。
- 用参数哈希绑定审批内容，识别“批小执行大”的参数漂移。
- 给循环与重试设置上限与升级路径，区分可恢复与需人工介入的失败。

## 前置知识

- 回看上一课：[Workflow 与 Agent 的区别](04-workflow-vs-agent.md)。
- 了解有限状态机的基本要素：状态、事件、转移。
- 了解幂等键与“至少一次投递”为什么要求操作可重复执行。

## 业务场景

售后助手在两条路径上都要等人：超额退款（>200 元）与人工复核（客户申请第二次退款）。

主管李工每天要在后台处理约 120 条待审批请求，其中一部分是三天前发起的、订单状态早已变化；还有一部分因为客服和客户是同一个账号而形同虚设。团队决定把审批做成一个独立的状态机，与对话解耦。

## 核心概念

| 术语 | 含义 | 在退款链路中的体现 |
| --- | --- | --- |
| *状态* | 流程当前所处的可枚举阶段 | 草稿、待审批、已批准、已执行、已拒绝、已过期 |
| *事件* | 触发转移的动作 | `submit`、`approve`、`reject`、`expire`、`execute` |
| *守卫*（guard） | 转移必须满足的条件 | 审批人 ≠ 发起人；未过期；参数未变 |
| *审批断点* | 流程暂停、状态落库、等待人工决定的点 | `awaiting_approval` |
| *序列化* | 把挂起时的运行态存成可恢复的数据 | 消息历史 + 状态 + 参数快照 |
| *超时/过期* | 超过时限后状态必须变化 | 30 分钟未决即 `expired` |
| *升级* | 超时后转给更高权限或更强约束 | 超时 2 次升级到组长 |
| *补偿* | 已执行但业务失败的补救动作 | 退款成功但订单未标记，需对账修复 |

一个可用的状态表如下（节选）：

| 状态 | 允许事件 | 守卫 | 超时行为 |
| --- | --- | --- | --- |
| 草稿 | submit | 参数通过校验 | 24 小时未提交则丢弃 |
| 待审批 | approve / reject / expire | 审批人合法、未过期 | 到期自动转 `expired` |
| 已批准 | execute | 参数哈希与批准时一致 | 未执行 2 小时后告警 |
| 已执行 | 无 | — | 只允许补偿，不允许再次执行 |

## 工作原理

审批断点的完整生命周期有六步：

1. **到达断点。** 工具调用被判为需审批，代码创建一条审批记录，状态 `awaiting_approval`，同时保存参数快照、参数哈希、发起人、到期时间。
2. **挂起运行。** 序列化当前运行态（消息历史、已完成的工具结果、下一步意图）并落库，返回“已受理，等待审批”。不同框架叫法不同，OpenAI Agents SDK 把这类暂停暴露为 `interruptions`，并支持把 `RunState` 序列化为 JSON 后恢复。
3. **人工决定。** 审批界面展示的是**具体参数**（订单号、金额、原因），不是“退款”这个抽象动作；决定写入审批记录。
4. **恢复。** 从持久化状态恢复运行，把决定作为一条可读的结果注入上下文（例如“审批被拒绝，原因是金额超限”），让模型据此改变答复。
5. **执行前复核。** 执行时再次比对参数哈希与订单状态。状态已变（已退款、已取消）就终止并告警，而不是继续。
6. **收尾与审计。** 记录主体、审批人、参数、时间、结果、追踪号；对超时与拒绝分别统计。

循环与重试要围绕这张表设计：

- **重试只针对可重试错误**（超时、限流、5xx），且必须复用同一幂等键。
- **给每次运行设重试预算**，例如同一工具最多 3 次、整条链路最多 2 轮重试。
- **无进展检测**：连续两次调用同一工具、同一参数且结果相同，视为空转，终止并转人工。
- **终止后必须留下状态**，不能“默默结束”，否则用户看到的是永远转圈。

## 架构与选型

| 状态存储方式 | 适用 | 代价 |
| --- | --- | --- |
| 进程内存 | 单机演示、短会话 | 重启即丢，无法跨实例恢复 |
| 数据库表 + 状态字段 | 绝大多数业务审批、需要查询与统计 | 需要迁移、并发控制与索引设计 |
| 队列 + 任务状态 | 长任务、需要重放与重试 | 运维复杂度上升，需处理重复投递 |
| 工作流引擎（如 Temporal 类） | 多步骤、长周期、强一致恢复 | 引入新基础设施与学习成本 |

分支与循环的设计建议：**把分支写成显式的守卫表，把循环写成带预算的有限自动机。** 分支散落在提示词里会让“为什么走了这条路”无法回答；循环没有预算会让成本与副作用都不可控。

## 最小示例

下面的状态机只用标准库，演示自批被拒、过期被拒、参数漂移被拒。运行环境 Python 3.9+。

```python
import hashlib
from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)   # 1) 固定时间，便于复现

# 2) 转移表：谁在什么状态下允许发生什么，一眼可查
TRANSITIONS = {
    "draft": {"submit": "awaiting_approval"},
    "awaiting_approval": {"approve": "approved", "reject": "rejected", "expire": "expired"},
    "approved": {"execute": "executed"},
    "executed": {},
    "rejected": {},
    "expired": {},
}

def params_hash(params):
    """把参数折成短哈希：审批绑定内容，执行前复核是否被改过。"""
    return hashlib.sha256(repr(sorted(params.items())).encode()).hexdigest()[:12]

def transition(state, event, now, ctx):
    allowed = TRANSITIONS.get(state["status"], {})
    if event not in allowed:                      # 3) 非法转移不抛异常，返回可解释的拒绝
        return state, f"rejected:event_not_allowed_in_{state['status']}"
    if event == "approve":
        if ctx["approver"] == state["requester"]:  # 4) 发起人不得自批
            return state, "rejected:self_approval"
        if now >= state["expires_at"]:             # 5) 过期审批一律不生效
            return state, "rejected:approval_expired"
    if event == "execute":
        if params_hash(ctx["params"]) != state["params_hash"]:
            return state, "rejected:params_drifted"  # 6) 防"批小执行大"
    if event == "expire" and now < state["expires_at"]:
        return state, "rejected:not_yet_expired"
    return {**state, "status": allowed[event],
            "updated_at": now.isoformat()}, "ok"

def new_request(requester, params, ttl_minutes=30):
    return {"status": "draft", "requester": requester,
            "params_hash": params_hash(params),
            "expires_at": T0 + timedelta(minutes=ttl_minutes)}

req = new_request("C-1001", {"order_id": "SO-2026-0001", "amount": 399})
req, m1 = transition(req, "submit", T0, {})
req, m2 = transition(req, "approve", T0 + timedelta(minutes=5),
                     {"approver": "C-1001"})       # 自批
req, m3 = transition(req, "approve", T0 + timedelta(minutes=40),
                     {"approver": "A-2001"})       # 过期后审批
req, m4 = transition(req, "approve", T0 + timedelta(minutes=5),
                     {"approver": "A-2001"})       # 合法审批
req, m5 = transition(req, "execute", T0 + timedelta(minutes=6),
                     {"params": {"order_id": "SO-2026-0001", "amount": 3999}})
req, m6 = transition(req, "execute", T0 + timedelta(minutes=6),
                     {"params": {"order_id": "SO-2026-0001", "amount": 399}})
print(req["status"], [m1, m2, m3, m4, m5, m6])
```

预期输出：

```text
executed ['ok', 'rejected:self_approval', 'rejected:approval_expired', 'ok', 'rejected:params_drifted', 'ok']
```

读法：非法转移只返回拒绝理由、状态不变，因此重复投递同一事件不会产生第二笔退款；`execute` 前的哈希比对把“审批通过的是 399 元”这件事写进了代码。

## 动手实验

**前置条件**：Python 3.9+，保存为 `approval_sm.py`。

**步骤**：

1. 运行一次，核对输出顺序与状态。
2. 增加一个 `expire` 事件，分别在到期前后触发，确认 `not_yet_expired` 与 `expired` 的差别。
3. 在 `transition` 中加入重试计数：同一状态下 `execute` 失败超过 2 次转 `manual_review`。
4. 把 `expires_at` 改成已过去的时间，验证“恢复后第一件事是检查超时”。

**预期结果**：步骤 2 得到 `awaiting_approval` 与 `expired` 两个不同状态；步骤 3 中第三次失败后状态变为 `manual_review`，不再重试。

**验证方法**：把 `transition` 当纯函数，对“状态 × 事件”全组合做表格驱动测试；对每个拒绝理由都应有至少一个用例。

**清理方法**：删除脚本与 `__pycache__`；本实验不涉及真实订单。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 同一退款被执行两次 | 执行前未检查状态，或幂等键每次重建 | 用同一幂等键重放请求，看下游是否去重 | 执行节点先读状态再执行，幂等键落库复用 |
| 审批三天后才生效 | 没有过期判定，或只在创建时判断 | 检查执行路径是否重新读取 `expires_at` | 恢复时强制校验时限，过期转 `expired` |
| 批准 199 元、退款 3999 元 | 审批只绑定动作，不绑定参数 | 对比审批记录与执行参数的哈希 | 参数快照 + 哈希复核 |
| 用户界面一直“处理中” | 挂起后没有超时与通知 | 查询该状态的最长停留时间 | 加超时任务与状态推送 |
| 重复调用同一工具耗尽预算 | 未做无进展检测 | 统计相邻调用的工具名与参数 | 相同调用+相同结果即终止并转人工 |

## 安全与生产注意事项

**<u>审批人必须与发起人分离，且审批角色要走白名单校验。</u>** 只判断“有一个 approval_token”远远不够——令牌可能被伪造、被复用，或由发起人自己签发。SDK 里“记住这次批准”的粘性设置尤其危险：OpenAI Agents SDK 文档说明，`always_approve` 类型的决定会在复用的上下文甚至其他 agent 的同名工具上继续生效；跨权限边界时应使用逐次决定。

**<u>挂起期间的外部状态会变化，恢复时必须重新校验，不能只信任挂起时的快照。</u>** 订单可能已被取消、已退款、金额被促销调整。恢复流程的第一步应是状态与参数复核，任何不一致都终止并告警，否则就是典型的 TOCTOU（检查与使用之间状态变化）问题。

## 本课总结

- **把审批写成显式状态机**：状态可查、事件受限、守卫明确，才能不重不漏。
- 审批断点 = 持久化运行态 + 参数快照 + 时限 + 恢复协议。
- 参数哈希把“批准了什么”固化下来，防止批小执行大。
- 超时不是异常而是正常状态，必须有明确的去向（过期、升级、转人工）。
- 循环要有预算与无进展检测，终止后仍需留下可读状态。

## 思考题

主管李工认为“超时就自动拒绝”太生硬，客户会流失；运营认为“超时就自动通过”风险太大。请设计第三种方案，并说明状态机如何表达它。

参考思路：第三种是分级超时——短时未决提醒审批人，二次超时升级到更高权限，仍未决则转人工电话确认并允许客户选择改期；状态机里用 `awaiting_approval` → `escalated` → `expired` 表达，每级带不同时限与通知策略。评价标准看两点：客户可见等待上限、每级审批人是否具备相应权限。

## 小测

1. 为什么非法转移应返回拒绝理由而不是抛出异常？
2. 下列哪项最需要“参数快照 + 哈希复核”？  
   A. 查询订单　B. 检索政策文档　C. 超额退款审批　D. 生成答复草稿
3. 恢复挂起运行时，为什么不能只信任挂起那一刻的订单状态？
4. 无进展检测的判据通常是什么？
5. 场景题：客服和客户共用同一登录账号代客操作。状态机应如何表达“代理关系”，避免自批？

## 答案与解析

1. 因为重复投递、并发点击、过期事件都是正常输入。抛异常会让调用方把它当系统故障而重试，反而制造重复执行；返回可解释的拒绝能让上层决定提示、转人工或放弃。
2. **C。** 它涉及资金且不可逆，必须固定“批准的是哪一组参数”。A、B 只读，D 无副作用，风险等级不同。
3. 因为挂起期间外部系统仍在变化：订单可能已退款、已取消或金额调整。只信快照会让“检查通过”与“实际状态”脱节，产生重复退款或错退。
4. 相邻调用使用同一工具、同一参数且返回相同结果（或状态未推进）。达到阈值即终止并转人工，避免用不同措辞反复试探。
5. 引入两个主体字段：`requested_by`（客户）与 `acting_as`（客服），审批守卫要求 `approver` 既不是客户也不是代操作客服，或在双人复核后才允许；同时把代理关系写入审计记录，保证可追溯到“谁代表谁”。

## 延伸阅读与下一课

- OpenAI Agents SDK：[Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)（中断与恢复流程、`RunState` 序列化、审批决定的作用域与粘性风险；截至 2026-10-19 复核）。
- OpenAI Agents SDK：[Sessions](https://openai.github.io/openai-agents-python/sessions/)（挂起后带同一 session 恢复才能接续同一段历史）。
- OWASP GenAI：[LLM03:2026 Excessive Agency](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/)（高影响动作需人工批准、分级执行建议）。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Workflow 与 Agent 的区别](04-workflow-vs-agent.md)。
- 下一课：[Agent 的规划、执行与反思](06-agent-planning-execution-and-reflection.md)。
