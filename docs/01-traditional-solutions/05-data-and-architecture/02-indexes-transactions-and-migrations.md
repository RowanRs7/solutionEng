---
title: 索引、事务、锁与数据库迁移
slug: indexes-transactions-and-migrations
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - sql-tables-and-relationships
outcomes:
  - 用执行计划判断一条查询能否用上索引、是否需要回表，并解释复合索引列顺序的影响
  - 列出新增或删除索引对读写与空间的代价，并给出保留或删除的依据
  - 写出一个可分批、可重入、可回滚的表结构迁移步骤及每步验证方法
last_reviewed: 2026-10-19
---

# 索引、事务、锁与数据库迁移

## 为什么需要学习

`orders` 涨到 8000 万行时，客服按手机号查订单要等 12 秒。开发连夜加索引，查询降到 20 毫秒；两周后写入峰值掉了一半——表上已有 11 个索引，4 个是别人索引的前缀。第三次更糟：加 `created_at` 索引的脚本直接 `ALTER TABLE`，锁表 41 分钟，下单全线超时，退款与库存回滚一起卡住。

三次故障是三笔账：读快了多少、写慢了多少、变更愿意停多久。不一起算，单点优化就会在别处变成事故。

> **核心结论：** 索引买的是读时间，付的是写成本与空间；事务和锁买的是正确性，付的是并发；迁移买的是变更能力，付的是停机与回滚风险。

## 学习目标

完成本课后，你能够：

- 读懂执行计划里的 `SCAN`、`SEARCH`、`USING COVERING INDEX`，判断查询是否走索引、是否回表。
- 解释最左前缀规则，说明调整复合索引列顺序会让哪些查询失效。
- 说明四种隔离级别各防住哪些异常，给出缩小锁范围与避免死锁的做法。
- 写出可分批、可重入、可回滚的迁移，并指出每步的验证数据。

## 前置知识

- 回看上一课：[SQL、表设计与数据关系](01-sql-tables-and-relationships.md)。
- 知道主键、唯一约束、外键与 `NULL` 的语义。
- 能读懂 `WHERE`、`ORDER BY`、`JOIN` 写出的查询意图。
- 能在本机运行 Python 3 标准库脚本。

## 业务场景

晴空商城这一侧面：订单库是下单、退款、仓储共用的主库，写峰值 1200 TPS，7×24 不可停。

- 客服列表页按“手机号 + 状态 + 时间段”筛选、按时间倒序分页，P95 是 12 秒。
- 一次退款要同改 `refunds`、`orders`（累计退款额）、`inventory`（回滚出库），三者必须一致；退款 worker 与仓库回调并发改同一批订单，两周内 9 次死锁，3 次转人工。
- 连接池上限 20，两条没走索引的慢查询就能占满。
- 下一版要加 `phone_norm` 列和 `(status, created_at)` 复合索引，没有停机窗口。

约束：已支付订单不能丢，新旧两版代码要能同时跑，每步可单独回滚，写峰值掉幅不超过 10%。

## 核心概念

*索引*（index）用空间换查找速度，默认实现是 B+ 树：叶子按索引列有序存放并记住行在哪里。

*聚簇索引*（clustered index）指行数据按主键组织，按主键查一次就拿到整行。<u>其他索引的叶子里只有索引列和主键</u>，取别的列要按主键再查一次，这次额外查找叫*回表*（row lookup）；所需列都在索引里，就是*覆盖索引*（covering index）。*最左前缀*（leftmost prefix）指复合索引按定义顺序排列，条件要从第一列开始连续使用，跳过第一列，后面的列就白建。

*事务*（transaction）是一组要么全做、要么全不做的操作：原子性保证不半途生效，隔离性决定并发事务互相看见什么。*隔离级别*（isolation level）用更多锁或更严快照换更少异常；*MVCC*（多版本并发控制）让写产生新版本、读按快照取版本，于是读不阻塞写。

*锁*（lock）分行锁、间隙锁、表锁；*死锁*（deadlock）是两个事务各持一把又都等对方那把。*连接池*（connection pool）复用预建的连接：池大小就是并发上限。*迁移*（migration）是对结构或数据的有序变更；*expand-contract*（扩展—收缩）把它拆成“先兼容、再切换、后清理”。

