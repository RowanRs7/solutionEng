---
title: Outbox、补偿与最终一致性
slug: outbox-compensation-and-eventual-consistency
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - message-queues-pubsub-and-dlq
outcomes:
  - 说明双写为何必然不一致，并用同一事务内的 Outbox 写法规避
  - 写出中继的投递与标记顺序，并解释为何只能保证至少一次投递
  - 区分回滚、补偿与对账各自能解决和不能解决的问题，并说明不一致窗口的用户可见影响
last_reviewed: 2026-10-19
---

# Outbox、补偿与最终一致性

## 为什么需要学习

晴空商城的退款审核通过时，系统要同时做两件事：把订单状态改成“退款中”，通知支付商发起退款。开发最初写成“先改库、再调接口”，于是三种事故轮流上演。改库成功、调接口超时，买家永远等不到这笔退款；调接口成功、提交时数据库报错，钱退了出去却没有任何记录；消息发出去了，消费者重启后从处理到一半的地方重来，同一笔钱退两次。

这三件事的共同点不是“代码写错了”，而是**一次本地事务和一个外部副作用被当成了一个原子操作**。

> **核心结论：** 跨系统的“同时成功”不存在；可工程化的只有“先记下要做的事、再可靠地做、做错能补、补没补上靠对账证明”。

## 学习目标

完成本课后，你能够：

- 解释*双写*问题，并说明 Outbox 表为什么能让“业务状态”与“待发事件”同生共死。
- 写出中继的投递与标记顺序，说明它为何只能保证*至少一次*，以及消费者靠什么去重。
- 区分数据库回滚、*补偿*与*对账*各自能解决和不能解决的问题。
- 为一次跨系统退款画出状态机，并说出*不一致窗口*内页面该显示什么文案。
- 用本地脚本复现“投递后崩溃 → 重复投递 → 幂等消费 → 补偿 → 三态对账”的完整链路。

## 前置知识

- 回看上一课：[消息队列、发布订阅与死信队列](10-message-queues-pubsub-and-dlq.md)。
- 理解数据库事务的提交是一条不可撤销的界线：提交后再“撤销”只能靠新的写操作。
- 知道*至少一次投递*意味着消息可能重复，*幂等*指重复执行与执行一次结果相同。
- 能在本机运行 `python3`（3.8+）；本课示例只用 `sqlite3` 与 `json` 标准库。

## 业务场景

“晴空商城”的退款横跨四个系统：订单库保存退款单状态，支付网关负责真正打款，仓库 WMS 负责回补库存，客服平台负责给买家答复。一次退款审核通过会牵动四处改动，约束各不相同：

- 支付商的退款接口偶发超时（1–90 秒），超时后重试可能造成重复打款。
- 消息队列只承诺至少一次投递，消费者随时可能收到重复事件。
- 库存回补依赖 WMS 回执，接口失败只能排队重试或人工补录。
- 财务要求日终能逐笔解释差额，不能出现“账上有、系统里没有”的款项。
- 买家在 App 里刷新页面，看到的进度必须与真实进度一致，不能靠改文案“让它看起来快了”。

客服主管的原话是：“客人不怕等，怕的是我们说不清在等什么。”这句话把投递可靠性、补偿能力和对外表述绑成了同一个设计问题。

## 核心概念

*双写*（dual write）指一个业务动作分别写两个不共享事务的存储，例如先写订单库再发消息。两次写之间任一失败，系统就停在不一致状态，而且没有组件会主动发现它。

*Outbox 表*是与业务表同库的事件暂存表：业务变更和待发事件写进同一个本地事务，提交一起生效，回滚一起消失。<u>它不保证事件被送达，只保证“已提交的变更一定有一条待发事件”</u>——这是后续所有可靠性的前提。

*中继*（relay）负责把 Outbox 里的事件搬到消息队列，也叫发布者。*至少一次投递*意味着中继在“已发送、尚未标记”之间崩溃时，重启会重发同一条事件，所以消费侧必须*幂等*：以 `event_id` 做唯一约束，重复事件被主键挡住。

