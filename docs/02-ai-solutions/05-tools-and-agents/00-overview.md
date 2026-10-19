---
title: 工具调用、Workflow 与 Agent
slug: tools-and-agents-overview
module: ai-solutions
stage: design
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - rag-and-knowledge-overview
outcomes:
  - 为一个业务助手写出工具契约（描述、参数 Schema、返回信封）并标注读写属性
  - 按诉求分布选择 workflow、受限 agent 或混合编排，并写出终止条件与预算
  - 为一次高影响工具调用设计权限三元组、审批断点、幂等键与审计字段
last_reviewed: 2026-10-19
---

# 工具调用、Workflow 与 Agent

## 单元目标

本单元解决一个问题：模型会说话，但不能安全地“做事”。学完后你能把业务动作拆成有契约的工具，把控制流从模型手里收回代码，只在真正需要判断的地方交给 Agent。三条主线：**契约**（描述、Schema、返回信封）、**权限与流程**（身份、对象、审批断点）、**可靠性**（超时、重试、幂等、审计）。

## 学习路线

预计学习时间为 **7–9 小时**，按顺序学习：

1. [Function Calling 的工作机制](01-function-calling-mechanics.md)：四段循环、回填与终止条件，执行在应用侧。
2. [工具描述、参数 Schema 与返回值](02-tool-schemas-and-descriptions.md)：描述管选择，Schema 管填参，信封管下一步。
3. [工具权限、校验与最小授权](03-tool-permissions-and-least-privilege.md)：主体、操作、对象三元组与分级执行。
4. [Workflow 与 Agent 的区别](04-workflow-vs-agent.md)：按控制流归属与诉求分布选编排。
5. [状态机、分支、循环与人工审批](05-state-machines-branches-and-approval.md)：审批写成可恢复、可过期的状态机。
6. [Agent 的规划、执行与反思](06-agent-planning-execution-and-reflection.md)：用外部信号判断对错，而非模型自评。
7. [会话状态、短期记忆与长期记忆](07-session-and-memory.md)：分作用域、定写入策略、留删除能力。
8. [MCP、单 Agent 与多 Agent 的边界](08-mcp-and-single-vs-multi-agent.md)：标准化暴露方式，不转移责任。
9. [工具超时、重试、沙箱、审计与失败模式](09-tool-reliability-sandbox-and-failure-modes.md)：让失败可识别、可收敛、可复盘。
10. [工具与 Agent 阶段综合测评](10-stage-assessment.md)：换场景检验迁移，产出设计说明书。

## 贯穿场景

晴空商城售后助手在本单元被逐层拆开：客户耳机左耳无声要求退款，链上有只读查询、政策检索、金额计算和高影响写退款。课程从“模型只产出调用意图”讲起，逐课收紧契约、权限、编排、审批、记忆与外部接入，最后回答客服的问题：“支付网关卡住的那笔退款到底成功了没有。”

## 必交成果

- 工具契约清单：读写属性、参数约束、返回信封与错误码。
- 权限与审批表：主体、操作、对象、判定依据、令牌绑定内容。
- 编排决策记录：诉求分布、选择依据、终止条件与步数预算。
- 状态机与超时去向表：状态、事件、守卫、超时后去向。
- 可靠性清单：分层超时、重试预算、幂等键、审计字段、已知失败模式。

## 完成规则

先学完九篇课程并完成课内小测与练习，再做阶段测评。测评满分 100 分：**80 分及以上**视为掌握；**60–79 分**按测评给出的复习路线回看对应课程，补完后重测一次；**低于 60 分**重做核心练习（工具契约、权限表、状态机）后再申请测评。提交成果时，未经确认的数字标“待测”并写明责任人与期限。

返回[AI 解决方案知识体系](../00-overview.md)。