| 隔离级别 | 能防住 | 防不住（标准定义） | 实现代价 |
| --- | --- | --- | --- |
| 读未提交 | 几乎没有 | 脏读、不可重复读、幻读 | 最低 |
| 读已提交 | 脏读 | 不可重复读、幻读 | 每条语句一个快照 |
| 可重复读 | 脏读、不可重复读 | 幻读 | 事务级快照，旧版本留更久 |
| 串行化 | 上述全部 | — | 范围锁或冲突检测，重试变多 |

*脏读*指读到未提交的数据，*不可重复读*指同一行两次读到不同值，*幻读*指同一范围两次读到不同行数。实现常比标准更严：PostgreSQL 的快照隔离几乎无幻读，代价是更早的序列化失败；InnoDB 用间隙锁挡范围插入，代价是更多死锁。

索引的代价：

| 手段 | 读的收益 | 写的代价 | 空间与运维 |
| --- | --- | --- | --- |
| 单列索引 | 等值与范围查询改走索引 | 每次插入或更新该列都维护一棵树 | 约为被索引数据的 1.2–1.5 倍 |
| 复合索引（等值在前） | 一次命中多条件，顺序合适还免排序 | 同上，列多更贵 | 更宽，每页条目更少 |
| 覆盖索引 | 免回表，随机 I/O 显著下降 | 与普通索引相同 | 多一列就白付 |
| 删除冗余前缀索引 | 不变，更长索引可顶替 | 写变快 | 立刻释放空间 |

## 工作原理

### 一次走索引的查询

1. 解析并改写 SQL，优化器按统计信息估算每种访问路径的行数与代价。
2. 从 B+ 树根走到叶子：千万级表约三层，3 次页读取就定位到 `customer_phone = '138...'`。
3. 叶子给出主键，再按主键到聚簇索引取整行——回表。命中 1 万行就多 1 万次随机 I/O，这才是慢查询的来源。
4. `SELECT` 的列全在索引里就跳过第 3 步；`ORDER BY` 与索引顺序一致时沿叶子读即可，否则要临时表加 `filesort`，`LIMIT 20` 也得先排完。
5. 最后按 `LIMIT` 截断。<u>没有 `ORDER BY` 的 `LIMIT` 不保证顺序稳定，分页会重复或漏行。</u>

### 一次退款事务

1. `BEGIN` 只声明边界，真正的锁在第一条写语句时加。
2. 依次更新 `refunds`、`orders`、`inventory`：每句拿一把排他锁并写前镜像供回滚，三把锁都在自己手上，其他退款只能排队或超时。
3. `COMMIT` 把日志刷盘后，别的会话才看得到新版本，锁同时释放。
4. 出错则 `ROLLBACK` 用前镜像还原。<u>连接归还池前必须结束事务</u>：留在 `idle in transaction` 的连接会把锁带进池里，谁拿到都可能被挡住。

### 一次在线迁移

1. expand：只加可空的新列或新表，旧代码不感知，回滚等于“不读新列”。
2. 双写：新代码同时写新旧两列，旧代码继续读旧列，两版并存不冲突。
3. 回填：按主键游标分批 `UPDATE`，每批一个短事务，条件带 `IS NULL` 让它可重入。
4. 建索引：用在线 DDL（`CREATE INDEX CONCURRENTLY`、`ALGORITHM=INPLACE, LOCK=NONE`）不阻塞读写；未指定 `ALGORITHM`/`LOCK` 且操作本身不支持在线执行时，才会复制整表并阻塞写入；MySQL 5.6 起多数二级索引 DDL 支持 Online DDL，是否锁表取决于具体操作与子句。
5. 切读前校验：新旧两种条件各查一次计数，一致才切换；观察一个版本周期后删旧列、旧索引。<u>删列是唯一不可逆的一步，必须最后做。</u>

## 架构与选型

| 手段 | 适合 | 不适合 | 代价 |
| --- | --- | --- | --- |
| 复合索引（等值列在前） | 列表页按“状态 + 时间段”筛选并排序 | 各列经常被单独查询 | 写放大，列顺序要按查询固定 |
| 悲观锁（`SELECT ... FOR UPDATE`） | 库存、余额这类强一致的短事务 | 长事务、事务内调外部接口 | 锁等待、死锁、吞吐下降 |
| 外部连接池（PgBouncer、HikariCP） | 应用实例多、连接数要收敛 | 依赖会话级状态或临时表 | 多一层配置和故障点 |
| 在线 DDL + expand-contract | 大表、无停机窗口 | 小表、有维护窗口 | 步骤多，要双写与校验 |