*补偿*（compensation）不是回滚，而是为已生效的步骤追加一个语义相反的**新动作**：退款失败就记一笔冲正，库存发不出去就下取消指令。补偿自身也要幂等、可重试、可人工接管。*对账*（reconciliation）把本地记录与对方结算数据定期比对，差异分成“只有本地”“只有对方”“金额不符”三类并逐项闭环。

*最终一致性*指系统在没有新写入的前提下，经过有限时间会收敛到一致状态；中间这段时间叫*不一致窗口*，它的长度就是用户要等的时长。*用户可见一致性*要求界面状态落在这个窗口之内：可以显示“退款处理中”，但不能在钱没到账时显示“已退款”。

| 手段 | 作用对象 | 能保证 | 不能保证 | 典型用法 |
| --- | --- | --- | --- | --- |
| 数据库回滚 | 单个本地事务 | 未提交的改动全部消失 | 已提交的改动、已发出的外部请求 | 审核不通过，整笔退款不落库 |
| 补偿 | 已提交的业务效果 | 用反向动作抵消影响 | 抵消一定成功、一定及时 | 支付商拒付后冲正本地账 |
| 对账 | 两个系统的事实记录 | 差异被找到并闭环 | 差异自动消失 | 日终比对退款单与结算文件 |

## 工作原理

一笔退款从审核到可对账，按时间顺序经过这些环节：

1. **同事务落库**：在一个事务里更新退款单状态、写订单流水、插入一条 `status='pending'` 的 Outbox 行。三者同生共死，不存在“状态改了但事件没记”。
2. **提交即事实**：提交后系统承诺的不再是“我要退款”，而是“这笔退款已受理且有一条待发事件”。此时外部世界还什么都不知道。
3. **中继取件**：中继按 `seq` 升序读取待发事件，多实例用 `FOR UPDATE SKIP LOCKED` 或单实例选举避免重复取件，读到的行仍留在表里。
4. **先投递、后标记**：把事件发给消息队列，收到 broker 确认后才把该行标记为 `sent`。<u>顺序反过来（先标记后发送）会在崩溃时永久丢事件</u>，而先发后标记最坏只是重复。这就是“至少一次”的来源。
5. **消费去重**：消费者在同一事务里先向去重表插入 `event_id`，主键冲突即处理过，直接跳过；插入成功才执行副作用。副作用与投递次数因此解耦。
6. **失败分流**：可重试错误（超时、5xx、限流）按退避重试；重试到上限或收到永久拒绝（参数非法、余额不足、账户冻结）时进入死信或补偿队列，等待人工或自动补偿。
7. **执行补偿**：对已生效的步骤发起反向动作，例如把本地退款单置为 `compensated` 并发布 `refund.compensated` 事件通知客服与仓库。补偿动作本身也走 Outbox，否则补偿消息同样会丢。
8. **日终对账**：拉取支付商结算文件与 WMS 回执，与本地退款单比对，差异生成工单并限期关闭。**对账是唯一能发现“事件丢了但我们不知道”的手段**，因为队列不会告诉你少了一条消息。
9. **对外表述**：状态机保留 `refunding` 与 `refunded` 两个状态，页面按真实状态渲染文案与预计时间；<u>绝不允许用前端“优化显示”把中间态藏起来</u>，那只会把技术不一致变成信任事故。

## 架构与选型

| 方案 | 一致性来源 | 实现成本 | 投递延迟 | 适用场景 | 不适用场景 |
| --- | --- | --- | --- | --- | --- |
| 直接双写（先写库再发消息） | 无 | 最低 | 毫秒 | 可接受丢失的通知、演示代码 | 涉及资金、库存、凭证 |
| Outbox 轮询中继 | 本地事务 + 重试 | 中，多一张表与一个进程 | 秒级（轮询间隔） | 大多数业务系统，改造量最小 | 极高吞吐、强顺序 |
| CDC 读日志（如 Debezium 订阅 WAL） | 本地事务 + 日志位点 | 中高，需运维连接器 | 亚秒到秒级 | 已有成熟 CDC 平台、不想改应用代码 | 团队无日志采集运维能力 |
| 事务消息（半消息 + 回查） | broker 参与两阶段 | 高，绑定具体中间件 | 毫秒到秒级 | 已统一使用支持事务消息的 MQ | 多消息中间件并存、跨云 |
| 分布式事务（2PC/XA） | 协调者两阶段提交 | 最高，跨库锁与可用性代价大 | 毫秒但吞吐受限 | 同厂商数据库、短事务、强一致必需 | 跨组织、跨云、长事务 |

