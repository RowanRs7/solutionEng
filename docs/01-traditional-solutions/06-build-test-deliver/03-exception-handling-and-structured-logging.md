---
title: 异常处理与结构化日志
slug: exception-handling-and-structured-logging
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - dependencies-config-and-secrets
outcomes:
  - 为一个服务定义包含 code、message、request_id、retriable 的统一错误信封
  - 区分用户输入错误、业务规则拒绝、依赖故障和系统故障，并为每类指定状态码、日志级别与可重试性
  - 用标准库 logging 与自定义 Formatter 输出每行一条 JSON 的结构化日志，并说明必填字段的用途
last_reviewed: 2026-10-19
---

# 异常处理与结构化日志

## 为什么需要学习

晴空商城的退款集成服务上线第二周，客服页面只剩一句“系统繁忙，请稍后重试”。有人反复点重试（那笔其实是订单不存在，永远重试不成功），有人直接转人工。运维被问“哪一步失败了”，只能拿订单号 `grep` 中文自由文本日志，而日志里夹着银行卡尾号和手机号。开发回答：“错误我都打日志了。”

问题不在“有没有处理”，而在三处同时缺失：**失败没有分类**，五类失败共用同一个 500；**异常没有边界**，有的被 `except: pass` 吞掉，有的以堆栈页暴露；**日志不是结构化的**，无法按字段过滤与告警。结果是调用方不知道该不该重试，排查退化成全文搜索。

> **核心结论：** 可预期的失败要用错误码和异常类型表达，不可预期的失败交由唯一边界兜底；日志是给机器检索和告警的，只有附带的文案才是给人读的。

## 学习目标

完成本课后，你能够：

- 写出包含 `code`、`message`、`request_id`、`retriable` 的统一错误信封，并说明每个字段由谁消费。
- 区分*用户输入错误*、*业务规则拒绝*、*依赖故障*、*系统故障*四类失败，为每类指定状态码、日志级别与可重试性。
- 用标准库 `logging` 加自定义 `Formatter` 输出每行一条 JSON 的结构化日志。
- 说出 5 个必填日志字段及各自用途，按级别规则判断一条事件该记 INFO、WARNING 还是 ERROR，并识别*日志注入*与敏感字段落盘两类风险。

## 前置知识

- 回看上一课：[依赖、虚拟环境、配置与 Secret](02-dependencies-config-and-secrets.md)。
- 会写 Python 3 的 `try / except / raise`，并定义过自定义异常类。
- 知道 HTTP 里 4xx 大致表示调用方问题、5xx 表示服务端问题。
- 了解[参数校验、错误模型与版本管理](../03-api-and-integration/03-validation-errors-and-versioning.md)中错误信封的形状；本课重点在异常边界与日志。

## 业务场景

`refund-service` 承接客服页面提交的退款：校验订单、调用支付商退款接口、写退款单、通知仓库。五类失败来源是：漏填 `order_id`、订单不存在或已全额退款、金额超过 500 元需人工审核、支付商超时或返回 5xx、自身代码缺陷（如金额为 `null`）。

现状是五类都落成 `500 + {"msg": "系统繁忙"}`；日志由 `print` 拼接中文，一条请求散成三行且没有请求标识；裸 `except:` 连 `KeyboardInterrupt` 一起吞。合规还要求日志不出现完整卡号与手机号，并能回答“谁在何时对哪个订单做了什么”。

目标因此很具体：客服页面按 `code` 分流——`ORDER_NOT_FOUND` 直接结单，`AMOUNT_EXCEEDS_LIMIT` 转人工审核，`PAYMENT_TIMEOUT` 显示“稍后重试”，`INTERNAL_ERROR` 建单并附 `request_id`。

## 核心概念

- *异常*：程序无法在当前上下文继续执行的信号，分为可预期（业务规则）与不可预期（代码缺陷、依赖故障）。
- *错误模型*：跨服务约定的失败描述方式，规定字段、错误码命名与状态码映射；其响应体部分称*错误信封*，即固定的 `error` 包裹结构。
- *异常边界*：唯一负责把内部异常翻译成“对外错误信封 + 日志事件”的那一层代码。
- *结构化日志*：每条记录都是键值对（通常一行 JSON），字段名固定，可被采集端建索引与聚合。
- *日志级别*：按“需要谁来看”分档的标签，决定落盘、采样与告警路由。
- *日志注入*：攻击者用换行、控制字符或超长字段伪造、污染日志记录。
- *脱敏*：写入日志前替换或哈希敏感值，保留可关联性而去掉可识别性。
- *可重试性*：`retriable` 的取值语义——原样重试是否有意义，由服务端而不是调用方猜测。

