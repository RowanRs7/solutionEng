---
title: 熔断、降级与隔离
slug: circuit-breaking-degradation-and-isolation
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: intermediate
duration: 50m
prerequisites:
  - timeout-retry-backoff-and-idempotency
outcomes:
  - 描述熔断器三态及每个状态转换的触发条件
  - 为一个依赖写出分级结论与对应的降级返回
  - 选择舱壁隔离维度并说明其吞吐与成本代价
last_reviewed: 2026-10-19
---

# 熔断、降级与隔离

## 为什么需要学习

晴空商城的退款集成服务在大促当天出了第一次真正的事故。支付商退款查询接口的 P99 从 300 毫秒涨到 25 秒，重试把每次请求放大成三次调用，连接池几分钟内被占满，连只读页面也打不开。客服退回截图和微信群，退款处理时间从两小时变回两天。

复盘结论是：拖垮服务的不是支付商，而是退款服务对“某个依赖变慢”没有结构性防御：超时 30 秒、失败照样重试、共用一个连接池。

> **核心结论：** 熔断、降级与隔离不解决“如何让失败不发生”，而是让一次失败只影响它本该影响的那一小部分。

## 学习目标

完成本课后，你能够：

- 描述熔断器 *closed*、*open*、*half-open* 三种状态及每个转换的触发条件。
- 为一个具体依赖写出分级结论，并给出与该级别匹配的降级返回。
- 选择舱壁隔离的维度，并说明它在吞吐与成本上的代价。
- 针对给定故障现象，判断优先用超时、重试、限流、熔断还是降级。

## 前置知识

- 回看上一课：[超时、重试、退避与幂等](05-timeout-retry-backoff-and-idempotency.md)。
- 理解超时、重试次数和总体时间预算之间的关系。
- 知道幂等键为什么能让重试安全。
- 能读懂 Python 的 `try/except/finally` 和线程的基本用法。

## 业务场景

退款集成服务串起四个外部依赖，重要性完全不同：

| 依赖 | 用途 | 故障时的业务影响 |
| --- | --- | --- |
| 支付商退款 API | 发起退款（写） | 退款无法完成，用户可等待 |
| ERP 订单查询 | 读发货与签收状态 | 客服看不到进度，但可受理 |
| 客服工单系统 | 回写处理结果（写） | 工单不同步，客服会重复处理 |
| 短信通知 | 告知用户（写） | 用户晚几分钟知道，站内信兜底 |

产品目标写得很清楚：退款受理可用性不低于 99.9%，ERP 故障时客服仍能受理退款，状态显示为“待核”。约束同样明确：资金类写操作不得伪造成功，短信失败允许丢弃。

上一课解决了“单次调用不要无限等待”和“重试要幂等”。本课回答剩下三个问题：何时停止调用、调用不了时返回什么、一个慢依赖如何不拖垮其他依赖。

## 核心概念

| 概念 | 本课程中的含义 | 晴空商城示例 |
| --- | --- | --- |
| *熔断器* | 调用链上的状态开关，失败即快速返回 | 支付商退款 API 的闸门 |
| *快速失败* | 不发起网络请求，直接返回错误或兜底值 | 打开后 3 毫秒返回“待核” |
| *半开探测* | 打开后只放极少量请求验证依赖是否恢复 | 放 1 个真实退款请求试探 |
| *降级* | 依赖不可用时用替代结果完成业务 | 订单状态返回“待核” |
| *兜底值* | 降级时返回的、与正常响应同构的数据 | `{"status": "pending_review", "degraded": true}` |
| *舱壁* | 为不同依赖分配独立容量 | 退款查询与提交用不同连接池 |
| *依赖分级* | 按业务不可替代性定级并配置容错动作 | 支付商为 P0，短信为 P2 |

**熔断是入口控制**，决定“要不要真的调用依赖”；**降级是出口控制**，决定“调用不了时给调用方什么”。两者常成对出现。只降级不熔断，每次都要先超时一次；只熔断不降级，只是把慢故障换成快故障，<u>很容易被误当成“已经修好了”</u>。

### 依赖分级的三档口径

| 级别 | 判定标准 | 晴空商城例子 | 故障时动作 |
| --- | --- | --- | --- |
| P0 核心 | 缺失则业务不成立 | 支付商退款 API | 快速失败，转异步受理进人工队列 |
| P1 重要 | 缺失则体验受损，可降级完成 | ERP 查询、工单回写 | 返回兜底值并标记降级 |
| P2 辅助 | 缺失只影响通知 | 短信通知 | 静默丢弃，写日志 |

