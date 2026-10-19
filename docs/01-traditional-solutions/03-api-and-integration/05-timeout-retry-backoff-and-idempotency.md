---
title: 超时、重试、退避与幂等
slug: timeout-retry-backoff-and-idempotency
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - pagination-filtering-and-rate-limits
outcomes:
  - 区分可重试、不可重试与结果未知三类失败并给出对应动作
  - 为一条调用链设定超时预算与带抖动的指数退避计划
  - 用幂等键和去重存储阻止重复退款与并发重复提交
last_reviewed: 2026-10-19
---

# 超时、重试、退避与幂等

## 为什么需要学习

晴空商城退款集成服务上线第一周，支付商接口在晚高峰抖动。一次读超时被 worker 当成失败，自动重试后支付商侧出现两笔 199 元退款，人工对账才发现。运维把重试次数调大；三天后支付商限流，重试同步涌入，退款队列堵到第二天。第三次事故更简单：客服刷新页面，同一笔退款提交了四次。

三次事故各修一处都能避免，却指向同一组决定：调用失败时凭什么判断对方没执行？愿意等多久？重复执行会出错吗？

> **核心结论：** 重试只能修复“调用没有成功”，无法修复“结果未知”；超时、退避与幂等必须作为一个整体设计。

## 学习目标

完成本课后，你能够：

- 把一次失败的调用归入可重试、不可重试与结果未知三类，并为每类写出对应动作。
- 为一条调用链设定超时预算，说明每层超时与上游剩余 deadline 的关系。
- 写出含指数退避、抖动、尝试上限与重试预算的重试计划，并算出最坏耗时。
- 设计一组幂等键与去重存储规则，说明它如何同时阻止重复提交与并发重复扣款。

## 前置知识

- 回看上一课：[分页、过滤、批量与限流](04-pagination-filtering-and-rate-limits.md)。
- 能读懂 HTTP 状态码与 `Retry-After`，知道 `4xx` 与 `5xx` 的处理方式不同（回看[HTTP 请求、响应与状态码](../02-web-and-network/03-http-request-response.md)）。
- 知道接口契约与统一错误模型的作用（回看[参数校验、错误模型与版本管理](03-validation-errors-and-versioning.md)）。
- 能读写 Python 的字典、异常与简单多线程代码。

## 业务场景

晴空商城这一侧面：客服提交退款、订单服务生成退款单、worker 调用支付商、成功后通知仓库回滚出库单。

- 客服页面要求 2 秒内确认受理，退款因此异步受理、后台执行。
- 支付商 `POST /v1/refunds` 响应在 1–90 秒间波动，偶发 `502` 与 `429`；超时后对方可能已执行成功。
- 支付商支持幂等键，最长 64 字符、保留 24 小时；超出窗口的重复请求算新退款。
- 仓库回滚也不能重复：重复回滚会把已出库商品重复入库，库存虚增。

约束三条：同一笔退款只扣一次，失败要自动恢复，限流时不能把双方一起压垮。

## 核心概念

*失败分类*（failure classification）在重试前先判断性质：*可重试*（连接中断、超时、`502`、`503`、`429`）是暂时性的；*不可重试*（参数错误、余额不足、`401`、`403`）重试多少次都一样；*结果未知*（读超时、连接中途断开）最危险，对方可能已执行。

*超时*（timeout）是等待上限，至少分三段：*连接超时*决定多久连不上就放弃，*读取超时*决定发出请求后等多久，*整体 deadline* 是必须给出结论的时间点。<u>只配一个笼统超时，等于把“连不上”和“已执行但没回包”混为一谈。</u>

*超时预算*（timeout budget）从对外承诺倒推：客服 2 秒受理、整笔退款 60 秒、支付商单次最多 20 秒；下游拿到“剩余预算”而非固定值。

*重试*（retry）是判定可重试后再次发起同一操作，*退避*（backoff）是两次尝试间的等待，*指数退避*让等待随次数翻倍，*抖动*（jitter）叠加随机量把客户端打散。<u>没有抖动的退避只是把尖峰推迟到同一秒。</u>

*幂等*（idempotent）指同一操作执行一次和多次结果相同。*幂等键*（idempotency key）是发起方为一次业务意图生成的标识；*去重存储*（deduplication store）按键记录“是否已受理、结果是什么”，拦截重复与并发。

