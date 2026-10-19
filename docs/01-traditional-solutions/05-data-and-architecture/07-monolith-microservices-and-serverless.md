---
title: 单体、微服务与无服务器架构
slug: monolith-microservices-and-serverless
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 60m
prerequisites:
  - data-quality-and-consistency
outcomes:
  - 用部署单元、数据所有权和调用开销三个维度区分单体、模块化单体、微服务与无服务器
  - 用可验证判据判断一个模块是否应当拆出独立部署单元，并说明暂不拆分的理由
  - 为给定场景选择架构形态，写出适用条件、代价、演进路径与常见反模式的修复方向
last_reviewed: 2026-10-19
---

# 单体、微服务与无服务器架构

## 为什么需要学习

晴空商城是 18 万行的单体应用：商品、订单、支付、库存、退款、客服工单同进程，共用一个 MySQL 主库。它撑过三次大促，但大促后 48 小时的退款高峰（日常 30 倍）里，同进程的压缩任务打满 CPU，退款 P95 从 240ms 涨到 9 秒；退款组改一行文案要等目录组两天。

管理层于是说：“我们上微服务吧。”六个月后常见的结果是：一次退款串了 6 个服务、7 次网络跳转，P95 更差；三个服务共用订单表；账单翻倍而人数没变。

问题不是谁更先进。**架构形态不是成熟度刻度，而是与团队规模、故障域和流量形态匹配的部署决策。**

> **核心结论：** 先让边界正确，再让边界分布式；能在一个部署单元里解决的，不要用一次网络调用解决。

## 学习目标

- 能够用*部署单元*、*数据所有权*和调用开销区分四种形态。
- 能够用变更耦合、扩展曲线、故障域、数据所有权判断模块该拆、后拆还是不该拆。
- 能够为业务目标写出选型结论，含适用条件、代价与不适用条件。
- 能够给出分阶段演进路径，并识别四类反模式。

## 前置知识

- 回看上一课：[数据质量、校验与一致性](06-data-quality-and-consistency.md)。
- 知道一次 HTTP 请求/响应的过程，理解“超时”和“连接池”的含义。
- 能读懂 `BEGIN`/`COMMIT` 构成的事务边界。

## 业务场景

晴空商城的现状可量化：一个应用承载 7 个模块，共用一个 MySQL 主库，退款读订单表并写支付流水表；24 人分 3 组共享发布窗口，日均 12 万订单，压缩任务曾让退款 P95 达 9 秒。目标退款 P95 ≤ 500ms、售后可独立发布，月增成本不超过 3000 元。

架构师要回答的是：退款变慢是“没拆分”造成的，还是“一个模块抢占 CPU”造成的？只把压缩任务移出进程，P95 会不会回到 240ms？拆开后那份“必须可对账”的要求由谁承担？

## 核心概念

*部署单元*是可独立构建、发布和回滚的最小产物：一个进程、一组容器或一个函数。*模块*是代码层边界，*服务*是部署层边界，<u>把目录改名成 `services/` 并不产生服务</u>。

*数据所有权*指谁有权定义和修改数据；允许读与允许写，耦合强度完全不同。*故障域*是一次故障能波及的最大范围：同进程内一个模块的内存泄漏会杀掉整个应用。

*微服务*把系统切成多个可独立部署、各自拥有数据、通过网络通信的服务。*无服务器*（serverless）把容量交给平台：以函数为单位按事件触发、按用量计费、可缩容到零。*冷启动*是实例从零初始化的耗时，<u>它影响 P99 尾延迟，不影响平均值</u>。

| 形态 | 部署单元 | 数据 | 调用开销 | 扩缩粒度 |
| --- | --- | --- | --- | --- |
| *单体* | 1 个 | 任何模块可读写任何表 | 进程内，纳秒级 | 只能整体 |
| *模块化单体* | 1 个，边界强制 | 一个库，表有唯一所有者 | 进程内 | 整体，可抽离耗时任务 |
| *微服务* | 每服务 1 个 | 各自独立库，只走 API 或事件 | 网络，毫秒级且会失败 | 按服务 |
| *无服务器* | 每函数 1 个 | 外部托管存储 | 网络 + 平台调度 | 平台自动，可到零 |

