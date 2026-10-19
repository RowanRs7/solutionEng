---
title: 运行与持续优化
slug: operate-and-optimize-overview
module: traditional-solutions
stage: operate-and-optimize
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - build-test-deliver-overview
outcomes:
  - 用日志、指标与链路三支柱描述一次退款故障，并给出可复核的定位证据
  - 为一个退款接口写出 SLI、SLO、错误预算与告警阈值，并说明告警如何降噪
  - 产出可执行的 Runbook 与复盘记录，含备份恢复与事故响应步骤
last_reviewed: 2026-10-19
---

# 运行与持续优化

## 单元目标

本单元把「能上线」推进到「能天天跑得住」：用日志、指标与链路看清系统正在发生什么，用 SLI/SLO 与错误预算把稳定性变成可谈判的数字，用容量、成本与故障复盘让系统在压力下依然可控。运行阶段的工作重心不是救火，而是把可观测、可承诺、可恢复这三件事固化进日常流程，让每次变更都有数据支撑、每次故障都有路径可循。学完你能独立搭起一条从信号采集到告警、响应、复盘、恢复的可运行闭环，并为每一次值班判断留下可核查的依据。

## 学习路线

预计学习时间 **7–9 小时**。课程按以下顺序学习：

1. [日志、指标、Tracing 与告警](01-logs-metrics-tracing-and-alerting.md)：三支柱各回答什么问题，告警按什么分级。
2. [Correlation ID 与请求链路](02-correlation-id-and-request-tracing.md)：一次调用如何被串成一条可回查的链路。
3. [OpenTelemetry、Prometheus 与 Grafana](03-opentelemetry-prometheus-grafana.md)：从埋点到看板的标准实现路径。
4. [SLI、SLO、SLA 与错误预算](04-sli-slo-sla-and-error-budget.md)：把稳定性变成可谈判、可告警的数字。
5. [性能、容量、配额与成本](05-performance-capacity-and-cost.md)：先找瓶颈，再谈扩容与省钱。
6. [故障分级、响应与复盘](06-incident-response-and-postmortem.md)：定级、止损，再把根因说清楚。
7. [备份、恢复与业务连续性](07-backup-restore-and-business-continuity.md)：备份存在不等于恢复得了。
8. [Runbook 与知识移交](08-runbooks-and-operational-handover.md)：值班新人能否不问人就完成止损。
9. [运行与优化阶段综合测评](09-stage-assessment.md)：检验本单元的掌握程度。

## 贯穿场景

晴空商城的退款链路已经交付上线，本单元盯的是它之后的每一天：退款单提交后转圈，到底是网关、退款服务还是支付渠道的问题；同一笔退款在日志里如何被 Correlation ID 串成一条完整链路；退款成功率该用哪个 SLI 度量，错误预算还剩多少才允许继续发版；大促退款量翻三倍时配额与成本卡在哪里；凌晨的退款积压如何分级响应并在复盘里说清根因；订单库误删后能恢复到哪个时间点；值班新人拿到 Runbook 能否不问人就完成止损。每一课补上退款运营的一个侧面。这些侧面共享同一把尺子：出问题时能多快定位、多快止损、能否说清影响了谁。

## 必交成果

- 一份三支柱观测方案：关键日志字段、核心指标与链路埋点清单。
- 退款链路的 SLI/SLO 定义与错误预算策略，含告警阈值与降噪规则。
- 一次容量与成本评估，给出配额建议和压测结论。
- 一份故障分级表与一次事故复盘记录，含时间线与改进项。
- 备份恢复演练记录与业务连续性说明。
- 可执行的值班 Runbook 与移交清单。

## 完成规则

先完成全部课程与练习，再做阶段测评。测评达到 **80 分**视为掌握；60–79 分按复习路线补课，重点回看失分课程；低于 60 分重做核心练习后再测。

返回[传统解决方案模块](../00-overview.md)。
