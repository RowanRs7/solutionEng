---
title: 知识地图
slug: knowledge-map
module: course-foundation
stage: discover
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - solution-lifecycle
outcomes:
  - 找到两个模块的学习入口
  - 区分已发布内容和计划内容
last_reviewed: 2026-11-18
---

# 知识地图

把这套课程想象成一张地图：**解决方案生命周期**告诉你一段方案工作通常经过哪些区域，两个知识模块是两条先后衔接的主路线，每个单元是路线中的一站，单课则负责讲清一个具体主题。术语表、技术索引和排障索引是查询入口，帮助你在忘记概念或遇到问题时回到正确位置。

第一次学习不必点开所有链接。沿“入门准备 → 传统解决方案 → AI 解决方案”前进即可；需要复习时，再按主题或症状查找。

## 已发布

### 课程入口与学习准备

当前目录的导论、学习指南、环境准备、生命周期和本页共同组成入口。先完成这些内容，再进入第一个知识模块。

### 传统解决方案：先补齐工程地基

从[传统解决方案模块概览](../01-traditional-solutions/00-overview.md)进入，按顺序学习七个单元：

1. [需求发现与定义](../01-traditional-solutions/01-discovery-and-requirements/00-overview.md)：把模糊业务诉求整理成可验收的需求包。
2. [Web 与网络](../01-traditional-solutions/02-web-and-network/00-overview.md)：理解请求怎样在网络中传输，以及常见网络问题怎样排查。
3. [API 与系统集成](../01-traditional-solutions/03-api-and-integration/00-overview.md)：学习系统之间怎样约定接口、传递消息和同步数据。
4. [身份、权限与安全](../01-traditional-solutions/04-identity-and-security/00-overview.md)：弄清用户是谁、能做什么，以及如何保护系统与数据。
5. [数据与应用架构](../01-traditional-solutions/05-data-and-architecture/00-overview.md)：学习数据怎样组织和保存，组件怎样组合，以及故障时怎样恢复。
6. [开发、测试与交付](../01-traditional-solutions/06-build-test-deliver/00-overview.md)：把设计实现为服务，通过测试、容器和发布流程交付。
7. [运行与持续优化](../01-traditional-solutions/07-operate-and-optimize/00-overview.md)：用监控、告警、故障响应和 Runbook 支撑上线后的运行。

其中，需求发现单元提供了一条完整的入门路径，适合作为正式学习的第一站：

- [解决方案架构师角色](../01-traditional-solutions/01-discovery-and-requirements/01-solution-architect-role.md)
- [利益相关者与业务目标](../01-traditional-solutions/01-discovery-and-requirements/02-stakeholders-and-business-goals.md)
- [现状调研与业务流程](../01-traditional-solutions/01-discovery-and-requirements/03-current-state-and-business-process.md)
- [用户、角色、场景与用例](../01-traditional-solutions/01-discovery-and-requirements/04-users-roles-scenarios-and-use-cases.md)
- [功能与非功能需求](../01-traditional-solutions/01-discovery-and-requirements/05-functional-and-non-functional-requirements.md)
- [系统边界、约束、依赖与假设](../01-traditional-solutions/01-discovery-and-requirements/06-boundaries-constraints-dependencies-assumptions.md)
- [优先级、范围与验收标准](../01-traditional-solutions/01-discovery-and-requirements/07-priorities-scope-and-acceptance.md)
- [风险与需求交付物](../01-traditional-solutions/01-discovery-and-requirements/08-risks-and-requirement-deliverables.md)
- [需求发现阶段综合测评](../01-traditional-solutions/01-discovery-and-requirements/09-stage-assessment.md)

### AI 解决方案：在工程地基上管理不确定性

完成传统模块后，从[AI 解决方案模块概览](../02-ai-solutions/00-overview.md)进入，按顺序学习八个单元：

1. [AI 基础](../02-ai-solutions/01-ai-foundations/00-overview.md)：理解模型、Token（模型处理输入和输出的基本单位）、生成机制和能力边界。
2. [AI 需求发现与定义](../02-ai-solutions/02-discovery-and-requirements/00-overview.md)：判断什么问题适合 AI，并定义可验收的目标。
3. [模型选择与 Prompt 设计](../02-ai-solutions/03-model-and-prompt/00-overview.md)：选择模型，设计给模型的指令、上下文和结构化输出。
4. [Embedding、检索与 RAG](../02-ai-solutions/04-rag-and-knowledge/00-overview.md)：把资料转成可检索的知识，为模型回答寻找依据并保留引用。
5. [工具调用、Workflow 与 Agent](../02-ai-solutions/05-tools-and-agents/00-overview.md)：让 AI 与工具协作，并明确固定流程和 Agent 决策的边界。
6. [AI 应用架构与传统集成](../02-ai-solutions/06-ai-application-architecture/00-overview.md)：把模型、知识、工具、权限、数据和运维接入完整请求链路。
7. [评测、安全与治理](../02-ai-solutions/07-evaluation-security-governance/00-overview.md)：用数据和指标检查效果，处理安全风险、审计和治理要求。
8. [部署、运行与优化](../02-ai-solutions/08-deploy-operate-optimize/00-overview.md)：处理容量、成本、可观测性、模型变更和持续优化。

每个单元的完整课程清单见该单元概览页；需要按技术主题回查时，使用[技术索引](../reference/technology-index.md)。

## 计划中

- 两个知识模块的核心课程均已发布；`card` 技术卡片、`advanced` 扩展专题和企业 AI 集成平台综合实战尚未建设。

“计划中”条目只说明学习路线，不创建失效链接。每个单元发布后，才会加入可点击入口。因此，看到“计划中”时不用寻找隐藏材料，先完成已发布的主线课程。

## 导航原则

- **继续主线学习：**按生命周期和两个模块的既定顺序前进，从单元概览进入具体课程。
- **忘记一个概念：**先查[术语表](../reference/glossary.md)，需要按技术主题定位时再查[技术索引](../reference/technology-index.md)。
- **实验或系统出现故障：**先看[排障索引](../reference/troubleshooting-index.md)，按症状找到入口，再回到对应课程理解机制，而不是只复制一个修复步骤。
