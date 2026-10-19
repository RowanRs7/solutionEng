---
title: 备份、恢复与业务连续性
slug: backup-restore-and-business-continuity
module: traditional-solutions
stage: operate-and-optimize
type: core
difficulty: intermediate
duration: 50m
prerequisites:
  - incident-response-and-postmortem
outcomes:
  - 为四个数据域写出 RPO 与 RTO 目标，并说明各自的批准人
  - 设计全量加增量加日志归档的备份链，并指出每层兑现的最坏 RPO
  - 用备份清单核对 RPO 达标情况，并写出一次恢复演练的证据与清理动作
last_reviewed: 2026-10-19
---

# 备份、恢复与业务连续性

## 为什么需要学习

2026 年 9 月，晴空商城一位运维执行清理脚本时连到了生产库，`DELETE FROM refund_event WHERE created_at < '2026-08-01'` 条件写错，变成全表删除，300 万条退款事件消失。真正麻烦的是随后九小时暴露的问题：

- 每日 02:00 的全量备份确实成功，但从没人确认它能不能被恢复。
- 备份加密了，密钥在那台已下线主机的本地目录里，找了两个小时。
- 恢复脚本依赖一个三个月前就迁走的备份服务器主机名。
- 次日 01:40 才恢复完，丢了 14 小时退款事件；对账差 1200 笔，客服答不出“退款到哪了”。

这个团队有备份，却没有恢复能力。两者之间的差距正是本课要补的部分。

> **核心结论：** 备份的价值不在“存下来了”，而在“事故当天能回到已知时间点、用可度量的时间恢复出来”，这一点只能由演练证据支撑。

## 学习目标

完成本课后，你能够：

- 为晴空商城的四个数据域写出 *RPO* 与 *RTO* 目标，并指出每个目标由谁批准、依据是什么。
- 设计一条“全量 + 增量 + 日志归档”的备份链，并说明每一层能兑现多少分钟的最坏 RPO。
- 用备份清单核对某数据域能否兑现 RPO，并判断最近演练记录是否有效。
- 写出一份恢复演练的步骤、证据采集项、验证方法与清理动作。

## 前置知识

- 回看上一课：[故障分级、响应与复盘](06-incident-response-and-postmortem.md)。
- 知道全量备份、增量备份和数据库日志归档分别备份了什么。
- 大致理解事务提交与 WAL（预写日志）的关系，能读懂 `SELECT count(*)`。
- 会运行 `python3` 脚本，知道 `sqlite3` 是 Python 标准库自带的。

## 业务场景

本单元继续跟退款服务，换到“数据被毁之后怎么办”这个侧面。晴空商城按“丢了会怎样”分成四域：

| 数据域 | 内容 | 业务后果 | RPO | RTO | 批准人 |
| --- | --- | --- | --- | --- | --- |
| 支付流水 | 支付单、退款流水、对账文件 | 资金对不上，监管问询 | 5 分钟 | 1 小时 | 财务 |
| 退款与工单 | `refund`、`refund_event`、客服工单 | 退款停滞，客服无法答复 | 15 分钟 | 4 小时 | 客服 |
| 商品目录与图片 | 商品、价格、图片 | 可降级为只读缓存继续卖货 | 24 小时 | 8 小时 | 商品运营 |
| 报表与日志 | 数仓宽表、审计日志 | 决策延迟，审计难追溯 | 24 小时 | 24 小时 | 数据 |

约束有四条：退款可追溯五年；大促期间最多 2 小时给用户答复；每月 1–3 日冻结期不做破坏性变更；单可用区故障必须扛得住。这些数字不是架构师一个人拍的，它们是业务方对“能丢多少、能停多久”的书面授权。

## 核心概念

*备份*是把数据在某一时刻的副本写到另一处存储。*恢复点（restore point）*是这个副本对应的时刻；<u>备份文件存在不等于恢复点可用，读不出来的备份不算恢复点</u>。

*恢复点目标（RPO）*回答“允许丢多少数据”，等于事故时刻与最近一个可用恢复点之间的距离。*恢复时间目标（RTO）*回答“允许停多久”，从事故发生算到业务重新可用。**RPO 看过去，RTO 看未来，两者都必须由业务方批准，不能由运维单方面承诺。**

