---
title: AI 解决方案知识体系
slug: ai-solutions-overview
module: ai-solutions
stage: design
type: card
difficulty: beginner
duration: 25m
prerequisites:
  - traditional-solutions-overview
outcomes:
  - 说明 AI 解决方案与传统解决方案的关系
  - 按生命周期定位 AI 模块的八个单元
last_reviewed: 2026-10-19
---

# AI 解决方案知识体系

## 为什么单列一个模块

AI 功能不是“接一个模型接口”就结束。它要处理不确定输出、检索质量、工具权限、评测基线、成本与延迟，还要与已有的身份、数据、集成和运维体系配合。传统模块解决“系统能不能正确运行”，AI 模块解决“系统在有概率出错的前提下仍然可用、可控、可验收”。

> **核心结论：** AI 解决方案的难点不在模型调用，而在不确定性的工程化管理。

## 模块路线

八个单元沿用同一套生命周期，从基础到生产：

1. [AI 基础](01-ai-foundations/00-overview.md)：模型、Token、生成机制与能力边界。
2. [AI 需求发现与定义](02-discovery-and-requirements/00-overview.md)：什么问题适合 AI，如何定义验收。
3. [模型选择与 Prompt 设计](03-model-and-prompt/00-overview.md)：选型、Prompt、结构化输出与路由。
4. [Embedding、检索与 RAG](04-rag-and-knowledge/00-overview.md)：知识接入、检索、引用与评测。
5. [工具调用、Workflow 与 Agent](05-tools-and-agents/00-overview.md)：工具契约、流程编排与 Agent 边界。
6. [AI 应用架构与传统集成](06-ai-application-architecture/00-overview.md)：请求链路、状态、流式、权限与成本。
7. [评测、安全与治理](07-evaluation-security-governance/00-overview.md)：数据集、指标、注入防护与审计。
8. [部署、运行与优化](08-deploy-operate-optimize/00-overview.md)：容量、成本、可观测性与模型变更。

## 与传统模块的关系

传统模块的七个单元是本模块的前置：身份与权限决定 AI 能读到什么，数据与架构决定知识库和状态怎么存，API 与集成决定工具和回调怎么接，运行与优化决定 AI 的 SLO 和故障处理。学习时遇到跨模块问题，回到对应传统课程查机制，不要在这里重复实现。

## 完成标准

每学完一个单元完成该单元的阶段测评；八个单元全部完成后，应能独立完成一份 AI 方案设计：问题定义、模型与检索选型、评测方案、安全边界、成本估算和上线运维计划。

返回[传统解决方案模块](../01-traditional-solutions/00-overview.md)。
