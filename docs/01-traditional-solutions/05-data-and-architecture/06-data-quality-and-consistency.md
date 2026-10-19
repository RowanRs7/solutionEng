---
title: 数据质量、校验与一致性
slug: data-quality-and-consistency
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 50m
prerequisites:
  - time-money-uuid-and-encoding
outcomes:
  - 解释数据质量的五个维度，并指出指定字段最可能失效的维度与检测手段
  - 区分应用层校验、数据库约束、异步稽核与对账各自能拦住什么、拦不住什么
  - 写出可并发的去重方案（判定键加唯一约束），并为一次退款划出一致性边界与修复动作
last_reviewed: 2026-10-19
---

# 数据质量、校验与一致性

## 为什么需要学习

晴空商城的退款月报连续三个月对不上：客服系统记录 1,284 笔，支付商结算文件只有 1,262 笔。查下去，三类问题同时发生：同一笔退款因超时被提交两次；金额在小程序、订单库、支付网关各存一个版本（元、分、带小数的字符串各一）；还有 22 笔只在本地，钱从未打出去。

第一反应是“写个脚本刷一下”，但刷数据只是把今天的不一致搬到明天：**没有入口校验，脏数据会持续产生；没有对账，已流出去的差异永远不会被发现。**

> **核心结论：** 数据质量不是上线前的一次清洗，而是三道持续的防线：入口校验拦住新错误，存储约束让绕过入口的写入同样失败，对账把流出系统的差异找回来。

## 学习目标

完成本课后，你能够：

- 解释数据质量的五个维度，并为给定字段指出最容易失效的维度和检测手段。
- 区分*应用层校验*、*数据库约束*、*异步稽核*与*对账*各能拦住什么、拦不住什么。
- 写出可并发的*去重*方案，说明“先查后插”为何在并发下必然漏。
- 为一次退款划分*一致性边界*：哪些步骤必须同事务、哪些只能最终一致。
- 用 `python3` 复现“脏数据被拒 → 判重 → 对账出差异 → 进修复队列”的链路。

## 前置知识

- 回看上一课：[时间、金额、UUID 与编码陷阱](05-time-money-uuid-and-encoding.md)。
- 知道 SQL 唯一约束会在插入时拒绝重复值，且整条语句失败而非静默跳过。
- 理解*幂等*：同一请求重复执行与执行一次的效果相同。
- 能运行 `python3`（3.8+）；示例只用 `sqlite3`、`hashlib` 与 `re` 标准库。

## 业务场景

“晴空商城”的订单与退款数据从五处汇入：小程序、订单库、支付回调、仓库 WMS 和客服工单，每个来源都在用自己的方式描述同一件事：

- 买家弱网下连点两次提交，重试生成了新订单号，两笔都进了库。
- 同一手机号有 `+86 138-0000-0001`、`8613800000001`、`138 0000 0001` 三种写法，客服搜不到人。
- 支付回调是渠道实收（已扣优惠券），订单里是应付金额，天然差几百元。
- 采购导入的商品表用 Excel 维护，SKU 混着大小写和全角空格。
- 财务要求日终把退款单与结算文件逐笔对上，每笔差异都要有人关闭。

约束同时存在：退款超过 500 元要人工审核；支付商 T+1 才给结算文件；客服页面必须显示真实状态。**数据错了却“看起来正常”，比页面报错更难处理**，因为没人会修不报警的系统。

## 核心概念

*数据质量*是数据满足使用目的的程度，拆成五个可检查维度：*完整性*（不缺值）、*唯一性*（不重复）、*有效性*（不越界）、*一致性*（跨系统同义）、*及时性*（按时可用）。

*校验*发生在应用进程内，按规则拒绝数据；*约束*由存储层守护，即使有人绕过应用直接写库也会失败，这是二者最本质的差别。*规范化*指把同一事实的不同写法收敛成唯一表示（手机号统一 11 位、金额统一为整数分），与数据库范式无关。*去重*是识别指向同一实体的多条记录并保留一条，依据叫*判定键*，其哈希值叫*指纹*。*对账*是定期比对两个独立持有的事实，差异分“只有我方”“只有对方”“值不符”。*一致性边界*是可被一次成败判定覆盖的最大范围：内可强一致，外只能最终一致加对账兜底。