分级必须由业务方确认，不能由开发按“依赖是否稳定”来定。<u>把不稳定的 P2 依赖当成 P0，等于为它牺牲整个受理流程。</u>

## 工作原理

一次退款查询请求依次穿过四层防护，顺序不能颠倒：

1. **识别依赖与级别**：查出本次调用涉及哪个依赖，读取分级配置（超时、阈值、能否降级）。
2. **申请舱壁名额**：按依赖获取名额，只等极短时间，拿不到就降级，不在这一层排队。
3. **检查熔断器**：open 则直接快速失败并降级；half-open 则检查探测名额是否还有剩余。
4. **发起真实调用**：带单次超时，重试次数有限，总耗时不超过该依赖的预算。
5. **归类结果**：超时、连接拒绝、5xx 记为*技术失败*；参数错误等 4xx 记为*业务失败*，不计入熔断统计。
6. **上报熔断器**：成功清零计数；失败累加，达阈值即打开并记录时刻。
7. **执行状态转移**：窗口结束后，由下一个到达的请求触发半开。
8. **写出降级痕迹**：结果带 `degraded`、原因码和请求标识，供监控和对账区分。

三态转移构成一条闭环：

- **closed → open**：窗口内样本量达标且技术失败率超阈值，或连续失败次数达到阈值。
- **open → half-open**：经过 `open_seconds` 后由第一个到达的请求推进，不是后台定时器。
- **half-open → closed**：探测成功，清零计数，恢复放行。
- **half-open → open**：探测失败，立刻重新打开并重置窗口。

<u>熔断器必须按依赖、按实例独立。</u>全局熔断器会把“短信发不出去”升级成“所有请求都失败”，这正是要防的事故。多实例各实例自行统计，不要用共享存储做全局计数，那会把熔断变成新的单点。

## 架构与选型

| 机制 | 解决的问题 | 适用场景 | 不适用或代价 |
| --- | --- | --- | --- |
| 客户端熔断库 | 按依赖统计失败并控制放行 | 服务内部调用、SDK 成熟 | 每种语言都要实现一遍 |
| 网关或服务网格熔断 | 统一策略，无需改代码 | 多语言、需集中治理 | 只看网络层指标 |
| 线程池隔离 | 彻底隔离阻塞与排队 | 同步阻塞、延迟差异大 | 线程切换与内存开销大 |
| 信号量隔离 | 限制并发，开销极小 | 异步非阻塞、调用很快 | 无法阻断调用方阻塞 |
| 进程或集群隔离 | 故障域最大分离 | 资金、风控链路 | 部署与运维成本最高 |
| 静态降级开关 | 人工切换行为 | 大促保障、计划内维护 | 依赖人工，容易忘记恢复 |

选型顺序是“先分级、再定入口、最后定隔离”。分级没有结论时，任何阈值都是拍脑袋：不知道短信可丢，就会给它配三次重试。

**默认应选择快速失败，而不是慢慢成功。**熔断加降级把依赖故障时的平均响应从 25 秒压到几十毫秒，代价是部分请求拿到兜底值；对“先接住再补”的业务，这个交换几乎总是划算的。

## 最小示例

下面用 Python 3 标准库实现熔断、舱壁和降级的组合，不需要第三方包。两段代码依次保存为同一个文件 `breaker_demo.py`。

第一段是熔断器和舱壁本身。所有状态修改都在锁内完成，因为真实服务里这些方法会被多个线程同时调用。