*备份链*是“一次全量 + 若干增量或日志归档”构成的依赖序列，恢复时必须从链首重放到目标时刻，<u>所以增量链越长，恢复越慢，RTO 越难兑现</u>。

*恢复演练*是在隔离环境按真实步骤恢复一次并记录各阶段耗时的活动。*业务连续性计划（BCP）*是“人、流程、备用设施、对外沟通”的完整安排，*灾难恢复（DR）*只是其中恢复 IT 系统的部分。*不可变备份*指保留期内无法删除或覆盖的副本；*3-2-1 规则*要求 3 份副本、2 种介质、1 份异地。

| 概念 | 回答的问题 | 计量单位 | 晴空商城例子 | 常见误用 |
| --- | --- | --- | --- | --- |
| RPO | 允许丢多少数据 | 分钟 | 支付流水 5 分钟 | 用平均备份间隔代替最坏间隔 |
| RTO | 允许停多久 | 分钟或小时 | 退款与工单 4 小时 | 只算数据库启动，不算密钥、入口与验证 |
| 演练记录 | 当前恢复能力有多大 | 分钟加证据 | 10-05，52 分钟 | 一年前演练一次就宣称“已演练” |

## 工作原理

一次“从定目标到事故当天恢复”的链路按时间顺序分为九步：

1. **分级数据**：按“丢了会怎样”划分数据域，一个域不达标就不要牵连全库。
2. **定 RPO 与 RTO**：业务方书面批准并写进清单；<u>目标同时决定成本，先问批准人愿不愿付</u>。
3. **选方式与频率**：让最坏间隔不超过 RPO。RPO 5 分钟必须有日志归档，每日全量做不到。
4. **执行并记账**：每条记录含起止时间、大小、校验和、密钥版本、保留截止日。
5. **加密与异地**：传输与静态都加密，至少一份在另一故障域，关键域配不可变保留期。
6. **自动校验**：校验和只证明“没坏在传输上”，还要真的打开备份读一次行数。
7. **演练**：隔离环境按真实顺序恢复并计时，记下每阶段耗时与卡住处。
8. **事故当天**：判定范围 → 选最近一个**校验通过**的恢复点 → 按序恢复密钥与配置、数据库、应用、入口、数据补偿。
9. **复盘**：演练时长与真实时长逐阶段对照，缺口写回清单。

第 8 步最常被写反。**密钥和配置必须最先恢复**，因为备份是加密的、脚本要读配置；<u>恢复到一半才发现密钥版本对不上，等于白用一次事故窗口</u>。

## 架构与选型

| 备份方式 | 可达 RPO | 可达 RTO | 成本 | 主要风险 |
| --- | --- | --- | --- | --- |
| 逻辑导出（`pg_dump`） | 小时级 | 小时级 | 低 | 大库导出慢，恢复要重建索引 |
| 物理基础备份 + WAL 归档 | 分钟级 | 分钟到小时 | 中 | 归档链复杂，链断则 RPO 退化 |
| 存储卷快照 | 分钟级 | 分钟级 | 中高 | 需保证快照时刻的文件系统一致性 |
| 云托管自动备份 + PITR | 分钟级 | 小时级 | 订阅费 | 恢复受控制台、配额与权限限制 |
| 对象存储版本化 + 跨区复制 | 分钟级 | 分钟级 | 中 | 版本膨胀，不配删除保护等于没有 |

| 场景 | 建议 | 理由 |
| --- | --- | --- |
| 支付流水这类资金数据 | 物理备份 + WAL 归档 + 异地 | RPO 5 分钟且不接受批量丢失 |
| 商品目录与图片 | 每日全量 + 对象存储版本化 | 数据可重建，RTO 宽松，可降级只读 |
| 已用托管库且 RPO 15 分钟 | 托管 PITR + 定期导出到自管存储 | 同时防误删与供应商级故障 |
| 每天只写几十条的表单系统 | 每日全量即可，不必上 PITR | 重方案的复杂度高于收益 |

选型收敛成四个问题：允许丢多少、允许停多久、恢复由谁执行、能否接受恢复能力由供应商决定。前两个决定备份方式，后两个决定要不要自管导出。