| 防线 | 作用时机 | 能拦住 | 拦不住 |
| --- | --- | --- | --- |
| 应用层校验 | 请求进入时 | 格式错误、必填缺失 | 绕过接口的写库、并发重复 |
| 存储约束 | 语句提交时 | 重复、空值、负金额、悬空引用 | 金额合法但业务上不该收 |
| 异步稽核 | 分钟到小时级 | 跨表、跨系统的规则违反 | 已发生的资金损失 |
| 对账 | 准实时或日终 | 双方记录不一致 | 双方错成同一份数据 |

## 工作原理

数据从产生到可以放心出报表，按数据流经过八个环节：

1. **接收与规范化**：手机号去空格与 `86` 前缀，金额转整数分，时间转 UTC 并保留原时区偏移。
2. **入口校验**：在规范化之后判定规则。<u>顺序反过来会误杀合法输入</u>：`+86 138-0000-0001` 匹配不了 11 位规则，而它是对的。
3. **写入约束**：把“不能重复、不能为空、不能为负”写进 schema，让批处理、运维 SQL、新服务守同一套规则。
4. **判定键去重**：订单与退款没有天然唯一键，用业务指纹（买家标识 + 金额 + 时间窗）建唯一索引。
5. **对外传输**：字段与类型由契约固定，消费方遇到未知字段或类型变化应显式失败。
6. **异步稽核**：按分钟或小时跑规则——已付订单必须有支付记录、退款必须能关联原单、库存不得为负。
7. **对账**：与外部权威事实（结算文件、WMS 回执）逐笔比对，产出三类差异；前提是承认“对方更接近真相”。
8. **差异修复**：每条差异落到有归属的动作——补写、冲正、作废或转人工，并记录责任人与关闭时间。<u>只出报表不建单，等于没做过对账</u>。

一致性边界要在设计阶段切清楚：下单与扣减库存同事务（超卖不可逆）；订单落库与发事件走 Outbox；退款与打款只能最终一致，对账是唯一兜底。

## 架构与选型

| 方案 | 一致性强度 | 成本 | 生效延迟 | 适用 | 不适用 |
| --- | --- | --- | --- | --- | --- |
| 应用层校验 | 直到下次写入 | 低 | 立即 | 所有外部输入 | 内部批处理、历史导入 |
| 数据库约束 | 语句级 | 低，需迁移 | 立即 | 唯一性、金额范围、引用完整 | 跨库不变量 |
| 契约校验 | 接口级 | 中 | 立即 | 多团队多语言 | 无 schema 的遗留系统 |
| 流式去重 | 秒级 | 中高 | 秒级 | 高频事件、重复投递常态化 | 数据量小、可离线重算 |
| 批处理稽核 | 小时到天级 | 低 | 小时级 | 跨表规则、历史体检 | 要求当场阻断 |
| 准实时对账 | 分钟级 | 高，需 CDC | 分钟级 | 资金、库存等不可逆副作用 | 对方只给日终文件 |

选型问四个问题：后果可逆吗？涉及资金、库存、发票时不可逆，就必须有对账。数据源受控吗？第三方只能对账。判定键稳定吗？含自增 ID 或随机数的等于没有去重。差异能容忍多久？分钟级上流式，天级用批处理。

修复分三种：补写缺失记录、冲正已生效的资金效果、作废误建实体。**任何修复都必须新增记录，禁止用 UPDATE 覆盖原始值**，否则审计时无法证明原值。

## 最小示例

问题：用一段只用标准库的脚本，把规范化、校验、唯一约束、指纹去重、三态对账与修复分流各演示一次。环境为 Python 3.8+，内存 SQLite；输入是四条模拟下单记录与三笔结算记录。

