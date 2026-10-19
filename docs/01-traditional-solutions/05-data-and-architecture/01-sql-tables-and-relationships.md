---
title: SQL、表设计与数据关系
slug: sql-tables-and-relationships
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - identity-and-security-overview
outcomes:
  - 把一段退款业务描述拆成表、主键与外键，并在三种关系中选对结构
  - 判断一处冗余该拆表还是该保留，并说明一致性的兜底方式
  - 用主键、外键、UNIQUE、CHECK、NOT NULL 把业务规则落到库上并验证拦截效果
last_reviewed: 2026-10-19
---

# SQL、表设计与数据关系

## 为什么需要学习

晴空商城的退款服务上线半年，财务对账时发现 37 笔退款金额与订单对不上；客服查一笔退款要手工拼四张表，其中两张用手机号关联，用户换号后历史记录整段断链。库里没有约束拦住这些数据，唯一防线是三个团队各自写了一遍校验。

> **核心结论：** 表结构是系统里最难改、影响面最广的接口；只有写进数据库的约束，才对所有写入通道同时生效。

## 学习目标

完成本课后，你能够：

- 把“订单—支付—退款—审核”拆成表，指出每张表的主键，以及外键该放在哪一侧。
- 在一对多、多对多、一对一三种关系中选对结构，并说出选错后的具体症状。
- 判断一处冗余该拆表还是该保留，并写出它的更新路径。
- 用 `NOT NULL`、`UNIQUE`、`CHECK`、外键把业务规则落到库上，并用 `sqlite3` 验证拦截是否真的发生。

## 前置知识

- 回看上一单元：[身份、权限与安全](../04-identity-and-security/00-overview.md)。
- 能读懂 `SELECT ... FROM ... JOIN ... WHERE` 的基本含义。
- 知道金额、时间在程序里都有类型与精度问题。
- 能运行 `python3 --version`；示例只用标准库 `sqlite3`。

## 业务场景

晴空商城的退款要同时满足五个部门：

- 一笔订单可含多件商品，退款可按件退，也可按部分金额退。
- 一笔订单可能分两次付款（定金加尾款），退款必须指回具体那笔支付流水。
- 超过 500 元的退款要审核，审核人、时间、理由要留档，且不能随退款单一起消失。
- 仓库按退款单号回收商品，扫码端只认单号。
- 客服要在 3 秒内调出“订单 → 支付 → 退款 → 审核”链路，且只能看脱敏手机号。

对应硬约束：退款必须挂在真实支付流水上；同一笔支付不能重复退款，重试和连点也不行；金额以分为单位；审核链保留五年。**先定关系，再定字段，最后加约束**——顺序反了，就只能靠应用层补洞。

## 核心概念

设计表的核心问题不是“存哪些字段”，而是“哪些事实属于同一条、靠什么连起来”。

- *表*是同一类事实的集合，一行一条事实，一列一个属性。
- *主键*唯一标识一行且不可为空：*代理键*与业务无关（自增 ID、UUID），*自然键*是业务唯一标识（`sku`）。
- *外键*的取值必须存在于另一张表的主键中，这条规则叫*参照完整性*，由库负责。
- *连接表*表达多对多：它自己是一张表，主键由两侧的键组合。
- *范式*是同一事实只存一处；*反范式*有意保留冗余，用一致性换读速度。
- *约束*是声明式规则，写入时检查，不通过即报错。
- *快照*是写入时复制下来的历史值，商品改价不影响已成交订单。
- *空值*（`NULL`）表示“未知”，它与任何值比较都得 `NULL`，所以 `NOT NULL` 也是避免三值逻辑坑的前提。

| 关系 | 结构 | 晴空示例 | 用错的表现 |
| --- | --- | --- | --- |
| 一对多 | 外键放在“多”的一方 | `orders.customer_id` 指向 `customers.id` | 订单 ID 塞进客户表，只能存一两条，或被迫拼字符串 |
| 多对多 | 建连接表，主键由两侧组合 | `order_items(order_id, sku)` | 订单表里存逗号分隔的 SKU，无法按商品查 |
| 一对一 | 共享主键，或外键加唯一约束 | `refund_audits.refund_id` 唯一 | 合并成宽表，一半列常为空，删退款时审核一起丢 |