选型依据三条：**先看读写比再决定加不加索引**，写多读少的表，索引数量是第一成本项；**锁的范围由事务边界决定**，事务里只留数据库操作；**迁移每步可单独回滚且可重入**。

## 最小示例

问题：不装数据库服务，先看清三件事：回表确实存在、最左前缀会失效、写会变贵，以及未提交的写会挡人、未提交的修改别人看不见。

环境：Python 3.9 以上，只用 `sqlite3` 与 `time`；第一个脚本全内存，第二个在 `/tmp/qk-db` 落文件。

```python
"""索引的三笔账：查找、回表、写入。只用标准库 sqlite3。"""
import sqlite3
import time

N = 100000                     # 行数只要够让“全表扫”和“走索引”拉开差距
SCHEMA = """
CREATE TABLE orders (
  id             INTEGER PRIMARY KEY,   -- 聚簇主键：整行按 id 存放，回表就是按 id 再查一次
  customer_phone TEXT NOT NULL,
  status         TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  note           TEXT
);
"""
INDEXES = (
    "CREATE INDEX idx_orders_phone ON orders(customer_phone)",
    "CREATE INDEX idx_orders_status_created ON orders(status, created_at)",  # 复合索引，顺序有意义
)


def rows(base, count):
    for i in range(base, base + count):
        yield (i, f"138{i:08d}", "paid" if i % 2 else "refunded", f"2026-10-{i % 28 + 1:02d}", "x" * 40)


con = sqlite3.connect(":memory:")
con.executescript(SCHEMA)
con.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", rows(1, N))
con.commit()


def plan(sql, params=()):
    # EXPLAIN QUERY PLAN 不执行查询，只给出访问路径：SCAN 全表扫，SEARCH 用索引
    return " | ".join(r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql, params))


def cost_us(sql, params=(), repeat=5):
    begin = time.perf_counter()
    for _ in range(repeat):                     # 重复取平均，抵消单次抖动
        con.execute(sql, params).fetchall()
    return (time.perf_counter() - begin) / repeat * 1_000_000


phone = "13800001234"
print("1 无索引按手机号查：", plan("SELECT * FROM orders WHERE customer_phone=?", (phone,)),
      f"  平均 {cost_us('SELECT * FROM orders WHERE customer_phone=?', (phone,)):.0f} µs")

for ddl in INDEXES:
    con.execute(ddl)                            # 建索引本身也要扫全表，时间随行数线性增长

print("2 有索引按手机号查：", plan("SELECT * FROM orders WHERE customer_phone=?", (phone,)),
      f"  平均 {cost_us('SELECT * FROM orders WHERE customer_phone=?', (phone,)):.0f} µs")

print("3 覆盖索引不回表：", plan(
    "SELECT status, created_at FROM orders WHERE status=? ORDER BY created_at", ("paid",)))
print("4 条件只用第二列：", plan("SELECT * FROM orders WHERE created_at=?", ("2026-10-05",)))
print("5 要取 note 只能回表：", plan("SELECT * FROM orders WHERE status=?", ("paid",)))


def build(with_index):
    fresh = sqlite3.connect(":memory:")
    fresh.executescript(SCHEMA)
    if with_index:                              # 索引先建好，测的是“维护索引”的成本，不是“构建”的成本
        for ddl in INDEXES:
            fresh.execute(ddl)
    begin = time.perf_counter()
    fresh.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", rows(1, 20000))
    fresh.commit()
    ms = (time.perf_counter() - begin) * 1000
    page_count = fresh.execute("PRAGMA page_count").fetchone()[0]
    pages = page_count * fresh.execute("PRAGMA page_size").fetchone()[0]
    fresh.close()
    return ms, pages / 1024 / 1024


plain, plain_mb = build(False)
indexed, indexed_mb = build(True)
print(f"6 插入 20000 行：无索引 {plain:.0f} ms / {plain_mb:.1f} MB，两个索引 {indexed:.0f} ms / {indexed_mb:.1f} MB")
```

预期输出（Python 3.14 实测，耗时随机器波动，看比值不看绝对值）：

```text
1 无索引按手机号查： SCAN orders   平均 2032 µs
2 有索引按手机号查： SEARCH orders USING INDEX idx_orders_phone (customer_phone=?)   平均 6 µs
3 覆盖索引不回表： SEARCH orders USING COVERING INDEX idx_orders_status_created (status=?)
4 条件只用第二列： SCAN orders
5 要取 note 只能回表： SEARCH orders USING INDEX idx_orders_status_created (status=?)
6 插入 20000 行：无索引 14 ms / 1.5 MB，两个索引 26 ms / 2.5 MB
```

