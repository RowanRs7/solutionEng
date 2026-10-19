---
title: Embedding、检索与 RAG
slug: rag-and-knowledge-overview
module: ai-solutions
stage: design
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - model-and-prompt-overview
outcomes:
  - 画出从文档入库到带引用回答的完整 RAG 链路，并标出每一环的失败模式
  - 为一份真实知识源产出检索方案：入库、切分、召回、rerank、权限与引用
  - 用分层指标与错误归因定位单条问答失败发生在检索层还是生成层
last_reviewed: 2026-10-19
---

# Embedding、检索与 RAG

## 单元目标

本单元回答一个问题：模型没学过、但你手上有的知识，怎么让它可靠地用上。

学完后，你能把散落在 HTML、PDF、Excel 与历史工单里的知识，变成一条可检索、可引用、可授权、可增量更新、可评测的检索服务，并能说清每一层选择放弃了什么。重点不是让一次问答看起来对了，而是让检索质量可测量、失败可归因、越权可阻断。本单元不讲模型训练，也不讲 Agent 编排。

## 学习路线

预计学习时间 **8–10 小时**，按以下顺序学习：

1. [Embedding、向量与语义相似度](01-embeddings-vectors-and-similarity.md)：把语义变成向量，并选对距离度量与阈值。
2. [距离度量、向量索引与向量数据库](02-vector-index-and-vector-databases.md)：用可量化的召回损失换取查询速度。
3. [文档加载、解析、清洗与元数据](03-document-ingestion-and-metadata.md)：让进入索引的数据干净、可过滤、可追溯。
4. [切分、重叠与上下文保留](04-chunking-and-context-preservation.md)：在原子单元边界切分，并让片段自带前提。
5. [关键词、向量、混合检索与 Query 改写](05-hybrid-search-and-query-rewriting.md)：用互补的多路召回覆盖标识符与口语提问。
6. [Rerank、结果筛选与上下文组装](06-rerank-and-context-assembly.md)：在固定 token 预算内把最强证据排到前面。
7. [引用、溯源与可信回答](07-citations-and-grounded-answers.md)：让每条结论都能回到具体原文与版本。
8. [权限感知检索与多租户隔离](08-permission-aware-retrieval.md)：先裁剪候选集，再取 top-k。
9. [增量索引、删除与数据同步](09-incremental-indexing-and-sync.md)：把索引当派生数据持续对账。
10. [RAG 评测与错误分析](10-rag-evaluation-and-error-analysis.md)：拆开检索层与生成层指标做归因。
11. [Graph RAG、长上下文与微调的选择](11-graph-rag-and-rag-vs-alternatives.md)：在四种方案之间按约束取舍。
12. [RAG 阶段综合测评](12-stage-assessment.md)：检验本单元掌握程度。

## 贯穿场景

晴空商城售后智能助手在本单元的侧面：客服问“耳机拆封了还能退吗”，答案分散在帮助中心政策页、法务 PDF、运营 Excel 运费表和 40 万条历史工单里。这条链路要同时应付五种真实失败——型号这类标识符检索不到、表格入库后丢表头、政策改版后旧答案还在、客服主管的私有备注被越权召回、知识库没有答案时模型硬编。每一课解决其中一段，最后合成一份自洽的检索设计。

## 必交成果

- Embedding 选型与阈值标定说明，附标注样本和度量绑定方式。
- 入库管线设计：解析策略、元数据字段、切分规则与幂等指纹。
- 检索链路配置：多路召回、融合参数、rerank 与上下文预算。
- 引用契约与拒答规则，含逐字校验方式和覆盖度阈值。
- 权限与同步方案：先过滤后召回、删除传播路径、对账手段。
- 分层评测集与回归门禁说明，检索层与生成层指标分开计算。

## 完成规则

先完成前十一课及其练习，再进入阶段综合测评。测评达到 **80 分**视为掌握；60–79 分按复习路线补课；低于 60 分重做核心练习，不要直接重考。

返回[AI 解决方案知识体系](../00-overview.md)。