## 工作原理

以“客服提交一笔退款”为线索看四种形态的路径：

1. **进入系统**：入口都是负载均衡或 API Gateway，差别从下一跳开始。
2. **单体**：请求进入应用进程，退款直接调订单与支付模块；函数调用共享连接池，“查订单 + 写退款记录”能放进一个本地事务，失败整体回滚。
3. **模块化单体**：退款改调订单模块的公开接口，构建流水线禁止跨模块直连。库是一个、事务也是一个——**边界是纪律，不是网络。**
4. **微服务**：网关路由到退款服务，它再调订单拿快照、调支付发起退款。一次业务变成多次网络往返，多出三类失败：超时、部分成功（钱退了记录没写）、重试放大（超时重试导致重复退款），因此要补幂等、超时预算、熔断与补偿，见[超时、重试、退避与幂等](../03-api-and-integration/05-timeout-retry-backoff-and-idempotency.md)与[熔断、降级与隔离](../03-api-and-integration/06-circuit-breaking-degradation-and-isolation.md)。
5. **跨服务一致性**：一个事务拆成两步，要用 *Saga*（把长事务拆成一组本地事务，失败反向补偿）或 [Outbox、补偿与最终一致性](../03-api-and-integration/11-outbox-compensation-and-eventual-consistency.md) 保证最终一致，靠对账兜底。
6. **无服务器**：事件（对象存储上传、队列消息、定时器、HTTP）到达时平台创建实例；函数必须无状态，数据放外部存储，单次执行有上限。流量为零时实例被回收，下次请求要付冷启动。

两条结论：**先拆读路径与异步消费者，再拆写路径**，因为写路径跨进程立刻要付一致性成本；<u>先还清共享表，再谈拆服务</u>，否则只是拆出两个连着同一个库的进程。

## 架构与选型

| 形态 | 适用 | 不适用 | 主要代价 |
| --- | --- | --- | --- |
| 单体 | 产品未定型、团队小、可整体扩容 | 单模块故障拖垮全站、发布互等 | 变更影响面大 |
| 模块化单体 | 业务复杂但团队不大，需独立发布 | 已大量共享表且无人整改 | 依赖纪律与构建检查 |
| 微服务 | 多团队并行、扩缩曲线差异大 | 数据无 owner；一次业务跨 5 个以上服务 | 运维、一致性、调试成本 |
| 无服务器 | 事件驱动、突发或稀疏流量、短时任务 | 长事务、常驻连接、怕冷启动 | 尾延迟、执行上限 |

判据比形态名更有用，逐条找证据：

| 判据（证据） | 支持拆分 | 反对拆分 |
| --- | --- | --- |
| 变更耦合（提交交集） | 两组代码几乎从不同时改 | 改 A 的 PR 有七成也要改 B |
| 扩展曲线（CPU 与池曲线） | 一个 CPU 密集、一个 IO 密集 | 负载同涨同落 |
| 故障域（复盘时间线） | 该模块曾拖垮全站 | 故障总是同时发生 |
| 数据所有权（写入来源） | 有一方能独立定义表结构 | 多方写同一张表且无 owner |
| 团队边界（on-call 归属） | 有团队能端到端负责 | 拆完无人值班 |

演进分阶段，每步有可验证的退出条件：

1. **单体加固**（单模块拖垮全站）：压缩、导出抽成独立 worker，退出看 P95。
2. **模块化**（发布互等）：定表所有权、只走接口、构建期检查，退出看违规依赖为 0。
3. **抽异步消费者**（已有事件通道）：通知、对账、报表先独立部署，退出看能否独立重放。
4. **抽写路径**（有团队且数据所有权清晰）：先画契约再拆库，退出看幂等与对账覆盖。
5. **局部函数化**（短时突发任务）：转码、导出上无服务器，退出看冷启动是否影响 P95。

