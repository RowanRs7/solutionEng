# Traditional Solutions Core Course (Deliveries 2–4)

> **For agentic workers:** Execute this plan unit by unit. Tasks 1–6 are independent and may run in parallel once Task 0 is complete. Each task fans out one writing subagent per lesson, then one for the unit overview and one for the stage assessment.

**Goal:** Publish the six remaining traditional-solutions units (60 core lessons, 6 unit overviews, 6 stage assessments) to the standard set by the discovery unit.

**Architecture:** Markdown remains the product. Every lesson is generated from `docs/_templates/lesson-template.md` against the spec's bullet list, then gated by `scripts/validate_docs.py`. Shared navigation files are updated once, in Task 7, so parallel writers never touch the same file.

**Spec:** `docs/superpowers/specs/2026-10-16-ai-solutions-curriculum-design.md`

**Executes:** delivery sequence plans 2, 3 and 4 from the 7-plan sequence (the sequence file lists them separately; one batch plan is used because all six units share one contract and one validator).

## Global Constraints

- Learner-facing prose is Chinese; file names and metadata values are stable English slugs.
- Audience: knows basic Python, lacks backend, enterprise-integration, deployment and operations experience.
- Each unit directory is `docs/01-traditional-solutions/<NN>-<unit-slug>/` with `00-overview.md`, lessons `01…NN`, and `(NN+1)-stage-assessment.md`.
- Teaching lessons use `type: core` and must contain all 16 headings from the template in order. Unit overviews use `type: card`. Stage assessments use `type: advanced` and follow `docs/_templates/assessment-template.md` plus the 09-unit assessment's structure (checklist, 15+ questions, scenario, deliverable task, 100-point rubric, answers, remediation).
- `last_reviewed: 2026-10-19` for every new file.
- `stage` values are limited to `discover`, `define`, `design`, `build-and-integrate`, `test-and-validate`, `deploy-and-deliver`, `operate-and-optimize`.
- One running scenario carries through all units: 晴空商城 (online retail), connecting mall, orders, payment, warehouse and customer service around refunds. Each lesson opens a new facet of it rather than inventing a new case.
- Prerequisites: lesson `01` lists the previous unit's overview slug; lesson `NN` lists lesson `NN-1`'s slug; the unit overview lists the previous unit's overview; the stage assessment lists the last lesson.
- Navigation block at the end of every lesson: 返回本单元目录 `00-overview.md`, 上一课 (file link), 下一课 (file link; the last lesson links the stage assessment; the assessment links the module overview).
- Lesson writers create exactly one file and never edit another file, never run `git add` or `git commit`.
- Code must run on Python 3.14 standard library only where possible. FastAPI, Docker and similar examples state installation, and any output that was not actually executed is labelled `预期输出` — never present a fabricated run as verified.
- No new third-party Python dependency. Diagrams for these units are deferred to a follow-up batch (see Ruling 1 in the ledger); prose must stand alone without a diagram.
- Do not touch `docs/02-ai-solutions/`, and do not change the discovery unit's lesson numbering.

## File Map

All paths are under `docs/01-traditional-solutions/`.

### Unit 02 — Web and network (10 files)

| # | File | Title | Slug | Stage | Time | Spec |
| --- | --- | --- | --- | --- | --- | --- |
| — | `02-web-and-network/00-overview.md` | Web 与网络 | `web-and-network-overview` | design | 20m | §5.2 route |
| 01 | `02-web-and-network/01-web-architecture-and-layers.md` | 客户端、服务端与网络分层 | `web-architecture-and-layers` | design | 45m | §5.2 第 1 项 |
| 02 | `02-web-and-network/02-tcp-ip-dns-and-firewall.md` | TCP/IP、DNS 与防火墙 | `tcp-ip-dns-and-firewall` | design | 55m | §5.2 第 2 项 |
| 03 | `02-web-and-network/03-http-request-response.md` | HTTP 请求、响应与状态码 | `http-request-response` | design | 60m | §5.2 第 3 项 |
| 04 | `02-web-and-network/04-headers-cookies-and-caching.md` | Header、Cookie 与缓存 | `headers-cookies-and-caching` | design | 50m | §5.2 第 4 项 |
| 05 | `02-web-and-network/05-https-tls-and-certificates.md` | HTTPS、TLS 与证书 | `https-tls-and-certificates` | design | 55m | §5.2 第 5 项 |
| 06 | `02-web-and-network/06-json-xml-and-encoding.md` | JSON、XML、CSV 与字符编码 | `json-xml-and-encoding` | design | 50m | §5.2 第 6 项 |
| 07 | `02-web-and-network/07-cors-csrf-and-browser-security.md` | CORS、CSRF 与浏览器安全 | `cors-csrf-and-browser-security` | design | 55m | §5.2 第 7 项 |
| 08 | `02-web-and-network/08-curl-and-network-diagnostics.md` | curl 与网络诊断 | `curl-and-network-diagnostics` | operate-and-optimize | 50m | §5.2 第 8 项 |
| 09 | `02-web-and-network/09-reverse-proxy-load-balancer-cdn.md` | 反向代理、负载均衡与 CDN | `reverse-proxy-load-balancer-cdn` | design | 55m | §5.2 第 9 项 |
| 10 | `02-web-and-network/10-stage-assessment.md` | Web 与网络阶段综合测评 | `web-and-network-stage-assessment` | design | 90m | §10 |

