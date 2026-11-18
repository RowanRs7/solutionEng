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
last_reviewed: 2026-11-18
---

# 排障索引

## 通用排障顺序

先别急着改配置。按这个顺序走一遍，能少绕很多弯路：确认现象 → 记下发生时间和请求标识 → 查最近变更 → 看配置、网络、依赖 → 最后翻日志和指标。每轮只改一个变量，改完立刻验证，这样才知道到底是哪一步起了作用。

## 按症状查找

下面每条都按“症状 → 常见原因 → 对应课程”来写。先找到最像的一条，再点进课程看原理和验证方法；症状对不上就别硬套，回到通用顺序重新走一遍。

- 连不上，客户端报 `connection refused`：要么端口上根本没有进程在监听，要么服务只绑定了 `127.0.0.1`，外部进不来 → [TCP/IP、DNS 与防火墙](../01-traditional-solutions/02-web-and-network/02-tcp-ip-dns-and-firewall.md)。
- 浏览器提示证书错误，比如 `ERR_CERT_AUTHORITY_INVALID`、`ERR_CERT_COMMON_NAME_INVALID`：多半是缺中间证书，或者证书里的域名（SAN）和访问地址对不上；直接用 IP 访问也会触发 → [HTTPS、TLS 与证书](../01-traditional-solutions/02-web-and-network/05-https-tls-and-certificates.md)。
- CORS 预检返回 `204` 看似通过，正式请求还是被拦：正式响应漏了 `Allow-Origin`，或者少了 `Vary: Origin`，缓存把 A 站的响应给了 B 站 → [CORS、CSRF 与浏览器安全](../01-traditional-solutions/02-web-and-network/07-cors-csrf-and-browser-security.md)。
- CDN 命中率接近 0、源站被打满：响应没带 `Cache-Control`，或者带了 `Set-Cookie`，被 CDN 判定为不能共享 → [Header、Cookie 与缓存](../01-traditional-solutions/02-web-and-network/04-headers-cookies-and-caching.md)。
- 扩容之后用户被反复踢回登录页：会话存在单台机器的内存里，新实例不认识旧会话，入口又没做会话保持 → [反向代理、负载均衡与 CDN](../01-traditional-solutions/02-web-and-network/09-reverse-proxy-load-balancer-cdn.md)。
- 超时重试之后出现两笔退款：把“结果未知”当成了失败，而且重试时换了新的幂等键，服务端认不出是同一笔 → [超时、重试、退避与幂等](../01-traditional-solutions/03-api-and-integration/05-timeout-retry-backoff-and-idempotency.md)。
- Webhook 重复投递、同一事件被处理两次：没按事件 ID 去重，或者去重逻辑写在业务副作用之后，等于没防住 → [Webhook、签名与重放保护](../01-traditional-solutions/03-api-and-integration/07-webhooks-signing-and-replay-protection.md)。
- 队列越堆越多：消费者不够、单条处理变慢，或者下游在限流。先看积压是匀速涨还是加速涨，再决定扩容还是先修下游 → [消息队列、发布订阅与死信队列](../01-traditional-solutions/03-api-and-integration/10-message-queues-pubsub-and-dlq.md)。
- 下游已经大面积超时，熔断器却一直停在 `closed`：只设了失败率阈值，没设最小请求数；流量太低时永远凑不够比例 → [熔断、降级与隔离](../01-traditional-solutions/03-api-and-integration/06-circuit-breaking-degradation-and-isolation.md)。
- 所有服务同时 `401`、提示签名无效：轮换密钥时先把旧密钥下线了，令牌头里的 `kid` 找不到对应密钥 → [JWT 结构、签发与校验](../01-traditional-solutions/04-identity-and-security/03-jwt-structure-and-validation.md)。
- 换令牌总是报 `invalid_grant`：授权码已经用过或过期，也可能 `redirect_uri` 和登记值差了一个字符 → [OAuth 2.0 授权流程与 PKCE](../01-traditional-solutions/04-identity-and-security/04-oauth2-flows-and-pkce.md)。
- 换了身份平台后，所有用户都被认成同一个人：拿 `email` 或第三方的 `user_id` 当主键，而字段含义已经变了 → [OpenID Connect 与身份令牌](../01-traditional-solutions/04-identity-and-security/05-openid-connect-and-id-tokens.md)。
- 改一下 `order_id` 就能读到别家的订单：只在应用层按租户过滤，数据层没有强制注入租户条件 → [RBAC、ABAC 与多租户权限](../01-traditional-solutions/04-identity-and-security/07-rbac-abac-and-multi-tenant-permissions.md)。
- 日志里出现完整 Key、密码或连接串：中间件打印了请求头，或者异常堆栈把配置带了出来 → [Secret、证书与密钥管理](../01-traditional-solutions/04-identity-and-security/08-secrets-and-key-management.md)。
- 退款总额和渠道差几分钱、越累越大：金额用 `FLOAT` 存，或者多处各自舍入、方向不一致 → [时间、金额、UUID 与编码陷阱](../01-traditional-solutions/05-data-and-architecture/05-time-money-uuid-and-encoding.md)。
- 客服看到的状态和财务对不上：写库后删缓存失败，或者用了“先删缓存再写库”的顺序 → [NoSQL、Redis 与缓存失效](../01-traditional-solutions/05-data-and-architecture/03-nosql-redis-and-caching.md)。
- 建了索引，查询还是全表扫：查询条件跳过了最左列，或者索引列被函数、类型转换包住了 → [索引、事务、锁与数据库迁移](../01-traditional-solutions/05-data-and-architecture/02-indexes-transactions-and-migrations.md)。
- 备份天天成功，恢复时却表不存在或数据缺失：直接用 `cp` 拷在线库文件，没走备份 API 和日志归档，拷到的本来就不完整 → [高可用、容错与灾难恢复](../01-traditional-solutions/05-data-and-architecture/09-high-availability-and-disaster-recovery.md)。
- 容器启动即退出，`ps` 里查不到：`CMD` 写成了 shell 形式还加了 `&`，主进程跑到后台，容器以为没事可做就退了 → [Docker 与 Docker Compose](../01-traditional-solutions/06-build-test-deliver/08-docker-and-compose.md)。
- `ss -lntp` 显示有监听，外部就是连不上：进程只绑定了 `127.0.0.1`，没有监听业务网卡 → [Linux、进程与诊断方法](../01-traditional-solutions/06-build-test-deliver/07-linux-processes-and-diagnostics.md)。
- 流水线全绿，发版后错误率立刻上升：生产和测试的配置或依赖不一致，甚至两次发布的产物根本不是同一份 → [CI/CD、变更、灰度与回滚](../01-traditional-solutions/06-build-test-deliver/09-cicd-migrations-canary-and-rollback.md)。
- 本地能跑，CI 或镜像里报 `ImportError`：依赖没锁版本，被解析出了新版本；或者包装进了系统解释器，而不是虚拟环境 → [依赖、虚拟环境、配置与 Secret](../01-traditional-solutions/06-build-test-deliver/02-dependencies-config-and-secrets.md)。
- 日志里有 `request_id`，同一个请求的多行还是串不起来：标识被拼进了文案而不是独立字段，或者没往下游透传 → [Correlation ID 与请求链路](../01-traditional-solutions/07-operate-and-optimize/02-correlation-id-and-request-tracing.md)。
- 面板上的 p95 是一条直线，出故障也不动：对 `_bucket` 求了平均值，或者对 summary 的分位数再取 `avg`，属于算错了指标 → [OpenTelemetry、Prometheus 与 Grafana](../01-traditional-solutions/07-operate-and-optimize/03-opentelemetry-prometheus-grafana.md)。
- 告警每天上百条，值班人开始无视：只按资源阈值告警，没按影响面分级，也没把同指纹的告警归并 → [日志、指标、Tracing 与告警](../01-traditional-solutions/07-operate-and-optimize/01-logs-metrics-tracing-and-alerting.md)。
- 答非所问，多轮追问总检索到上一个话题：没做指代消解，改写时又把实体换掉了。先把改写前后的查询打出来，实体只允许来自原句和会话 → [关键词、向量、混合检索与 Query 改写](../02-ai-solutions/04-rag-and-knowledge/05-hybrid-search-and-query-rewriting.md)。
- 引用和原文对不上，引文本身没错但结论相反：只校验了“引用存不存在”，没校验“它能不能支持这句断言”。要加逐字比对和支撑判断 → [引用、溯源与可信回答](../02-ai-solutions/04-rag-and-knowledge/07-citations-and-grounded-answers.md)。
- 切分后上下文断裂，命中的片段缺前提：片段把限定条件或标题切掉了。改成按结构切分、给片段加标题前缀，必要时用父子块 → [切分、重叠与上下文保留](../02-ai-solutions/04-rag-and-knowledge/04-chunking-and-context-preservation.md)。
- 召回被长度截断，回答引用了不存在的条款：上下文预算不够时截断了条款正文，编号就和正文错位了。改为整条丢弃，由组装器统一编号 → [Rerank、结果筛选与上下文组装](../02-ai-solutions/04-rag-and-knowledge/06-rerank-and-context-assembly.md)。
- 越权读到别人的文档、不同租户互相可见：先做 ANN 检索再过滤，或者租户 ID 取自前端参数。改成检索前裁剪，租户只从服务端会话里解析 → [权限感知检索与多租户隔离](../02-ai-solutions/04-rag-and-knowledge/08-permission-aware-retrieval.md)。
- 检索指标很高，回答还是不能用，也分不清该改检索还是改生成：只记了最终答案，没记 retrieved IDs。补齐链路埋点，再按固定顺序归因 → [RAG 评测与错误分析](../02-ai-solutions/04-rag-and-knowledge/10-rag-evaluation-and-error-analysis.md)。
- 模型返回的 JSON 少字段或多字段，导致入库失败：没开严格模式、没设 `additionalProperties: false`。字段全部 required，并在服务端拒绝未知字段 → [结构化输出与 JSON Schema](../02-ai-solutions/03-model-and-prompt/05-structured-output-and-json-schema.md)。
- JSON 解析反复失败、偶尔空答复：修复提示没带具体错误，或者响应被截断却没检查结束原因。限制修复 1 到 2 次，并显式处理截断 → [输出解析、校验、修复与重试](../02-ai-solutions/03-model-and-prompt/06-output-parsing-validation-and-repair.md)。
- 流式输出中断、页面一直转圈：网关把流式响应缓冲住了。先用 `curl -N` 看是不是逐段到达，再关掉代理缓冲 → [流式响应、批处理与异步任务](../02-ai-solutions/03-model-and-prompt/07-streaming-batch-and-async.md)。
- 刷新页面答复就没了、重连后重复渲染：会话只存在前端内存里，服务端又忽略 `Last-Event-ID`。改成服务端持久化，并按事件 ID 去重 → [会话、消息、状态与流式输出](../02-ai-solutions/06-ai-application-architecture/04-session-state-and-streaming.md)。
- 工具调用参数不合法、总缺字段：必填项太多，或者字段名看不出含义。减少必填、改成语义化命名，再补示例值 → [工具描述、参数 Schema 与返回值](../02-ai-solutions/05-tools-and-agents/02-tool-schemas-and-descriptions.md)。
- 工具重复调用、写操作执行两次：非幂等的写操作被自动重试了。把幂等键落库复用，并显式建模“结果未知” → [工具超时、重试、沙箱、审计与失败模式](../02-ai-solutions/05-tools-and-agents/09-tool-reliability-sandbox-and-failure-modes.md)。
- Agent 死循环、轮次耗尽也没人知道原因：终止条件只有“模型说完了”这一个。要加最大轮数、无进展检测和预算上限 → [Function Calling 的工作机制](../02-ai-solutions/05-tools-and-agents/01-function-calling-mechanics.md)。
- 首 Token 延迟高，但逐字输出很流畅：时间花在排队或预填充上，解码本身正常。把 TTFT 拆成两段看，扩副本或开前缀缓存 → [并发、吞吐、首 Token 延迟与总延迟](../02-ai-solutions/08-deploy-operate-optimize/03-concurrency-throughput-and-latency.md)。
- Token 成本异常上涨，请求量没变账单却翻倍：历史记录或检索片段膨胀，或者降级链把简单问题送进了贵模型。按版本对比输入 token 分布 → [Token 用量、预算与成本控制](../02-ai-solutions/08-deploy-operate-optimize/04-token-cost-and-budget.md)。
- 供应商限流返回 429，退避之后错误率反而更高：固定间隔重试形成了同步尖峰。改成指数退避加抖动，设重试预算，配额耗尽就直接降级 → [供应商限流、模型退化与 AI Runbook](../02-ai-solutions/08-deploy-operate-optimize/08-provider-limits-model-drift-and-runbook.md)。
- 评测基线漂移，供应商也没发公告：模型别名被静默升级了。固定快照 ID，并每天用黄金集跑分 → [回归、A/B 与在线评测](../02-ai-solutions/07-evaluation-security-governance/07-regression-ab-and-online-evaluation.md)。
- 注入攻击绕过系统提示，回答里出现裂图或外链：指令和数据走了同一个通道，光声明规则只是软约束。加定界、裁剪能力、检查输出、设外链白名单 → [Prompt Injection 与数据外泄](../02-ai-solutions/07-evaluation-security-governance/08-prompt-injection-and-data-exfiltration.md)。
- 灰度后效果回退，回滚了问题还在：只回滚了 Prompt，索引和模型还是新的。把版本三元组做成可原子切换的发布单元 → [灰度、回滚、迁移与持续评测](../02-ai-solutions/08-deploy-operate-optimize/07-gray-release-rollback-and-continuous-eval.md)。
- 模型指标很高，业务方仍不验收：指标口径和真实工单分布对不上。先把准确性、延迟、成本和业务指标对齐 → [准确性、延迟、成本与业务指标](../02-ai-solutions/02-discovery-and-requirements/07-accuracy-latency-cost-and-metrics.md)。