```python
"""数据质量最小闭环：规范化、校验、约束、指纹去重与三态对账。只用标准库。"""
import hashlib
import re
import sqlite3

PHONE = re.compile(r"^1[3-9]\d{9}$")  # 只挡明显错误，不追求覆盖全部运营商号段


def normalize_phone(raw):
    """把 +86 138-0000-0001 / 8613800000001 / 138 0000 0001 统一成 13800000001。"""
    digits = re.sub(r"\D", "", raw)  # 丢掉空格、加号、横线等一切非数字
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]  # 剥掉国际前缀，避免同一号码两种存法
    return digits


def validate(raw):
    """返回 (规范化后的行, 错误列表)；应用层校验负责说明人可读的原因。"""
    row = dict(raw)
    row["phone"] = normalize_phone(raw["phone"])  # 先规范化再判断，否则规则会被格式绕过
    errors = []
    try:
        row["amount_cents"] = int(str(raw["amount_cents"]).strip())  # 金额统一为整数分
    except ValueError:
        row["amount_cents"] = -1  # 解析失败置为非法值，交给同一套规则处理
        errors.append(("amount_cents", "amount_not_integer"))
    if not PHONE.match(row["phone"]):
        errors.append(("phone", "phone_invalid"))
    return row, errors


def setup():
    """三张表分别代表主数据、业务单据和对方给的结算文件。"""
    db = sqlite3.connect(":memory:")  # 内存库，脚本结束即消失，不污染本机
    db.executescript(
        """
        CREATE TABLE customers (
            id    TEXT PRIMARY KEY,
            phone TEXT NOT NULL UNIQUE,       -- 自然键唯一：同一号码不许建两个账号
            name  TEXT NOT NULL
        );
        CREATE TABLE orders (
            id           TEXT PRIMARY KEY,
            buyer_phone  TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),  -- 兜住绕过应用的写入
            created_at   TEXT NOT NULL,
            state        TEXT NOT NULL DEFAULT 'paid'
        );
        CREATE TABLE payments (
            payment_id   TEXT PRIMARY KEY,
            order_id     TEXT NOT NULL UNIQUE,  -- 一笔订单最多一条结算记录
            amount_cents INTEGER NOT NULL
        );
        """
    )
    return db


def order_fingerprint(order):
    """业务指纹：同一买家、同一金额、同一分钟内提交，视为同一笔下单。"""
    minute = order["created_at"][:16]  # 截到分钟，容忍客户端重试带来的秒级抖动
    key = f'{order["phone"]}|{order["amount_cents"]}|{minute}'
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]  # 定长、可索引、不泄露原文


def reconcile(db):
    """三态对账：集合差与金额比较，各自对应不同的业务含义。"""
    local = dict(db.execute("SELECT id, amount_cents FROM orders WHERE state = 'paid'"))
    remote = dict(db.execute("SELECT order_id, amount_cents FROM payments"))
    only_local = sorted(set(local) - set(remote))   # 我方认为已付，对方没有记录
    only_remote = sorted(set(remote) - set(local))  # 对方收到钱，我方没有订单
    mismatch = sorted(k for k in set(local) & set(remote) if local[k] != remote[k])
    return local, remote, only_local, only_remote, mismatch


def repair_queue(local, remote, only_local, only_remote, mismatch):
    """差异必须落到有归属的动作上，否则对账只是生成了一份报表。"""
    queue = []
    for order_id in only_local:
        queue.append((order_id, "manual", "查支付网关流水，禁止直接补记收款"))
    for order_id in only_remote:
        queue.append((order_id, "manual", "核对商户号与测试单，疑似串号"))
    for order_id in mismatch:
        diff = local[order_id] - remote[order_id]
        queue.append((order_id, "auto_adjust", f"差额 {diff} 分，生成冲正单交财务复核"))
    return queue


def main():
    db = setup()
    raw_rows = [  # 四条输入覆盖三种真实坑：格式不一、非法号码、超时重试重复
        {"order_id": "SO-1001", "phone": "+86 138-0000-0001", "amount_cents": "12800", "created_at": "2026-10-19T10:00:00"},
        {"order_id": "SO-1002", "phone": "13800000002", "amount_cents": 5000, "created_at": "2026-10-19T10:05:00"},
        {"order_id": "SO-1003", "phone": "23800000003", "amount_cents": 9900, "created_at": "2026-10-19T10:06:00"},
        {"order_id": "SO-1009", "phone": "138 0000 0001", "amount_cents": 12800, "created_at": "2026-10-19T10:00:05"},
    ]

    accepted, rejected = [], []
    for raw in raw_rows:
        row, errors = validate(raw)
        if errors:
            rejected.append((raw["order_id"], errors))
        else:
            accepted.append(row)
    print(f"1) 规范化+校验：入参 {len(raw_rows)} 条 → 通过 {len(accepted)} 条，拒绝 {rejected}")

    phone = accepted[0]["phone"]
    # 两个请求各自先查后插：查的时候都查不到，裁决只能发生在插入那一刻
    checked = [db.execute("SELECT 1 FROM customers WHERE phone = ?", (phone,)).fetchone() for _ in range(2)]
    outcomes = []
    for index in range(2):
        try:
            db.execute("INSERT INTO customers VALUES (?, ?, '张三')", (f"C-{index}", phone))
            outcomes.append("inserted")
        except sqlite3.IntegrityError:
            outcomes.append("blocked")
    print(f"2) 先查后插：两次查询 {checked}，两次插入 {outcomes}；唯一约束才是裁判")

    seen, unique, duplicates = {}, [], []
    for row in accepted:
        fingerprint = order_fingerprint(row)
        if fingerprint in seen:
            duplicates.append((row["order_id"], seen[fingerprint]))
        else:
            seen[fingerprint] = row["order_id"]
            unique.append(row)
    print(f"3) 指纹去重：{len(accepted)} 笔合规输入 → {len(unique)} 笔唯一，判重 {duplicates}")

    for row in unique:
        db.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, 'paid')",
            (row["order_id"], row["phone"], row["amount_cents"], row["created_at"]),
        )
    db.execute("INSERT INTO orders VALUES ('SO-1004', ?, 3000, '2026-10-19T09:00:00', 'paid')", (phone,))
    db.executemany(
        "INSERT INTO payments VALUES (?, ?, ?)",
        [
            ("P-1001", "SO-1001", 12800),
            ("P-1002", "SO-1002", 4500),  # 渠道优惠券少收 500 分，与本地金额不符
            ("P-9005", "SO-1005", 7700),  # 我方无此订单，疑似商户号串号
        ],
    )
    db.commit()

    local, remote, only_local, only_remote, mismatch = reconcile(db)
    print(f"4) 对账：本地 {len(local)} 笔 / 支付方 {len(remote)} 笔 → 只有我方={only_local} 只有支付方={only_remote} 金额不符={mismatch}")

    queue = repair_queue(local, remote, only_local, only_remote, mismatch)
    auto = sum(1 for _, mode, _ in queue if mode == "auto_adjust")
    print(f"5) 修复队列 {len(queue)} 条：自动生成单据 {auto} 条，人工核实 {len(queue) - auto} 条")
    for order_id, mode, action in queue:
        print(f"   - {order_id} [{mode}] {action}")


main()
```

