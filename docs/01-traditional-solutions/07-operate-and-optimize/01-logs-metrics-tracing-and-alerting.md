---
title: 日志、指标、Tracing 与告警
slug: logs-metrics-tracing-and-alerting
module: traditional-solutions
stage: operate-and-optimize
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - build-test-deliver-overview
outcomes:
  - 区分日志、指标、Tracing 各自能回答的问题，并为一次排障任务选出合适的支柱
  - 写出含时间、级别、事件名、请求标识、链路标识与关键属性的结构化日志行，并说明每个字段的消费方
  - 按影响面与紧迫度把告警定为 P1–P4，并用同因归并、抑制、多窗口阈值完成一次降噪
last_reviewed: 2026-10-19
---

# 日志、指标、Tracing 与告警

## 为什么需要学习

大促当天上午十点，客服群连发三条消息：退款提交后一直转圈，有用户连点五次生成五个退款单，仓库说没收到退款通知。运维同时段收到 412 条告警，其中 380 条是“CPU 超过 80%”，没有一条说明退款是否成功。开发打开日志，只见“调用支付失败”“支付接口异常”这类中文句子，没有订单号，也看不出是哪台机器。

三个缺口各有其位：日志是自由文本，只能全文 `grep`；指标只有机器资源，缺“退款成功率”这类业务信号；链路只到网关，支付调用是黑盒。于是告警只能盯着资源阈值响，却回答不了“用户是否正在受影响”。

> **核心结论：** 可观测性不是把三套工具都装上，而是让日志、指标、链路共享同一套标识，从而能回答“哪里坏了、坏了多久、影响了谁”。

## 学习目标

完成本课后，你能够：

- 区分日志、指标、Tracing 各自能回答和不能回答的问题，为一个具体排障任务选中合适支柱。
- 写出包含时间、级别、事件名、`request_id`、`trace_id` 与关键属性的结构化日志行，并说明每个字段由谁消费。
- 按影响面与紧迫度把告警定为 P1–P4，并给出对应的通知渠道与响应时限。
- 用同因归并、抑制、多窗口阈值三条手段，把 3 条以上候选告警收敛成 1–2 条可行动告警。

## 前置知识

- 回看上一单元：[开发、测试与交付](../06-build-test-deliver/00-overview.md)。
- 知道 HTTP 4xx 与 5xx 的区别，能读一行 JSON。
- 已读过[异常处理与结构化日志](../06-build-test-deliver/03-exception-handling-and-structured-logging.md)，理解 `request_id` 的用途。

## 业务场景

`refund-service` 承接客服页面提交的退款：校验订单、调用支付商、写退款单、通知仓库。大促期间每分钟约 300 笔，链路上有网关、退款服务、支付商与仓库通知四个环节，四类人想知道的事并不相同：

- 客服：这笔退款什么状态，能否给用户一句准话？
- 值班开发：是支付商慢，还是我们自己慢？
- 仓储：退款单为什么没生成，要不要人工补？
- 财务：今天的退款成功率对得上对账单吗？

目标因此很具体：故障发生后 5 分钟内，值班人能用证据回答“哪一步、影响多少笔”；30 分钟内给出“继续观察还是回滚”。约束有三条：不能在退款主路径上加阻塞式上报；日志不得出现完整卡号与手机号；告警只在业务受损时响，而不是在 CPU 抖动时响。

## 核心概念

- *可观测性*：只依据系统对外输出的事实推断内部状态，不用改代码插断点。
- *日志*：离散事件的结构化记录，回答“这一次发生了什么”，代价是量大且需检索。
- *指标*：对同类事件做数值聚合得到的时间序列，回答“整体趋势与阈值”，代价是丢失单次细节。
- *Tracing*（链路追踪）：一次请求跨多个服务时的 span 树，回答“慢在哪一跳、错在哪一环”。
- *Span*：链路中的一个工作单元，带开始时间、耗时、状态与父子关系。
- *SLI* 与 *SLO*：SLI 是可计算的指标（如退款成功率），SLO 是给它定的目标（如 99.5%/30 天）；*错误预算* 是 1 减去 SLO 后允许消耗的失败额度。
- *告警分级*：按影响面（多少人受影响）与紧迫度（能否等到明天）给事件定优先级。
- *指纹*：由告警的固定维度（服务、接口、错误类）拼成的字符串，同指纹即同一条告警，也是归并与抑制的依据。