| 概念 | 本课中的含义 | 晴空商城示例 |
| --- | --- | --- |
| 读超时 | 请求已送达，但等不到响应 | 支付商 20 秒未回包，退款可能已成功 |
| 幂等键 | 业务意图的稳定标识 | `refund-8871-v1` |
| 去重存储 | 幂等键到结果的映射 | `refund_dedupe` 表，`key` 上有唯一索引 |

失败分类决定后续动作：

| 失败类别 | 典型信号 | 能否重试 | 正确动作 |
| --- | --- | --- | --- |
| 可重试 | 连接被拒绝、`502`/`503`/`429`、连接超时 | 能 | 按退避计划重试，同一幂等键 |
| 不可重试 | `400`、`401`/`403`、业务拒付 | 不能 | 立即失败，记录原因转人工 |
| 结果未知 | 读超时、连接中途断开 | 只能带幂等键重试 | 同一幂等键重试或查询，再对账 |

## 工作原理

一次退款的完整处理顺序如下：

1. 客服提交退款，服务端用业务单号派生幂等键 `refund-8871-v1` 并写入 `pending` 退款单；`refund_dedupe.key` 的唯一索引挡住重复提交，直接返回已有单号。
2. 客服 2 秒内拿到受理编号，后续全异步。
3. worker 算出整体 deadline（受理时间 + 60 秒），剩余时间写入后续每一步。
4. 调用前先在去重存储 *claim* 键：抢到才允许扣款，抢到 `done` 直接返回历史结果。
5. 发起请求，连接超时 2 秒、读取超时 20 秒，两者之和不超过剩余预算。
6. 响应先分类：`2xx` 成功；`429` 与 `5xx` 可重试；`400`、`401`、业务拒付不可重试，立即结束。
7. 可重试时算等待 `random(0, min(cap, base × 2^(n-1)))`，再检查剩余预算能否放下等待加一次读取超时，放不下就停。
8. 读超时或连接中断归入结果未知：<u>不能换新键，也不能直接判失败</u>，只能用同一幂等键重试或查询状态。
9. 确认成功后写入 `status=done` 与响应，之后重放原样返回，不再扣款。
10. 重试耗尽仍不确定时标记 `uncertain` 进对账队列；<u>不能静默丢弃，也不能标失败让客服手工重提</u>。

两个边界：*重试预算*要求重试量不超过总请求的 10%，超了该熔断；幂等键生命周期要求去重记录保留到最后一次可能重试之后，超出窗口只能走对账。

## 架构与选型

| 方案 | 适合 | 不适合 | 代价 |
| --- | --- | --- | --- |
| 固定间隔重试 | 内网、调用量小 | 下游限流、客户端同质 | 同时失败者同时重试，形成尖峰 |
| 指数退避 + 抖动 + 上限 | 多数跨系统同步调用 | 需秒级恢复的强实时链路 | 参数要按预算调，最坏耗时要算 |
| 队列异步重试 + 死信 | 允许分钟级完成、需削峰 | 用户在前台同步等待 | 需要队列、幂等与可观测 |
| 去重表（唯一索引 + 结果列） | 资金、订单等写操作 | 极高并发写同一键 | 需要事务与清理策略 |
| Redis `SETNX` 幂等标记 | 高并发快速拦截 | 不允许丢标记的资金场景 | 内存可能丢数据，需持久化 |
| 天然幂等（状态机 CAS） | 状态流转明确的操作 | 无法表达“同一意图”的接口 | 需要改造业务模型 |

选型依据三条：**写操作一律要求幂等**；**重试方式由时间预算决定**，秒级预算同步重试，分钟级交给队列；**去重存储的持久性由损失金额决定**，资金类必须落在事务型数据库。查询接口可以裸重试，但仍要配超时和上限。

## 最小示例

问题：不接真实支付商，先看清退避计划怎样被预算截断，以及“先查后写”为什么会重复扣款。

环境：Python 3.9 以上，只用标准库 `random`、`threading`。输出是退避计划与扣款次数。

