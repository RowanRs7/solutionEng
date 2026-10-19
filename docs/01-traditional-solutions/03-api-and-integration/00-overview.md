---
title: API 与系统集成
slug: api-and-integration-overview
module: traditional-solutions
stage: design
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - web-and-network-overview
outcomes:
  - 为一项业务能力定出资源模型、接口契约与版本策略
  - 为失败路径选择重试、熔断、异步或补偿机制并说明理由
  - 完成本单元全部课程与练习，并通过阶段综合测评
last_reviewed: 2026-10-19
---

# API 与系统集成

## 单元目标

本单元把“接口能调通”推进到“多方能长期独立演进”。学完后，你能为一项业务能力写出稳定的资源模型与契约，并针对超时、重复、洪峰和数据滞后，选出一套可解释、可验收的集成机制。你还需要能说清每项选择放弃了什么。

## 学习路线

预计学习时间为 **9–11 小时**。课程按以下顺序学习：

1. [API、REST 与资源建模](01-api-rest-and-resource-modeling.md)：把业务用例拆成资源、标识与方法。
2. [OpenAPI 与接口契约](02-openapi-and-contracts.md)：用机器可读契约约定字段、示例与变更。
3. [参数校验、错误模型与版本管理](03-validation-errors-and-versioning.md)：让失败可判断，让升级不伤调用方。
4. [分页、过滤、批量与限流](04-pagination-filtering-and-rate-limits.md)：处理大数据量与调用量激增。
5. [超时、重试、退避与幂等](05-timeout-retry-backoff-and-idempotency.md)：区分可重试与不可重试的失败。
6. [熔断、降级与隔离](06-circuit-breaking-degradation-and-isolation.md)：阻止局部故障扩散成全站故障。
7. [Webhook、签名与重放保护](07-webhooks-signing-and-replay-protection.md)：安全地接收对方的主动通知。
8. [轮询、SSE、WebSocket 与回调](08-polling-sse-websocket-and-callbacks.md)：按实时性要求选择通知方式。
9. [邮件、短信、定时任务与文件交换](09-email-sms-jobs-and-file-exchange.md)：处理非实时、批量与外部通道。
10. [消息队列、发布订阅与死信队列](10-message-queues-pubsub-and-dlq.md)：用异步解耦生产者与消费者。
11. [Outbox、补偿与最终一致性](11-outbox-compensation-and-eventual-consistency.md)：保证跨系统状态最终收敛。
12. [ETL、ELT、CDC 与数据同步](12-etl-elt-cdc-and-data-sync.md)：让数据在系统之间可靠流动。
13. [同步与异步集成模式选型](13-sync-vs-async-integration-selection.md)：在约束下组合出完整方案。
14. [API 与集成阶段综合测评](14-stage-assessment.md)：检验本单元掌握程度。

## 贯穿场景

晴空商城的退款要跨客服工作台、退款服务、支付供应商、仓库与财务对账。本单元只看集成侧面：退款请求如何建模并被重复提交，支付回调延迟或重复时状态如何收敛，仓库拦截发货走同步还是异步，财务对账如何发现差异并补偿。每一课补全其中一段链路，最后合成一份自洽的集成设计。

## 必交成果

- 退款域的接口契约片段，含错误模型与版本策略。
- 超时、重试、退避与幂等键的配置表。
- 同步与异步集成模式的选型对照表及结论。
- Webhook 验签与重放防护说明。
- 含 Outbox 与补偿的失败恢复与对账流程。

## 完成规则

先完成前十三课及其练习，再进入阶段综合测评。测评达到 **80 分**视为掌握；60–79 分应按复习路线补课；低于 60 分应重新完成核心练习。

返回[传统解决方案模块](../00-overview.md)。