三支柱分工：

| 要回答的问题 | 合适的支柱 | 典型数据 | 不该用它判断 |
| --- | --- | --- | --- |
| 某个订单的退款为什么失败 | 日志 | `event=refund.failed`、`error_code` | 全站成功率趋势 |
| 退款成功率是否跌破 SLO | 指标 | `refund_success_ratio` 时间序列 | 具体是哪一笔失败 |
| 3 秒延迟出在哪一跳 | Tracing | span 耗时树与关键路径 | 长期容量规划 |
| 这个错误是新问题还是老问题 | 指标 + 日志 | 错误率曲线与该错误首次出现时间 | 单笔业务细节 |
| 影响哪些渠道、多少笔 | 指标（按业务维度切分） | 分渠道、分仓库的错误率 | 内部函数级原因 |

<u>三者不是替代关系：日志缺标识就只能全文搜索，指标缺业务维度就只能看 CPU，链路缺上下文传播就断在半路。</u>

告警分级：

| 级别 | 判定依据（影响面 × 紧迫度） | 晴空商城示例 | 通知渠道 | 响应时限 |
| --- | --- | --- | --- | --- |
| P1 | 核心业务不可用且无自动降级 | 退款成功率 5 分钟内从 99.6% 跌到 60% | 电话 + 值班群 | 5 分钟 |
| P2 | 主流程可用但持续受损，错误预算快速消耗 | 单渠道退款失败率 12% 持续 10 分钟 | 群内 @值班人 | 30 分钟 |
| P3 | 非核心功能异常，有明确兜底 | 退款状态推送延迟 5 分钟 | 工单或群，不 @ | 当日 |
| P4 | 趋势性风险，当前无用户影响 | 磁盘使用率 7 天涨 20% | 周报 / 看板 | 本周 |

**级别由“用户受到的影响”决定，不由“指标有多难看”决定。** CPU 90% 而成功率正常是 P4 看板项；CPU 40% 而成功率腰斩是 P1。

## 工作原理

一次退款从发生到被发现，数据按这条路径流动：

1. **入口建立上下文**：网关为请求生成 `trace_id`，上游已带则继承；本跳另有 `span_id`。
2. **日志携带标识**：写日志时把 `request_id`、`trace_id`、`route`、`status` 与业务字段写成键值，而不是拼进文案。
3. **链路逐跳传递**：调支付商、写库各产生子 span，`parent_span_id` 指向调用方，上下文通过请求头传下去。
4. **指标由事件聚合**：采集端按 `route`、`status`、`error_code` 计数并做直方图，得到成功率与 P95 延迟。
5. **规则周期评估**：告警规则按窗口计算表达式，如 `失败数 / 总数 > 0.01`，并要求窗口内最小请求量。
6. **归并与抑制**：同指纹告警合并计数；高等级事件出现后，同链路的低等级告警静默。
7. **按级别通知**：P1 打电话，P2 群内 @，P3 进工单，避免所有级别都推向同一个群。
8. **回查并复盘**：从 `trace_id` 看哪一跳慢，再用 `error_code` 聚合日志，最后用指标确认影响笔数；事后记下哪个信号先动、阈值是否要改。

顺序上有一条硬约束：<u>先有标识，再谈告警</u>。没有 `trace_id` 的日志、没有业务维度的指标，规则再精细也只能报“有问题”，报不出“哪里有问题”。

## 架构与选型

| 方案 | 适用 | 不适用 | 代价与权衡 |
| --- | --- | --- | --- |
| 全托管可观测平台 | 团队小、不愿维护存储、需要快速上线 | 数据驻留有硬要求、流量极大且成本敏感 | 上手快、免运维；按量计费，日志放量后费用难控 |
| 自建（OpenTelemetry 采集 + Prometheus + Grafana + 日志平台） | 有平台团队、需要深度定制与成本控制 | 无人专职运维的小团队 | 可控可移植；采集、存储、升级都要人维护 |
| 最小方案（结构化日志 + 少量指标 + 平台告警） | 刚上线的单体服务、教学实验 | 多服务跨团队排障 | 成本最低；只有日志时缺趋势 |