四类反模式：**分布式单体**（拆了却必须同时发版）、**共享数据库微服务**（保留耦合还叠加网络故障）、**纳米服务**（一次业务跳 7 次网络）、**函数里做长事务**（触顶并重复执行）。

## 最小示例

问题：把“哪个模块能先独立部署”变成带理由的可复现报告。环境：`python3`（3.8+），只用标准库，不联网；输入依赖图，输出判定与原因。

```python
from collections import defaultdict

# 边类型：sync 同步调用，event 异步事件，table 直接读写对方的数据库表
DEPENDENCIES = {
    "catalog":    [],                                        # 商品目录：最底层被依赖方
    "order":      [("catalog", "sync"), ("inventory", "sync"),
                   ("payment", "sync"), ("notify", "event")],  # 订单编排四条出向边
    "payment":    [("order", "table")],                       # 支付回调直接写订单表
    "inventory":  [("catalog", "sync")],                      # 库存读商品信息
    "aftersales": [("order", "sync"), ("payment", "sync"),
                   ("inventory", "event"), ("notify", "event")],  # 退款与售后
    "crm":        [("aftersales", "table")],                  # 客服工单直接读写售后表
    "notify":     [],                                         # 只是事件的消费者
}
MAX_FAN_OUT = 2   # 出向依赖超过 2 个，说明它还在替别人编排流程
MIN_FAN_IN = 2    # 至少 2 个调用方，说明边界已真实存在

def in_cycle(start):
    """从 start 出发能否再回到 start：能回到就说明两侧必须一起发布。"""
    stack = [target for target, _ in DEPENDENCIES[start]]      # 从直接下游开始
    seen = set()                                               # 防止绕环死循环
    while stack:
        node = stack.pop()
        if node == start:                                      # 又走回起点，成环
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(target for target, _ in DEPENDENCIES[node])  # 继续往下游
    return False

def uses_shared_table(module):
    """任一方向的 table 边都算共享表：读和写对方的表，破坏性一样。"""
    outbound = any(kind == "table" for _, kind in DEPENDENCIES[module])  # 我方写对方表
    inbound = any(kind == "table" for deps in DEPENDENCIES.values()      # 对方写我方表
                  for target, kind in deps if target == module)
    return outbound or inbound

fan_in = defaultdict(int)
for module, deps in DEPENDENCIES.items():
    for target, _ in deps:
        fan_in[target] += 1                                    # 统计被依赖次数

ready, blocked = [], []
print("模块耦合报告（晴空商城现状）")
for module in sorted(DEPENDENCIES):                            # 排序让输出可逐次对比
    out_edges = len(DEPENDENCIES[module])
    reasons = []
    if in_cycle(module):
        reasons.append("参与循环依赖")
    if uses_shared_table(module):
        reasons.append("存在共享表读写")
    if out_edges > MAX_FAN_OUT:
        reasons.append(f"出向依赖过多({out_edges})")
    if fan_in[module] < MIN_FAN_IN:
        reasons.append(f"独立调用方不足({fan_in[module]})")
    verdict = "可先拆分" if not reasons else "暂不拆分"
    print(f"  {module:<10} fan-in={fan_in[module]} fan-out={out_edges} "
          f"共享表={'是' if uses_shared_table(module) else '否'} → {verdict}")
    (ready if not reasons else blocked).append((module, reasons))

print("\n第一批可独立部署：" + "，".join(m for m, _ in ready))
print("暂不拆分的原因：")
for module, reasons in blocked:
    print(f"  {module:<10} " + "；".join(reasons))               # 理由必须对应判据
```

流程三段：建图、算派生量（`fan_in`、`fan_out`、成环、共享表）、按阈值判定并打印理由。把“共享表”编码成边类型而非注释，因为它最难偿还；判定必须带理由，因为<u>只给结论的评审意见无法被验证</u>。