选型按顺序问四个问题：副作用丢了会不会造成资金或库存损失？会，就必须有 Outbox 或事务消息，且必须有对账；团队有没有 CDC 运维能力？没有就先上轮询中继；延迟要求秒级还是亚秒级？秒级以内轮询足够；能否接受补偿而非回滚？不能，说明业务流程本身要重设计。

补偿设计有三条硬规则：**补偿必须是独立可调用的接口**，不能内联在原流程里；**补偿要有额度上限与审批**，防止一次重放把一万笔退款全冲正；**补偿要有终态**，超时未完成必须转人工，不能无限重试。

## 最小示例

问题：用一段只用标准库的脚本，把“同事务写 Outbox、投递后崩溃、重复投递、幂等消费、补偿、三态对账”各演示一次。环境为 Python 3.8+，数据库用内存 SQLite，不连任何真实中间件。

```python
"""Outbox 最小闭环：同事务写事件、至少一次投递、幂等消费、补偿与对账。只用标准库。"""
import json
import sqlite3


def setup():
    """四张表分别是：业务表、Outbox、消费去重表、支付商调用记录。"""
    db = sqlite3.connect(":memory:")  # 内存库，脚本结束即消失，不污染本机
    db.executescript(
        """
        CREATE TABLE orders (id TEXT PRIMARY KEY, amount INTEGER, status TEXT NOT NULL);
        CREATE TABLE outbox (
            seq      INTEGER PRIMARY KEY AUTOINCREMENT,  -- 单调递增，决定发布顺序
            event_id TEXT UNIQUE NOT NULL,               -- 消费者去重用的稳定标识
            topic    TEXT NOT NULL,
            payload  TEXT NOT NULL,
            status   TEXT NOT NULL DEFAULT 'pending'     -- pending -> sent，标记即水位
        );
        CREATE TABLE consumed (event_id TEXT PRIMARY KEY);  -- 幂等表：重复投递被主键挡住
        CREATE TABLE refunds (refund_id TEXT PRIMARY KEY, amount INTEGER, state TEXT NOT NULL);
        CREATE TABLE provider_calls (refund_id TEXT PRIMARY KEY, amount INTEGER);
        """
    )
    return db


def approve_refund(db, order_id, refund_id, amount):
    """一个本地事务同时改状态与写事件，这就是 Outbox 的全部秘密。"""
    event = {"event_id": f"evt-{refund_id}", "refund_id": refund_id, "amount": amount}
    with db:  # with 块正常结束即提交；抛异常则整体回滚，不存在半截状态
        db.execute("UPDATE orders SET status = 'refunding' WHERE id = ?", (order_id,))
        db.execute("INSERT INTO refunds VALUES (?, ?, 'approved')", (refund_id, amount))
        db.execute(
            "INSERT INTO outbox(event_id, topic, payload) VALUES (?, ?, ?)",
            (event["event_id"], "refund.approved", json.dumps(event)),
        )


def relay(db, broker, crash_after_publish=False):
    """中继：先投递、拿到确认后标记；崩溃点落在两者之间就会重复投递。"""
    pending = db.execute(
        "SELECT seq, event_id, topic, payload FROM outbox WHERE status = 'pending' ORDER BY seq"
    ).fetchall()
    for seq, _event_id, topic, payload in pending:
        broker.append((topic, payload))  # 1. 投递；这里用一个列表代替消息队列
        if crash_after_publish:
            return seq  # 2. 模拟投递后进程崩溃：消息已发出，标记没写
        db.execute("UPDATE outbox SET status = 'sent' WHERE seq = ?", (seq,))
        db.commit()  # 3. 标记与投递是两次写，所以整体语义只能是“至少一次”
    return None


def consume(db, broker):
    """消费者：先去重表抢插，再执行副作用，重复消息不会二次生效。"""
    applied = 0
    for topic, payload in broker:
        body = json.loads(payload)
        try:
            with db:  # 去重记录与副作用同事务，避免“记了但没做”
                db.execute("INSERT INTO consumed(event_id) VALUES (?)", (body["event_id"],))
                if topic == "refund.approved":
                    db.execute(
                        "INSERT INTO provider_calls VALUES (?, ?)",
                        (body["refund_id"], body["amount"]),
                    )
                    db.execute(
                        "UPDATE refunds SET state = 'requested' WHERE refund_id = ?",
                        (body["refund_id"],),
                    )
            applied += 1
        except sqlite3.IntegrityError:
            continue  # 主键冲突 = 这条事件处理过，跳过而不是报错
    return applied


def compensate(db, refund_id, reason):
    """补偿是新的正向动作：冲正本地状态并发布事件，而不是删掉历史。"""
    event = {"event_id": f"evt-comp-{refund_id}", "refund_id": refund_id, "reason": reason}
    with db:
        db.execute("UPDATE refunds SET state = 'compensated' WHERE refund_id = ?", (refund_id,))
        db.execute(  # 补偿事件也走 Outbox，否则补偿消息同样会丢
            "INSERT INTO outbox(event_id, topic, payload) VALUES (?, ?, ?)",
            (event["event_id"], "refund.compensated", json.dumps(event)),
        )


def reconcile(db, settlement):
    """三态对账：只有本地、只有对方、金额不符；一致的不进工单。"""
    local = dict(db.execute("SELECT refund_id, amount FROM refunds"))
    only_local = sorted(set(local) - set(settlement))  # 我方认为发起过，对方没收到
    only_remote = sorted(set(settlement) - set(local))  # 对方打过款，我方无记录
    mismatch = sorted(k for k in set(local) & set(settlement) if local[k] != settlement[k])
    return only_local, only_remote, mismatch


def main():
    db = setup()
    db.execute("INSERT INTO orders VALUES ('SO-1001', 12800, 'paid')")
    db.commit()

    approve_refund(db, "SO-1001", "RF-1001", 12800)
    pending = db.execute("SELECT COUNT(*) FROM outbox WHERE status = 'pending'").fetchone()[0]
    print(f"1) 提交后待发={pending} 条，订单已改状态，外部一个字节都没发出")

    broker = []
    crash_point = relay(db, broker, crash_after_publish=True)  # 投递成功、标记失败
    relay(db, broker)  # 中继重启：同一条事件被再投一次
    sent, unsent = db.execute(
        "SELECT SUM(status = 'sent'), SUM(status = 'pending') FROM outbox"
    ).fetchone()
    print(f"2) 崩溃于 seq={crash_point}，投递={len(broker)} 次，已标记={sent} 未标记={unsent}")

    first = consume(db, broker)  # 正常消费
    again = consume(db, broker)  # broker 重投
    calls = db.execute("SELECT COUNT(*) FROM provider_calls").fetchone()[0]
    print(f"3) 首次生效={first} 重投生效={again}，支付商被调用={calls} 次")

    compensate(db, "RF-1001", "provider_rejected")  # 支付商永久拒绝
    relay(db, broker)
    consume(db, broker)
    state = db.execute("SELECT state FROM refunds WHERE refund_id = 'RF-1001'").fetchone()[0]
    print(f"4) 补偿后状态={state}，最后一条事件={broker[-1][0]}")

    db.executemany(  # 另外两笔来自其他渠道，用于演示对账差异
        "INSERT INTO refunds VALUES (?, ?, 'requested')", [("RF-1002", 11800), ("RF-1003", 5000)]
    )
    db.commit()
    settlement = {"RF-1002": 11800, "RF-1003": 3000, "RF-1004": 9900}
    only_local, only_remote, mismatch = reconcile(db, settlement)
    print(f"5) 对账：只有本地={only_local} 只有对方={only_remote} 金额不符={mismatch}")


main()
```