约束能表达的规则都该下库：

| 约束 | 保证什么 | 晴空示例 | 注意 |
| --- | --- | --- | --- |
| `NOT NULL` | 这一行必须有值 | `refunds.reason` | 加在已有空值的列上会失败，要先补数据 |
| `UNIQUE` | 列组合在表内唯一 | `customers.phone`；`(payment_id, idempotency_key)` | 自带索引，有写入代价 |
| `CHECK` | 单行内的取值规则 | `amount_cents > 0` | 不能写子查询，跨行规则表达不了 |
| `FOREIGN KEY` | 引用的父行必须存在 | `refunds.payment_id → payments.id` | 子表列没索引时，删父行会全表扫描 |

**外键是唯一能拦住孤儿数据的机制。**<u>只在 ORM 模型里声明外键、不在库里建，等于给批处理、运维手工 SQL 和 CDC 回灌留了三个后门。</u>

## 工作原理

设计阶段自下而上：

1. 圈名词，区分*实体*（客户、订单、支付、退款）与*属性*（手机号、金额、时间）。
2. 给每个实体定主键：优先代理键，业务唯一值退化为 `UNIQUE` 约束。
3. 一对多：外键放在“多”的一方，并建索引，方便按父行反查。
4. 多对多：抽出连接表，把数量、成交价这类“连接上的属性”一并放进去。
5. 复制会变的值：商品名称、成交价、收货地址以*快照*写进订单行。
6. 把业务规则逐条翻译成约束，并标出哪条是跨行规则。
7. 统一命名：小写蛇形、表名复数、外键 `<单数>_id`、金额列以 `_cents` 结尾。
8. 写成版本化迁移脚本，先在空库和脱敏副本上各跑一次。

写入阶段自上而下，以一笔 399 元的部分退款为例：

9. 校验订单存在，且状态允许退款。
10. 追加退款流水，`payment_id` 外键指向原支付；负数金额在 `CHECK` 处被拒。
11. 靠唯一约束挡住重复提交：网关重试时第二次插入失败，服务把它翻译成“已受理”。
12. 写审核记录，`refund_id` 外键指向退款单，审核人不允许为空，删权限单独收走。
13. 提交事务，四张表要么同时可见，要么同时不可见。
14. 客服按 `order_id` 连接查询，没有退款的分支用 `LEFT JOIN`，否则整笔订单会从结果里消失。

两个顺序要写进团队规范：<u>先建父表再建子表、先清孤儿再加外键</u>；<u>先定关系再调字段</u>，改列名容易，改关系要迁数据。

## 架构与选型

规范化与反范式是一笔明确的交易：

| 情况 | 建议 | 理由 | 代价 |
| --- | --- | --- | --- |
| 同一事实被多处写入（手机号） | 范式化 | 改一次处处生效 | 查询要多连接 |
| 历史单据展示（商品名、成交价） | 反范式，写快照 | 主数据会变，历史不能被改写 | 冗余列只能写一次 |
| 报表要连五六张表 | 适度反范式或建汇总表 | 响应时间稳定 | 必须定义重算方式 |

主键选型取决于“谁生成、要不要暴露”：

| 类型 | 优点 | 缺点 | 适用 |
| --- | --- | --- | --- |
| 自增整数 | 短、有序、索引友好 | 暴露业务量、多库合并会冲突 | 单库明细表 |
| UUID | 客户端可生成、合并无冲突 | 体积大、随机写入差 | 分布式写入、离线生成 |
| 自然键（`sku`） | 可读、导入方便 | 业务值一变，所有引用都要改 | 确实稳定且全局唯一的编码 |

约束放在哪一层，也常被误判：

