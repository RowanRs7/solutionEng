---
title: Correlation ID 与请求链路
slug: correlation-id-and-request-tracing
module: traditional-solutions
stage: operate-and-optimize
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - logs-metrics-tracing-and-alerting
outcomes:
  - 区分 correlation ID、request ID 与 trace ID 的生成者、生命周期与适用问题
  - 在 HTTP 头、消息属性与 Webhook 回调中透传或重建关联标识，使多服务日志按同一 ID 聚合
  - 诊断四类典型断链，给出验证命令与修复方向
last_reviewed: 2026-10-19
---

# Correlation ID 与请求链路

## 为什么需要学习

晴空商城一笔退款穿过客服工单、网关、`refund-service`、订单服务、支付商、仓库队列和回调表。某晚一笔 1,280 元退款停在“已受理、未出库”，客服只有订单号 `SO-20261019-0417`，运维在三个平台分别看到一次请求、四次重试和一条失败。可每个组件都在入口自己 `uuid4()`，回调更是全新请求——日志都在，却没有一条线串起来。

> **核心结论：** 一个业务事务的全部日志，必须能被一个在入口生成、被所有下游原样继承的标识串起来；标识每层重生成一次，日志再多也不构成链路。

## 学习目标

完成本课后，你能够：

- 区分 *correlation ID*、*request ID*、*trace ID* 的生成者、生命周期与适用问题。
- 为一次退款设计标识的生成规则、传递载体与统一日志字段名。
- 写出跨服务透传与上下文重建的代码，让 5 个组件的日志成链。
- 用一条命令验证链路是否断掉，并指出断在哪一跳。

## 前置知识

- 回看上一课：[日志、指标、Tracing 与告警](01-logs-metrics-tracing-and-alerting.md)。
- 知道结构化日志把可变信息放进字段而非文案（见[异常处理与结构化日志](../06-build-test-deliver/03-exception-handling-and-structured-logging.md)）。
- 知道 HTTP 头大小写不敏感，`X-` 前缀只是约定。
- 了解异步消息可能重复投递、顺序不保证。

## 业务场景

退款七跳：客服提交 → 网关鉴权 → `refund-service` 受理 → 订单服务确认可退 → 支付商发起 → 队列通知出库 → 支付商异步回调。

要回答的很具体：在支付商那步等了多久？重试几次、每次为什么失败？回调落在同一笔退款单上吗？仓库收没收到？为什么 500 笔补单在日志里像一次请求？

约束同样具体：支付商不能改造，也不回显我们的头；工单系统只能粘文本；日志留 30 天且不含完整卡号；平台不可任意 `join`。

## 核心概念

- *关联标识（correlation ID）*：一个业务事务的稳定标识，从建单到终态不变。
- *请求标识（request ID）*：一次物理调用的标识，每跳与每次重试都不同。
- *轨迹标识（trace ID）* 与 *跨度（span）*：一次追踪一个 `trace_id`，每段组件执行为带耗时的 `span`。
- *透传（propagation）*：读取入站标识，原样写入下一次出站调用或消息属性。
- *上下文（context）*：当前请求在内存中携带的标识，通常放在 `ContextVar` 里。
- *断链*：某一跳没继承上游标识，其日志落到查不到的孤立 ID 下。
- *业务键（business key）*：双方都持有、可对外核对的标识，如商户退款单号。

| 标识 | 谁生成 | 何时变化 | 关联粒度 | 典型用途 |
| --- | --- | --- | --- | --- |
| correlation ID | 业务入口（客服建单） | 事务内不变 | 一次退款全生命周期 | 跨服务聚合、工单回查 |
| request ID | 每个服务入口 | 每次调用都变 | 一次 HTTP 调用 | 区分重试、定位单次失败 |
| trace ID | 链路入口 SDK 或网关 | 一次追踪内不变 | 一次追踪 | 调用树与耗时 |
| span ID | 每个组件 | 每进入一个组件 | 一跳 | 定位慢的一跳 |
| 业务键 | 业务系统 | 事务内不变 | 一笔退款单 | 对外对账、Webhook 回查 |

前四个是技术标识，末一个是业务标识。**没有业务键，Webhook 与外部对账永远接不回原链路**。

<u>字段名必须全平台唯一</u>：`corrId`、`correlation_id`、`traceId` 并存时，采集端就无法用一条查询聚合。

## 工作原理

一次退款的标识生命周期按数据流展开：