把代码保存为 `outbox_demo.py`，运行 `python3 outbox_demo.py`，预期输出：

```text
1) 提交后待发=1 条，订单已改状态，外部一个字节都没发出
2) 崩溃于 seq=1，投递=2 次，已标记=1 未标记=0
3) 首次生效=1 重投生效=0，支付商被调用=1 次
4) 补偿后状态=compensated，最后一条事件=refund.compensated
5) 对账：只有本地=['RF-1001'] 只有对方=['RF-1004'] 金额不符=['RF-1003']
```

五段输出各验证一个承诺。第 1 段说明状态与事件在同一事务落库，此时对外不可见；第 2 段是核心：崩溃点让同一条事件投递两次，Outbox 只标记一次，这正是“至少一次”；第 3 段证明幂等表挡住第二次副作用；第 4 段说明补偿是新增状态与新增事件，历史行没被删除；第 5 段里 `RF-1001` 出现在“只有本地”是合理的——它已被补偿，但仍需在对账里被人工关闭一次，<u>这正说明补偿不能替代对账</u>。

## 动手实验

### 前置条件

本机有 `python3`（3.8+）与可写目录；不需要消息队列、支付账号或网络。实验只使用内存数据库，不产生外部连接。

### 步骤

1. 把示例代码保存为 `outbox_demo.py`，运行一次，逐行核对输出与“预期输出”。
2. 把第 2 段的 `crash_after_publish=True` 改为 `False`，再运行，观察投递次数与“已标记”数值的变化。
3. 删除 `consume` 里的 `consumed` 插入语句（保留其余逻辑），重跑，观察支付商调用次数。
4. 把 `compensate` 中的 `UPDATE refunds` 删掉，只留 Outbox 插入，观察第 4 段输出是否还能反映终态。
5. 把 `settlement` 里的 `RF-1002` 金额由 `11800` 改为 `12000`，观察对账结果是“金额不符”还是“只有对方”。