```python
import threading
import time
from enum import Enum


class BreakerOpen(Exception):
    """熔断打开时抛出，表示本次调用不消耗依赖。"""


class State(Enum):
    CLOSED = "closed"        # 正常放行
    OPEN = "open"            # 直接拒绝
    HALF_OPEN = "half_open"  # 只放少量探测


class CircuitBreaker:
    def __init__(self, failure_threshold=3, open_seconds=2.0, half_open_probes=1):
        # 连续失败阈值：小流量系统用连续次数比失败率更稳
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds      # 打开后等待多久才允许探测
        self.half_open_probes = half_open_probes  # 半开时最多放行的请求数
        self.state = State.CLOSED
        self.failures = 0
        self.opened_at = 0.0
        self.probes = 0
        self._lock = threading.Lock()         # 状态是共享可变数据，必须加锁

    def before_call(self):
        with self._lock:
            if self.state is State.OPEN:
                # 用单调时钟计算窗口，避免系统时间回拨导致提前放行
                if self._now() - self.opened_at >= self.open_seconds:
                    self.state = State.HALF_OPEN   # 由第一个到达的请求推动
                    self.probes = 0
                else:
                    raise BreakerOpen("熔断中")
            if self.state is State.HALF_OPEN:
                if self.probes >= self.half_open_probes:
                    raise BreakerOpen("半开探测名额已用完")
                self.probes += 1              # 名额先占后调，防止并发涌入

    def on_success(self):
        with self._lock:
            if self.state is State.HALF_OPEN:
                self.state = State.CLOSED     # 探测成功，正式恢复
                self.failures = 0

    def on_failure(self):
        with self._lock:
            self.failures += 1
            # 半开下失败说明依赖没恢复，立刻重新打开并重置窗口
            if self.state is State.HALF_OPEN or self.failures >= self.failure_threshold:
                self.state = State.OPEN
                self.opened_at = self._now()

    @staticmethod
    def _now():
        return time.monotonic()


class Bulkhead:
    """用信号量限制同一依赖的并发数，拿不到名额就降级。"""

    def __init__(self, limit):
        self._slots = threading.BoundedSemaphore(limit)

    def try_enter(self, timeout=0.0):
        return self._slots.acquire(timeout=timeout)  # timeout 很短，不在这一层排队

    def leave(self):
        self._slots.release()
```

第二段是依赖模拟、组合调用和驱动脚本。`query_order` 展示了防护链的正确顺序：先舱壁、再熔断、最后调用，`finally` 保证名额一定归还。

```python
ERP_DOWN = threading.Event()   # 置位表示 ERP 故障


def erp_lookup(order_id):
    time.sleep(0.3)            # 模拟一次网络往返
    if ERP_DOWN.is_set():
        raise TimeoutError("ERP 查询超时")
    return {"order_id": order_id, "status": "paid", "degraded": False, "reason": None}


def fallback_order(order_id, reason):
    # 兜底值与正常响应同构，并显式标记降级，下游才不会误读
    return {"order_id": order_id, "status": "pending_review",
            "degraded": True, "reason": reason}


breaker = CircuitBreaker()
bulkhead = Bulkhead(limit=2)


def query_order(order_id):
    if not bulkhead.try_enter(timeout=0.05):
        return fallback_order(order_id, "bulkhead_full")   # 容量耗尽也算降级原因
    try:
        breaker.before_call()
        try:
            result = erp_lookup(order_id)
        except Exception:
            breaker.on_failure()
            return fallback_order(order_id, "erp_error")
        breaker.on_success()
        return result
    except BreakerOpen:
        return fallback_order(order_id, "breaker_open")
    finally:
        bulkhead.leave()       # 任何分支都要归还名额，否则名额会泄漏


print("阶段 1：ERP 故障，连续查询 4 次")
ERP_DOWN.set()
for i in range(1, 5):
    start = time.monotonic()
    r = query_order(f"SO-{i}")
    print(f"  call{i} 用时 {time.monotonic() - start:.2f}s 状态 {r['status']} "
          f"原因 {r['reason']} 熔断器 {breaker.state.value}")

print("阶段 2：等待恢复窗口，关闭故障后做一次探测")
time.sleep(2.1)
ERP_DOWN.clear()
r = query_order("SO-5")
print(f"  probe 状态 {r['status']} 熔断器 {breaker.state.value}")

print("阶段 3：4 个并发请求争抢 2 个舱壁名额")
barrier = threading.Barrier(4)
out, lock = [], threading.Lock()


def worker(index):
    barrier.wait()             # 让 4 个线程尽量同时出发
    r = query_order(f"SO-B{index}")
    with lock:
        out.append((index, r["status"], r["reason"]))


threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
for index, status, reason in sorted(out):
    print(f"  B{index} 状态 {status} 原因 {reason}")
```

运行方式与输出：

```bash
python3 breaker_demo.py
```

预期输出（耗时可能有一两毫秒浮动）：