四类失败的分工：

| 失败类别 | 典型来源 | 责任方 | 状态码 | 错误码示例 | 日志级别 | `retriable` |
| --- | --- | --- | --- | --- | --- | --- |
| 用户输入错误 | 缺字段、类型错、格式不对 | 调用方 | 400 | `INVALID_ARGUMENT` | WARNING | false |
| 业务规则拒绝 | 超限、状态不允许、需人工审核 | 业务规则 | 422 / 409 / 404 | `AMOUNT_EXCEEDS_LIMIT` | WARNING | false |
| 依赖故障 | 支付商超时、限流、连接池耗尽 | 外部或容量 | 503 / 504 | `PAYMENT_TIMEOUT` | WARNING（单次）/ ERROR（成片） | true |
| 系统故障 | 代码缺陷、数据不一致、磁盘满 | 我方 | 500 | `INTERNAL_ERROR` | ERROR + 堆栈 | false |

日志级别的含义要按“谁来看”定义，而不是按“我觉得多严重”：

| 级别 | 含义 | 何时使用 | 是否进告警 |
| --- | --- | --- | --- |
| DEBUG | 开发期细节 | 只在本机打开，生产默认关闭 | 否 |
| INFO | 正常业务事实 | `request.finished`、退款受理成功 | 否（可作指标来源） |
| WARNING | 可预期但需关注 | 4xx 业务拒绝、单次依赖超时 | 达阈值才告警（如 5 分钟 > 20 次） |
| ERROR | 需要人介入 | 未预期异常、写库失败、重试耗尽 | 是 |
| CRITICAL | 服务整体不可用 | 启动失败、配置缺失、密钥过期 | 是，立即 |

<u>级别描述的是“需要谁来看”，不是“我有多着急”。</u>把业务拒绝记成 ERROR，会让告警被淹没；把代码缺陷记成 WARNING，会让故障静默上线。

必填字段与其消费方：

| 字段 | 示例 | 用途 |
| --- | --- | --- |
| `ts` | `2026-10-19T17:02:11+0800` | 排序与时间窗聚合；带时区偏移，跨区可比 |
| `level` | `WARNING` | 采样与告警路由 |
| `event` | `refund.rejected` | 点号分层的稳定事件名，是枚举而非自然语句 |
| `request_id` | `b136bf925051` | 跨服务串联的唯一键，也是报给客服的凭据 |
| `route` / `status` | `POST /api/v1/refunds` / `422` | 定位接口与结果；`route` 用模板而非真实路径 |
| `error_code` / `error_type` | `AMOUNT_EXCEEDS_LIMIT` / `AmountExceedsLimit` | 聚合根因；前者对外，后者对内 |
| `duration_ms` | `0.04` | 延迟分布；与 `status` 联查可区分“慢而错” |

<u>不要用真实值充当 `route` 或 `event` 的维度</u>：`/refunds/SO-...` 会让指标基数爆炸，成本失控。

## 工作原理

一次失败请求的数据流：

1. **入口接收**：继承上游的 `X-Request-Id`，缺失时本地生成，并写回响应头。
2. **边界内执行业务**：校验、查订单、调支付商、写库都落在同一段 `try` 内。边界只包一层，不在每个函数里各写 `try/except`。
3. **抛出而非返回哨兵值**：业务规则用具体异常类型表达，并携带 `field`（对外可定位）与 `internal`（仅进日志）。
4. **分类捕获**：先捕获基类 `AppError` 取出 `status / code / retriable / message`，再捕获剩余 `Exception` 兜底。
5. **生成错误信封**：对外只输出 `code`、`message`、`request_id`、`retriable` 与可选 `field`；堆栈、SQL、依赖原始返回值不出服务。
6. **写判定事件**：`refund.rejected`（WARNING）或 `refund.crashed`（ERROR 加堆栈），带 `error_code`、`error_type`、`internal`。
7. **写访问事件**：在 `finally` 中记 `request.finished`，带 `request_id`、`outcome`、`duration_ms`。
8. **采集与路由**：告警规则写成“`event=refund.crashed` 计数 > 0”或“`error_code=PAYMENT_TIMEOUT` 5 分钟 > 20 次”，不匹配文案。
9. **回查**：客服工单只写 `request_id` 与 `code`，运维用它一次取回全部相关记录。