第 3 条免排序，是因为 `status` 等值在前、`created_at` 有序在后；第 4 条丢掉第一列，索引作废；第 6 条写入翻倍、体积多六成，就是“索引数 + 1”的写放大。第二个脚本把锁的两个事实跑出来：

```python
"""两个连接抢同一行：未提交的写会挡住别人，等待超时只是把阻塞变成错误。"""
import os
import sqlite3

DB = "/tmp/qk-db/tx.db"
if os.path.exists(DB):
    os.remove(DB)                                   # 每次从干净状态开始，否则上一轮的残留会干扰观察

# isolation_level=None 关掉驱动的隐式事务，事务边界由 BEGIN/COMMIT 显式控制
con1 = sqlite3.connect(DB, timeout=0.2, isolation_level=None)
con2 = sqlite3.connect(DB, timeout=0.2, isolation_level=None)
con1.execute("PRAGMA journal_mode=WAL")             # WAL 下读不被写阻塞，更接近线上 MVCC 的观感
con1.execute("CREATE TABLE inventory (sku TEXT PRIMARY KEY, qty INTEGER)")
con1.execute("INSERT INTO inventory VALUES ('SKU-1', 10)")

con1.execute("BEGIN IMMEDIATE")                     # 立刻取写锁，模拟“扣库存还没提交”的长事务
con1.execute("UPDATE inventory SET qty = qty - 1 WHERE sku = 'SKU-1'")
print("con1 未提交时自己看到：", con1.execute(
    "SELECT qty FROM inventory WHERE sku='SKU-1'").fetchone()[0])

try:
    con2.execute("UPDATE inventory SET qty = qty - 1 WHERE sku = 'SKU-1'")
    print("并发写：成功了（不符合预期）")
except sqlite3.OperationalError as exc:             # timeout=0.2 秒等不到锁就报错
    print("并发写被挡：", exc)                        # 说明写锁在提交或回滚前不会释放

print("con2 看到的数量：", con2.execute(
    "SELECT qty FROM inventory WHERE sku='SKU-1'").fetchone()[0], "（未提交的修改不可见）")

con1.execute("COMMIT")                              # 提交：版本对其他人可见，锁同时释放
try:
    con2.execute("UPDATE inventory SET qty = qty - 1 WHERE sku = 'SKU-1'")
    print("提交后重试：成功")
except sqlite3.OperationalError as exc:
    print("提交后仍然失败：", exc)

for con in (con1, con2):                            # 连接必须显式关闭，池化场景下等价于“归还”
    con.close()
print("最终数量：", sqlite3.connect(DB).execute(
    "SELECT qty FROM inventory WHERE sku='SKU-1'").fetchone()[0])
```

预期输出：

```text
con1 未提交时自己看到： 9
并发写被挡： database is locked
con2 看到的数量： 10 （未提交的修改不可见）
提交后重试：成功
最终数量： 8
```

`plan()` 只问“怎么走”，`cost_us()` 只问“走多久”，`build()` 只问“写多贵”；`tx_lab.py` 用 `BEGIN IMMEDIATE` 制造长事务、用 `timeout=0.2` 把锁等待变成可观察的错误，`COMMIT` 前后各读一次就看到“隔离”与“释放”。取舍：SQLite 只有库级写锁、没有隔离级别参数，只能证明“锁在提交前不释放、未提交版本不可见”，行锁与间隙锁要换 PostgreSQL 或 InnoDB 复现。

## 动手实验

前置条件：Python 3.9 以上，`sqlite3` 3.35 以上（`DROP COLUMN` 需要），无网络与账号；文件只放在 `/tmp/qk-db`。