### 预期结果

步骤 1 得到上文五段输出。步骤 2 崩溃消失，`投递=1`、`已标记=1`，说明无崩溃时不会重复；步骤 3 支付商被调用 2 次，说明缺幂等表的代价是副作用翻倍；步骤 4 状态停在 `requested`，本地账已冲正而页面说“进行中”，出现“状态与事实分叉”；步骤 5 `RF-1002` 落入金额不符，说明三态分类依赖金额比较而非 ID 存在性。

### 验证方法

把关键行为写成断言：`assert calls == 1`、`assert only_local == ['RF-1001']`、`assert state == 'compensated'`。可再补一条“崩溃前后 Outbox 行数不变”，用 `python3 -c` 或 `unittest` 跑通，说明幂等与顺序两个性质都在生效。

### 清理方法

删除 `outbox_demo.py` 与 `__pycache__`。数据库是 `:memory:`，进程退出即释放，不留数据文件；若改成了磁盘路径，确认是本机临时目录后再删除。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 订单显示“退款中”，支付商从未收到请求 | 双写：改库成功、发消息失败且无人重试 | 查 Outbox 是否有对应行、中继日志是否有该 `seq` | 改为同事务写 Outbox，并加中继与积压告警 |
| 同一笔退款被支付商扣了两次 | 至少一次投递 + 消费端无幂等 | 按 `event_id` 与业务主键查重复调用记录 | 去重表加唯一约束，副作用与去重同事务 |
| 事件表持续增长、查询越来越慢 | 只发不清理，或缺归档策略 | 统计 `sent` 行数与最老时间戳 | 按时间分区归档 `sent` 行，保留期满足审计 |
| 事件顺序错乱，先收到“已完成”再收到“已受理” | 多分区并发消费、中继乱序取件 | 对比同一业务聚合的 `seq` 与消费顺序 | 按业务主键分区，或消费端按版本号丢弃旧状态 |
| 对账差异长期挂账、无人关闭 | 无差异工单与关闭时限 | 查对账差异表的创建时间与状态分布 | 差异自动建单、超时升级、月度差异率纳入指标 |
| 补偿跑了两遍，用户收到两笔冲正 | 补偿接口无幂等键、无额度上限 | 查补偿请求是否带唯一键与审批号 | 补偿独立幂等键 + 单笔上限 + 双人复核 |