顺序上有一条硬约束：<u>错误信封先定型，日志字段再与之对齐</u>；否则同一故障在响应、日志、工单里会有三种叫法。

## 架构与选型

异常处理的三种常见组织方式：

| 方案 | 适用 | 不适用 | 代价与权衡 |
| --- | --- | --- | --- |
| 框架中间件统一处理（如 FastAPI `exception_handler`） | Web 请求生命周期内的失败 | 批处理、消费者、定时任务 | 覆盖最好、成本最低；线程池与异步任务里的异常不经过它 |
| 装饰器或上下文管理器逐入口包裹 | 多入口（HTTP、CLI、消费者） | 每个函数都套一层 | 灵活可组合；过度使用让控制流分散 |
| 全局兜底加关键位置显式 `raise` （推荐） | 大多数服务 | 无 | 边界唯一、规则用类型表达；要求团队约定异常层次，否则子类失控 |

日志落地方式按部署形态选：容器化且已有日志平台时，结构化 JSON 写 stdout 由平台采集；单机无采集平台才写本地文件并轮转，代价是容器重启后文件消失。<u>本地开发的文本 formatter 要用配置项切换，不要手改代码。</u>

选型依据是先回答“谁来看、看多久、用它做什么告警”：答案若是“平台按 `error_code` 聚合”，就必须结构化；若只是本机排障脚本，`print` 也许够用。**分界不在技术先进程度，而在使用者的检索方式。**

## 最小示例

要解决的问题：一次请求只应产生一条判定事件加一条访问事件，两者共享 `request_id`；对外响应绝不包含堆栈。环境：Python 3.9 及以上，只用标准库。输入：四组 `(订单号, 金额)`。输出：四行响应写入 stdout，若干行 JSON 日志写入 stderr。

```python
"""统一错误信封与结构化日志的最小骨架：只用标准库。"""

import json
import logging
import sys
import time
import uuid

MAX_REFUND_CENTS = 50_000              # 与校验同源，不在文案里写死"500 元"
ROUTE = "POST /api/v1/refunds"         # 用模板而非真实路径，避免日志指标基数爆炸


class AppError(Exception):
    """可预期失败的基类：子类只声明差异，不重复实现。"""

    status = 500                       # 默认保守：未知失败一律 500，不伪装成客户端错误
    code = "INTERNAL_ERROR"            # 稳定标识，发布后不改含义
    retriable = False                  # 明确回答"原样重试有没有意义"
    message = "服务暂时不可用"          # 对外文案只说下一步能做什么

    def __init__(self, *, field=None, internal=None):
        super().__init__(self.message)
        self.field = field             # 出问题的入参名，前端可直接高亮
        self.internal = internal       # 只在日志里出现的排查线索


class InvalidArgument(AppError):
    status, code, message = 400, "INVALID_ARGUMENT", "请求参数不合法"


class AmountExceedsLimit(AppError):
    status, code, message = 422, "AMOUNT_EXCEEDS_LIMIT", "单笔退款超过 500 元，需人工审核"


def error_envelope(exc, request_id):
    """唯一出口：成功与失败共用一套键名，客户端不必写两套解析。"""
    body = {"code": exc.code, "message": exc.message,
            "request_id": request_id, "retriable": exc.retriable}
    if exc.field:                      # 仅在有定位信息时出现，不用空字符串占位
        body["field"] = exc.field
    return {"error": body}


RESERVED = ("request_id", "route", "outcome", "status", "duration_ms",
            "error_code", "error_type", "internal")


class JsonFormatter(logging.Formatter):
    """把 LogRecord 变成一行 JSON：字段名固定，采集端才能建索引。"""

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),  # 带偏移，跨时区可比
            "level": record.levelname,      # 采样与告警路由的依据
            "event": record.getMessage(),   # 点号分层的稳定事件名，不是自然语句
        }
        for name in RESERVED:              # 白名单：未约定属性不会意外落盘
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:                # 堆栈的换行被转义为 \n，仍是一条记录一行
            payload["exc_type"] = record.exc_info[0].__name__
            payload["stack"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


handler = logging.StreamHandler(sys.stderr)   # 日志走 stderr，业务输出走 stdout
handler.setFormatter(JsonFormatter())
LOG = logging.getLogger("refund")
LOG.addHandler(handler)
LOG.setLevel(logging.INFO)             # 生产默认 INFO，DEBUG 由配置打开而不是改代码
LOG.propagate = False                  # 不向 root logger 重复输出


def log_event(level, event, **fields):
    LOG.log(level, event, extra=fields)   # 字段走 extra，不拼进 msg 破坏结构


def log_crash(event, **fields):
    LOG.exception(event, extra=fields)    # 只在 except 块内调用，自动附带当前堆栈


def refund(order_id, amount_cents):
    if not isinstance(order_id, str) or not order_id.startswith("SO-"):
        raise InvalidArgument(field="order_id")
    if amount_cents > MAX_REFUND_CENTS:   # 金额为 None 时此处抛 TypeError，进入兜底分支
        raise AmountExceedsLimit(field="amount_cents",
                                 internal=f"limit={MAX_REFUND_CENTS} got={amount_cents}")
    return {"refund_id": "rf-demo-001", "status": "accepted"}


def handle_refund(order_id, amount_cents):
    """异常边界：整个过程只有这一处 try，其它函数只负责 raise。"""
    request_id = uuid.uuid4().hex[:12]    # 实验步骤 5 改为继承上游 X-Request-Id
    started = time.perf_counter()
    outcome = "ok"
    try:
        return 200, refund(order_id, amount_cents)
    except AppError as exc:               # 可预期失败：记分类信息，不回堆栈
        outcome = "rejected"
        log_event(logging.WARNING, "refund.rejected", request_id=request_id,
                  route=ROUTE, status=exc.status, error_code=exc.code,
                  error_type=type(exc).__name__, internal=exc.internal)
        return exc.status, error_envelope(exc, request_id)
    except Exception:                     # 兜底：代码缺陷也必须收敛成同一个信封
        outcome = "crashed"
        log_crash("refund.crashed", request_id=request_id, route=ROUTE,
                  status=500, error_code="INTERNAL_ERROR")
        return 500, error_envelope(AppError(), request_id)
    finally:                              # 访问事件与判定事件共用 request_id
        log_event(logging.INFO, "request.finished", request_id=request_id,
                  route=ROUTE, outcome=outcome,
                  duration_ms=round((time.perf_counter() - started) * 1000, 2))


CASES = [("SO-20261019-001", 12_000),      # 正常受理
         ("SO-20261019-001", 80_000),      # 业务规则拒绝
         ("XX-1", 100),                    # 参数不合法
         ("SO-20261019-001", None)]        # 代码缺陷

for order_id, amount in CASES:
    status, body = handle_refund(order_id, amount)
    print(status, json.dumps(body, ensure_ascii=False, sort_keys=True))
```