1. 建目录，把上面两段代码存成 `index_lab.py` 与 `tx_lab.py` 各跑一次，记下第 1、2 条耗时与第 6 条的写入体积。
2. 把复合索引改成 `(created_at, status)` 再跑：第 3 条从 `SEARCH` 退化为 `SCAN`，但仍覆盖且沿索引顺序无需排序；第 4 条反而用上索引。体会顺序是为查询定制的。
3. 把第 5 条 `SELECT *` 改成 `SELECT status, created_at`，看是否变成 `USING COVERING INDEX`。
4. 把 `timeout` 改成 0，看报错从等待超时变成立即失败；再删掉 `COMMIT` 并关闭连接，看 `con2` 是否仍被挡住。
5. 迁移演练：写 `migrate_lab.py`，建一张 5000 行的 `orders`，实现加列、分批回填、校验、收缩四步，回填循环用下面骨架，批大小先设 500：

   ```python
   cursor = 0
   while True:                              # 按主键游标推进，越往后不会变慢
       ids = [r[0] for r in con.execute(
           "SELECT id FROM orders WHERE id > ? ORDER BY id LIMIT ?", (cursor, 500))]
       if not ids:
           break
       con.execute("BEGIN IMMEDIATE")       # 每批一个短事务：持锁时间只由批大小决定
       con.execute("UPDATE orders SET phone_norm = REPLACE(customer_phone,' ','') "
                   "WHERE id > ? AND id <= ? AND phone_norm IS NULL", (cursor, ids[-1]))
       con.execute("COMMIT")
       cursor = ids[-1]
   ```

   再把批大小改成 5000 跑一次，比较单批持锁时长。

预期结果：步骤 1 约 2 毫秒对 6 微秒、写入 14 毫秒对 26 毫秒；步骤 2 第 4 条从 `SCAN` 变 `SEARCH`；步骤 3 第 5 条变覆盖索引；步骤 4 立即报 `database is locked`；步骤 5 回填后空值行为 0，重跑回填影响 0 行。

验证方法：数计划里 `COVERING` 与 `SEARCH` 的次数，比计时更稳；可重入看第二次回填的 `total_changes` 是否为 0；回滚演练停在加列阶段，执行 `DROP INDEX idx_orders_phone_norm;` 与 `ALTER TABLE orders DROP COLUMN phone_norm;`，确认旧查询仍可用。

清理方法：`rm -rf /tmp/qk-db`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 建了索引，查询还是全表扫 | 条件跳过最左列，或索引列被函数、类型转换包住 | 看计划是否 `SCAN`，`WHERE` 是否 `substr(phone,1,3)=?` | 让索引列裸用；按查询重排索引 |
| 写入 TPS 下降、磁盘增长 | 索引过多，或存在冗余前缀索引 | 统计每张表索引数与写放大比值 | 删被更长索引覆盖的前缀索引、无人查询的索引 |
| 高峰迁移导致全站超时 | 直接 `ALTER TABLE` 且该操作不支持在线执行，触发表复制与锁写 | 看迁移时段的锁等待与慢查询 | 改在线 DDL，回填分批，避开峰值 |
| 连接池耗尽、请求排队 | 长事务或慢查询占着连接，事务里还调了外部接口 | 查 `idle in transaction` 会话数与池等待指标 | 收紧事务边界、设语句超时、池大小按并发定 |
| 死锁日志反复出现 | 不同代码路径以不同顺序更新同一批行 | 看死锁日志里两条相反顺序的 SQL | 统一加锁顺序（按主键升序），缩小事务范围 |

## 安全与生产注意事项

**<u>在生产主库上对大表执行会锁写的 `ALTER TABLE`（未指定在线子句，或操作本身不支持 Online DDL）会让订单写入阻塞，损失按分钟计。</u>** 后果不止是慢：连接池被占满，退款与库存回滚一起停摆，恢复还要等 DDL 结束。缓解：用在线 DDL，先在小表验证耗时，迁移排在低峰并设 `lock_timeout`。

**<u>迁移脚本没有回滚路径或不可重入，失败后只能恢复备份，等于把几小时的已支付订单丢回过去。</u>** 缓解：expand-contract 三段式，每步单独提交、单独验证；回填条件带 `IS NULL` 保证可重跑；删列前留一个版本周期并演练回滚。

**<u>数据库账号权限过大、连接串写在代码或日志里，一次误操作就能删库或泄露凭据。</u>** 缓解：迁移用专用账号，只授予该库 DDL 权限，生产禁止 `DROP`；连接串从密钥管理读取，日志脱敏。

## 本课总结

- 索引是交易：读变快换来写变贵、空间变大，索引数量要按读写比审批。
- 回表才是慢查询的主因；覆盖索引与正确的列顺序能把随机 I/O 降到 0，跳过最左列则索引作废。
- 隔离级别用可见性换并发；锁在提交或回滚前不释放，事务越小越不容易死锁与耗尽连接池。
- 迁移按 expand-contract 走：先兼容、再回填与切读、最后清理，每步可重入、可单独回滚。

## 思考题