```text
阶段 1：ERP 故障，连续查询 4 次
  call1 用时 0.31s 状态 pending_review 原因 erp_error 熔断器 closed
  call2 用时 0.30s 状态 pending_review 原因 erp_error 熔断器 closed
  call3 用时 0.30s 状态 pending_review 原因 erp_error 熔断器 open
  call4 用时 0.00s 状态 pending_review 原因 breaker_open 熔断器 open
阶段 2：等待恢复窗口，关闭故障后做一次探测
  probe 状态 paid 熔断器 closed
阶段 3：4 个并发请求争抢 2 个舱壁名额
  B1 状态 paid 原因 None
  B2 状态 pending_review 原因 bulkhead_full
  B3 状态 pending_review 原因 bulkhead_full
  B4 状态 paid 原因 None
```

输出对应三个设计意图：第 4 次调用耗时接近 0，说明快速失败生效、依赖没被再次访问；探测成功后回到 closed，说明半开是唯一出口；阶段 3 只有两个请求真正打到依赖，说明容量限制收窄了故障域。

代码有两处取舍：阈值用连续失败次数而非失败率，因为演示流量太小；舱壁用信号量而非线程池，因为同步调用本身就在线程里。

## 动手实验

### 任务：为退款服务做依赖分级并演练三种故障

前置条件：Python 3.8 以上，离线环境，不需要任何第三方库或真实凭据。

1. 复制下表，为四个依赖各填一行，并写清判断依据。

| 依赖 | 级别 | 单次超时 | 熔断阈值 | 降级动作 | 是否允许降级为“成功” |
| --- | --- | --- | --- | --- | --- |
| 支付商退款 API |  |  |  |  |  |
| ERP 订单查询 |  |  |  |  |  |
| 客服工单回写 |  |  |  |  |  |
| 短信通知 |  |  |  |  |  |

2. 把 `erp_lookup` 改成三个桩：全部失败、30% 概率失败、恢复正常但慢 3 秒。
3. 将 `failure_threshold` 改为 5、`open_seconds` 改为 10，用 20 次顺序调用观察熔断器在第几次打开、打开后有多少次走了 `breaker_open`。
4. 把 `Bulkhead(limit=2)` 改为 `limit=1` 和 `limit=8`，重复阶段 3，记录降级比例。

预期结果：第 5 次调用后 `breaker.state` 变为 `open`，第 6 次起耗时小于 10 毫秒且原因为 `breaker_open`；等待 10 秒后的下一次调用进入 `half_open` 并只放 1 个探测。舱壁为 1 时 4 个并发请求中 3 个降级，为 8 时全部成功。

验证方法：打印 `breaker.state.value` 和 `r["reason"]`，确认“失败 + 快速失败 + 成功”等于总调用数，且 open 期间没有一次真正执行了 `erp_lookup`（可在桩函数里加计数）。

清理方法：删除 `breaker_demo.py`，调用 `ERP_DOWN.clear()` 复位事件；本实验不产生外部状态或凭据。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 依赖已经大面积超时，熔断器却一直是 closed | 用失败率做阈值但没有最小请求数，低流量下永远达不到比例 | 打印窗口内请求数与失败数 | 同时使用绝对次数与失败率，并设置最小样本量 |
| 熔断打开后接口仍然报 500 | 只熔断没降级，异常直接冒到上层 | 检查 open 期间每个接口的响应体 | 为每个依赖定义兜底值，并带 `degraded` 标记 |
| 参数错误也把熔断器打开了 | 4xx 业务失败与技术失败混在一起统计 | 按错误类型拆分指标 | 只把超时、连接失败和 5xx 计入技术失败 |
| 降级后前端报空指针或金额显示为 0 | 兜底值与正常响应不同构，字段缺失 | 对比正常与降级响应的字段集合 | 兜底对象字段与正常响应一致，缺值用显式 null |
| 舱壁可用名额随时间单调下降 | 某条分支 `return` 前没有释放名额 | 打印信号量剩余计数 | 统一用 `finally` 释放，并对名额占用加监控 |

## 安全与生产注意事项

**<u>把降级写成伪造成功，会让资金类操作出现账实不符。</u>**支付商超时却返回 `status: refunded`，客服和用户都以为退款已发生。后果是对账缺口、重复投诉甚至重复退款。缓解：写路径的降级只能返回“已受理/待核”并落库为可追踪任务，任何“已完成”终态都必须来自依赖的真实响应。

**<u>熔断恢复时放量过猛会二次击穿依赖，责任在调用方。</u>**半开状态下一次放全量，会形成*惊群*：恢复瞬间的流量再次把依赖压垮，而依赖方会认为是你打挂了它。缓解：半开探测数固定为 1，恢复后按 10%、50%、100% 阶梯放量，并与依赖方确认恢复信号。