1. **建单时生成**：客服系统生成 `correlation_id` 与 `merchant_ref` 写入退款单，此后全链路只认这两个值。
2. **出站带上**：写进 `X-Correlation-Id` 与 `X-Merchant-Ref`。内存里的上下文重启即失，头是唯一可靠的传递面。
3. **网关收口**：白名单加长度上限，不合法或缺失则本地生成并记 `correlation_source=gateway`；这是唯一允许新建标识的地方。
4. **入口绑定并回填**：中间件读头、校验、写入上下文、注册到日志 `Filter`；调下游时写回出站头，同时生成新的 `request_id`。
5. **外部依赖**：支付商不回显我们的头，只能把 `merchant_ref` 记进日志。**外部系统不配合时，业务键是唯一的接回点。**
6. **Webhook 重建**：回调是全新请求，先按 `merchant_ref` 查单取回标识再绑定；查不到就新建、标 `store_miss` 并告警。
7. **消息透传**：标识写进消息属性（Kafka header、SQS attribute），消费者从属性恢复；只塞消息体容易被漏解析。
8. **批处理拆分**：批次一个 `batch_id`，但每条业务记录各有标识，否则 500 笔补单塌成一条无法审计的记录。
9. **聚合取证**：按标识过滤、按 `ts` 排序，相邻事件耗时差即该跳耗时；把链回填工单才算可复核的排障。

硬约束：<u>标识只在入口生成一次，中间层只读不改</u>。任何“为了方便而重新生成”的改动，都会在故障那一晚暴露代价。

另两个细节：`ContextVar` 不跨线程池与后台任务，提交时要显式传值；请求结束要 `reset`，否则复用的线程会带着上一笔的标识。

## 架构与选型

| 方案 | 适用 | 不适用 | 权衡 |
| --- | --- | --- | --- |
| 每跳重新生成 request ID | 单体应用，调用不出进程 | 任何跨服务、跨队列链路 | 零改造，但日志天然无法关联 |
| 自建 correlation ID 头透传（本课起点） | 服务数量可控、平台可按字段检索 | 调用树与逐跳耗时剖分 | 成本低；出入站都要改 |
| W3C Trace Context + OpenTelemetry | 多语言多团队、需要 span 与采样 | 只想知道“经过哪些服务”的小系统 | 自动注入、生态完整；要引入 SDK 与后端 |
| 网关或网格统一注入 | 流量都经过网关/网格 | 批处理、外部回调、直连库 | 业务代码几乎不改；网格外流量仍断链 |
| 日志平台按订单号推断 | 应急排查 | 同订单有多笔退款或重试 | 会把不同事务合并，不能长期用 |

选型先回答“要回答什么问题”：只问“经过哪些服务、卡在哪一跳”，correlation ID 加统一字段就够；要问“哪一跳慢了、调用树什么样”，才需要 trace ID 与 span，成熟做法是两个都记。**判断标准不是技术先进程度，而是排障时第一个被问到的问题。**

## 最小示例

要解决的问题：一次退款经过五个组件，日志要落在同一标识下，回调与消息两条异步路径不能断链。环境：Python 3.9 及以上，只用标准库；stdout 输出 JSON 日志，stderr 输出聚合报告。