| 位置 | 放什么 | 不放什么 |
| --- | --- | --- |
| 数据库约束 | 唯一、非空、取值域、引用完整性 | 依赖外部系统的规则、跨行累计 |
| 应用层 | 权限、跨服务规则、可读的报错 | 唯一性（并发下必失效） |
| 事务或触发器 | 跨行累计（退款不得超实付） | 复杂业务编排 |

**能被单行表达的事实交给库，需要看别的行或别的系统的规则交给事务；两者都不能省的，写两遍并让库那遍兜底。**

## 最小示例

问题：建出客户、订单、支付、退款四张表，验证外键、`CHECK`、`UNIQUE`、`ON DELETE RESTRICT` 能拦住几类坏数据，并算出订单净额。环境 Python 3.8+，只用标准库，库在内存里，不联网。

```python
import sqlite3

conn = sqlite3.connect(":memory:")           # 内存库，实验结束即消失，不会留下脏数据
conn.execute("PRAGMA foreign_keys = ON")     # SQLite 默认关闭外键检查，每个连接都必须显式打开

conn.executescript("""
CREATE TABLE customers (
    id            INTEGER PRIMARY KEY,        -- 代理键：与业务无关，换手机号不影响任何关联
    phone         TEXT NOT NULL UNIQUE,       -- 一个人一个手机号，唯一性交给库，不交给代码
    display_name  TEXT NOT NULL
);

CREATE TABLE orders (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(id),   -- 一对多：外键放在“多”的订单侧
    status        TEXT NOT NULL CHECK (status IN ('created','paid','refunding','refunded','closed')),
    total_cents   INTEGER NOT NULL CHECK (total_cents >= 0)    -- 金额用整数分，浮点会在累加时丢精度
);

CREATE TABLE payments (
    id            INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(id),
    amount_cents  INTEGER NOT NULL CHECK (amount_cents > 0),   -- 支付金额不可能是 0 或负数
    paid_at       TEXT NOT NULL
);

CREATE TABLE refunds (
    id              INTEGER PRIMARY KEY,
    payment_id      INTEGER NOT NULL REFERENCES payments(id) ON DELETE RESTRICT,  -- 有退款记录的支付不许删
    amount_cents    INTEGER NOT NULL CHECK (amount_cents > 0),
    reason          TEXT NOT NULL,            -- 审核理由必填，避免“无说明退款”
    idempotency_key TEXT NOT NULL,
    UNIQUE (payment_id, idempotency_key)      -- 同一请求重试第二次必然撞唯一约束，这是幂等的最后一道闸
);
""")

cur = conn.cursor()
cur.execute("INSERT INTO customers (phone, display_name) VALUES ('13800000000', '林夏')")
customer_id = cur.lastrowid                              # 自增主键由库生成，应用只拿回值
cur.execute("INSERT INTO orders (customer_id, status, total_cents) VALUES (?, 'paid', 59900)", (customer_id,))
order_id = cur.lastrowid
cur.execute("INSERT INTO payments (order_id, amount_cents, paid_at) VALUES (?, 59900, '2026-10-19T10:00:00Z')", (order_id,))
payment_id = cur.lastrowid
cur.execute("INSERT INTO refunds (payment_id, amount_cents, reason, idempotency_key) VALUES (?, 39900, '少发一件', 'req-001')", (payment_id,))
print("正常退款写入:", cur.rowcount == 1)

def expect_fail(label, sql, params=()):
    # 每条坏数据都在独立 SAVEPOINT 里试，失败后回滚，不影响后续用例
    conn.execute("SAVEPOINT probe")
    try:
        conn.execute(sql, params)
        print(label, "没有拦住")                # 走到这里说明约束缺失
    except sqlite3.IntegrityError as exc:
        print(label, "已拦截:", exc)            # 约束生效，报错信息里带着约束名
    finally:
        conn.execute("ROLLBACK TO probe")
        conn.execute("RELEASE probe")

# 1) 挂在不存在的支付流水上的退款：外键拦
expect_fail("外键", "INSERT INTO refunds (payment_id, amount_cents, reason, idempotency_key) VALUES (999, 100, '测试', 'req-x')")
# 2) 负数退款：CHECK 拦
expect_fail("CHECK", "INSERT INTO refunds (payment_id, amount_cents, reason, idempotency_key) VALUES (?, -100, '测试', 'req-y')", (payment_id,))
# 3) 同一幂等键重试：唯一约束拦，业务上表现为“已受理”
expect_fail("UNIQUE-幂等", "INSERT INTO refunds (payment_id, amount_cents, reason, idempotency_key) VALUES (?, 100, '重试', 'req-001')", (payment_id,))
# 4) 重复手机号：唯一约束拦
expect_fail("UNIQUE-手机号", "INSERT INTO customers (phone, display_name) VALUES ('13800000000', '另一个人')")
# 5) 删除仍有退款记录的支付：RESTRICT 拦
expect_fail("RESTRICT", "DELETE FROM payments WHERE id = ?", (payment_id,))

# 6) 汇总：按订单算实付与已退，没有退款的分支用 LEFT JOIN 才不会整行消失
row = conn.execute("""
    SELECT o.id, p.amount_cents AS paid, COALESCE(SUM(r.amount_cents), 0) AS refunded
    FROM orders o
    JOIN payments p ON p.order_id = o.id
    LEFT JOIN refunds r ON r.payment_id = p.id
    GROUP BY o.id, p.amount_cents
""").fetchone()
print("订单汇总: 实付", row[1], "已退", row[2], "净额", row[1] - row[2])
```