## 安全与生产注意事项

**<u>把卡号、身份证号、完整地址直接写进 Outbox 的 payload，等于把这些数据在业务库、消息队列、消费者日志和各环境副本里各留一份。</u>** 事件一旦进入队列往往保留数天到数周，且会被多个下游重复消费与落盘，事后既无法撤回也难以清点扩散范围。缓解：payload 只放业务 ID 与必要金额，敏感字段由消费者按权限回查；必须携带时先加密并限制可解密主体；同时给 Outbox 与队列设置保留期和清理任务。

**<u>补偿接口若复用普通退款接口且不设额度上限，一次重放或一次误操作就能批量冲正真实资金。</u>** 补偿天然具备“反向大量写”的能力，比正向接口更危险。缓解：补偿作为独立资源单独授权，强制幂等键与审批单号，设置单笔与单日上限，超过阈值转双人复核，并把每次补偿的请求人、原因与影响笔数写入审计日志。

**<u>中继进程被授予整库写权限，或消费者可以删除 Outbox 行，一次越权就能静默抹掉未发出的资金事件。</u>** 缓解：中继与消费者使用最小权限账号，只允许更新 `status` 字段；Outbox 表禁止物理删除，只能归档；对 `pending` 行数设置单调性告警，积压突增或长期不降即触发值班。

另外两条常规控制：`event_id` 与幂等键要能追溯到发起人，便于事后审计；生产环境必须为“Outbox 积压时长”“对账差异未关闭数”“补偿执行次数”配仪表盘与告警，否则上面所有机制都只是文档里的承诺。

## 本课总结

- **双写必然不一致**，Outbox 用“同一本地事务”把业务状态与待发事件绑在一起，这是可靠性的起点。
- 中继**先投递、后标记**，因此只能保证至少一次；重复由消费者的幂等表吸收，顺序由业务键分区或版本号保证。
- **补偿是新的正向动作，不是回滚**；它需要独立幂等键、额度上限、终态和人工接管路径。
- **对账是唯一能发现“悄悄丢了一条事件”的手段**，差异必须分类、建单、限期关闭。
- 最终一致性对用户意味着**一段可解释、可度量的等待**；状态机与文案必须忠于真实状态，而不是修饰它。

## 思考题

退款单要求“24 小时内必有结论”，支付商一天只提供一次结算文件，而你们的重试窗口只有 2 小时。请设计这套系统的收敛方案：状态如何划分、哪些动作自动、哪些必须人工、如何度量“12 小时内完成的退款占比”，以及在支付商整段不可用时业务是否暂停。写出你的取舍理由。

参考思路：把“结论”拆成“受理、处理中、已退款、已补偿、待人工”五个状态，先保证 24 小时内必有终态，而不是必成功；2 小时窗口结束后进入补偿或人工队列，结算文件到达后再校正终态。指标要写清起算点（审核通过时间）、分母（已受理笔数）与是否含人工处理。支付商不可用时通常暂停自动重试但不暂停受理，降级比例计入事故记录；若资金风险不可接受，由业务所有者决定暂停受理，而不是开发默认选择。

## 小测

1. 判断：只要把“写库”和“发消息”放在同一段代码里并用 `try/except` 包起来，就可以避免双写不一致。
2. Outbox 中继在“已投递、未标记”时崩溃，重启后的正确行为是？  
   A. 跳过该行继续发后面的　B. 重新投递该行，消费者去重　C. 删除该行避免重复　D. 停止中继等待人工确认
3. 支付商返回“账户已冻结”，正确处置是？  
   A. 按指数退避无限重试　B. 进入补偿或人工队列，落终态　C. 改成同步重试十次　D. 忽略该响应继续下一笔