### Unit 03 — API and integration (15 files)

| # | File | Title | Slug | Stage | Time | Spec |
| --- | --- | --- | --- | --- | --- | --- |
| — | `03-api-and-integration/00-overview.md` | API 与系统集成 | `api-and-integration-overview` | design | 20m | §5.3 route |
| 01 | `03-api-and-integration/01-api-rest-and-resource-modeling.md` | API、REST 与资源建模 | `api-rest-and-resource-modeling` | design | 55m | §5.3 第 1 项 |
| 02 | `03-api-and-integration/02-openapi-and-contracts.md` | OpenAPI 与接口契约 | `openapi-and-contracts` | design | 50m | §5.3 第 2 项 |
| 03 | `03-api-and-integration/03-validation-errors-and-versioning.md` | 参数校验、错误模型与版本管理 | `validation-errors-and-versioning` | design | 55m | §5.3 第 3 项 |
| 04 | `03-api-and-integration/04-pagination-filtering-and-rate-limits.md` | 分页、过滤、批量与限流 | `pagination-filtering-and-rate-limits` | design | 50m | §5.3 第 4 项 |
| 05 | `03-api-and-integration/05-timeout-retry-backoff-and-idempotency.md` | 超时、重试、退避与幂等 | `timeout-retry-backoff-and-idempotency` | build-and-integrate | 60m | §5.3 第 5 项 |
| 06 | `03-api-and-integration/06-circuit-breaking-degradation-and-isolation.md` | 熔断、降级与隔离 | `circuit-breaking-degradation-and-isolation` | build-and-integrate | 50m | §5.3 第 5 项 |
| 07 | `03-api-and-integration/07-webhooks-signing-and-replay-protection.md` | Webhook、签名与重放保护 | `webhooks-signing-and-replay-protection` | design | 55m | §5.3 第 6 项 |
| 08 | `03-api-and-integration/08-polling-sse-websocket-and-callbacks.md` | 轮询、SSE、WebSocket 与回调 | `polling-sse-websocket-and-callbacks` | design | 55m | §5.3 第 7 项 |
| 09 | `03-api-and-integration/09-email-sms-jobs-and-file-exchange.md` | 邮件、短信、定时任务与文件交换 | `email-sms-jobs-and-file-exchange` | build-and-integrate | 50m | §5.3 第 8 项 |
| 10 | `03-api-and-integration/10-message-queues-pubsub-and-dlq.md` | 消息队列、发布订阅与死信队列 | `message-queues-pubsub-and-dlq` | design | 60m | §5.3 第 9 项 |
| 11 | `03-api-and-integration/11-outbox-compensation-and-eventual-consistency.md` | Outbox、补偿与最终一致性 | `outbox-compensation-and-eventual-consistency` | build-and-integrate | 55m | §5.3 第 10 项 |
| 12 | `03-api-and-integration/12-etl-elt-cdc-and-data-sync.md` | ETL、ELT、CDC 与数据同步 | `etl-elt-cdc-and-data-sync` | build-and-integrate | 55m | §5.3 第 11 项 |
| 13 | `03-api-and-integration/13-sync-vs-async-integration-selection.md` | 同步与异步集成模式选型 | `sync-vs-async-integration-selection` | design | 55m | §5.3 第 12 项 |
| 14 | `03-api-and-integration/14-stage-assessment.md` | API 与集成阶段综合测评 | `api-and-integration-stage-assessment` | design | 90m | §10 |

### Unit 04 — Identity, permission and security (12 files)