选型先回答三个问题：数据是否含个人信息（决定能否出网）；每月日志量级是 GB 还是 TB（决定存储与保留期）；值班是否有专人（决定渠道与响应承诺）。

另两项权衡常被漏掉。**指标基数**：把 `order_id` 当标签会让每个订单各占一条时间序列，内存先被烧光，业务维度只应取渠道、仓库、状态这类有限枚举。**采样率**：生产常用 1%–10% 头部采样，但**错误请求应全采**，否则最需要的那条恰好没被记录；可行做法是尾部采样或对 `status>=500` 强制保留。

## 最小示例

问题：用同一批原始事件，同时产出结构化日志、成功率与 P95 指标、一条 span 树，并把 3 条候选告警收敛成 1 条可行动告警。环境：Python 3.9 及以上，只用标准库。输入：6 个请求的 `(request_id, trace_id, status, duration_ms)`。输出：6 行 JSON 日志、1 行指标、4 行 span、1 行告警裁决。

```python
"""最小可观测性骨架：日志、指标、链路、告警共用同一套标识。"""
import json

# ---------- 1. 结构化日志：一行一条 JSON，字段名固定 ----------
def log_event(level, event, **fields):
    record = {"level": level, "event": event}      # event 是点号分层的稳定枚举，不是自然语句
    record.update(fields)                          # 业务字段平铺，不嵌套，便于按字段过滤
    return json.dumps(record, ensure_ascii=False, sort_keys=True)  # 键排序让输出可复现

# ---------- 2. 指标：从同一批事件派生，不另设一套埋点 ----------
REQUESTS = [                                       # (request_id, trace_id, status, duration_ms)
    ("req-1001", "tr-7f3a", 200,   40.0),
    ("req-1002", "tr-7f3b", 200,   55.0),
    ("req-1003", "tr-7f3c", 200,  210.0),
    ("req-1004", "tr-7f3d", 502, 3010.0),          # 支付商超时
    ("req-1005", "tr-7f3e", 502, 3120.0),          # 同因不同请求，指纹相同
    ("req-1006", "tr-7f3f", 200,   60.0),
]

def p95(values):
    ordered = sorted(values)                       # 必须先排序再取分位
    return ordered[max(0, int(round(0.95 * len(ordered))) - 1)]   # 小样本用最近秩，不插值

def metrics(requests):
    statuses = [status for _, _, status, _ in requests]
    durations = [duration for *_, duration in requests]
    failures = sum(1 for s in statuses if s >= 500)  # 只把服务端失败算进 SLI
    return {"requests": len(requests), "failures": failures,
            "error_rate": round(failures / len(requests), 3),      # 比率跨流量可比
            "p95_latency_ms": p95(durations)}

# ---------- 3. 链路：父子 span 共享 trace_id，据此定位慢在哪一跳 ----------
def spans_for(trace_id):
    return [   # 每个 span 只记本跳耗时，不重复累计，总耗时由根 span 给出
        {"trace_id": trace_id, "span_id": "s1", "parent": None, "name": "gateway", "ms": 20.0},
        {"trace_id": trace_id, "span_id": "s2", "parent": "s1", "name": "refund-service", "ms": 3010.0},
        {"trace_id": trace_id, "span_id": "s3", "parent": "s2", "name": "payment.call", "ms": 3000.0},
        {"trace_id": trace_id, "span_id": "s4", "parent": "s2", "name": "db.insert", "ms": 8.0},
    ]

# ---------- 4. 告警：分级 + 同因归并 + 抑制 ----------
CANDIDATES = [   # 一次故障通常同时点亮多条规则，先收集再裁决，而不是逐条推送
    {"signal": "single_5xx",       "route": "POST /refunds", "severity": "P4"},
    {"signal": "error_rate_high",  "route": "POST /refunds", "severity": "P2"},
    {"signal": "p95_latency_high", "route": "POST /refunds", "severity": "P3"},
]

def adjudicate(candidates, cause):
    kept, dropped = [], []
    for alert in sorted(candidates, key=lambda a: a["severity"]):  # 高等级先到，由它决定归并
        if alert["signal"] == "single_5xx":                        # 单次失败不构成行动项
            dropped.append([alert["signal"], "非行动项，只留日志"])
            continue
        if any(k["route"] == alert["route"] for k in kept):        # 同址同因：并入已有事件
            dropped.append([alert["signal"], f"并入 {kept[0]['severity']} 同一事件"])
            continue
        kept.append(dict(alert, cause=cause))                      # 带根因，值班人不必猜
    return kept, dropped

if __name__ == "__main__":
    for request_id, trace_id, status, duration in REQUESTS:
        level = "WARNING" if status >= 500 else "INFO"             # 级别描述"要谁来看"
        event = "request.failed" if status >= 500 else "request.finished"
        print(log_event(level, event, request_id=request_id, trace_id=trace_id,
                        route="POST /refunds", status=status, duration_ms=duration))
    print("-" * 30)
    print(json.dumps(metrics(REQUESTS), ensure_ascii=False, sort_keys=True))
    print("-" * 30)
    for span in spans_for("tr-7f3d"):                              # 只展开失败的那条链路
        print(json.dumps(span, ensure_ascii=False, sort_keys=True))
    print("-" * 30)
    kept, dropped = adjudicate(CANDIDATES, cause="payment_timeout")  # 根因来自指标与链路交叉
    print(json.dumps({"page": kept, "dropped": dropped}, ensure_ascii=False, sort_keys=True))
```