## 计划索引

两个知识模块均已发布，暂无计划中的排障入口。

## 已发布课程中的需求发现问题

这类问题不会报错，但会让方案从第一步就偏。出现下面的情况，先回需求课补，而不是继续往下画架构。

- 角色职责、决策权或责任边界不清：[解决方案架构师角色](../01-traditional-solutions/01-discovery-and-requirements/01-solution-architect-role.md)。
- 目标、责任人或意见冲突不清：[利益相关者与业务目标](../01-traditional-solutions/01-discovery-and-requirements/02-stakeholders-and-business-goals.md)。
- 对真实流程、等待或返工没有证据：[现状调研与业务流程](../01-traditional-solutions/01-discovery-and-requirements/03-current-state-and-business-process.md)。
- 用户要求含糊，异常流程缺失：[用户、角色、场景与用例](../01-traditional-solutions/01-discovery-and-requirements/04-users-roles-scenarios-and-use-cases.md)。
- “快、安全、稳定”等词无法验收：[功能与非功能需求](../01-traditional-solutions/01-discovery-and-requirements/05-functional-and-non-functional-requirements.md)。
- 项目责任、外部依赖或假设不清：[系统边界、约束、依赖与假设](../01-traditional-solutions/01-discovery-and-requirements/06-boundaries-constraints-dependencies-assumptions.md)。
- 需求冲突、范围不断增加或完成标准争议：[优先级、范围与验收标准](../01-traditional-solutions/01-discovery-and-requirements/07-priorities-scope-and-acceptance.md)。
- 风险没人负责、缺少备用方案或需求信息散落：[风险与需求交付物](../01-traditional-solutions/01-discovery-and-requirements/08-risks-and-requirement-deliverables.md)。