```python
"""按预算生成重试计划：每次尝试都假设用满超时，最坏耗时不超出 budget。"""
import random

def build_plan(budget=10.0, attempt_timeout=3.0, base=0.5, cap=4.0, seed=7):
    rng = random.Random(seed)   # 固定种子只为让输出可复现；生产里应使用不可预测的随机源
    plan, spent, attempt = [], 0.0, 1
    while True:
        if spent + attempt_timeout > budget:      # 剩余预算已放不下一次尝试
            plan.append(f"放弃：已用 {spent:.1f}s，剩余不足以再等 {attempt_timeout}s")
            return plan
        plan.append(f"第 {attempt} 次尝试：最多等 {attempt_timeout:.1f}s，累计 {spent:.1f}s")
        if attempt == 4:                          # 最大尝试次数兜底，防止无限重试
            plan.append("放弃：达到最大尝试次数 4")
            return plan
        ceiling = min(cap, base * 2 ** (attempt - 1))  # 指数增长并按上限封顶
        wait = round(rng.uniform(0, ceiling), 2)       # full jitter：在 0..ceiling 间随机取值
        plan.append(f"  退避 {wait:.2f}s（本次上限 {ceiling:.1f}s）")
        spent += attempt_timeout + wait           # 按最坏情况累加：这次尝试可能照样超时
        attempt += 1

print("\n".join(build_plan()))
```

预期输出（`seed=7`，Python 3.14 实测）：

```text
第 1 次尝试：最多等 3.0s，累计 0.0s
  退避 0.16s（本次上限 0.5s）
第 2 次尝试：最多等 3.0s，累计 3.2s
  退避 0.15s（本次上限 1.0s）
第 3 次尝试：最多等 3.0s，累计 6.3s
  退避 1.30s（本次上限 2.0s）
放弃：已用 10.6s，剩余不足以再等 3.0s
```

第三行只退避 1.30 秒，是抖动在起作用；换成固定 2 秒，同一批 worker 会同时再打向支付商。

第二个脚本验证去重的原子性：判断“有没有记录”和写入“正在处理”必须在同一个临界区里完成。

```python
"""同一幂等键被两个线程同时提交：原子 claim 扣一次，先查后写扣两次。"""
import sys
import threading

ATOMIC = len(sys.argv) < 2 or sys.argv[1] != "naive"   # 传 naive 参数即复现竞态

class RefundService:
    def __init__(self):
        self._lock = threading.Lock()          # 原子模式下保护“判断 + 写入”
        self._barrier = threading.Barrier(2)   # 让两个线程都读到空记录后再各自写入
        self._records = {}                     # 真实系统这里是带唯一索引的去重表
        self.charges = []                      # 每次真实扣款追加一次，代替对支付商的调用

    def refund(self, key, amount):
        decision = self._claim(key, amount)
        if decision == "new":
            self.charges.append(key)                        # 只有抢到“新请求”的线程才扣款
            record = self._records[key]
            record["status"] = "done"                       # 结果落库，供后续重放
            record["result"] = {"refund_id": f"rf_{len(self.charges)}", "amount": amount}
            return record["result"]
        if decision == "replay":
            return self._records[key]["result"]             # 重放：返回首次结果，不再扣款
        return {"error": decision}                          # conflict 或 in_progress

    def _claim(self, key, amount):
        def decide(record):                                 # 决策逻辑只写一份
            if record is None:
                self._records[key] = {"amount": amount, "status": "in_progress", "result": None}
                return "new"
            if record["amount"] != amount:
                return "conflict"                           # 同键不同金额：拒绝，防止键被误复用
            if record["status"] == "in_progress":
                return "in_progress"                        # 首次仍在执行，第二次不应再发起
            return "replay"

        if ATOMIC:
            with self._lock:                                # 判断与写入同处一个临界区
                return decide(self._records.get(key))
        record = self._records.get(key)                     # 先查
        if record is None:
            self._barrier.wait()                            # 两个线程都确认“没记录”后才继续
        return decide(record)                               # 后写：都按新请求处理，于是扣两次

def run_case():
    service = RefundService()
    workers = [threading.Thread(target=service.refund, args=("refund-8871", 199)) for _ in range(2)]
    for worker in workers: worker.start()
    for worker in workers: worker.join()
    replay = service.refund("refund-8871", 199)             # 事后重放：不得再扣款
    return len(service.charges), replay


count, replay = run_case()
print(f"mode={'atomic' if ATOMIC else 'naive'} 扣款次数={count} 重放返回={replay}")
```

预期输出（Python 3.14 实测）：