```python
"""用标准库模拟一次退款事务的关联标识全链路：HTTP 头透传、消息属性、Webhook 重建。"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar

# 当前执行流的标识：下游不必层层加参数，日志也不必手工拼 ID
CORR = ContextVar("corr", default="-")
REQ = ContextVar("req", default="-")

# 退款单表：商户单号 -> correlation_id，Webhook 重建上下文的唯一依据
STORE = {}
MERCHANT_REF = "RF-20261019-0417"

class CtxFilter(logging.Filter):
    """把 ContextVar 里的标识灌进每条记录，业务代码不必显式传 ID。"""

    def filter(self, record):
        record.corr = CORR.get()
        record.req = REQ.get()
        return True

class JsonFormatter(logging.Formatter):
    """键名固定，采集端才可能只按一个字段聚合。"""

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "service": record.service,
            "event": record.getMessage(),
            "correlation_id": record.corr,
            "request_id": record.req,
        }
        payload.update(getattr(record, "fields", {}))  # 业务字段另开一层，不占用保留键
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
handler.addFilter(CtxFilter())
LOG = logging.getLogger("trace")
LOG.addHandler(handler)
LOG.setLevel(logging.INFO)
LOG.propagate = False

RECORDS = []  # 收集事件，仅用于最后的聚合演示

def emit(service, event, **fields):
    """唯一写日志入口：事件名是稳定枚举，可变信息一律走字段。"""
    RECORDS.append({"correlation_id": CORR.get(), "service": service, "event": event, **fields})
    LOG.info(event, extra={"service": service, "fields": fields})

def is_valid(value):
    """白名单加长度上限：防日志注入与索引基数爆炸。"""
    return isinstance(value, str) and 8 <= len(value) <= 64 and all(
        ch.isalnum() or ch in "-_" for ch in value
    )

def carrier_from_inbound(headers, service):
    """服务入口：沿用上游标识，缺失或非法才本地生成并记录来源。"""
    raw = headers.get("x-correlation-id", "")
    if is_valid(raw):
        CORR.set(raw)
        source = "upstream"
    else:
        CORR.set(f"corr-{uuid.uuid4().hex[:12]}")
        source = "local"
    REQ.set(uuid.uuid4().hex[:8])  # 每次物理调用一个，重试时才会变
    emit(service, "request.received", correlation_source=source)

def forward(headers, from_service, to_service):
    """出站：把当前标识原样写回请求头，绝不重新生成。"""
    out = dict(headers)  # 复制，避免下游改写上游的快照
    out["x-correlation-id"] = CORR.get()
    emit(from_service, "call.downstream", target=to_service)
    return out

def order_service(headers):
    carrier_from_inbound(headers, "order-service")
    emit("order-service", "order.loaded", order_no="SO-20261019-0417")

def refund_service(headers):
    carrier_from_inbound(headers, "refund-service")
    order_service(forward(headers, "refund-service", "order-service"))
    # 支付商不回显我们的头，只能靠商户单号在对方后台对上账
    emit("refund-service", "payment.requested", provider="pay-x", merchant_ref=MERCHANT_REF)
    attrs = {"x-correlation-id": CORR.get()}  # 消息属性就是异步世界的请求头
    emit("refund-service", "message.published", target="warehouse.queue")
    warehouse_consumer(attrs, {"merchant_ref": MERCHANT_REF})

def warehouse_consumer(attrs, body):
    """消费者没有 HTTP 头，上下文只能从消息属性恢复。"""
    carrier_from_inbound({"x-correlation-id": attrs.get("x-correlation-id", "")}, "warehouse-consumer")
    emit("warehouse-consumer", "pick.scheduled", merchant_ref=body["merchant_ref"])

def payment_webhook(body):
    """回调是全新请求：头里没有我们的标识，只能按商户单号回查退款单重建。"""
    corr = STORE.get(body["merchant_ref"])
    CORR.set(corr or f"corr-{uuid.uuid4().hex[:12]}")
    REQ.set(uuid.uuid4().hex[:8])
    emit("refund-service", "payment.callback", correlation_source="store" if corr else "local")

def batch_job(refund_nos):
    """批处理：整个批次共用一个标识会毁掉链路，必须每个业务单一个。"""
    batch_id = f"batch-{uuid.uuid4().hex[:6]}"
    for no in refund_nos:
        CORR.set(f"corr-{no}")  # 补单未登记时按业务单号派生，仍可追溯
        REQ.set(uuid.uuid4().hex[:8])
        emit("batch-job", "refund.reconciled", merchant_ref=no, batch_id=batch_id)

def report():
    """排障时真正想要的视图：一个标识一条链。"""
    print("--- 按 correlation_id 聚合 ---", file=sys.stderr)
    groups = {}
    for rec in RECORDS:
        groups.setdefault(rec["correlation_id"], []).append(rec["event"])
    for corr, events in sorted(groups.items()):
        print(f"{corr} ({len(events)} hops): {' -> '.join(events)}", file=sys.stderr)

def main():
    corr = "corr-8f3a1c9d2b7e"  # 业务事务 ID：客服建单时生成并落库，整个生命周期不变
    STORE[MERCHANT_REF] = corr
    CORR.set(corr)
    REQ.set(uuid.uuid4().hex[:8])
    emit("cs-console", "refund.created", merchant_ref=MERCHANT_REF)
    refund_service({"x-correlation-id": corr})
    payment_webhook({"merchant_ref": MERCHANT_REF, "status": "succeeded"})
    batch_job(["RF-20261019-0501", "RF-20261019-0502"])
    report()

if __name__ == "__main__":
    main()
```

运行：`python3 correlation_trace.py`

预期输出（节选，`request_id`、`ts` 与随机后缀每次不同）：

