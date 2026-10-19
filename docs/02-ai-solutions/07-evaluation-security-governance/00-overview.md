---
title: 评测、安全与治理
slug: evaluation-governance-overview
module: ai-solutions
stage: test-and-validate
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - ai-application-architecture-overview
outcomes:
  - 为一条带检索与工具调用的 AI 功能写出可复现的黄金集、分层指标与通过门槛
  - 用中间产物把端到端失败归因到检索、生成或工具，并给出证据
  - 列出注入、外泄、越权与内容安全的控制点，并说明审计与治理所需的留痕
last_reviewed: 2026-10-19
---

# 评测、安全与治理

## 单元目标

AI 输出是分布而非确定值，"测得对"与"防得住"必须一起设计。本单元解决四件事：用什么样本判断变更变好还是变坏；怎么把失败定位到具体环节；怎么在模型必然出错的假设下限制损害；怎么留下可核对的证据。学完后，你应能为带检索与工具调用的 AI 应用写出可执行、可复现、可追责的方案，而不是只给一句"效果不错"。

## 学习路线

预计学习时间为 **8–10 小时**，按以下顺序学习：

1. [AI 测试与传统测试的差异](01-ai-testing-vs-traditional.md)：判定单位从单条输出变成分布。
2. [Golden Dataset 与评测样本设计](02-golden-datasets-and-sample-design.md)：把样本变成带口径的资产。
3. [正确性、相关性、忠实度与完整性](03-correctness-relevance-faithfulness.md)：四项指标各自对照什么事实源。
4. [检索、生成与端到端分层评测](04-layered-and-end-to-end-evaluation.md)：用中间产物做归因，用召回估算天花板。
5. [工具调用与 Agent 任务成功率](05-tool-and-agent-success-metrics.md)：成功由业务终态定义，工具返回码只是过程。
6. [人工评审与 LLM-as-a-Judge](06-human-review-and-llm-as-a-judge.md)：先有量表与金标准，再谈自动评分。
7. [回归、A/B 与在线评测](07-regression-ab-and-online-evaluation.md)：离线门禁决定能否发布，在线指标决定能否扩量。
8. [Prompt Injection 与数据外泄](08-prompt-injection-and-data-exfiltration.md)：指令与数据同通道，防御落在能力与输出上。
9. [敏感数据、隐私与数据泄露](09-sensitive-data-privacy-and-leakage.md)：可还原性决定共享权限，副本扩散才是主风险。
10. [越权工具调用、Guardrail 与审批](10-excessive-agency-guardrails-and-approval.md)：模型只提议，策略引擎才授权。
11. [内容安全、审计、版权与 AI 治理](11-content-safety-audit-and-governance.md)：把原则写成可判定、可处置、可申诉的控制点。
12. [评测与治理阶段综合测评](12-stage-assessment.md)：本单元综合检查，覆盖全部十一课。

## 贯穿场景

晴空商城售后智能助手的链路是：客服提问 → 检索售后政策与订单 → 生成答复与退款建议 → 人工确认 → 调用 `refund.create` 建单。本单元从测试与治理的侧面看这条链路：

- 政策库更新或 Prompt 改一个字，怎么判断是修复还是退化？
- 端到端通过率掉了 5 个点，该改检索、改生成，还是改工具契约？
- 客户上传的聊天截图里藏了指令，系统还剩几道闸门？
- 出了问题，能否拿出"谁、在什么版本下、依据哪条策略、做了什么决定"的记录？

每一课切开一个侧面，最后用阶段测评拼成完整方案。

## 必交成果

完成本单元时应产出以下五份材料：

1. **黄金集**：不少于 100 条样本，含覆盖矩阵、标注规范、三套划分与防污染规则。
2. **指标卡**：四项质量指标、检索层指标与 Agent 严格成功率，逐项写清样本量、基线、阈值与判定方式。
3. **失败归因表**：至少 20 条端到端失败，标注最早出错层与证据字段。
4. **工具分级与审批矩阵**：四级的额度、fail-closed、幂等与审批绑定要求。
5. **安全与治理清单**：四类外泄通道及控制点、注入用例、审计字段、AI 标识与复核责任人。

## 完成规则

先学完 11 篇课程并完成练习，再做阶段测评。满分 100 分：**80 分**视为掌握；**60–79 分**按复习路线补课并重做失分部分；**低于 60 分**重做全部练习与场景题，不要直接进入下一单元。指标与阈值必须写明来源、样本量和复核日期，凭空数字不算成果。

返回[AI 解决方案知识体系](../00-overview.md)。