| # | File | Title | Slug | Stage | Time | Spec |
| --- | --- | --- | --- | --- | --- | --- |
| — | `04-identity-and-security/00-overview.md` | 身份、权限与安全 | `identity-and-security-overview` | design | 20m | §5.4 route |
| 01 | `04-identity-and-security/01-authentication-authorization-and-audit.md` | 认证、授权与审计 | `authentication-authorization-and-audit` | design | 50m | §5.4 第 1 项 |
| 02 | `04-identity-and-security/02-passwords-mfa-session-and-apikeys.md` | 密码、MFA、Session 与 API Key | `passwords-mfa-session-and-apikeys` | design | 55m | §5.4 第 2 项 |
| 03 | `04-identity-and-security/03-jwt-structure-and-validation.md` | JWT 结构、签发与校验 | `jwt-structure-and-validation` | build-and-integrate | 60m | §5.4 第 3 项 |
| 04 | `04-identity-and-security/04-oauth2-flows-and-pkce.md` | OAuth 2.0 授权流程与 PKCE | `oauth2-flows-and-pkce` | design | 60m | §5.4 第 4 项 |
| 05 | `04-identity-and-security/05-openid-connect-and-id-tokens.md` | OpenID Connect 与身份令牌 | `openid-connect-and-id-tokens` | design | 50m | §5.4 第 5 项 |
| 06 | `04-identity-and-security/06-sso-saml-and-enterprise-identity.md` | SSO、SAML 与企业身份接入 | `sso-saml-and-enterprise-identity` | design | 60m | §5.4 第 6 项 |
| 07 | `04-identity-and-security/07-rbac-abac-and-multi-tenant-permissions.md` | RBAC、ABAC 与多租户权限 | `rbac-abac-and-multi-tenant-permissions` | design | 60m | §5.4 第 7 项 |
| 08 | `04-identity-and-security/08-secrets-and-key-management.md` | Secret、证书与密钥管理 | `secrets-and-key-management` | operate-and-optimize | 50m | §5.4 第 8 项 |
| 09 | `04-identity-and-security/09-web-api-attacks-and-secure-design.md` | 常见 Web/API 攻击与安全设计 | `web-api-attacks-and-secure-design` | design | 60m | §5.4 第 9 项 |
| 10 | `04-identity-and-security/10-data-classification-encryption-and-compliance.md` | 数据分类、脱敏与合规基础 | `data-classification-encryption-and-compliance` | design | 55m | §5.4 第 10 项 |
| 11 | `04-identity-and-security/11-stage-assessment.md` | 身份与安全阶段综合测评 | `identity-and-security-stage-assessment` | design | 90m | §10 |

### Unit 05 — Data and application architecture (12 files)

| # | File | Title | Slug | Stage | Time | Spec |
| --- | --- | --- | --- | --- | --- | --- |
| — | `05-data-and-architecture/00-overview.md` | 数据与应用架构 | `data-and-architecture-overview` | design | 20m | §5.5 route |
| 01 | `05-data-and-architecture/01-sql-tables-and-relationships.md` | SQL、表设计与数据关系 | `sql-tables-and-relationships` | design | 55m | §5.5 第 1 项 |
| 02 | `05-data-and-architecture/02-indexes-transactions-and-migrations.md` | 索引、事务、锁与数据库迁移 | `indexes-transactions-and-migrations` | design | 60m | §5.5 第 2 项 |
| 03 | `05-data-and-architecture/03-nosql-redis-and-caching.md` | NoSQL、Redis 与缓存失效 | `nosql-redis-and-caching` | design | 55m | §5.5 第 3 项 |
| 04 | `05-data-and-architecture/04-object-storage-and-file-management.md` | 对象存储与文件管理 | `object-storage-and-file-management` | design | 45m | §5.5 第 4 项 |
| 05 | `05-data-and-architecture/05-time-money-uuid-and-encoding.md` | 时间、金额、UUID 与编码陷阱 | `time-money-uuid-and-encoding` | design | 55m | §5.5 第 5 项 |
| 06 | `05-data-and-architecture/06-data-quality-and-consistency.md` | 数据质量、校验与一致性 | `data-quality-and-consistency` | design | 50m | §5.5 第 6 项 |
| 07 | `05-data-and-architecture/07-monolith-microservices-and-serverless.md` | 单体、微服务与无服务器架构 | `monolith-microservices-and-serverless` | design | 60m | §5.5 第 7 项 |
| 08 | `05-data-and-architecture/08-api-gateway-and-service-discovery.md` | API Gateway 与服务发现 | `api-gateway-and-service-discovery` | design | 50m | §5.5 第 8 项 |
| 09 | `05-data-and-architecture/09-high-availability-and-disaster-recovery.md` | 高可用、容错与灾难恢复 | `high-availability-and-disaster-recovery` | operate-and-optimize | 60m | §5.5 第 9 项 |
| 10 | `05-data-and-architecture/10-architecture-tradeoffs-and-adr.md` | 架构权衡、ADR 与容量成本 | `architecture-tradeoffs-and-adr` | design | 60m | §5.5 第 10 项 |
| 11 | `05-data-and-architecture/11-stage-assessment.md` | 数据与架构阶段综合测评 | `data-and-architecture-stage-assessment` | design | 90m | §10 |

