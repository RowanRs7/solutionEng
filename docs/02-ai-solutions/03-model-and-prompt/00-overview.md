---
title: 模型选择与 Prompt 设计
slug: model-and-prompt-overview
module: ai-solutions
stage: design
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - ai-discovery-overview
outcomes:
  - 用能力、单价、延迟与上下文四个维度，为主模型和降级模型给出可复核的选型依据
  - 产出带指令层级、变量校验与版本号的 Prompt 模板，并用 JSON Schema 约束输出
  - 为解析失败、流式/批处理与模型降级设计可观测的兜底路径
last_reviewed: 2026-10-19
---

# 模型选择与 Prompt 设计

## 单元目标

本单元把模型选型和 Prompt 当作生产配置，而不是一次性的聊天技巧。学完后，你应当能回答三个问题：这类请求该交给哪一档模型；提示词怎样写才能稳定、可复现、可回滚；模型不按约定输出时，系统怎样在有限预算内恢复或安全降级。

## 学习路线

预计 7–9 小时。建议按顺序学习，每课完成动手实验后再进入下一课。

1. [模型能力、价格、速度与上下文权衡](01-model-capability-price-speed-tradeoffs.md)：用四维约束和单会话成本做选型，而不是追求单项最强。
2. [指令层级与 System Prompt](02-instruction-hierarchy-and-system-prompts.md)：分清指令层级，并用代码补上提示词管不住的权限。
3. [Zero-shot、Few-shot 与示例设计](03-zero-shot-few-shot-and-examples.md)：先建基线再校准，识别示例集偏斜与收益递减。
4. [Prompt 模板、变量与版本管理](04-prompt-templates-and-versioning.md)：把提示词变成可校验、可追踪、可回滚的生产资产。
5. [结构化输出与 JSON Schema](05-structured-output-and-json-schema.md)：用契约约束形状，把业务规则留给代码。
6. [输出解析、校验、修复与重试](06-output-parsing-validation-and-repair.md)：按语法、结构、语义、业务四层处理失败，并设定重试预算。
7. [流式响应、批处理与异步任务](07-streaming-batch-and-async.md)：交互场景缩短等待，离线场景压低成本，两者不能混用。
8. [多模态输入与推理模型边界](08-multimodal-and-reasoning-models.md)：先判断是否真的需要图像、文档或推理，再计算其成本与延迟。
9. [模型路由、降级与何时停止优化 Prompt](09-model-routing-and-when-to-stop.md)：用确定性规则分层，配三级降级，并用收益曲线决定何时停手。
10. [模型与 Prompt 阶段综合测评](10-stage-assessment.md)：用新场景检验九课知识的迁移与落地。

## 贯穿场景

晴空商城售后智能助手在本单元只露出“模型与 Prompt”这一侧：顾客问退换货政策、查询订单状态、上传破损照片、申请高额退款。你要为这些请求选择模型档位，写清 System Prompt 的裁决规则，用 few-shot 校准判定尺度，用 JSON Schema 固定输出，再决定哪些请求流式返回、哪些转人工、哪些在失败时降级。

检索质量、知识库切分和引用生成属于后续 RAG 单元，本单元不展开；这里只处理“拿到上下文之后，模型怎样稳定地产生可用结果”。

## 必交成果

完成本单元时，至少提交以下六项：

1. 一页模型选型与成本测算表：主模型、备用模型、单会话成本、首 Token 与端到端延迟目标。
2. 一版可运行的 System Prompt：含角色、边界、冲突裁决、拒答话术与外部数据隔离声明。
3. 一份脱敏 few-shot 示例集：标注覆盖类目、难例、反例与真实分布对照。
4. 一份 JSON Schema 与校验流程：含枚举、可选字段、四层校验、一次修复重试和兜底。
5. 一份路由与降级策略：确定性规则、三级降级链、熔断条件与响应归因字段。
6. 一份 Prompt 迭代记录：评测集前后对比、成本与延迟变化、停止优化的判断依据。

## 完成规则

先学完全部九课并完成各课动手实验，再做阶段测评。测评满分 100 分：80 分及以上为掌握；60–79 分按错题补课并重做场景分析；低于 60 分重做本单元练习，再闭卷重测。补课时不要只重读正文，要回到对应课次重跑实验并留下记录。

返回[AI 解决方案知识体系](../00-overview.md)。