运行 `python3 observability_demo.py`。预期输出（`sort_keys` 保证键序稳定）：

```text
{"duration_ms": 40.0, "event": "request.finished", "level": "INFO", "request_id": "req-1001", "route": "POST /refunds", "status": 200, "trace_id": "tr-7f3a"}
{"duration_ms": 55.0, "event": "request.finished", "level": "INFO", "request_id": "req-1002", "route": "POST /refunds", "status": 200, "trace_id": "tr-7f3b"}
{"duration_ms": 210.0, "event": "request.finished", "level": "INFO", "request_id": "req-1003", "route": "POST /refunds", "status": 200, "trace_id": "tr-7f3c"}
{"duration_ms": 3010.0, "event": "request.failed", "level": "WARNING", "request_id": "req-1004", "route": "POST /refunds", "status": 502, "trace_id": "tr-7f3d"}
{"duration_ms": 3120.0, "event": "request.failed", "level": "WARNING", "request_id": "req-1005", "route": "POST /refunds", "status": 502, "trace_id": "tr-7f3e"}
{"duration_ms": 60.0, "event": "request.finished", "level": "INFO", "request_id": "req-1006", "route": "POST /refunds", "status": 200, "trace_id": "tr-7f3f"}
------------------------------
{"error_rate": 0.333, "failures": 2, "p95_latency_ms": 3120.0, "requests": 6}
------------------------------
{"ms": 20.0, "name": "gateway", "parent": null, "span_id": "s1", "trace_id": "tr-7f3d"}
{"ms": 3010.0, "name": "refund-service", "parent": "s1", "span_id": "s2", "trace_id": "tr-7f3d"}
{"ms": 3000.0, "name": "payment.call", "parent": "s2", "span_id": "s3", "trace_id": "tr-7f3d"}
{"ms": 8.0, "name": "db.insert", "parent": "s2", "span_id": "s4", "trace_id": "tr-7f3d"}
------------------------------
{"dropped": [["p95_latency_high", "并入 P2 同一事件"], ["single_5xx", "非行动项，只留日志"]], "page": [{"cause": "payment_timeout", "route": "POST /refunds", "severity": "P2", "signal": "error_rate_high"}]}
```

整体流程：

1. `log_event()` 用固定键名加平铺业务字段，采集端才能建索引、写过滤条件。
2. `metrics()` 从同一批事件派生比率与分位数，避免“日志一套、埋点一套”口径打架。
3. `spans_for()` 表达父子关系：`refund-service` 的 3010ms 里 `payment.call` 占 3000ms，关键路径一目了然。
4. `adjudicate()` 先按级别排序，再丢非行动项、归并同因项，只推一条带根因的 P2。