把代码保存为 `/tmp/ddl_demo.py`，运行：

```bash
python3 /tmp/ddl_demo.py
```

预期输出：

```text
正常退款写入: True
外键 已拦截: FOREIGN KEY constraint failed
CHECK 已拦截: CHECK constraint failed: amount_cents > 0
UNIQUE-幂等 已拦截: UNIQUE constraint failed: refunds.payment_id, refunds.idempotency_key
UNIQUE-手机号 已拦截: UNIQUE constraint failed: customers.phone
RESTRICT 已拦截: FOREIGN KEY constraint failed
订单汇总: 实付 59900 已退 39900 净额 20000
```

流程是：声明结构 → 插入一条合法链路 → 用五条坏数据逐项试探防线 → 连接加聚合验证读路径。三个设计选择：主键一律用代理键，业务值可自由变更；外键规则显式写 `RESTRICT`，因为“不写”在不同数据库里默认行为并不一致；每条用例包在 `SAVEPOINT` 里，一次失败不污染后续验证。

示例没有表达“退款总额不得超过实付”：那是跨行规则，`CHECK` 里不能写子查询。<u>遇到跨行规则要当场记下，用事务加行锁实现，别以为加了 `CHECK` 就完成了。</u>

## 动手实验

### 任务：给订单加商品明细，验证复合主键与价格快照

前置条件：本机有 `python3`，无需安装数据库，无需联网。

1. 新建 `/tmp/sql_lab.py`，用 `sqlite3.connect(":memory:")` 加 `PRAGMA foreign_keys = ON` 建连接。
2. 建 `orders`、`products(sku PRIMARY KEY, name, price_cents)` 与 `order_items(order_id, sku, quantity, unit_price_cents)`，后者主键写成 `PRIMARY KEY (order_id, sku)`。
3. 插入两件商品和订单 1 的两行明细，再插一行重复 SKU，确认被拦。
4. 把某件商品价格从 `12900` 改成 `9900`，查订单行快照价与订单合计。

预期结果：重复 SKU 报 `UNIQUE constraint failed: order_items.order_id, order_items.sku`；改价后商品表为 `9900`，订单行仍是 `12900`；合计 `30700`，明细两行。