### Unit 06 — Development, testing and delivery (12 files)

| # | File | Title | Slug | Stage | Time | Spec |
| --- | --- | --- | --- | --- | --- | --- |
| — | `06-build-test-deliver/00-overview.md` | 开发、测试与交付 | `build-test-deliver-overview` | build-and-integrate | 20m | §5.6 route |
| 01 | `06-build-test-deliver/01-fastapi-service-and-layering.md` | FastAPI 最小服务与项目分层 | `fastapi-service-and-layering` | build-and-integrate | 60m | §5.6 第 1 项 |
| 02 | `06-build-test-deliver/02-dependencies-config-and-secrets.md` | 依赖、虚拟环境、配置与 Secret | `dependencies-config-and-secrets` | build-and-integrate | 50m | §5.6 第 2 项 |
| 03 | `06-build-test-deliver/03-exception-handling-and-structured-logging.md` | 异常处理与结构化日志 | `exception-handling-and-structured-logging` | build-and-integrate | 55m | §5.6 第 3 项 |
| 04 | `06-build-test-deliver/04-git-branching-and-code-review.md` | Git、版本与代码审查 | `git-branching-and-code-review` | build-and-integrate | 45m | §5.6 第 4 项 |
| 05 | `06-build-test-deliver/05-test-levels-and-acceptance.md` | 单元、集成、契约、端到端与验收测试 | `test-levels-and-acceptance` | test-and-validate | 60m | §5.6 第 5 项 |
| 06 | `06-build-test-deliver/06-performance-security-and-data-testing.md` | 性能、安全与数据质量测试 | `performance-security-and-data-testing` | test-and-validate | 55m | §5.6 第 6 项 |
| 07 | `06-build-test-deliver/07-linux-processes-and-diagnostics.md` | Linux、进程与诊断方法 | `linux-processes-and-diagnostics` | operate-and-optimize | 50m | §5.6 第 7 项 |
| 08 | `06-build-test-deliver/08-docker-and-compose.md` | Docker 与 Docker Compose | `docker-and-compose` | deploy-and-deliver | 55m | §5.6 第 8 项 |
| 09 | `06-build-test-deliver/09-cicd-migrations-canary-and-rollback.md` | CI/CD、变更、灰度与回滚 | `cicd-migrations-canary-and-rollback` | deploy-and-deliver | 60m | §5.6 第 9 项 |
| 10 | `06-build-test-deliver/10-cloud-kubernetes-and-iac.md` | 云计算、Kubernetes 与 IaC | `cloud-kubernetes-and-iac` | deploy-and-deliver | 55m | §5.6 第 10 项 |
| 11 | `06-build-test-deliver/11-stage-assessment.md` | 开发、测试与交付阶段综合测评 | `build-test-deliver-stage-assessment` | build-and-integrate | 90m | §10 |

### Unit 07 — Operate and optimize (10 files)