**<u>只有一种备份方式时，它既是备份也是单点。</u>**

## 最小示例

问题：体检一份备份清单——能否兑现 RPO，最近演练还能否证明 RTO。

环境：Python 3.8 以上，只用标准库；输入是内联清单，输出逐域判定与退出码。

```python
#!/usr/bin/env python3
"""drill_report.py：用备份清单核对 RPO，用演练记录核对 RTO。"""
from datetime import datetime

ISO = "%Y-%m-%dT%H:%M:%S"  # 统一时间格式，避免不同来源的时间串解析失败

# 业务方书面批准的目标，固化在脚本里而不是只写在文档里：
# 目标进了代码，不达标就是一条可见的失败，而不是一句"下次注意"。
TARGETS = {
    "payment_ledger": {"rpo_minutes": 5, "rto_minutes": 60},
    "refund": {"rpo_minutes": 15, "rto_minutes": 240},
    "catalog": {"rpo_minutes": 1440, "rto_minutes": 480},
}

# 观测窗口结束时间，等价于"如果事故就发生在这一刻"。
NOW = datetime.strptime("2026-10-18T10:20:00", ISO)

# 每个数据域可用的恢复点：(时间, 是否通过校验)。
# 只有校验通过的记录才算数：读不出来的备份只是占用了存储。
RESTORE_POINTS = {
    "payment_ledger": [
        ("2026-10-18T10:00:00", True),
        ("2026-10-18T10:05:00", True),
        ("2026-10-18T10:10:00", False),  # 归档分片缺失，校验失败
        ("2026-10-18T10:15:00", True),
    ],
    "refund": [
        ("2026-10-18T02:00:00", True),
        ("2026-10-18T02:15:00", True),
        ("2026-10-18T02:30:00", False),
        ("2026-10-18T10:15:00", True),
    ],
    "catalog": [  # 每日全量，只有两个恢复点
        ("2026-10-17T02:00:00", True),
        ("2026-10-18T02:00:00", True),
    ],
}

# 最近一次恢复演练：(开始时间, 完成时间)。从未演练过的域不写在这里。
DRILLS = {
    "payment_ledger": ("2026-10-05T09:00:00", "2026-10-05T09:52:00"),
    "refund": ("2026-10-05T14:00:00", "2026-10-05T19:10:00"),
    "catalog": ("2026-07-11T09:00:00", "2026-07-11T11:30:00"),
}

DRILL_MAX_AGE_DAYS = 90  # 超过 90 天的演练记录不能代表今天的能力


def worst_rpo_minutes(points, now):
    """最坏 RPO 取相邻可用恢复点的最大间隔，而不是平均值。"""
    verified = sorted(datetime.strptime(t, ISO) for t, ok in points if ok)
    if not verified:
        return None  # 没有任何可用恢复点，等价于 RPO 无穷大
    # 事故可能恰好落在下一次备份之前，所以窗口末尾这一段也要算进去。
    edges = verified + [now]
    return max(int((b - a).total_seconds() // 60) for a, b in zip(edges, edges[1:]))


def main():
    failures = []
    for domain, target in TARGETS.items():
        print(f"数据域 {domain}")
        rpo = worst_rpo_minutes(RESTORE_POINTS.get(domain, []), NOW)
        if rpo is None:
            failures.append(domain)
            print("  RPO 无可用恢复点 → 不达标")
        else:
            ok = rpo <= target["rpo_minutes"]
            failures += [] if ok else [domain]
            print(f"  RPO 最坏间隔 {rpo} 分钟（目标 {target['rpo_minutes']}）→ {'达标' if ok else '不达标'}")

        if domain not in DRILLS:
            failures.append(domain)
            print("  RTO 从未演练 → 不达标")
            continue
        started, finished = (datetime.strptime(t, ISO) for t in DRILLS[domain])
        minutes = int((finished - started).total_seconds() // 60)
        rto_ok = minutes <= target["rto_minutes"]
        failures += [] if rto_ok else [domain]
        print(f"  RTO 演练 {minutes} 分钟（目标 {target['rto_minutes']}）→ {'达标' if rto_ok else '不达标'}")
        age = (NOW - finished).days
        if age > DRILL_MAX_AGE_DAYS:  # 演练过期与演练超时是两种不同的缺口
            failures.append(domain)
            print(f"  演练距今 {age} 天，超过 {DRILL_MAX_AGE_DAYS} 天 → 记录失效")
    print(f"结论：{len(set(failures))} 个数据域存在缺口")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

运行与预期输出：

```console
$ python3 drill_report.py
数据域 payment_ledger
  RPO 最坏间隔 10 分钟（目标 5）→ 不达标
  RTO 演练 52 分钟（目标 60）→ 达标