关键设计有三点：<u>指标从事件派生而不是另写埋点</u>，否则口径迟早不一致；`error_rate` 用比率而非失败计数，流量翻倍时才不误报；告警里必须有 `cause`，否则值班人还得从头查。

## 动手实验

前置条件：Python 3.9+；无第三方依赖；将上面的代码保存为 `observability_demo.py`；当前目录可写。

1. 运行 `python3 observability_demo.py > out.txt 2>&1`，确认日志为 6 行、指标为 1 行。
2. 校验可机读：`python3 -c "import json;[json.loads(l) for l in open('out.txt') if l.startswith('{')]" && echo ok`。
3. 按标识回查：`grep tr-7f3d out.txt` 应同时取回该请求的日志行与 span 行，且 `request_id` 一致。
4. 改指标口径：把 `failures` 改为只统计 `status == 502`，重跑，观察 `error_rate` 是否仍为 0.333。
5. 加固阈值：给 `adjudicate()` 增加 `min_requests=20`，请求数不足 20 时不推 P2、只记 INFO。
6. 降噪演练：新增一条 `{"signal": "payment_timeout_spike", "route": "POST /refunds", "severity": "P1"}`，观察它如何把 P2 归并掉。

预期结果：步骤 2 输出 `ok`；步骤 3 取回 5 行（该请求的 1 条日志 + 4 条 span）；步骤 6 中 `page` 只剩 P1 一条，P2 与 P3 出现在 `dropped` 中。

验证方法：检查每条 `request.failed` 都带 `trace_id`；检查 `page` 数组长度始终为 1；用 `python3 -c` 断言 `kept[0]["cause"] == "payment_timeout"`。

清理方法：`rm -f observability_demo.py out.txt`，并确认没有残留的临时日志目录。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 日志里有 `request_id`，但仍无法关联同一请求的多行 | 标识被拼进文案而非独立字段，或未传 `trace_id` | 统计日志中带 `trace_id` 的记录占比 | 把标识提为顶层字段，并在调用链上传递上下文 |
| 告警每天上百条，值班人开始忽略 | 只按资源阈值告警，未按影响面分级 | 抽查 20 条告警，统计真正需要动作的比例 | 改为业务 SLI 告警，P4 只进看板 |
| 故障期间同一条告警刷屏 | 未做指纹归并，每次评估都新建事件 | 按 `route + error_code` 分组计数 | 引入分组与静默窗口，同指纹合并计数 |
| 指标曲线与日志数量对不上 | 指标来自采样日志，或口径不同（4xx 是否算失败） | 取同一 5 分钟窗口比对分子分母 | 明确 SLI 定义并写进文档，指标从事件派生 |
| 链路在服务边界断掉 | 上下文未通过请求头传递，或异步任务未注入 | 看子服务日志里是否有 `trace_id` | 使用标准上下文传播，异步入口手动注入 |

## 安全与生产注意事项

**<u>日志里出现完整卡号、手机号或访问令牌，等于把敏感数据复制到检索权限更松的系统。</u>** 后果是合规事件：日志平台通常按团队开放读权限，波及范围比生产库更大。缓解办法是写入前统一脱敏（保留后四位或哈希），字段走白名单，禁止 `**kwargs` 全量落盘。

**<u>对告警通道做长期静默或以“告警太多”为由关掉规则，会让真正的 P1 静默失败。</u>** 后果是故障从 5 分钟发现退化为用户投诉后才发现。缓解办法是静默必须带到期时间与责任人，关闭规则需二级审批，每周核对“30 天内是否有 SLO 违规却没有对应告警”。

另外，*生产数据* 进入追踪系统前要先定保留期与访问控制，链路里同样可能含用户标识；对外状态页与内部看板应使用不同数据集。

## 本课总结