```text
$ python3 dedupe.py
mode=atomic 扣款次数=1 重放返回={'refund_id': 'rf_1', 'amount': 199}
$ python3 dedupe.py naive
mode=naive 扣款次数=2 重放返回={'refund_id': 'rf_1' 或 'rf_2', 'amount': 199}
```

说明：naive 模式下两个线程都会写结果，末次写入胜出，`refund_id` 的编号随调度顺序可能变化（`rf_1` 或 `rf_2` 都正常）；这一组只核对扣款次数 = 2 与重放不再新扣款，编号本身不是断言对象。

整体分三段：`decide()` 只描述“记录该怎么判”，`_claim()` 决定加不加锁，`refund()` 只在拿到 `new` 时扣款。真实系统里锁由唯一索引或事务替代；<u>“判断与写入必须原子”这条不变</u>。

## 动手实验

前置条件：已装 Python 3.9 以上，无需网络与账号；文件只放在 `/tmp`。

1. 建实验目录，把上面两段代码存成 `backoff.py` 与 `dedupe.py`：
   ```bash
   mkdir -p /tmp/qk-retry && cd /tmp/qk-retry
   ```
2. 跑三种模式，记录扣款次数：
   ```bash
   python3 dedupe.py
   python3 dedupe.py naive
   python3 backoff.py
   ```
3. 在 `decide()` 里加过期检查，模拟 TTL 到期：写入 `expire_at = time.time() + TTL` 且 `TTL = 0`，过期即当作没有记录。再运行 `python3 dedupe.py`。
4. 把 `backoff.py` 的 `attempt_timeout` 改成 6、`budget` 保持 10，观察预算如何吃掉尝试次数。
5. 恢复 `attempt_timeout=3`，把 `budget` 改成 120、尝试上限从 4 改成 8、`cap` 改成 30，观察最坏耗时。

预期结果：步骤 2 原子模式扣 1 次、`naive` 扣 2 次、重放都不再扣款；步骤 3 原子模式也变成 2 次；步骤 4 只打印一次尝试即放弃（累计 6.2 秒）；步骤 5 打印满 8 次尝试，最坏耗时逼近 90 秒。

验证方法：扣款次数直接对应资金损失；步骤 3 说明 TTL 短于重试窗口等于没有幂等；步骤 4、5 说明预算、封顶与尝试上限要一起调。

清理方法：`rm -rf /tmp/qk-retry`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 超时后重试，支付商侧出现两笔退款 | 把“结果未知”当失败，重试还换了新键 | 按金额与时间查支付商后台重复单 | 结果未知只带同一幂等键重试，并加对账 |
| 重试次数加到 5 次，成功率几乎没涨 | 重试了不可重试错误 | 统计失败响应的状态码分布 | 只对超时、`429`、`5xx` 重试 |
| 下游恢复瞬间流量更高，队列被压垮 | 固定间隔退避，缺少抖动 | 看重试量与原始曲线是否同步尖峰 | 指数退避 + full jitter + 重试预算 |
| 每层超时都合规，端到端却超时 | 每层都设满预算，串起来超出承诺 | 用 trace 看各段耗时与 deadline | 按剩余预算递减下发超时 |
| 客服刷新一次就多一张退款单 | 幂等键由服务端每次请求重新生成 | 查去重表键是否一单一键 | 键由业务单号派生，客户端也可生成 |
| 同一幂等键金额不同却返回旧结果 | 只比键、不比请求指纹 | 查去重记录是否存请求摘要 | 存请求指纹，不一致返回 `409` |

## 安全与生产注意事项

**<u>把“超时”当成“没执行”，会对资金操作产生真实重复扣款。</u>** 读超时的语义是“不知道结果”，不是“失败”，后果是双倍退款与对账差异。缓解：结果未知只允许带同一幂等键重试，并为 `uncertain` 准备日终对账。

**<u>幂等键出现在 URL、日志明文或可预测序列里，可被用来重放他人的操作结果。</u>** 后果是越权读取退款详情、探测订单量级，甚至触发重复退款。缓解：键只放请求头与内部存储，日志脱敏，按租户隔离，记录设固定保留期。

**<u>没有上限的重试会在下游故障时把流量放大成雪崩。</u>** 后果是重试挤占正常请求、连接池耗尽，故障扩散回自家服务。缓解：尝试上限、总预算、抖动与重试预算四件套同时上线，重试率超标时交给熔断。

去重表清理必须晚于幂等窗口，否则旧键被清掉后重放会变成新单。