| # | File | Title | Slug | Stage | Time | Spec |
| --- | --- | --- | --- | --- | --- | --- |
| — | `07-operate-and-optimize/00-overview.md` | 运行与持续优化 | `operate-and-optimize-overview` | operate-and-optimize | 20m | §5.7 route |
| 01 | `07-operate-and-optimize/01-logs-metrics-tracing-and-alerting.md` | 日志、指标、Tracing 与告警 | `logs-metrics-tracing-and-alerting` | operate-and-optimize | 55m | §5.7 第 1 项 |
| 02 | `07-operate-and-optimize/02-correlation-id-and-request-tracing.md` | Correlation ID 与请求链路 | `correlation-id-and-request-tracing` | operate-and-optimize | 50m | §5.7 第 2 项 |
| 03 | `07-operate-and-optimize/03-opentelemetry-prometheus-grafana.md` | OpenTelemetry、Prometheus 与 Grafana | `opentelemetry-prometheus-grafana` | operate-and-optimize | 55m | §5.7 第 3 项 |
| 04 | `07-operate-and-optimize/04-sli-slo-sla-and-error-budget.md` | SLI、SLO、SLA 与错误预算 | `sli-slo-sla-and-error-budget` | operate-and-optimize | 55m | §5.7 第 4 项 |
| 05 | `07-operate-and-optimize/05-performance-capacity-and-cost.md` | 性能、容量、配额与成本 | `performance-capacity-and-cost` | operate-and-optimize | 50m | §5.7 第 5 项 |
| 06 | `07-operate-and-optimize/06-incident-response-and-postmortem.md` | 故障分级、响应与复盘 | `incident-response-and-postmortem` | operate-and-optimize | 55m | §5.7 第 6 项 |
| 07 | `07-operate-and-optimize/07-backup-restore-and-business-continuity.md` | 备份、恢复与业务连续性 | `backup-restore-and-business-continuity` | operate-and-optimize | 50m | §5.7 第 7 项 |
| 08 | `07-operate-and-optimize/08-runbooks-and-operational-handover.md` | Runbook 与知识移交 | `runbooks-and-operational-handover` | deploy-and-deliver | 50m | §5.7 第 8 项 |
| 09 | `07-operate-and-optimize/09-stage-assessment.md` | 运行与优化阶段综合测评 | `operate-and-optimize-stage-assessment` | operate-and-optimize | 90m | §10 |

### Shared navigation (Task 7)

- `docs/01-traditional-solutions/00-overview.md`: link all seven units instead of the current prose-only route.
- `docs/00-start-here/04-knowledge-map.md`: move the six units from 计划中 to 已发布.
- `docs/reference/glossary.md`: add every term newly defined by these units, one row per term, anchored to its first full explanation.
- `docs/reference/technology-index.md`: link new topics to their lessons.
- `docs/reference/troubleshooting-index.md`: link new symptoms to their lessons.
- `README.md`: keep the start path; no structural change expected.

## Generation Contract

Every lesson file starts with this front matter, in this key order, with no extra keys:

```yaml
---
title: <Chinese title>
slug: <slug>
module: traditional-solutions
stage: <stage value>
type: core
difficulty: beginner|intermediate
duration: <time>
prerequisites:
  - <slug>
outcomes:
  - <checkable outcome>
  - <checkable outcome>
  - <checkable outcome>
last_reviewed: 2026-10-19
---
```

Then `# <Chinese title>` followed by exactly these H2 headings in order:

`为什么需要学习`、`学习目标`、`前置知识`、`业务场景`、`核心概念`、`工作原理`、`架构与选型`、`最小示例`、`动手实验`、`常见错误与排查`、`安全与生产注意事项`、`本课总结`、`思考题`、`小测`、`答案与解析`、`延伸阅读与下一课`

Style rules (from spec §8–§9): `**bold**` for conclusions, `*italics*` for first-use terms, `<u>` for error-prone points, **`**<u>bold underline</u>**`** for security or production risks, blockquotes for a core conclusion, tables for comparisons, ordered lists for procedures. 2–4k Chinese characters. 小测 has 3–5 concept questions plus 1 scenario question; 答案与解析 explains wrong options.

## Task 1: Unit 02 — Web and network

**Files:** the 10 files of Unit 02 in the File Map.

**Interfaces:** consumes `discovery-and-requirements-overview`; produces `web-and-network-overview` consumed by Unit 03.

- [ ] **Step 1:** Dispatch one writing subagent per lesson (01–09) in parallel, using the Generation Contract and the row from the File Map.
- [ ] **Step 2:** Write `00-overview.md` (card: unit goal, 7–9 hour route, lesson list, deliverables, completion rule, link back to module overview and forward to the stage assessment).
- [ ] **Step 3:** Write `10-stage-assessment.md` (advanced: checklist, 15+ questions, fresh scenario, deliverable task, 100-point rubric, answers with misconception analysis, score-based remediation links).
- [ ] **Step 4:** Run `python3 scripts/validate_docs.py docs/01-traditional-solutions/02-web-and-network`; fix every issue.
- [ ] **Step 5:** Commit: `git add docs/01-traditional-solutions/02-web-and-network && git commit -m "docs: publish web and network unit"`.