运行：`python3 refund_service.py 2> logs.jsonl`

预期输出（`request_id` 与耗时每次不同）：

```text
200 {"refund_id": "rf-demo-001", "status": "accepted"}
422 {"error": {"code": "AMOUNT_EXCEEDS_LIMIT", "field": "amount_cents", "message": "单笔退款超过 500 元，需人工审核", "request_id": "b136bf925051", "retriable": false}}
400 {"error": {"code": "INVALID_ARGUMENT", "field": "order_id", "message": "请求参数不合法", "request_id": "4b65a18cb544", "retriable": false}}
500 {"error": {"code": "INTERNAL_ERROR", "message": "服务暂时不可用", "request_id": "390feb90ccf6", "retriable": false}}
```

`logs.jsonl` 中的三段（堆栈已截断，行号随文件版本变化）：

```text
{"duration_ms": 0.0, "event": "request.finished", "level": "INFO", "outcome": "ok", "request_id": "d7a16f037776", "route": "POST /api/v1/refunds", "ts": "2026-10-19T16:59:39+0800"}
{"error_code": "AMOUNT_EXCEEDS_LIMIT", "error_type": "AmountExceedsLimit", "event": "refund.rejected", "internal": "limit=50000 got=80000", "level": "WARNING", "request_id": "b136bf925051", "route": "POST /api/v1/refunds", "status": 422, "ts": "2026-10-19T16:59:39+0800"}
{"error_code": "INTERNAL_ERROR", "event": "refund.crashed", "exc_type": "TypeError", "level": "ERROR", "request_id": "390feb90ccf6", "route": "POST /api/v1/refunds", "stack": "Traceback (most recent call last):\n  ...\nTypeError: '>' not supported between instances of 'NoneType' and 'int'", "status": 500, "ts": "2026-10-19T16:59:39+0800"}
```

整体流程：