数据域 refund
  RPO 最坏间隔 480 分钟（目标 15）→ 不达标
  RTO 演练 310 分钟（目标 240）→ 不达标
数据域 catalog
  RPO 最坏间隔 1440 分钟（目标 1440）→ 达标
  RTO 演练 150 分钟（目标 480）→ 达标
  演练距今 98 天，超过 90 天 → 记录失效
结论：3 个数据域存在缺口
$ echo $?
1
```

流程是：剔掉校验失败的恢复点 → 补上窗口末尾一段 → 取最大间隔与 RPO 比较 → 比演练时长与记录年龄 → 用退出码把结论交给流水线。

两处值得停一下。`payment_ledger` 每 5 分钟一个恢复点，但 10:10 那条校验失败，最坏间隔变成 10 分钟——**一次校验失败就会吃光全部余量**。`catalog` 的 1440 分钟恰好等于目标，判“达标”却毫无余量：<u>RPO 等于目标，意味着任何一次备份失败都立刻不达标</u>。

## 动手实验

### 目标

在 SQLite 上走一遍“在线备份 → 校验 → 误删 → 恢复”，看清热备份和 `cp` 的区别。

### 前置条件

Python 3.8 以上（自带 `sqlite3`），无需网络和数据库服务。所有文件都建在 `/tmp` 下的临时目录里，不污染工作区。

### 步骤

1. 建生产库，开 WAL 模式，写入 3 条退款事件。
2. 用 `Connection.backup()` 做在线热备份到 `snapshot.db`。
3. 记录备份文件的 sha256，并以**只读方式**打开备份读出行数。
4. 模拟事故：`DELETE FROM refund_event` 清空全表。
5. 从备份整表回灌，核对行数。
6. 对照实验：checkpoint 后新写一条只存在于 WAL 的记录，再 `cp shop.db naive.db`，看副本少了什么。

```console
$ mkdir -p /tmp/lesson07-drill && cd /tmp/lesson07-drill
$ python3 - <<'PY'
import hashlib, pathlib, shutil, sqlite3

# 1. 生产库用 WAL 模式：这是 SQLite 在线热备份的常见前提
con = sqlite3.connect("shop.db")
con.execute("PRAGMA journal_mode=WAL")
con.executescript("""
CREATE TABLE refund_event (id TEXT PRIMARY KEY, refund_id TEXT NOT NULL, note TEXT);
INSERT INTO refund_event VALUES
  ('E-1','R-1001','created'), ('E-2','R-1001','approved'), ('E-3','R-1002','created');
""")
con.commit()
print("备份前生产行数:", con.execute("SELECT count(*) FROM refund_event").fetchone()[0])

# 2. 在线热备份：走 backup API，业务不必停写
snap = sqlite3.connect("snapshot.db")
con.backup(snap)   # 快照是一致性视图，不会读到写了一半的事务
snap.close()

# 3. 校验：sha256 只证明文件没被改坏，能读出行数才证明备份可用
digest = hashlib.sha256(pathlib.Path("snapshot.db").read_bytes()).hexdigest()
print("备份 sha256 前 16 位:", digest[:16])
ro = sqlite3.connect("file:snapshot.db?mode=ro", uri=True)  # 只读打开，校验动作不改备份
print("备份可读行数:", ro.execute("SELECT count(*) FROM refund_event").fetchone()[0])
ro.close()

# 4. 模拟误删：条件写错，全表清空
con.execute("DELETE FROM refund_event")
con.commit()
print("事故后生产行数:", con.execute("SELECT count(*) FROM refund_event").fetchone()[0])

