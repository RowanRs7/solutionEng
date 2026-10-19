---
title: 开发、测试与交付
slug: build-test-deliver-overview
module: traditional-solutions
stage: build-and-integrate
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - data-and-architecture-overview
outcomes:
  - 搭出一个分层清晰的 FastAPI 服务，并把依赖、配置与 Secret 纳入工程管理
  - 为一次接口变更写出分层测试与 CI/CD 流程，含迁移、灰度与回滚步骤
  - 用日志、容器与 Linux 诊断手段定位一次集成故障并给出证据
last_reviewed: 2026-10-19
---

# 开发、测试与交付

## 单元目标

本单元把设计落到能构建、能验证、能反复发布的工程实践上：用 FastAPI 写出分层服务，把配置与密钥管住，用异常处理和结构化日志让故障可定位，用分支与测试分层建立质量闸门，最后借助 Docker、CI/CD 与 Kubernetes 把变更安全送上生产，并在出问题时灰度回滚。学完你能独立搭起一条从提交到上线的交付链路，并为每一次拒绝、回滚和排障提供可复核的证据。

## 学习路线

预计学习时间 **9–11 小时**。课程按以下顺序学习：

1. [01-fastapi-service-and-layering.md](01-fastapi-service-and-layering.md)：FastAPI 最小服务与项目分层。
2. [02-dependencies-config-and-secrets.md](02-dependencies-config-and-secrets.md)：依赖、虚拟环境、配置与 Secret。
3. [03-exception-handling-and-structured-logging.md](03-exception-handling-and-structured-logging.md)：异常处理与结构化日志。
4. [04-git-branching-and-code-review.md](04-git-branching-and-code-review.md)：Git、版本与代码审查。
5. [05-test-levels-and-acceptance.md](05-test-levels-and-acceptance.md)：单元、集成、契约、端到端与验收测试。
6. [06-performance-security-and-data-testing.md](06-performance-security-and-data-testing.md)：性能、安全与数据质量测试。
7. [07-linux-processes-and-diagnostics.md](07-linux-processes-and-diagnostics.md)：Linux、进程与诊断方法。
8. [08-docker-and-compose.md](08-docker-and-compose.md)：Docker 与 Docker Compose。
9. [09-cicd-migrations-canary-and-rollback.md](09-cicd-migrations-canary-and-rollback.md)：CI/CD、变更、灰度与回滚。
10. [10-cloud-kubernetes-and-iac.md](10-cloud-kubernetes-and-iac.md)：云计算、Kubernetes 与 IaC。
11. [11-stage-assessment.md](11-stage-assessment.md)：开发、测试与交付阶段综合测评。

## 贯穿场景

晴空商城的退款方案在前一单元已经设计成型，到了本单元就要真正跑起来：退款接口怎样分层、支付密钥从哪里读、一次失败请求怎样在日志里被一眼定位、改动由谁审查、测试覆盖到哪一层才算验收、压测与安全扫描如何不拖慢发布、镜像与 Compose 怎样复现环境、数据库迁移和灰度发布如何避免退款被重复扣款、Kubernetes 与 IaC 又怎样让环境随时可重建。每一课补上退款链路的一个工程侧面，合起来才是一条可交付、可回滚的链路。

## 必交成果

- 可运行的 FastAPI 服务骨架，含分层目录与配置注入。
- 异常处理与结构化日志清单，能定位一次具体的失败请求。
- 测试方案：单元、集成、契约与端到端各层的用例和验收标准。
- Dockerfile 与 Compose 编排文件，可在本地一键启动依赖。
- CI/CD 流水线配置，含迁移、灰度与回滚步骤说明。
- 阶段测评答卷与复盘记录。

## 完成规则

先完成全部课程与练习，再做阶段测评。测评达到 **80 分**视为掌握；60–79 分按复习路线补课，重点回看失分课程；低于 60 分重做核心练习后再测。

返回[传统解决方案模块](../00-overview.md)。