保存为 `data_quality_demo.py` 后运行 `python3 data_quality_demo.py`，预期输出：

```text
1) 规范化+校验：入参 4 条 → 通过 3 条，拒绝 [('SO-1003', [('phone', 'phone_invalid')])]
2) 先查后插：两次查询 [None, None]，两次插入 ['inserted', 'blocked']；唯一约束才是裁判
3) 指纹去重：3 笔合规输入 → 2 笔唯一，判重 [('SO-1009', 'SO-1001')]
4) 对账：本地 3 笔 / 支付方 3 笔 → 只有我方=['SO-1004'] 只有支付方=['SO-1005'] 金额不符=['SO-1002']
5) 修复队列 3 条：自动生成单据 1 条，人工核实 2 条
   - SO-1004 [manual] 查支付网关流水，禁止直接补记收款
   - SO-1005 [manual] 核对商户号与测试单，疑似串号
   - SO-1002 [auto_adjust] 差额 500 分，生成冲正单交财务复核
```

五段输出各验证一件事。第 1 段说明规范化必须在校验之前：两种写法的号码被收敛成同一个值。第 2 段是核心：两次 `SELECT` 都返回 `None`，只靠检查两个请求都会插入，唯一约束让第二个变成 `blocked`。第 3 段说明指纹里不能放订单号，否则重试产生的 `SO-1009` 会被当成新单。第 4 段区分三种差异，第 5 段让它们落到动作上，<u>但没有一条直接改原始行</u>。