# 5. 恢复：把备份表整段回灌，恢复点即"备份完成时刻"
con.execute("ATTACH DATABASE 'snapshot.db' AS bak")
con.execute("INSERT INTO refund_event SELECT * FROM bak.refund_event")
con.commit()
con.execute("DETACH DATABASE bak")
print("恢复后生产行数:", con.execute("SELECT count(*) FROM refund_event").fetchone()[0])

# 6. 对照实验：先把已有数据 checkpoint 进主文件，再写一条只存在 WAL 里的新事件
con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
con.execute("INSERT INTO refund_event VALUES ('E-4','R-1003','created')")
con.commit()
shutil.copyfile("shop.db", "naive.db")  # 最常见的"备份脚本就是 cp"
naive = sqlite3.connect("naive.db")
print("cp 副本行数:", naive.execute("SELECT count(*) FROM refund_event").fetchone()[0],
      "生产行数:", con.execute("SELECT count(*) FROM refund_event").fetchone()[0])
naive.close()
con.close()
PY
```

### 预期结果

```text
备份前生产行数: 3
备份 sha256 前 16 位: 257a4bccfccaa4b2
备份可读行数: 3
事故后生产行数: 0
恢复后生产行数: 3
cp 副本行数: 3 生产行数: 4
```

### 验证方法

- 第 3 步读出 `3`：备份不只是“写成功”，还“能打开、能查询”。
- 第 4 到 5 步从 `0` 回到 `3`：这是一次真恢复，而不是对着备份做 `ls`。
- 第 6 步副本 `3` 而生产 `4`：`cp` 悄悄丢了一条已提交记录，脚本却仍显示“成功”；把第 3 步改成可写连接再跑，还能看到校验动作改动了 `snapshot.db`。

### 清理方法

```console
$ cd .. && rm -rf /tmp/lesson07-drill
```

执行前确认路径正是这个临时目录，不要在仓库目录下删除。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 备份天天成功，恢复时表不存在 | 用 `cp` 拷在线库文件，数据还在 WAL 里 | 只读打开备份执行 `SELECT count(*)` | 改用备份 API、物理工具或快照 |
| 恢复出来比预期旧几小时 | 只回全量，没接增量或日志归档 | 查清单里最新可用恢复点 | 补齐归档，演练完整链 |
| 演练 40 分钟，真实事故 9 小时 | 演练在空库上做，没算密钥与入口 | 对比演练记录与真实时间线 | 用生产规模数据演练，密钥与入口纳入计时 |
| 某天起备份全部消失 | 保留策略误配，或权限与生产同域 | 查作业日志有无 `skipped` 与删除审计 | 保留策略显式化，删除双人审批，配不可变 |
| 报表说 RPO 达标，事故仍丢半天数据 | 用平均间隔或“最后一次成功”算 | 按最坏相邻间隔重算 | 把最坏间隔做成常规指标并告警 |

## 安全与生产注意事项

**<u>未加密的备份是第二份完整的数据泄露源。</u>** 支付流水与工单含账户、手机号和退款原因，备份常被复制到共享文件服务器或对象存储桶，那里权限通常比生产库宽松。缓解：静态与传输都加密，密钥独立管理并与备份存储分权，恢复需双人确认并留审计。

**<u>能删除备份的凭据，等于能一次性销毁公司的恢复能力。</u>** 勒索软件第一目标常是备份目录，而“备份账号”常为省事被授予读写删全权限。缓解：写入与删除分权、生产账号无删除权、保留期内配不可变、留离线副本，并定期验证审计。

**<u>恢复演练必须在隔离环境进行，禁止把生产备份回灌生产库。</u>** 回灌会覆盖事故后新产生的合法数据，把一次故障变成两次。缓解：演练用独立网络与凭据，演练库带 `drill-` 前缀并设过期回收。

## 本课总结

- **RPO 看过去、RTO 看未来**，两者都由业务方批准并写进系统清单。
- 兑现 RPO 的是**最坏相邻间隔**而非平均间隔；一次校验失败就会吃光余量。
- 校验和只证明文件没坏，**能打开读出行数**才证明备份是恢复点。
- 恢复顺序是**密钥与配置、数据库、应用、入口、数据补偿**，顺序写反会白耗事故窗口。
- 演练证据比“我们有备份”可信；**过期记录不代表今天的能力**。

## 思考题

大促冻结期临近，支付流水的 RPO 只能做到 15 分钟而目标是 5 分钟；补齐日志归档要改主库配置并停写约 20 分钟。请给出方案：选“接受现状”“申请变更窗口”还是“临时降级”，理由是什么，需要谁批准、留什么证据。

参考思路：先写清事实——15 分钟缺口意味着最坏丢 15 分钟流水，能否承受由财务负责人判断。路径有三：变更排到冻结期后第一个窗口，期间对大额交易加人工对账；用双写或从库旁路采集缩短缺口；把降级当成明确的风险接受并书面记录负责人与复核日期。无论选哪条都要留下“谁批的、依据什么、何时失效”。

## 小测

1. 某数据域每小时全量备份一次且从未失败，它的 RPO 是多少？
   A. 1 小时　B. 30 分钟　C. 最近一个校验通过的恢复点到事故时刻的距离　D. 0
2. 判断：备份文件存在且 sha256 校验通过，就可以把它算作可用恢复点。
3. 恢复顺序里，为什么密钥与配置要排在数据库之前？
4. 一条演练记录距今 200 天、当时耗时 30 分钟，RTO 目标是 2 小时。它能说明当前 RTO 达标吗？
5. 场景题：财务要求支付流水 RPO 不超过 5 分钟。现有方案是每日 02:00 全量加每小时增量，且只保留一份在同一个可用区。作为架构师，你会提出哪三个必须修改的点？

## 答案与解析

1. **C。**RPO 是从事故时刻往回数到最近一个可用恢复点的距离，取决于事故何时发生、该点是否通过校验。A、B 把备份间隔当 RPO，忽略了事故落在两次备份之间、最近备份也可能损坏；D 只在持续归档且零丢失时接近。
2. **错。**校验和只覆盖“文件未被改动或截断”，不覆盖“是否完整、能否恢复”：可能缺归档分片、缺 WAL、缺密钥版本。<u>必须真的打开备份读一次</u>。
3. 备份加密，恢复脚本要读配置才知道连哪里、用哪个密钥版本。先恢复数据再找密钥，窗口会耗在等权限审批上；密钥或配置不可用，数据回来服务也起不来。
4. 不能。30 分钟只是 200 天前的测量值，期间数据量、依赖人员都可能变；200 天未演练本身就是缺口。演练记录要有有效期（示例取 90 天），过期只能作历史参考。
5. 三点：加日志或 WAL 归档，让最坏间隔进入分钟级（全量加每小时增量做不到 5 分钟）；加异地与不可变副本，单可用区单副本扛不住区域故障也防不住误删；把“校验通过才算恢复点”和定期演练写进流程，否则前两点只是纸面能力。

### 动手实验参考

关键不是敲对 API，而是看到三件事：backup API 在业务不停写时给出一致快照；校验必须真的读一次；`cp` 会静默丢数据。若把第 2 步换成 `shutil.copyfile("shop.db", "snapshot.db")` 再重跑，第 3 步会读到 `0` 行或直接报表不存在——这就是最常见的“备份显示成功、恢复没有数据”。清理时确认删除的是 `/tmp/lesson07-drill`。

## 延伸阅读与下一课

- SQLite 官方文档：[Backup API](https://www.sqlite.org/backup.html)（在线热备份的语义与调用方式）。
- SQLite 官方文档：[Write-Ahead Logging](https://www.sqlite.org/wal.html)（WAL 文件与 checkpoint 的关系，解释了为什么不能直接 `cp`）。
- PostgreSQL 官方文档：[Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html)（基础备份加 WAL 归档如何兑现分钟级 RPO）。
- Google SRE Book：[Data Integrity: What You Read Is What You Wrote](https://sre.google/sre-book/data-integrity/)（备份、校验与恢复在可靠性体系中的位置）。
- ISO/IEC 22301:2019《安全与韧性——业务连续性管理体系》（BCM 体系要求，不含具体技术实现）。
- NIST SP 800-34 Rev.1《Contingency Planning Guide for Federal Information Systems》（DR 与 BCP 的规划步骤与演练要求）。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[故障分级、响应与复盘](06-incident-response-and-postmortem.md)。
- 下一课：[Runbook 与知识移交](08-runbooks-and-operational-handover.md)。