4. 对账发现“只有对方有、我方无记录”，最可能的原因是？  
   A. 我方重复退款　B. 我方事件或记录丢失，对方已实际打款　C. 金额算错　D. 队列积压
5. 补偿与回滚最本质的区别是？  
   A. 补偿更快　B. 补偿不需要事务　C. 补偿是用新的正向动作抵消已提交的效果　D. 补偿只用于数据库
6. 场景题：上线两周后财务发现，某天有 37 笔退款在本地是 `requested`，支付商结算文件里也没有。中继日志显示当天有一次发布超时重试，Outbox 该时段 `pending` 行数为 0。请指出至少三个可能环节，并说明先查哪一个。

## 答案与解析

1. **错。** `try/except` 只能接住本进程内的异常，接不住“消息已发出但标记失败”“进程被 kill”“网络超时但对方已处理”。问题出在两个存储不共享事务边界，不在错误处理写得好不好。
2. **B。** 先投递后标记的语义就是允许重复，重投是设计内的行为，去重由消费者主键约束完成。A 会永久丢掉这条事件；C 破坏可追溯性且可能在消息未真正入队时丢事件；D 把可用性交给人工，与至少一次的本意相反。
3. **B。** “账户已冻结”是永久失败，重试只会放大告警与成本，必须落终态并转人工或补偿。A 与 C 都在做无意义重试；D 会让这笔退款永远停在中间态。
4. **B。** 对方有记录说明钱真的动了，我方没有说明本地写失败、事件丢失或写入了错误库。A 与现象方向相反；C 会让它落入“金额不符”；D 只影响时效，不产生单边记录。
5. **C。** 回滚作用于未提交的本地事务，补偿作用于已提交的事实，只能追加反向动作。A 与本质无关；B 恰恰相反，补偿通常需要自己的事务与幂等键；D 缩小了范围，补偿也作用于库存、额度等外部效果。
6. 参考：可能环节至少三个——中继在“投递成功、标记失败”后**真的把消息投丢了**（broker 未持久化或主题配置错误），于是 `pending` 为 0 却无任何消费记录；消费者**去重表误判**（`event_id` 生成不唯一或复用了上一批值），副作用被跳过却记了已消费；支付商**实际收到并执行**，但当天结算文件未包含这笔，双方都无终态。先查第一个：比对中继日志的 `seq`、broker 侧该主题当天消息数、去重表三处计数。日志有 `seq` 而 broker 无消息，问题在投递；broker 有而消费者无，问题在消费侧。`pending` 为 0 只说明“中继认为发完了”，恰恰是最该怀疑的证据。

### 动手实验参考

步骤 2 取消崩溃后 `投递=1`、`已标记=1`，说明重复来自崩溃点而非设计缺陷；步骤 3 支付商被调用 2 次，说明幂等表不是“优化”而是资金防线；步骤 4 中状态停留在 `requested`，而本地账已冲正，说明补偿必须同时更新状态与发布事件，缺一项就会出现“账平了但页面没变”；步骤 5 中 `RF-1002` 落入金额不符，说明对账不能只比对 ID 集合。

## 延伸阅读与下一课

- microservices.io 的 Transactional Outbox 模式，含轮询与日志抽取两种实现对比：<https://microservices.io/patterns/data/transactional-outbox.html>。
- microservices.io 的 Saga 模式，补偿事务与协调方式的原始描述：<https://microservices.io/patterns/data/saga.html>。
- PostgreSQL 文档中 `SELECT` 的 `FOR UPDATE SKIP LOCKED`，多实例中继取件的依据：<https://www.postgresql.org/docs/current/sql-select.html>。
- Python 标准库 [sqlite3](https://docs.python.org/3/library/sqlite3.html) 的事务与 `with` 连接行为说明，用于解释示例中的提交边界。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[消息队列、发布订阅与死信队列](10-message-queues-pubsub-and-dlq.md)。
- 下一课：[ETL、ELT、CDC 与数据同步](12-etl-elt-cdc-and-data-sync.md)。
