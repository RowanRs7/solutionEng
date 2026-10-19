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
- 答非所问、多轮追问总检索到上一话题：未做指代消解，或改写时替换了实体；先打印改写前后查询，实体只允许来自原句与会话 → [关键词、向量、混合检索与 Query 改写](../02-ai-solutions/04-rag-and-knowledge/05-hybrid-search-and-query-rewriting.md)。
- 引用与原文不符，引文正确但结论相反：只校验了“引用是否存在”，没校验“是否支持断言”；增加逐字比对与支撑判断 → [引用、溯源与可信回答](../02-ai-solutions/04-rag-and-knowledge/07-citations-and-grounded-answers.md)。
- 切分后上下文断裂，命中片段缺前提：片段切断了限定条件或标题；改用结构切分加标题前缀，必要时用父子块 → [切分、重叠与上下文保留](../02-ai-solutions/04-rag-and-knowledge/04-chunking-and-context-preservation.md)。
- 召回被长度截断，回答引用了不存在的条款：上下文预算不足时截断了条款正文，编号与正文错位；改为整条丢弃并由组装器统一编号 → [Rerank、结果筛选与上下文组装](../02-ai-solutions/04-rag-and-knowledge/06-rerank-and-context-assembly.md)。
- 越权读到他人文档、不同租户互相可见：先 ANN 后过滤，或租户取自前端参数；改为检索前裁剪，租户只从服务端会话解析 → [权限感知检索与多租户隔离](../02-ai-solutions/04-rag-and-knowledge/08-permission-aware-retrieval.md)。
- 检索指标很高但回答仍不可用，分不清该改检索还是改生成：只记录了最终答案、没记 retrieved IDs；补齐链路埋点并按固定归因顺序判定 → [RAG 评测与错误分析](../02-ai-solutions/04-rag-and-knowledge/10-rag-evaluation-and-error-analysis.md)。
- 模型返回的 JSON 少字段或多出字段导致入库失败：未开严格模式、未设 `additionalProperties: false`；字段全部 required，并在服务端拒绝未知字段 → [结构化输出与 JSON Schema](../02-ai-solutions/03-model-and-prompt/05-structured-output-and-json-schema.md)。
- JSON 解析反复失败、偶发空答复：修复提示没带具体错误，或响应被截断而结束原因未检查；限定 1–2 次修复并显式处理截断 → [输出解析、校验、修复与重试](../02-ai-solutions/03-model-and-prompt/06-output-parsing-validation-and-repair.md)。
- 流式输出中断、页面一直转圈：网关缓冲了流式响应；先用 `curl -N` 确认是否逐段到达，再关闭代理缓冲 → [流式响应、批处理与异步任务](../02-ai-solutions/03-model-and-prompt/07-streaming-batch-and-async.md)。
- 刷新页面答复消失、重连后重复渲染：会话只存在前端内存，且服务端忽略 `Last-Event-ID`；改为服务端持久化并按事件 ID 去重 → [会话、消息、状态与流式输出](../02-ai-solutions/06-ai-application-architecture/04-session-state-and-streaming.md)。
- 工具调用参数不合法、总是缺字段：必填项过多或字段名不自解释；减少必填、改语义化命名并补示例值 → [工具描述、参数 Schema 与返回值](../02-ai-solutions/05-tools-and-agents/02-tool-schemas-and-descriptions.md)。
- 工具重复调用、写操作被执行两次：非幂等写操作被自动重试；幂等键落库复用，并把“结果未知”显式建模 → [工具超时、重试、沙箱、审计与失败模式](../02-ai-solutions/05-tools-and-agents/09-tool-reliability-sandbox-and-failure-modes.md)。
- Agent 死循环、轮次耗尽但没人知道原因：只有“模型说完了”这一个终止条件；加最大轮数、无进展检测与预算上限 → [Function Calling 的工作机制](../02-ai-solutions/05-tools-and-agents/01-function-calling-mechanics.md)。
- 首 Token 延迟高、逐字输出却流畅：排队或预填充耗时，解码正常；把 TTFT 拆成两段，扩容副本或启用前缀缓存 → [并发、吞吐、首 Token 延迟与总延迟](../02-ai-solutions/08-deploy-operate-optimize/03-concurrency-throughput-and-latency.md)。
- Token 成本异常上涨、请求量平稳但账单翻倍：历史或检索片段膨胀，或回退链把简单问题送进贵模型；按版本对比输入 token 分布 → [Token 用量、预算与成本控制](../02-ai-solutions/08-deploy-operate-optimize/04-token-cost-and-budget.md)。
- 供应商限流返回 429、退避后错误率反升：固定间隔重试形成同步尖峰；改指数退避加抖动与重试预算，配额耗尽时直接降级 → [供应商限流、模型退化与 AI Runbook](../02-ai-solutions/08-deploy-operate-optimize/08-provider-limits-model-drift-and-runbook.md)。
- 评测基线漂移，供应商没有公告也退化：模型别名被静默升级；固定快照 ID，并用每日金标集跑分 → [回归、A/B 与在线评测](../02-ai-solutions/07-evaluation-security-governance/07-regression-ab-and-online-evaluation.md)。
- 注入攻击绕过系统提示、答复里出现裂图或外链：指令与数据同通道，声明只是软约束；加定界、能力剪裁、输出检查与外链白名单 → [Prompt Injection 与数据外泄](../02-ai-solutions/07-evaluation-security-governance/08-prompt-injection-and-data-exfiltration.md)。
- 灰度后效果回退、回滚后问题依旧：只回滚了 Prompt，索引与模型仍是新的；把版本三元组做成可原子切换的发布单元 → [灰度、回滚、迁移与持续评测](../02-ai-solutions/08-deploy-operate-optimize/07-gray-release-rollback-and-continuous-eval.md)。
- 模型指标很高、业务方仍不验收：指标口径与真实工单分布不一致；先把准确性、延迟、成本与业务指标对齐 → [准确性、延迟、成本与业务指标](../02-ai-solutions/02-discovery-and-requirements/07-accuracy-latency-cost-and-metrics.md)。

## 计划索引

两个知识模块均已发布，暂无计划中的排障入口。

## 已发布课程中的需求发现问题

- 角色职责、决策权或责任边界不清：[解决方案架构师角色](../01-traditional-solutions/01-discovery-and-requirements/01-solution-architect-role.md)。
- 目标、责任人或意见冲突不清：[利益相关者与业务目标](../01-traditional-solutions/01-discovery-and-requirements/02-stakeholders-and-business-goals.md)。
- 对真实流程、等待或返工没有证据：[现状调研与业务流程](../01-traditional-solutions/01-discovery-and-requirements/03-current-state-and-business-process.md)。
- 用户要求含糊，异常流程缺失：[用户、角色、场景与用例](../01-traditional-solutions/01-discovery-and-requirements/04-users-roles-scenarios-and-use-cases.md)。
- “快、安全、稳定”等词无法验收：[功能与非功能需求](../01-traditional-solutions/01-discovery-and-requirements/05-functional-and-non-functional-requirements.md)。
- 项目责任、外部依赖或假设不清：[系统边界、约束、依赖与假设](../01-traditional-solutions/01-discovery-and-requirements/06-boundaries-constraints-dependencies-assumptions.md)。
- 需求冲突、范围不断增加或完成标准争议：[优先级、范围与验收标准](../01-traditional-solutions/01-discovery-and-requirements/07-priorities-scope-and-acceptance.md)。
- 风险没人负责、缺少备用方案或需求信息散落：[风险与需求交付物](../01-traditional-solutions/01-discovery-and-requirements/08-risks-and-requirement-deliverables.md)。