1. `refund()` 只表达规则，不合规就 `raise`，不 `return None`，也不 `print`。
2. `handle_refund()` 是唯一边界，分支顺序即优先级：业务基类、兜底、收尾。
3. `error_envelope()` 让四类失败共享键名，客户端只写一套分支。
4. `JsonFormatter` 用白名单而非 `record.__dict__` 全量输出——否则 `args`、`exc_info` 这类不可序列化对象会让格式化自身抛错，日志系统成了新的故障源。
5. `finally` 记录 `duration_ms`，保证失败请求也有延迟数据。

关键设计是 `internal` 与 `message` 分离：<u>把 `limit=50000 got=80000` 写进对外文案等于公布业务阈值</u>，彻底丢弃又让支持团队无法解释“为什么被拒”。

## 动手实验

前置条件：Python 3.9 及以上；无第三方依赖；已保存 `refund_service.py`；当前目录可写。

1. 运行 `python3 refund_service.py 2> logs.jsonl`，核对四行响应与“判定 + 访问”事件是否成对。
2. 验证日志可机读：`python3 -c "import json;[json.loads(l) for l in open('logs.jsonl')]" && echo ok`。
3. 取出 `refund.crashed` 的 `request_id` 并 `grep logs.jsonl`，确认能取回该请求的两条记录。
4. 修掉缺陷：在比较金额之前加 `if not isinstance(amount_cents, int): raise InvalidArgument(field="amount_cents")`，重跑。
5. 继承上游标识：给 `handle_refund` 增加 `request_id=None` 参数，并改为 `request_id = request_id or uuid.uuid4().hex[:12]`；调用时传入 `"req-cs-0001"`。
6. 加脱敏：在 `log_event` 前把 `order_id` 换成 `hashlib.sha256(order_id.encode()).hexdigest()[:8]`，字段名改为 `order_id_hash`。

预期结果：

- 步骤 2 输出 `ok`；步骤 3 取回的两条记录 `event` 不同但 `request_id` 相同。
- 步骤 4 之后 `logs.jsonl` 不再出现 `"level": "ERROR"`，第四组用例降级为 WARNING。
- 步骤 5 出现 `"request_id": "req-cs-0001"`；步骤 6 只有 `order_id_hash`，无明文订单号。

验证方法：`python3 -c "import json,collections;print(collections.Counter(json.loads(l)['level'] for l in open('logs.jsonl')))"`，步骤 4 之后预期为 `Counter({'INFO': 4, 'WARNING': 3})`。级别分布的下降就是“缺陷被消化”的证据。

清理方法：删除 `refund_service.py` 与 `logs.jsonl`；本实验不联网、不写数据库。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 线上全是 500，客服无法分流 | 所有失败共用一个兜底错误码 | 统计 `error_code` 的取值分布，只有一个值 | 按失败类别建异常子类，边界映射到不同 `code` 与状态码 |
| 有故障但日志里找不到 | 裸 `except: pass`，或 `except Exception: return None` | 搜索 `pass` 与 `return None`；在兜底分支加计数 | 边界内捕获、边界外记录；禁止空 `except` |
| 攻击者能伪造日志行 | 用户输入被拼进 `msg`，其中含换行与假 `level` | 提交含换行的入参后看日志是否多出一行 | 字段白名单加超长截断，不拼原始输入 |
| `request_id` 关联不到上下游 | 每层各自生成，或网关未透传 | 对比网关与服务日志里的同一标识 | 入口继承 `X-Request-Id`，缺失才生成 |

## 安全与生产注意事项

**<u>把完整卡号、手机号、token 或整个请求体原样写进日志，等于把日志平台变成第二个未加密的用户数据库。</u>** 后果是任何有日志查看权限的人（含外包与临时排障账号）都能批量导出敏感数据，而日志的备份与转发链路通常不受生产数据库那套访问控制约束。缓解：写入前统一脱敏（卡号留后四位、标识哈希、请求体只记字段名与长度），对 `stack` 与 `internal` 截断，并用静态扫描守住敏感字段清单。

**<u>只记录异常文案而不记录堆栈与上下文，会在真正的故障上浪费最宝贵的排查时间。</u>** 后果是日志里只有“服务暂时不可用”一句对外文案，无法定位哪一行、哪个订单、什么入参，MTTR 从分钟级变成小时级。缓解：对外文案与内部记录彻底分离，兜底分支必须写 `exc_type`、`stack`、`request_id`、`route` 与脱敏后的业务键。

## 本课总结

