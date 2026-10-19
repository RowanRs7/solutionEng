---
title: 排障索引
slug: troubleshooting-index
module: reference
stage: operate
type: card
difficulty: beginner
duration: 10m
prerequisites:
  - learning-guide
outcomes:
  - 用症状定位排障入口
last_reviewed: 2026-10-19
---

# 排障索引

## 通用排障顺序

确认现象、记录时间和请求标识，再检查配置、网络、依赖、日志、指标和最近变更。每次只改变一个变量。

## 按症状查找

- 连接被拒，客户端报 `connection refused`：端口没有进程监听，或服务只绑定了 `127.0.0.1` → [TCP/IP、DNS 与防火墙](../01-traditional-solutions/02-web-and-network/02-tcp-ip-dns-and-firewall.md)。
- 浏览器报证书错误，如 `ERR_CERT_AUTHORITY_INVALID`、`ERR_CERT_COMMON_NAME_INVALID`：缺中间证书，或 SAN 未含访问域名、客户端直接用 IP 访问 → [HTTPS、TLS 与证书](../01-traditional-solutions/02-web-and-network/05-https-tls-and-certificates.md)。
- CORS 预检返回 `204`，正式请求仍被拦：正式响应漏发 `Allow-Origin`，或缺 `Vary: Origin` 导致缓存串源 → [CORS、CSRF 与浏览器安全](../01-traditional-solutions/02-web-and-network/07-cors-csrf-and-browser-security.md)。
- CDN 命中率接近 0、源站被打满：响应缺 `Cache-Control`，或带了 `Set-Cookie` 被缓存判为不可共享 → [Header、Cookie 与缓存](../01-traditional-solutions/02-web-and-network/04-headers-cookies-and-caching.md)。
- 扩容后用户被反复踢回登录页：会话存在单机内存，入口没有会话保持 → [反向代理、负载均衡与 CDN](../01-traditional-solutions/02-web-and-network/09-reverse-proxy-load-balancer-cdn.md)。
- 超时重试后出现两笔退款：把“结果未知”当失败，重试时还换了新的幂等键 → [超时、重试、退避与幂等](../01-traditional-solutions/03-api-and-integration/05-timeout-retry-backoff-and-idempotency.md)。
- Webhook 重复投递、同一事件被处理两次：未按事件 ID 去重，或去重写在业务副作用之后 → [Webhook、签名与重放保护](../01-traditional-solutions/03-api-and-integration/07-webhooks-signing-and-replay-protection.md)。
- 队列堆积持续增长：消费者不足、单条处理变慢或下游限流，先看堆积斜率再扩容 → [消息队列、发布订阅与死信队列](../01-traditional-solutions/03-api-and-integration/10-message-queues-pubsub-and-dlq.md)。
- 依赖已大面积超时，熔断器却一直是 `closed`：只设了失败率阈值、没设最小请求数，低流量下永远达不到比例 → [熔断、降级与隔离](../01-traditional-solutions/03-api-and-integration/06-circuit-breaking-degradation-and-isolation.md)。
- 所有服务同时 `401`、报签名无效：轮换密钥时先下线了旧密钥，令牌头里的 `kid` 对不上 → [JWT 结构、签发与校验](../01-traditional-solutions/04-identity-and-security/03-jwt-structure-and-validation.md)。
- 换令牌总是 `invalid_grant`：授权码已用过或过期，或 `redirect_uri` 与登记值不完全一致 → [OAuth 2.0 授权流程与 PKCE](../01-traditional-solutions/04-identity-and-security/04-oauth2-flows-and-pkce.md)。
- 换了身份平台后全部用户被认成同一个人：用 `email` 或第三方 `user_id` 当主键，字段语义已经变了 → [OpenID Connect 与身份令牌](../01-traditional-solutions/04-identity-and-security/05-openid-connect-and-id-tokens.md)。
- 改 `order_id` 就能读到别家订单：只在应用层按租户过滤，数据层没有强制注入租户条件 → [RBAC、ABAC 与多租户权限](../01-traditional-solutions/04-identity-and-security/07-rbac-abac-and-multi-tenant-permissions.md)。
- 日志里出现完整 Key、密码或连接串：中间件打印了请求头，或异常堆栈带出配置 → [Secret、证书与密钥管理](../01-traditional-solutions/04-identity-and-security/08-secrets-and-key-management.md)。
- 退款总额与渠道差几分钱、金额越累越大：金额用 `FLOAT` 存储，或多处逐笔舍入方向不同 → [时间、金额、UUID 与编码陷阱](../01-traditional-solutions/05-data-and-architecture/05-time-money-uuid-and-encoding.md)。
- 客服看到的状态与财务不一致：写库后删缓存失败，或用了“先删缓存后写库”的顺序 → [NoSQL、Redis 与缓存失效](../01-traditional-solutions/05-data-and-architecture/03-nosql-redis-and-caching.md)。
- 建了索引，查询还是全表扫：条件跳过最左列，或索引列被函数、类型转换包住 → [索引、事务、锁与数据库迁移](../01-traditional-solutions/05-data-and-architecture/02-indexes-transactions-and-migrations.md)。
- 备份天天成功，恢复时表不存在或数据缺失：用 `cp` 拷在线库文件、未走备份 API 与日志归档 → [高可用、容错与灾难恢复](../01-traditional-solutions/05-data-and-architecture/09-high-availability-and-disaster-recovery.md)。
- 容器启动即退出、`ps` 里看不到：`CMD` 写成 shell 形式并加了 `&`，主进程没有留在前台 → [Docker 与 Docker Compose](../01-traditional-solutions/06-build-test-deliver/08-docker-and-compose.md)。
- `ss -lntp` 有监听但外部访问不通：进程只绑定了 `127.0.0.1`，没有监听业务网卡 → [Linux、进程与诊断方法](../01-traditional-solutions/06-build-test-deliver/07-linux-processes-and-diagnostics.md)。
- 流水线全绿，发布后错误率立刻上升：生产与测试的配置或依赖不同，产物也不是同一份 → [CI/CD、变更、灰度与回滚](../01-traditional-solutions/06-build-test-deliver/09-cicd-migrations-canary-and-rollback.md)。
- 本地能跑，CI 或镜像内报 `ImportError`：依赖未锁定被解析出新版本，或装进了系统解释器 → [依赖、虚拟环境、配置与 Secret](../01-traditional-solutions/06-build-test-deliver/02-dependencies-config-and-secrets.md)。
- 日志里有 `request_id`，同一请求的多行仍关联不起来：标识被拼进文案而非独立字段，或未在下游透传 → [Correlation ID 与请求链路](../01-traditional-solutions/07-operate-and-optimize/02-correlation-id-and-request-tracing.md)。
- 面板 p95 是一条直线、故障时也不动：对 `_bucket` 求平均值，或对 summary 分位再取 `avg` → [OpenTelemetry、Prometheus 与 Grafana](../01-traditional-solutions/07-operate-and-optimize/03-opentelemetry-prometheus-grafana.md)。
- 告警每天上百条、值班人开始忽略：只按资源阈值告警，未按影响面分级，也没做同指纹归并 → [日志、指标、Tracing 与告警](../01-traditional-solutions/07-operate-and-optimize/01-logs-metrics-tracing-and-alerting.md)。