```text
{"correlation_id": "corr-8f3a1c9d2b7e", "event": "refund.created", "level": "INFO", "merchant_ref": "RF-20261019-0417", "request_id": "430ed351", "service": "cs-console", "ts": "2026-10-19T17:08:18+0800"}
{"correlation_id": "corr-8f3a1c9d2b7e", "correlation_source": "upstream", "event": "request.received", "level": "INFO", "request_id": "bdebb17e", "service": "refund-service", "ts": "2026-10-19T17:08:18+0800"}
{"correlation_id": "corr-8f3a1c9d2b7e", "correlation_source": "store", "event": "payment.callback", "level": "INFO", "request_id": "331e4245", "service": "refund-service", "ts": "2026-10-19T17:08:18+0800"}
```

```text
--- 按 correlation_id 聚合 ---
corr-8f3a1c9d2b7e (10 hops): refund.created -> request.received -> call.downstream -> request.received -> order.loaded -> payment.requested -> message.published -> request.received -> pick.scheduled -> payment.callback
corr-RF-20261019-0501 (1 hops): refund.reconciled
corr-RF-20261019-0502 (1 hops): refund.reconciled
```

整体流程：`main()` 生出全链路唯一一次新标识；`refund_service()` 从入站头恢复上下文，`forward()` 只复制加回填；`payment.requested` 用商户单号补上不回显头的缺口；`payment_webhook()` 按 `STORE` 回查接回原链；`batch_job()` 每单派生独立标识并记 `batch_id`；`report()` 相当于日志平台的那条查询。

关键设计是“承接而非重建”：入口先校验再采用，既保链路又挡伪造；标识放保留字段，避免入参也叫 `request_id` 时覆盖。

## 动手实验

前置条件：Python 3.9 及以上；无第三方依赖；已保存 `correlation_trace.py`；当前目录可写。

1. 运行 `python3 correlation_trace.py`：12 行日志里 `correlation_id` 只有三种取值，主事务 10 跳。
2. 取主事务事件序列：`grep 'corr-8f3a1c9d2b7e' <(python3 correlation_trace.py 2>/dev/null) | python3 -c "import sys,json;print([json.loads(l)['event'] for l in sys.stdin])"`。
3. 制造断链：把 `refund_service()` 的 `attrs` 改成 `{}`，重跑，看仓库消费者出现在陌生标识下。
4. 修复：让 `warehouse_consumer()` 在属性缺失时按 `merchant_ref` 回查 `STORE` 重建上下文。
5. 挡伪造：把调用改成 `{"x-correlation-id": "corr-ok\nFAKE level=ERROR"}`，确认被拒并本地生成。
6. 放大批量：`batch_job` 改 200 条单号，看是否出现 200 个独立标识。

预期结果：步骤 1 得三组；步骤 3 多出 2 跳孤立链、主事务掉到 8 跳；步骤 4 恢复 10 跳；步骤 5 来源为 `local` 且日志不多行；步骤 6 报告 201 行。

验证方法：`python3 correlation_trace.py 2>/dev/null | python3 -c "import sys,json,collections;print(dict(collections.Counter(json.loads(l)['correlation_id'] for l in sys.stdin)))"`，主标识计数应等于跳数，计数下降即断链。

清理方法：删除 `correlation_trace.py`；本实验不联网、不写数据库、不发真实消息。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 同一笔退款在各服务日志里 ID 不同 | 每层各自生成，中间件只“设置”不“继承” | 比对网关与下游首条日志 | 先读后写，缺失才生成并记来源 |
| 下游标识是 `-` 或空 | 字段名不一致，或中间件未注册 | 抽样检查字段名与注入点 | 统一字段名，采集端做别名映射 |
| 仓库消费者总是孤立成链 | 标识只进消息体，未进属性 | 查看消息 header | 生产端写属性，缺失按业务键回查 |
| 支付回调接不回原退款单 | 回调是新请求，且没按业务键回查 | 回调日志是否只有新标识 | 用 `merchant_ref` 查单重建并记 `store_miss` |
| 一次重试变成两条无关记录 | 重试时重新生成了标识 | 对比重试前后的标识 | 同一逻辑事务沿用原标识，幂等键单独记 |
| 500 笔补单在日志里像一次请求 | 只在批次级设置了标识 | 该标识记录数是否等于批大小 | 每条记录一个标识，批次另设 `batch_id` |

## 安全与生产注意事项

**<u>correlation ID 会出现在响应头、日志和客服工单里，绝不能由客户端任意决定。</u>** 后果有三层：换行与控制字符可伪造日志行，让攻击行为像另一笔业务；他人标识会制造“串单”假象，把排障引偏；超长高基数的值会撑爆索引与计费。缓解：入口校验白名单与长度，不合法就丢弃并本地生成，记 `correlation_source`，对 `local` 占比升高告警。