<u>降级路径不能跳过鉴权、审计和限流。</u>兜底值同样会进入客服界面和财务报表，仍要走权限校验和审计日志，否则“降级”就成了绕过控制的后门。阈值、容量和降级开关的变更都应按生产配置管理：有评审、有记录、可回滚，并在大促前压测。

## 本课总结

- **熔断器是入口开关，用三态把“持续失败”换成“快速失败”**，代价是部分请求拿到兜底值。
- **降级是出口契约**，兜底值必须与正常响应同构并显式标记；资金写操作只能降级为“待核”。
- 依赖分级先于机制选型：级别决定超时、阈值和降级动作，且要由业务方确认。
- 舱壁用容量换取影响范围，信号量隔离便宜、线程池隔离彻底，进程隔离最贵。
- 没有观测就没有熔断：失败率、窗口、open 时长和降级比例都要有指标。

## 思考题

支付商退款接口有 30% 的概率超时。产品经理要求把熔断阈值从 20% 提到 50%，理由是“这样还有 70% 的成功率，总比不调用好”。请分析这个要求忽略了什么，并写出你的回应。

参考思路：先区分“调用尝试的成功率”和“用户可感知的完成率”。30% 超时意味着每次失败都占满超时预算并消耗连接，重试再放大三倍负载，可能把依赖推向完全不可用。提高阈值能多救回一些请求，代价是恢复更慢。替代方案：保持低阈值但延长 `open_seconds`、把退款提交改为异步受理、对超时请求查结果而非盲目重试。最终由业务方在“受理速度”和“依赖可用性”之间决定。

## 小测

1. 判断：熔断器打开后，所有调用都应立即失败，不再发起网络请求。对还是错？
2. 判断：熔断器只在 `open_seconds` 到期时自动变回 closed。对还是错？
3. 半开状态只允许极少量请求通过，主要原因是：  
   A. 节省带宽　B. 避免恢复瞬间的流量再次压垮依赖　C. 让日志更少　D. 满足审计要求
4. 下列哪种结果不应计入熔断器的技术失败：  
   A. 连接超时　B. 依赖返回 503　C. 依赖返回 400 参数错误　D. TCP 连接被重置
5. 场景题：ERP 查询超时后，退款服务直接返回 `status: refunded` 并继续后续流程。问题出在哪里，应该怎么改？

## 答案与解析

1. **对。**打开即不再消耗依赖，这才把 25 秒等待换成毫秒级返回；若仍发起调用，熔断只剩报表功能。
2. **错。**到期只表示“允许试探”，真正推进到 half-open 的是到期后第一个请求，也只有探测成功才回到 closed。把它当定时自动恢复，会掩盖依赖仍未恢复。
3. **B。**半开是唯一恢复通道，放行量必须小于依赖承受能力。A、C 只影响资源与日志量，D 与探测数量无关。
4. **C。**400 说明请求已到达并被正确处理，依赖是健康的；计入会因用户输错参数而误熔断。A、B、D 都表示依赖不可用或不可达。
5. 两层问题：伪造终态（依赖没确认却输出“已完成”，导致账实不符和重复退款），以及异常被吞掉（监控看不到依赖已故障）。改法：返回“已受理/待核”并落库为可追踪任务，带 `degraded` 与原因码，熔断器照常累计失败，由异步补偿在 ERP 恢复后核对。

### 动手实验参考

分级表没有唯一答案，但依据要能辩护。合理填法：支付商退款 API 为 P0，超时 5 秒，连续 5 次失败熔断，降级为“已受理待确认”，不得降级为成功；ERP 查询为 P1，超时 2 秒，失败率 50% 且样本不少于 20 次时熔断，降级为“待核”；工单回写为 P1，降级为本地队列重试；短信为 P2，直接丢弃。若表里出现“全是 P0”或“降级都返回成功”，说明分级没做。

## 延伸阅读与下一课

- [Microsoft Azure 架构中心：断路器模式](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [Microsoft Azure 架构中心：舱壁模式](https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
- [AWS Builders' Library：超时、重试与抖动退避](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)
- [Google SRE 手册：处理过载](https://sre.google/sre-book/handling-overload/)
- [Envoy：异常点检测（outlier detection）](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/outlier)
- 术语与缩写可查[术语表](../../reference/glossary.md)。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[超时、重试、退避与幂等](05-timeout-retry-backoff-and-idempotency.md)。
- 下一课：[Webhook、签名与重放保护](07-webhooks-signing-and-replay-protection.md)。