## 动手实验

### 前置条件

本机有 `python3`（3.8+）与可写目录；不需要数据库服务、支付账号或网络。

### 步骤

1. 把示例保存为 `data_quality_demo.py`，运行一次，逐行核对输出与“预期输出”。
2. 把 `normalize_phone` 里的 `re.sub(r"\D", "", raw)` 改成 `digits = raw`，重跑，观察第 1 段通过条数。
3. 把 `order_fingerprint` 的键改为只含 `order_id`，重跑，观察第 3 段是否还能判出重复。
4. 删掉 `customers.phone` 上的 `UNIQUE`，重跑第 2 段，观察两次插入结果。
5. 把 `P-1002` 的金额由 `4500` 改为 `5000`，重跑，观察第 4、5 段。

### 预期结果

步骤 2 中 `phone_invalid` 变多：带符号的号码过不了 11 位规则，说明“先校验后规范化”会误杀合法输入。步骤 3 判重为空，`SO-1009` 成了独立订单，说明判定键放了唯一 ID 等于没去重。步骤 4 两次插入都返回 `inserted`。步骤 5 差异消失，说明对账只是一面照出事实的镜子。

### 验证方法

把关键行为写成断言：`assert len(unique) == 2`、`assert outcomes == ["inserted", "blocked"]`、`assert mismatch == ["SO-1002"]`，用 `unittest` 跑通。

### 清理方法

删除 `data_quality_demo.py` 与 `__pycache__`；内存库随进程退出释放。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 同一手机号有两个账号 | 只有应用层“先查后插” | 按规范化号码分组统计 `COUNT(*) > 1` | 先规范化存量，再加唯一索引 |
| 同一订单在列表出现两次 | 判定键不稳，混了自增 ID 或时间戳 | 抽 20 条重复记录比对业务字段 | 用自然键或指纹建唯一索引 |
| 差异每天几十条、长期不收敛 | 只出报表、无人建单关闭 | 查差异表的创建时间分布与状态 | 自动建单、指派责任人、设关闭时限 |
| 稽核规则跑了但告警不触发 | 规则只过滤，未统计被过滤的行数 | 用一条已知违规数据验证是否命中 | 输出违规明细与计数，对计数设基线告警 |

## 安全与生产注意事项

**<u>把生产库写权限交给“修数据脚本”，用 UPDATE 覆盖金额与状态，一次误执行就能抹掉审计线索且无法回滚。</u>** 事后无法区分“修复”与“篡改”。缓解：修复只走受控接口，仅允许追加冲正或作废；执行前后对影响行做快照与校验；操作写入审计日志。

**<u>校验失败日志和对账差异文件里直接落手机号、身份证号、完整银行卡号。</u>** 这些文件常被下载到个人电脑或导入日志平台，等于把敏感数据复制到无人管理的副本。缓解：日志只记字段名与脱敏值；差异文件加密并设保留期；导出要有权限与审计。

**<u>让“自动修复”拥有无限额度的生产写权限。</u>** 一条规则误判就能批量冲正真实资金。缓解：自动分支只生成待复核单据，设单笔与单日限额，超阈值转双人复核。

另外，为“稽核违规数”“差异未关闭数”配告警，否则规则只是文档里的承诺。

## 本课总结

- **数据质量按维度定义、按规则检测**：五个维度各有手段，笼统说“数据不准”无法验收。
- **校验与约束是两道防线**：应用层给出可读理由，存储层让绕过应用的写入同样失败。
- **先规范化、再校验、后去重**：顺序错了会误杀合法输入或让判定键失效。
- **去重的可靠性来自唯一索引**：两次查询之间的窗口正是并发重复发生的地方。
- **一致性边界要显式切分**：不可逆副作用必须同事务，跨系统部分只能最终一致并对账兜底。