- 日志回答“这一次发生了什么”，指标回答“趋势是否越线”，Tracing 回答“慢在哪一跳”，三者靠同一套标识互相印证。
- 结构化日志的关键不是 JSON 格式，而是字段名固定、标识齐全、级别描述“要谁来看”。
- 告警级别由影响面与紧迫度决定，P1 打电话，P4 进看板；指标难看但用户无感，不该叫醒人。
- 降噪三板斧是同因归并（指纹）、抑制（高等级压低等级）、多窗口阈值（过滤瞬时抖动）。
- 可观测性方案要在成本、基数、采样率之间取舍，错误请求应全采，敏感字段必须在落盘前处理。

## 思考题

退款成功率连续三天下滑，但每天都“刚好”没有触发告警：成功率为 99.4%，SLO 是 99.5%/30 天。作为架构师，你会如何判断这是“阈值太松”还是“业务确实在恶化”？请说明你需要补哪些信号、如何设计规则，以及怎样避免把值班人变成告警的奴隶。

参考思路：先区分单点阈值与多窗口*燃烧率*（错误预算消耗速度），用 1 小时与 6 小时窗口交叉判断；再补分渠道、分支付商的 SLI，看下滑是否集中在某个维度；最后对照错误预算余额，若两天内就会耗尽 30 天预算，应升级为 P2 而不是等跌破 SLO。没有响应动作的告警应改为看板。

## 小测

1. 想判断“退款延迟是否整体变差”，最该先看哪类数据？  
   A. 单条请求的日志　B. P95 延迟时间序列　C. 某个 span 的堆栈　D. CPU 使用率
2. 结构化日志中把 `order_id` 设为指标标签的主要风险是什么？
3. 告警级别应由什么决定？请说出两个维度。
4. 链路采样率为 5% 时，为什么仍要求错误请求全量保留？
5. 场景题：一次支付商故障产生 3 条告警——单次 5xx（P4）、退款失败率 12%（P2）、P95 延迟超阈值（P3）。值班人应该收到几条，为什么？

## 答案与解析

1. **B。**趋势问题需要聚合后的时间序列。A、C 只能回答单次请求的细节，看十次也推不出整体趋势；D 是资源信号，与业务延迟无必然关系。
2. 会造成指标基数爆炸：每个订单一条时间序列，内存与存储成本随订单量线性增长。订单号属于无界取值，只能进日志与链路属性，不能进指标标签。
3. 影响面（受影响用户或业务量）与紧迫度（能否等到下一个工作日）。只按指标数值大小分级，会让“CPU 高但用户无感”抢占电话通道。
4. 因为错误是低频事件，5% 采样下一条失败链路大概率被丢弃，恰好丢掉唯一能定位根因的证据；同时 SLO 统计需要完整失败计数。可行做法是尾部采样或对错误状态强制保留。
5. 只收到 1 条 P2。单次 5xx 不构成行动项，只留日志；延迟告警与失败率告警同址同因，归并进同一事件。三条候选恰好演示了降噪三板斧：丢弃非行动项、同因归并、按级别抑制。

### 动手实验参考

步骤 4 换成 `status == 502` 后 `error_rate` 仍为 0.333，因为样本里恰好只有 502，这暴露“口径变了、数据没覆盖新情况”的盲区。步骤 5 的 `min_requests` 在推送前判断流量，不足则降为 INFO。步骤 6 加入 P1 后排序把它放最前，P2、P3 被归并。

## 延伸阅读与下一课

- OpenTelemetry 官方文档：[https://opentelemetry.io/docs/](https://opentelemetry.io/docs/)（三支柱的采集与上下文传播标准）
- Prometheus 文档：[https://prometheus.io/docs/introduction/overview/](https://prometheus.io/docs/introduction/overview/)（指标类型与告警规则）
- Prometheus 告警实践：[https://prometheus.io/docs/practices/alerting/](https://prometheus.io/docs/practices/alerting/)（`for` 子句、告警命名与抑制）
- W3C Trace Context：[https://www.w3.org/TR/trace-context/](https://www.w3.org/TR/trace-context/)（`traceparent` 头格式）
- 返回[本单元目录](00-overview.md)。
- 回看上一单元：[开发、测试与交付](../06-build-test-deliver/00-overview.md)。
- 下一课：[Correlation ID 与请求链路](02-correlation-id-and-request-tracing.md)。