```bash
python3 coupling_report.py
```

预期输出：

```text
模块耦合报告（晴空商城现状）
  aftersales fan-in=1 fan-out=4 共享表=是 → 暂不拆分
  catalog    fan-in=2 fan-out=0 共享表=否 → 可先拆分
  crm        fan-in=0 fan-out=1 共享表=是 → 暂不拆分
  inventory  fan-in=2 fan-out=1 共享表=否 → 可先拆分
  notify     fan-in=2 fan-out=0 共享表=否 → 可先拆分
  order      fan-in=2 fan-out=4 共享表=是 → 暂不拆分
  payment    fan-in=2 fan-out=1 共享表=是 → 暂不拆分

第一批可独立部署：catalog，inventory，notify
暂不拆分的原因：
  aftersales 存在共享表读写；出向依赖过多(4)；独立调用方不足(1)
  crm        存在共享表读写；独立调用方不足(0)
  order      参与循环依赖；存在共享表读写；出向依赖过多(4)
  payment    参与循环依赖；存在共享表读写
```

`order` 与 `payment` 因“支付回调写订单表”互为环，任一方先拆都会退化成分布式事务，应先整改数据所有权。

## 动手实验

前置条件：本机有 `python3`（3.8+），已把脚本存为 `/tmp/dsh-arch-lab/coupling_report.py`，不联网、不需数据库。

1. `mkdir -p /tmp/dsh-arch-lab && cd /tmp/dsh-arch-lab`，保存脚本后运行 `python3 coupling_report.py > baseline.txt`。
2. 新增促销模块：加入 `"promotion": [("catalog", "sync"), ("notify", "event")]`，并给 `order` 追加 `("promotion", "sync")`。
3. 再跑一次，比较 `catalog`、`notify` 的 `fan-in` 与可拆列表，记下 `promotion` 的判定理由。
4. 扮演整改：把 `crm` 的 `("aftersales", "table")` 改成 `("aftersales", "event")`，再跑一次，观察 `aftersales` 与 `crm` 的判定，并写出结论：这一轮整改之后售后能拆了吗？

预期结果：第 3 步后 `catalog`、`notify` 的 `fan-in` 变 3，可拆列表仍是 `catalog，inventory，notify`，`promotion` 被判“独立调用方不足(1)”。第 4 步后 `aftersales` 的“共享表”消失，但仍“暂不拆分”（出向依赖过多 4、调用方不足 1）。

验证方法：`python3 coupling_report.py | diff - baseline.txt`，确认变化只出现在你改的边上，每条理由都能对应判据表。清理方法：`rm -rf /tmp/dsh-arch-lab`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 拆分后 P95 反而变差 | 按技术层拆得太细 | 用 tracing 数跨进程跳数 | 合并过细服务，读路径加缓存，非核心步骤改异步 |
| 两个服务仍须同时上线 | 共享表或共享配置，契约未独立 | 列出双方写入的表与配置项 | 划清数据所有权，用兼容契约替代同步发布 |
| 平时正常，大促超时 | 慢依赖占满连接池，缺舱壁与超时 | 看连接池等待与排队数 | 设超时预算、舱壁隔离、降级返回，独立扩容热点 |
| 账单上涨但流量没涨 | 每服务最低副本乘以环境数 | 按环境统计副本数与空闲 CPU | 合并低流量服务，非生产缩容，稀疏任务改无服务器 |

## 安全与生产注意事项

**<u>每拆出一个部署单元，就多一个可能被错误暴露的入口。</u>** 单体时代内部调用不出进程，拆分后管理接口往往可直接调用；网络策略一宽松或误绑公网，未授权者就能调退款、改价。缓解：服务间强制认证、默认拒绝的网络策略、只经网关暴露、上线前扫描端口。