```python
conn.executescript("""
CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT NOT NULL);
CREATE TABLE products (
    sku         TEXT PRIMARY KEY,             -- 自然键：仓库存量、扫码枪、采购单都用它
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0)
);
CREATE TABLE order_items (
    order_id         INTEGER NOT NULL REFERENCES orders(id),
    sku              TEXT NOT NULL REFERENCES products(sku),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),  -- 成交价快照，不受商品改价影响
    PRIMARY KEY (order_id, sku)               -- 复合主键：同一订单同一 SKU 只能一行
);
""")
```

验证方法：查快照价是否仍为 `12900`、`SUM(quantity * unit_price_cents)` 是否为 `30700`。重复插入没报错，说明主键退化成了单列自增 `id`。

清理方法：`rm -f /tmp/sql_lab.py`。内存库随进程结束消失，不留残留表。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 历史订单的商品名与金额跟着新品变了 | 订单行只存 `product_id`，展示时回查商品表 | 改价改名后重开旧订单 | 订单行保存名称与成交价*快照* |
| 删掉一条测试客户，订单列表整段消失 | 外键写成 `ON DELETE CASCADE`，删父行连带删子行 | 在副本库删除，统计 `orders` 行数变化 | 业务主表用 `RESTRICT`，删除改成状态位 |
| 对账差几分钱，金额越累越大 | 金额用 `FLOAT`，累加出现舍入误差 | 逐笔相加与 `SUM()` 对比 | 存整数分或 `NUMERIC(12,2)`，应用层统一换算 |
| 同一笔支付被退了两次 | 判重只在应用层，重试或并发直接绕过 | 用同一 `Idempotency-Key` 连发两次 | 在 `(payment_id, idempotency_key)` 上建唯一约束 |
| 退款总额超过实付，库毫无反应 | 把跨行规则误当成单行 `CHECK` | 构造两笔各退 70% 的用例 | 事务内 `SELECT ... FOR UPDATE` 校验累计额 |
| 迁移加外键这步失败 | 子表已有孤儿行，或父子列类型不一致 | 迁移前跑 `LEFT JOIN ... WHERE 父.id IS NULL` | 先清孤儿数据，再按“子表→父表”建 |

## 安全与生产注意事项

**<u>只把校验写在应用层，等于给批量导入、运维手工 SQL 和 CDC 回灌开了三个后门。</u>** 这些通道不走业务代码，一笔没有对应支付的退款可以静悄悄进库，等对账才发现，也查不出是哪条通道写坏的。缓解：唯一约束、外键、`CHECK` 全部落库；批处理复用同一套结构；对孤儿数据与异常写入量定期巡检。

**<u>用物理 `DELETE` 清理“过期”业务数据，会直接删断退款与审核的审计链。</u>** 事后无法回答“谁在什么时候批准了这笔退款”，这既是财务问题也是合规事故。缓解：业务表软删除、审计表只追加，应用账号不授予 `DELETE` 权限，清理只能走审批过的归档任务。

**<u>把手机号、身份证号、退款金额塞进同一张宽表。</u>** 一旦为客服查询而给出这张表的读权限，敏感字段就一起暴露，导出与日志也无从脱敏。缓解：按上一单元的数据分级拆表拆列，客服只走脱敏视图，敏感字段单独加密。

## 本课总结

- 表结构是最难改的接口：先定关系，再定字段，最后加约束。
- 主键只负责唯一标识，不承载业务含义；会变的业务值退化为 `UNIQUE` 列。
- 一对多把外键放在“多”的一方；多对多必须有连接表；一对一用共享主键或唯一外键。
- 范式保证同一事实只存一处，反范式用冗余换速度；每处冗余都要有更新路径与重算方式。
- 约束写在库里才对所有写入通道生效，但跨行规则只能靠事务与锁。

## 思考题

客服列表页要在 3 秒内展示“订单号 + 商品名 + 已退金额”，团队想在 `orders` 上冗余 `product_name` 和 `refunded_cents`。请说明：什么情况下这个冗余值得，什么情况下会变成两处真相，你用什么机制让不一致被及时发现。