## 计划索引

AI 模块尚未发布，以下排障入口待对应课程上线后补充链接。

- RAG 答案无依据、引用对不上原文：计划中。
- 检索命中率低、切分或嵌入模型选错：计划中。
- Agent 工具调用失败、参数不合法或反复循环：计划中。
- 模型输出不稳定、同一输入时好时坏：计划中。
- Prompt 变更后效果回退、缺评测基线：计划中。
- 模型调用超时、被限流或成本失控：计划中。

## 已发布课程中的需求发现问题

- 角色职责、决策权或责任边界不清：[解决方案架构师角色](../01-traditional-solutions/01-discovery-and-requirements/01-solution-architect-role.md)。
- 目标、责任人或意见冲突不清：[利益相关者与业务目标](../01-traditional-solutions/01-discovery-and-requirements/02-stakeholders-and-business-goals.md)。
- 对真实流程、等待或返工没有证据：[现状调研与业务流程](../01-traditional-solutions/01-discovery-and-requirements/03-current-state-and-business-process.md)。
- 用户要求含糊，异常流程缺失：[用户、角色、场景与用例](../01-traditional-solutions/01-discovery-and-requirements/04-users-roles-scenarios-and-use-cases.md)。
- “快、安全、稳定”等词无法验收：[功能与非功能需求](../01-traditional-solutions/01-discovery-and-requirements/05-functional-and-non-functional-requirements.md)。
- 项目责任、外部依赖或假设不清：[系统边界、约束、依赖与假设](../01-traditional-solutions/01-discovery-and-requirements/06-boundaries-constraints-dependencies-assumptions.md)。
- 需求冲突、范围不断增加或完成标准争议：[优先级、范围与验收标准](../01-traditional-solutions/01-discovery-and-requirements/07-priorities-scope-and-acceptance.md)。
- 风险没人负责、缺少备用方案或需求信息散落：[风险与需求交付物](../01-traditional-solutions/01-discovery-and-requirements/08-risks-and-requirement-deliverables.md)。