**<u>拆分会把本地事务变成多步，部分失败就是资金错账。</u>** 支付已退、退款单未写、重试又发一次，后果是重复退款与对账差异。缓解：全链路幂等键、Outbox 保证状态与消息同生共死、按日对账并留人工冲正。

**<u>无服务器函数的环境变量、日志与错误上报常夹带密钥和完整请求体。</u>** 后果是凭据泄露与个人信息超范围留存；缓解：密钥服务托管、日志脱敏、执行角色最小权限。

## 本课总结

- 选型看三件事：几个部署单元、数据归谁所有、调用是否跨网络。
- 判据要落到证据上：变更耦合、扩展曲线、故障域、数据所有权。
- 模块化单体用纪律换本地事务；微服务用复杂度换独立性，顺序是加固、模块化、抽异步消费者、抽写路径、局部函数化。
- 共享表与循环依赖是前置债务，<u>不还清就拆，只会得到一台分布式单体</u>。

## 思考题

晴空商城要在 3 个月内把退款 P95 降到 500ms，预算每月 3000 元，24 人团队无人有 Kubernetes 经验，管理层却坚持一次拆成 6 个服务。请给出替代方案，说明先做哪一步、用什么证据说服管理层；若你判断拆服务确实必要，又用哪条判据支撑？

参考思路：先量化收益差——把压缩任务抽成独立 worker 可能已让 P95 回到 240ms，成本远低于 6 套服务。说服材料应是连接池等待、CPU 争抢、发布阻塞天数与成本估算。若确需拆服务，判据通常是“独立团队 + 清晰数据所有权 + 扩缩曲线差异”，并分阶段交付、保留回滚点。

## 小测

1. 下列哪项最能区分模块化单体与微服务？  
   A. 代码目录是否按业务划分　B. 模块之间是否通过网络调用　C. 是否使用容器　D. 是否使用消息队列
2. “服务之间直接读写对方的数据库表”属于哪种反模式？它保留了单体的什么缺点？
3. 判断：无服务器架构因为没有服务器，所以不需要考虑容量与超时限制。对还是错？
4. 场景题：客服要“导出上月退款明细”，每月 1 号跑一次、单次 40 分钟，其余时间无流量。它应并入退款服务常驻，还是做成无服务器定时任务？请说明判据与风险。

## 答案与解析

1. **B。**模块化单体仍是进程内调用与本地事务，只靠纪律与构建检查约束边界；微服务的边界是网络。A 是代码组织方式，C、D 是工具，任何形态都能用。
2. **共享数据库微服务。**它保留了单体的耦合：对方改表结构你就会被连带破坏，也无法独立迁移，还叠加网络不可靠。
3. **错。**函数有执行时长、并发上限与冷启动，容量从“选机器”变成“选配额与并发策略”；出网、连接数和临时存储同样有约束。
4. 应做成无服务器定时任务：流量稀疏、时长接近上限但不超过、无强事务、失败可重跑。风险是 40 分钟触顶（需分批续跑）、冷启动、个人信息外泄（最小权限与保留期）、重跑需幂等。

### 动手实验参考

第 3 步：`catalog` 与 `notify` 的 `fan-in` 变 3，说明“被依赖更多”不等于“更该先拆”；`promotion` 只有 1 个调用方，边界未被验证，暂不拆。第 4 步：把 `crm→aftersales` 改成 `event` 只还清一半债务，`aftersales` 仍受出向依赖与调用方数量限制——评分看能否逐条对应判据。

## 延伸阅读与下一课

- Martin Fowler，[MonolithFirst](https://martinfowler.com/bliki/MonolithFirst.html)：为什么多数成功案例先做单体。
- Martin Fowler，[Microservices Resource Guide](https://martinfowler.com/microservices/)：微服务模式与文章索引。
- AWS 文档，[Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)：执行时长与并发上限等硬约束。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[数据质量、校验与一致性](06-data-quality-and-consistency.md)。
- 下一课：[API Gateway 与服务发现](08-api-gateway-and-service-discovery.md)。