参考思路：判断依据是这两个值的更新频率与一致性容忍度。商品名属于主数据、会变，冗余后旧订单显示新名字就是错的，应当存下单快照而不是回填；已退金额是高频写、必须精确的聚合，冗余就要在每次退款事务里同步更新，并发多条退款时极易漂移。更稳的顺序是先把读路径优化到可接受（索引、短时缓存），确有瓶颈再加汇总列，并安排定时重算与差值告警。

## 小测

1. 一笔订单包含多件商品，同一件商品也出现在多张订单里，这属于哪种关系？
   A. 一对一　B. 一对多　C. 多对多　D. 没有关系
2. 为什么通常不建议把手机号当作客户表的主键？请给出至少两个理由。
3. `NOT NULL`、`UNIQUE`、`CHECK`、`FOREIGN KEY` 各拦下哪类坏数据？各用一句话说明。
4. 反范式的代价是什么？为什么订单行里的商品名称不算“没必要的冗余”？
5. 场景题：财务要求“任何一笔支付的退款总额都不得超过实付金额”，团队提议加 `CHECK (amount_cents <= 59900)`。这个约束能达成目的吗？你会怎么落这条规则？

## 答案与解析

1. **C。** 两侧都能对应多行，必须用连接表 `order_items` 表达，数量与成交价这类“连接上的属性”也放进去。A 错在一对一要求两侧各只有一行；B 错在一对多的外键只能放一侧，表达不了双向多；D 错在两侧确有业务关联。
2. 手机号会变（换号、携号转网），还可能被回收再分配，做主键就要级联改写所有引用行；它又是个人信息，容易被带进日志、URL 与导出文件。更稳的做法是代理键加 `UNIQUE (phone)`。
3. `NOT NULL` 拦“该有值却没有”的行；`UNIQUE` 拦重复，含并发重复提交；`CHECK` 拦单行内的取值越界；`FOREIGN KEY` 拦“引用了不存在的父行”，同时约束删除顺序。
4. 代价是同一事实存两份，任一份漏更新就出现两处真相。订单行的商品名与成交价是**快照**，记录下单那一刻的事实；商品表现值属于主数据，语义不同，不该随主数据变化。
5. 不能。`CHECK` 是单行约束，只看当前这一行，看不到同一支付的其他退款行；写死 `59900` 还把业务参数固化进了表结构。正确做法是在退款事务内先 `SELECT ... FOR UPDATE` 锁住支付行、累加已退金额再判超限；唯一约束防重复，金额非正由 `CHECK` 兜底。

### 动手实验参考

合理实现不唯一。三个检查点：`order_items` 主键是否为 `(order_id, sku)`；两个外键是否都指向真实父表；`unit_price_cents` 是否在插入时写入，而不是查询时回查。重复插入没报错说明主键退化成单列自增 `id`；改价后订单行金额跟着变，说明存的是引用不是快照。进阶可试着把 `quantity > 0` 与商品下架状态组合成业务规则，观察哪些能写进 `CHECK`、哪些必须进事务。

## 延伸阅读与下一课

- [PostgreSQL 文档：约束](https://www.postgresql.org/docs/current/ddl-constraints.html)，`CHECK`、`UNIQUE`、外键与 `ON DELETE` 的语义边界。
- [PostgreSQL 文档：数值类型](https://www.postgresql.org/docs/current/datatype-numeric.html)，`numeric`、`real`、`double precision` 的精度差异，是“金额不用浮点”的依据。
- [SQLite 文档：外键支持](https://www.sqlite.org/foreignkeys.html)，解释为何每个连接都要执行 `PRAGMA foreign_keys = ON`。

- 返回[本单元目录](00-overview.md)。
- 回看上一单元：[身份、权限与安全](../04-identity-and-security/00-overview.md)。
- 下一课：[索引、事务、锁与数据库迁移](02-indexes-transactions-and-migrations.md)。