`orders` 有 8000 万行、写峰值 1200 TPS，要新增 `phone_norm` 列、建 `(status, created_at)` 复合索引，让列表页从 12 秒降到 200 毫秒且不能停机。请给出迁移顺序、每步的验证数据，以及最可能出事的一步和止损方案。

参考思路：先加可空列，再双写并按主键游标回填（批间限速、条件 `IS NULL` 保证可重入），用“新列计数 vs 旧列表达式计数”对齐作为切读门槛；然后在线建索引，观察一个版本周期再删旧列。最可能出事的是建索引与回填争抢 I/O：止损是限速回填、放到低峰、备好 `DROP INDEX CONCURRENTLY` 与“旧列仍可读”的退路。

## 小测

1. 复合索引 `(status, created_at)` 上，哪条查询用不上这个索引？  
   A. `WHERE status = ?`　B. `WHERE status = ? AND created_at > ?`　C. `WHERE created_at > ?`　D. `WHERE status = ? ORDER BY created_at`
2. 什么情况下查询不需要回表？以晴空商城列表页举例。
3. 按标准定义，可重复读能防住脏读和不可重复读，为什么仍可能出现幻读？
4. 连接池被打满，最先应该查什么？  
   A. 把池上限调大　B. 是否有长事务或慢查询长期占着连接　C. 升级数据库版本　D. 给所有表加索引
5. 场景题：业务要求“12 秒降到 200 毫秒”且不能停机，团队提议在大表上加三个单列索引。你怎么回应，按什么顺序推进？

## 答案与解析

1. **C。**复合索引按 `(status, created_at)` 排序，只给第二列条件用不上有序结构，只能全表扫。A 用第一列；B 是等值加范围；D 用第一列过滤、第二列自然有序，还免排序。
2. `SELECT` 的列全在索引里时不用回表。列表页只要 `status`、`created_at` 和 `id`（`id` 就在索引叶子里），计划显示 `USING COVERING INDEX`；加上 `note` 就必须回表。
3. 可重复读锁的是“已存在行”的可见版本，不阻止别人插入新行；同一事务两次范围查询之间冒出新行就是幻读。标准解法是串行化；InnoDB 的间隙锁、PostgreSQL 的快照隔离能挡掉大部分幻读，代价是更多锁或更早的序列化失败。
4. **B。**池满通常不是池小，而是连接被长时间占住。调大上限（A）只是把压力推给数据库；C、D 与故障无关，加索引反而增加写成本。
5. 先不接受“三个单列索引”：写放大三倍，而优化器面对多条件通常只选一个索引。顺序是：先用执行计划确认真实查询形态，按等值列在前、`ORDER BY` 列在后设计复合索引并做成覆盖索引；再按 expand-contract 在线建索引，盯写 TPS 与锁等待，用 P95 判断是否达标。

### 动手实验参考

步骤 1 只有第 1 条是 `SCAN`，其余出现 `SEARCH`，耗时差约 500 倍，看量级即可。步骤 2 换顺序后第 3 条从 `SEARCH` 退化为 `SCAN`，但仍覆盖且沿索引顺序无需排序；第 4 条从 `SCAN` 变 `SEARCH`：索引是为某组查询定制的。步骤 3 去掉 `note` 变覆盖索引，列表页返回列越少越好。步骤 4 中 `timeout=0` 立即失败，说明超时只是把“阻塞”翻译成“错误”，锁没消失；`con2` 一直被挡，正是池里一个忘记提交的事务能拖垮整池的原因。步骤 5 第二次回填影响 0 行，证明 `IS NULL` 让脚本可重入；批大小 500 改成 5000 后持锁明显变长，所以批大小按时长定，不按行数定。

## 延伸阅读与下一课

- [PostgreSQL：Indexes](https://www.postgresql.org/docs/current/indexes.html)——索引类型与复合索引。
- [PostgreSQL：Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)——隔离级别与各异常定义。
- [PostgreSQL：CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html)——`CONCURRENTLY` 与遗留的 invalid 索引。
- [MySQL 8.0 Reference Manual：InnoDB Locking](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking.html)——行锁、间隙锁与死锁检测。
- [SQLite：EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html)——执行计划字段含义。
- [HikariCP：About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)——池大小为什么应远小于直觉值。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[SQL、表设计与数据关系](01-sql-tables-and-relationships.md)。
- 下一课：[NoSQL、Redis 与缓存失效](03-nosql-redis-and-caching.md)。