## 本课总结

- 重试前先分类：可重试才退避，不可重试立刻失败，结果未知只带同一幂等键重试或查询。
- 超时是预算而非单个数字：按承诺倒推，余量逐层递减，连接与读取分开。
- 指数退避必须有上限和抖动，否则只是把尖峰推迟；重试率超标时该熔断而不是继续重试。
- 幂等靠“幂等键 + 去重存储 + 原子判断写入”，写操作没有幂等就不许自动重试。
- 去重记录生命周期必须长于重试窗口，超出窗口只能走对账。

## 思考题

支付商只保留幂等键 24 小时，客服却可能在 48 小时后重试一张 `uncertain` 的退款单。请设计一套“不重复退款、也不靠人工逐单核对”的方案，说明每层存储保留多久、由谁判断。

参考思路：把“重试窗口”和“业务可重复窗口”分开。24 小时内由幂等键与去重表兜住；超出窗口先不要重发，而是按退款单号查询支付商侧最终状态，把“不确定”降级为“已确认成功/已确认不存在”；确实不存在的单用新版本键重发并记录版本链。日终对账兜住查询也失败的情况，人工只处理差异。

## 小测

1. 下列哪种失败不应重试？  
   A. 连接被拒绝　B. `503 Service Unavailable`　C. `400` 金额格式错误　D. 连接超时
2. 为什么指数退避需要加抖动？
3. 读超时与连接超时，哪一种更可能属于“结果未知”？为什么？
4. 幂等键应该由谁生成、以什么为粒度？同一个键换了金额时应该怎么处理？
5. 场景题：支付商返回 `429` 并带 `Retry-After: 30`，但这次退款总预算只剩 20 秒。重试计划怎么走？

## 答案与解析

1. **C。**`400` 是参数或业务校验失败，重试只会得到同样结果。A、B、D 都是暂时性失败：连接被拒绝可能来自重启，`503` 表示上游过载，超时说明报文没送到。
2. 客户端按同样的退避时间重试、失败时刻又接近，就会形成同步尖峰，把刚恢复的下游再次打垮。抖动把重试摊平到一段时间里；<u>没有抖动的退避只是把尖峰推迟。</u>
3. 读超时更可能。连接超时说明请求还没送达，对方大概率没执行；读超时说明请求已发出，对方可能已处理完但响应没回来，不能当失败处理——这正是它必须配幂等键的原因。
4. 由发起业务意图的一方生成，粒度是“一次业务意图”而非“一次 HTTP 请求”：晴空商城用业务单号派生 `refund-8871-v1`。同一个键换了金额说明键被复用，必须返回 `409`。
5. `Retry-After: 30` 超过剩余预算 20 秒，不能在当前调用里等。应把任务放回队列并延迟 30 秒，本次以“处理中”结束，重试仍用同一幂等键；既遵守对方节奏，也不空占连接。

### 动手实验参考

步骤 2 中 `atomic` 模式扣 1 次：`_lock` 把“判断有没有记录”和“写入 in_progress”合成一个临界区，第二个线程只能看到 `in_progress` 或 `done`。`naive` 模式扣 2 次：两个线程都读到空记录，又都在 `barrier` 之后写入，于是都认为自己是首次请求。步骤 3 把 TTL 设为 0 后原子模式也扣 2 次，说明幂等有效期由去重记录决定，而不是由代码里的锁决定。步骤 4 把单次超时抬到 6 秒后，一次尝试加退避就吃掉 6.2 秒，第二次尝试放不进 10 秒预算，计划只剩一次；步骤 5 放宽预算与上限后计划跑到 8 次，最坏约 85 秒，说明参数必须按对外承诺反推。

## 延伸阅读与下一课

- [RFC 9110：HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)——§9.2.2 定义幂等方法，说明哪些方法可以安全重复执行。
- [AWS Builders' Library：Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)——超时分层与抖动策略的工程实践。
- [Stripe API：Idempotent requests](https://docs.stripe.com/api/idempotent_requests)——幂等键的接口语义、重放与冲突处理。
- [Google SRE Book：Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)——重试如何放大故障，以及重试预算的思路。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[分页、过滤、批量与限流](04-pagination-filtering-and-rate-limits.md)。
- 下一课：[熔断、降级与隔离](06-circuit-breaking-degradation-and-isolation.md)。
