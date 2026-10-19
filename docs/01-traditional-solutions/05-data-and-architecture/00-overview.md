---
title: 数据与应用架构
slug: data-and-architecture-overview
module: traditional-solutions
stage: design
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - identity-and-security-overview
outcomes:
  - 为业务实体设计表结构、索引与迁移脚本，并说明事务与隔离级别的作用
  - 判断何时引入缓存、对象存储或 NoSQL，并给出失效与容量依据
  - 在单体、微服务与无服务器之间做出取舍，并写出可评审的 ADR
last_reviewed: 2026-10-19
---

# 数据与应用架构

## 单元目标

本单元把需求与接口落到能长期运行的数据和应用结构上：设计表与关系、控制事务与一致性、选择缓存与存储形态，并在单体、微服务与服务化之间做出有依据的取舍。学完你能独立产出一份包含数据模型、架构方案与 ADR 的设计说明，并能向他人解释每个决定的代价与适用边界。本单元不追求背下产品名，而要求你在具体约束下写出可被评审、可被验证的设计。

## 学习路线

预计学习时间 **8–10 小时**。课程按以下顺序学习：

1. [01-sql-tables-and-relationships.md](01-sql-tables-and-relationships.md)：SQL、表设计与数据关系。
2. [02-indexes-transactions-and-migrations.md](02-indexes-transactions-and-migrations.md)：索引、事务、锁与数据库迁移。
3. [03-nosql-redis-and-caching.md](03-nosql-redis-and-caching.md)：NoSQL、Redis 与缓存失效。
4. [04-object-storage-and-file-management.md](04-object-storage-and-file-management.md)：对象存储与文件管理。
5. [05-time-money-uuid-and-encoding.md](05-time-money-uuid-and-encoding.md)：时间、金额、UUID 与编码陷阱。
6. [06-data-quality-and-consistency.md](06-data-quality-and-consistency.md)：数据质量、校验与一致性。
7. [07-monolith-microservices-and-serverless.md](07-monolith-microservices-and-serverless.md)：单体、微服务与无服务器架构。
8. [08-api-gateway-and-service-discovery.md](08-api-gateway-and-service-discovery.md)：API Gateway 与服务发现。
9. [09-high-availability-and-disaster-recovery.md](09-high-availability-and-disaster-recovery.md)：高可用、容错与灾难恢复。
10. [10-architecture-tradeoffs-and-adr.md](10-architecture-tradeoffs-and-adr.md)：架构权衡、ADR 与容量成本。
11. [11-stage-assessment.md](11-stage-assessment.md)：数据与架构阶段综合测评。

## 贯穿场景

晴空商城要把退款处理时间从三天压到半天。退款要同时改动订单、支付、库存三处数据，于是本单元逐课追问：退款单如何建模、扣款与回滚怎样放进一个事务、索引怎样支撑按时间与状态的查询、审核截图存到哪里、金额与时间戳如何避免偏差、三方对账数据不一致时以谁为准、是否真要把退款拆成独立服务、网关如何统一鉴权和限流、数据库故障时能否降级受理。每一课补上这条链路的一个侧面，合起来才是一份可交付的设计。

## 必交成果

- 订单与退款相关的表结构、关系图和建表加迁移脚本。
- 关键查询的索引清单与慢查询分析说明。
- 缓存键设计与失效策略表，含缓存穿透和雪崩的应对。
- 数据校验规则与三方对账的一致性检查清单。
- 服务拆分方案与至少两份 ADR。
- 高可用与容灾演练方案，含 RTO、RPO 目标。

## 完成规则

先完成全部课程与练习，再做阶段测评。测评达到 **80 分**视为掌握；60–79 分按复习路线补课，重点回看失分课程；低于 60 分重做核心练习后再测。

返回[传统解决方案模块](../00-overview.md)。