- **可预期的失败用类型与错误码表达，不可预期的失败由唯一边界兜底。**
- 错误信封的字段要少而稳：`code` 给程序，`message` 给人，`request_id` 给排查，`retriable` 给重试决策。
- **级别定义的是“谁来看”，不是“我多着急”。** 字段走 `extra`、事件名用点号分层，拒绝记 WARNING，需要人介入的记 ERROR。
- 敏感值写入前脱敏，堆栈留在服务端，日志行不得由用户输入拼接。

## 思考题

退款服务每天 30 万次调用，其中 `AMOUNT_EXCEEDS_LIMIT` 约 8 万次（都需人工审核，属正常业务）。团队希望完整保留每笔被拒的订单号与金额用于审计，但日志成本已经翻倍。请给出方案，并说明：哪些字段进索引、哪些只写不索引、如何在保住审计的前提下降低量级、如何证明方案有效。

参考思路：先区分“审计需求”与“排障需求”。审计走独立的只追加流与单独保留期，不与调试日志共用索引；调试日志对 WARNING 采样，或只记 `request_id` 与 `error_code`，细节按 `request_id` 回查审计流。索引只留低基数维度（`route`、`error_code`、`level`、`status`），订单号存值不建索引。有效性证据：日志量与成本曲线、按 `request_id` 回查的成功率、审计抽查通过率。

## 小测

1. 哪个字段负责告诉调用方“原样重试是否有意义”？  
   A. `message`　B. `retriable`　C. `request_id`　D. `status`
2. 业务规则拒绝（金额超限、需人工审核）更适合记哪个级别？  
   A. ERROR，因为业务失败了　B. WARNING，可预期且需关注但不必立即介入　C. DEBUG，因为系统没坏　D. CRITICAL，因为涉及金额
3. 为什么结构化日志不应把 `order_id` 用 f-string 拼进 `msg`？
4. `except Exception: pass` 在生产代码中为什么危险？
5. 场景题：客服要求“每个失败工单都能看到卡在哪一步、以及该不该再点一次重试”，而合规要求“日志不得出现完整手机号”。你会怎样设计错误响应与日志字段？

## 答案与解析

1. **B。** `retriable` 是明确的布尔语义。A 是给人读的文案，会被改写；C 只用于串联排查；D 只能粗略区分 4xx 与 5xx。
2. **B。** 它有既定处理路径（转人工），需要关注但不该触发呼叫。A 会让告警被业务拒绝淹没；C 会让运营数据在排查时消失；D 语义过重。
3. 拼接后字段只存在于一段文本中，采集端无法按 `order_id` 过滤、聚合或建索引，结构化日志退化回文本日志；用户输入里的换行与控制字符还能直接污染整行记录，形成日志注入。
4. 它把可预期失败、依赖故障与代码缺陷一起隐藏：没有错误码、堆栈与计数，故障表现为“结果不对”而不是“报错”。<u>即便兜底，也必须记录并映射到统一错误码。</u>
5. 参考方向：响应保留 `code`、`message`、`request_id`、`retriable`，再加可选 `step`（`VALIDATE`、`CHARGE`、`PERSIST`），客服页面按 `code` 与 `retriable` 决定是否显示重试按钮；日志记 `step`、`error_code`、`error_type`、`duration_ms`，手机号只记哈希或后四位。工单里只放 `request_id`。

### 动手实验参考

步骤 3 的一种实现：`python3 -c "import json;print([json.loads(l)['request_id'] for l in open('logs.jsonl') if json.loads(l)['event']=='refund.crashed'][0])"`，再用得到的值 `grep`，应返回两个事件。步骤 4 的判断标准是 `logs.jsonl` 中 `"level": "ERROR"` 的计数为 0，且 `outcome` 只有 `ok` 与 `rejected`；若仍是 `crashed`，说明类型校验加在了比较之后而不是之前。

## 延伸阅读与下一课

- [Python 官方文档：logging](https://docs.python.org/3/library/logging.html)：`Formatter`、`extra` 与 `exception()` 的权威行为。
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)：与本课错误信封对照的标准写法。
- [RFC 5424: The Syslog Protocol](https://www.rfc-editor.org/rfc/rfc5424.html)：严重级别定义的来源，理解“级别 = 谁来看”。
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)：敏感字段、日志注入与保留策略的检查清单。
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)：日志与指标、Tracing 共用字段时的约定。
- 返回[本单元目录](00-overview.md)。
- 回看上一课：[依赖、虚拟环境、配置与 Secret](02-dependencies-config-and-secrets.md)。
- 下一课：[Git、版本与代码审查](04-git-branching-and-code-review.md)。
