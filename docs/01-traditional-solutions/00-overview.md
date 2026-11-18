---
title: 传统解决方案知识体系
slug: traditional-solutions-overview
module: traditional-solutions
stage: discover
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - knowledge-map
outcomes:
  - 说明传统工程能力为何是 AI 方案的基础
  - 描述传统解决方案模块的学习路线
last_reviewed: 2026-11-18
---

# 传统解决方案知识体系

## 为什么先学传统工程

AI 应用仍然运行在真实的软件系统中。它需要网络传输、API、身份认证、权限控制、数据同步、异步处理、测试、部署和监控。模型回答得再好，若权限传递错误、Webhook 重复处理或数据管道失效，方案仍会失败。

可以这样理解：模型像一个很会答题的新同事，但公司要正常运转，还得有门禁、工位、审批流程、仓库和值班表。门禁没配好，他进不了办公室；审批没定义，他签的字没人认；仓库账目乱了，他查到的数据就是错的。传统工程能力就是这些“让公司正常开门”的设施。

> **核心结论：** AI 能力建立在传统工程能力之上，而不是替代它。

这个模块也决定了你排查问题的顺序。页面打不开、数据对不上、审批串了号，绝大多数原因不在模型，而在请求链路、权限或数据流。先学会看这些地方，后面遇到 AI 问题时才不会被“模型是不是不聪明”带偏。

## 模块路线

本模块完整走过解决方案生命周期，七个单元已全部发布：

1. [需求发现与定义](01-discovery-and-requirements/00-overview.md)：从业务诉求到可验收的需求包。
2. [Web 与网络](02-web-and-network/00-overview.md)：HTTP、TLS、DNS、代理与网络排障。
3. [API 与系统集成](03-api-and-integration/00-overview.md)：接口契约、异步集成、消息与数据同步。
4. [身份、权限与安全](04-identity-and-security/00-overview.md)：认证、授权、SSO 与安全设计。
5. [数据与应用架构](05-data-and-architecture/00-overview.md)：数据建模、缓存、架构形态与灾备。
6. [开发、测试与交付](06-build-test-deliver/00-overview.md)：FastAPI、测试、容器与发布。
7. [运行与持续优化](07-operate-and-optimize/00-overview.md)：可观测性、SLO、故障响应与 Runbook。

这七个单元不是七门互不相干的课，而是同一套交付流程的七段：先问清要做什么，再决定系统怎么通信、谁来授权、数据存哪、怎么测、怎么上线、上线后怎么盯。前一单元的输出，往往就是后一单元的输入。

## 完成标准

完成本模块后，学习者应能把业务目标转化为可验证需求，选择常见集成和安全机制，并说明部署、运行和故障恢复方案。每个单元以一份 100 分阶段测评为完成标志。

不必等“全部学完”再回头复习。每完成一个单元，就用它检查前面单元留下的结论是否仍站得住：需求里的验收标准，是否能在测试与运行阶段找到证据。

从[需求发现与定义](01-discovery-and-requirements/00-overview.md)开始。需求阶段会产出可测量的**验收标准**；完成八篇课程后，使用 `09-stage-assessment.md` 检查掌握程度。