## 思考题

晴空商城计划把退款口径从“订单应付金额”改成“渠道实收金额”，财务要求切换当天账目仍能对上。请设计这次切换：历史数据怎么处理，校验与约束怎么改，对账基准用哪一套，什么条件下应该回退。

参考思路：不要试图一天对齐全部历史。可拆三步：新写入带口径版本并同时落两种金额；对账按版本分组比对；在确认的基准日切换报表口径，旧口径只读保留。校验加“版本与端一致”的规则，约束允许两列并存但禁止同时为空。回退条件必须在切换前写进方案，例如版本缺失率超过基线。

## 小测

1. 判断：只要接口层做了严格校验，数据库就不需要唯一约束和 `CHECK`。
2. “先查后插”去重在并发下失效的根本原因是？  
   A. 查询太慢　B. 检查与插入之间存在时间窗口　C. 隔离级别太低　D. 没有加索引
3. 关于规范化与校验的顺序，正确的是？  
   A. 先校验再规范化　B. 先规范化再校验　C. 顺序无关　D. 规范化放在对账之后
4. 对账发现“只有对方有、我方无记录”，最应先怀疑什么？  
   A. 重复收款　B. 我方记录丢失或渠道串号　C. 金额算错　D. 口径不一致
5. 修复一条错误的退款金额，最符合要求的做法是？  
   A. 直接 `UPDATE` 改成正确值　B. 删除错误行重插　C. 追加冲正记录并保留原行　D. 在报表层修正
6. 场景题：商品列表里同一个 SKU 出现两条，价格不同、销量各算一半，两边都不报错。请指出至少三个可能的环节，说明先查哪一个，并给出防止再犯的约束设计。

## 答案与解析

1. **错。** 应用层校验只覆盖经过该接口的写入，批处理、运维 SQL、新服务都不走这段代码；只有约束也不行，它给不出可读的拒绝理由。
2. **B。** 检查与插入是两个动作，中间没有机制阻止别人插入。A、C 只放大窗口；D 反而让两个请求更容易都查到“不存在”。
3. **B。** 带 `+86` 的合法号码过不了 11 位规则，先校验就会误拒。A 顺序反了；C 忽略格式差异；D 让脏数据先落库。
4. **B。** 对方有记录说明钱动了，我方没有说明写入失败、事件丢失或渠道串号。A 方向相反；C 会落入“值不符”；D 影响的是口径比较。
5. **C。** 冲正保留原值与修复痕迹。A 抹掉原值不可回滚；B 破坏可追溯性；D 只改展示，源数据仍错。
6. 参考：先查**判定键**——SKU 是否有唯一约束、是否被全角空格或大小写拆成两个值；再查**写入路径**——是否有第二条导入通道绕过校验；最后查**聚合口径**——是否按商品行 ID 而非 SKU 统计。防再犯：SKU 入库前统一大写去空白并对规范化值建唯一索引，导入通道复用同一套校验，把“重复 SKU 写入尝试”做成指标。

### 动手实验参考

步骤 2 通过条数下降，说明规范化必须先于校验；步骤 3 判重为空，说明判定键放入唯一 ID 会让去重失效；步骤 4 两次插入都成功，暴露应用层检查的并发窗口。

## 延伸阅读与下一课

- PostgreSQL 约束章节，`UNIQUE`、`CHECK`、`EXCLUDE` 的语义与代价：<https://www.postgresql.org/docs/current/ddl-constraints.html>。
- SQLite `CREATE TABLE` 文档，示例中唯一约束与 `CHECK` 的依据：<https://www.sqlite.org/lang_createtable.html>。
- JSON Schema 官方网站，用于在接口边界固定字段与类型：<https://json-schema.org/>。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[时间、金额、UUID 与编码陷阱](05-time-money-uuid-and-encoding.md)。
- 下一课：[单体、微服务与无服务器架构](07-monolith-microservices-and-serverless.md)。