**<u>把 correlation ID 当作身份凭据或幂等键，会同时造成越权与重复处理。</u>** 后果是客服凭一个 ID 就能查到别人的退款单，或同一标识的重试被当成不同请求而重复退款。缓解：标识只用于关联，查询仍走鉴权；幂等键独立设计为“业务单号 + 操作类型”。

## 本课总结

- **标识只在入口生成一次，中间层只读不改；每层重生成一次，日志就退回按时间窗硬读。**
- correlation ID 对齐事务，request ID 对齐调用，trace ID 与 span 对齐调用树。
- 跨进程传递只有三个可靠载体：HTTP 头、消息属性、用业务键回查数据库。
- **外部系统不回显你的头时，业务键就是唯一的接回点。**
- 断链是默认状态：字段名统一、来源可观测、计数可比较，才谈得上“有链路”。

## 思考题

晴空商城要接入第二家支付商，它不接受自定义请求头，回调只带自己的交易号，而合规要求理赔时能证明“这笔钱从哪个工单、经几次重试、由谁审批后发起”。请给出标识方案，并说明新增哪张映射、回调如何重建上下文、30 天日志过期后如何自证。

参考思路：把“可自证”与“可检索”分开。退款单持久保存 correlation ID、工单号、审批人与支付商交易号，日志只做 30 天内的检索；回调以交易号查映射取回标识，查不到即告警并进人工对账。理赔证据从业务库与审计流水出——日志有保留期，账不能有。

## 小测

1. 关于 correlation ID 与 request ID，正确的说法是？  
   A. 二者等价，只留一个即可　B. 前者在事务内不变，后者每次调用都变　C. 网关应把 request ID 重写为 correlation ID　D. correlation ID 必须在每个服务入口重新生成
2. 支付商回调是全新请求，正确做法是？  
   A. 为回调新建 trace，不关联原事务　B. 从回调头读取我们上次发的标识　C. 用回调携带的业务键回查退款单，取回标识重建上下文　D. 用订单号重新生成标识
3. 为什么不应把 correlation ID 直接当作幂等键？
4. 异步消息里标识最该放在哪里？  
   A. 消息体 JSON 的任意字段　B. 消息属性或 header　C. 消费者启动时读的环境变量　D. topic 名
5. 场景题：团队给 6 个服务都加了透传，值班时仍只能一条条翻日志，且网关日志里的标识与下游对不上。你会按什么顺序排查，先改哪一处？

## 答案与解析

1. **B。** A 错在用途不同：一个回答“哪一笔业务”，一个回答“哪一次调用”；C 的重写会抹掉上游上下文；D 正是断链成因。
2. **C。** A 主动放弃关联；B 想当然，回调方通常不回显自定义头；D 生成新值等于断链，订单号也不能替代事务标识。
3. 幂等键要求“同一请求重复到达结果一致”，绑定具体操作与参数；correlation ID 绑定事务身份，受理、退款、出库共享同一标识。混用会让不同操作被判为重复而丢弃。
4. **B。** 属性随消息投递、不侵入业务载荷，两端都能直接读。A 让标识混进业务契约，改结构就可能丢；C 是进程级配置，区分不了单条消息；D 的粒度是整个主题，等于没有标识。
5. 参考方向：先定位“断在哪一跳”，别先改代码。先比对网关与下游首条日志，判断是未透传还是字段名不一致；再查采集端映射，确认两个字段名是否被当成两回事；再确认中间件是“读后写”还是“直接覆盖”。先改字段名，再改中间件语义。

### 动手实验参考

步骤 3 的预期是出现一组只有 `request.received -> pick.scheduled` 两跳的孤立链路，`correlation_source` 为 `local`。步骤 4 的修复思路：属性缺失时用 `body["merchant_ref"]` 查 `STORE`，查到则复用，否则生成并记 `store_miss`；修复后主链路应回到 10 跳。步骤 5 的判断标准是日志行数不变且来源为 `local`——若多一行或出现 `FAKE`，说明校验没生效。

## 延伸阅读与下一课

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)：`traceparent` 与 `tracestate` 的规范定义。
- [OpenTelemetry：Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)：跨进程与跨异步边界传递上下文的官方说明。
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)：头字段语法与转发规则。
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)：日志注入与敏感字段检查清单。
- 返回[本单元目录](00-overview.md)。
- 回看上一课：[日志、指标、Tracing 与告警](01-logs-metrics-tracing-and-alerting.md)。
- 下一课：[OpenTelemetry、Prometheus 与 Grafana](03-opentelemetry-prometheus-grafana.md)。