## Task 2: Unit 03 — API and integration

**Files:** the 15 files of Unit 03.

**Interfaces:** consumes `web-and-network-overview`; produces `api-and-integration-overview` consumed by Unit 04.

- [ ] **Step 1:** Dispatch one writing subagent per lesson (01–13) in parallel.
- [ ] **Step 2:** Write `00-overview.md`.
- [ ] **Step 3:** Write `14-stage-assessment.md`.
- [ ] **Step 4:** Validate the unit directory; fix every issue.
- [ ] **Step 5:** Commit: `docs: publish api and integration unit`.

## Task 3: Unit 04 — Identity, permission and security

**Files:** the 12 files of Unit 04.

**Interfaces:** consumes `api-and-integration-overview`; produces `identity-and-security-overview` consumed by Unit 05.

- [ ] **Step 1:** Dispatch one writing subagent per lesson (01–10) in parallel.
- [ ] **Step 2:** Write `00-overview.md`.
- [ ] **Step 3:** Write `11-stage-assessment.md`.
- [ ] **Step 4:** Validate the unit directory; fix every issue.
- [ ] **Step 5:** Commit: `docs: publish identity and security unit`.

## Task 4: Unit 05 — Data and application architecture

**Files:** the 12 files of Unit 05.

**Interfaces:** consumes `identity-and-security-overview`; produces `data-and-architecture-overview` consumed by Unit 06.

- [ ] **Step 1:** Dispatch one writing subagent per lesson (01–10) in parallel.
- [ ] **Step 2:** Write `00-overview.md`.
- [ ] **Step 3:** Write `11-stage-assessment.md`.
- [ ] **Step 4:** Validate the unit directory; fix every issue.
- [ ] **Step 5:** Commit: `docs: publish data and architecture unit`.

## Task 5: Unit 06 — Development, testing and delivery

**Files:** the 12 files of Unit 06.

**Interfaces:** consumes `data-and-architecture-overview`; produces `build-test-deliver-overview` consumed by Unit 07.

- [ ] **Step 1:** Dispatch one writing subagent per lesson (01–10) in parallel.
- [ ] **Step 2:** Write `00-overview.md`.
- [ ] **Step 3:** Write `11-stage-assessment.md`.
- [ ] **Step 4:** Validate the unit directory; fix every issue.
- [ ] **Step 5:** Commit: `docs: publish build test deliver unit`.

## Task 6: Unit 07 — Operate and optimize

**Files:** the 10 files of Unit 07.

**Interfaces:** consumes `build-test-deliver-overview`; the assessment's next step returns to the module overview.

- [ ] **Step 1:** Dispatch one writing subagent per lesson (01–08) in parallel.
- [ ] **Step 2:** Write `00-overview.md`.
- [ ] **Step 3:** Write `09-stage-assessment.md`.
- [ ] **Step 4:** Validate the unit directory; fix every issue.
- [ ] **Step 5:** Commit: `docs: publish operate and optimize unit`.

## Task 7: Shared navigation and indexes

**Files:** the six shared files in the File Map.

**Interfaces:** consumes all 72 new files; produces a navigable course with no planned-link gaps.

- [ ] **Step 1:** Update `docs/01-traditional-solutions/00-overview.md` so all seven units are clickable and the route matches the published order.
- [ ] **Step 2:** Update `docs/00-start-here/04-knowledge-map.md`; move the six units under 已发布, keep only genuinely unpublished AI units under 计划中.
- [ ] **Step 3:** Update `docs/reference/glossary.md` with the terms these units define.
- [ ] **Step 4:** Update `docs/reference/technology-index.md` and `docs/reference/troubleshooting-index.md`.
- [ ] **Step 5:** Validate `docs`; fix every issue.
- [ ] **Step 6:** Commit: `docs: connect traditional modules navigation`.

## Task 8: Release verification

- [ ] **Step 1:** Run `python3 -m unittest discover -s tests -v`; all tests pass.
- [ ] **Step 2:** Run `python3 scripts/validate_docs.py docs`; exit 0, no output.
- [ ] **Step 3:** Run `git diff --check`; exit 0.
- [ ] **Step 4:** Follow the learner path: README → introduction → lifecycle → module overview → unit 02 → … → unit 07 assessment → module overview. No dead ends.
- [ ] **Step 5:** Confirm every unit has exactly one `00-overview.md` and one `*-stage-assessment.md`, and that no file outside `docs/01-traditional-solutions/` plus the six shared files changed.
