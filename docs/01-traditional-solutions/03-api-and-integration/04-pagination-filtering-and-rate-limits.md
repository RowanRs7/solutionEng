---
title: 分页、过滤、批量与限流
slug: pagination-filtering-and-rate-limits
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - validation-errors-and-versioning
outcomes:
  - 对比 offset 分页与游标分页的失效条件，并为订单列表选出可解释的一种
  - 写出带 limit 上限、字段白名单和稳定排序键的列表接口契约
  - 说明批量操作选择全或无还是部分成功，并写出可核对的响应结构
  - 用令牌桶参数推算突发上限与平均速率，并解释 429 与 Retry-After 的含义
last_reviewed: 2026-10-19
---

# 分页、过滤、批量与限流

## 为什么需要学习

晴空商城的客服翻到工单列表第 3 页，发现第 2 页最后一单又出现了，同一单被备注两次、仓库也处理两次。同一周，ERP 每五分钟拉一次全量订单把数据库 CPU 打到 90%，开放给物流的接口被脚本刷了二十万次，商城首页开始超时。

三个故障来源相同：列表接口只写了“能返回数据”，没写翻页依据、可查字段、批量失败如何处理、每秒允许调用多少次。**这些不是优化项，而是接口契约的一部分。**

> **核心结论：** 分页、过滤、批量与限流的本质是同一件事——用明确的契约换取可预测的成本，让调用方知道“怎么翻完”“能查什么”“失败几条”“还能调几次”。

## 学习目标

完成本课后，你能够：

- 指出一次 offset 分页在“翻页期间有新数据插入”时会产生重复行或漏行，并说明游标分页为什么能规避。
- 为 `GET /api/orders` 写出 `limit` 上限、`sort` 白名单、过滤字段枚举与递归翻页的完整契约。
- 区分批量操作的“全或无”和“部分成功”语义，并给出带 `operation_id` 的响应结构。
- 用令牌桶参数算出接口的突发上限与平均速率，并区分 429、`Retry-After` 与配额用尽。
- 运行本课的标准库脚本，复现重复行、游标翻页和 429 序列。

## 前置知识

- 回看上一课：[参数校验、错误模型与版本管理](03-validation-errors-and-versioning.md)。
- 知道 HTTP 方法、状态码和查询字符串的作用，能读懂一次 `GET` 请求的完整报文。
- 知道列表数据通常来自数据库表，并理解“排序需要索引”。
- 能在本机运行 `python3 --version`；本课示例只用标准库。

## 业务场景

“晴空商城”的退款集成服务有四类调用方，本单元只看它们与列表类接口的接触面：

- 客服工作台展示工单列表，按状态筛选、按创建时间或金额排序，每页 20 条，要翻到底。
- 财务对账每五分钟增量拉一次订单，要求“不漏一条、不重复一条”。
- 客服主管勾选最多 200 单发起批量退款，少数可能已被退过，业务不接受“一条脏数据导致整批失败”。
- 物流合作方调用开放 API 查运单，合同约定每分钟 600 次，超出要被拒绝而不是拖慢主站。

架构师要回答：翻页用什么锚点？能否随意指定排序字段？失败几单怎么告知？限流按什么维度统计？答案都要写进契约，而不是等故障后补。

## 核心概念

*分页*把大结果集切成若干页返回，以控制响应大小与查询成本。*offset 分页*用“跳过多少条、取多少条”定位；它简单，但依赖“第 N 条”，而位置会随数据增删移动。

*游标分页*（cursor pagination）用“上一页最后一行的排序键值”定位。*游标*（cursor）是编码该值的字符串，服务端按“排在它之后的行”继续取，不关心前面有多少条。

| 对比项 | offset 分页 | 游标分页 |
| --- | --- | --- |
| 定位依据 | 绝对位置（跳过 N 条） | 相对位置（排序键之后） |
| 翻页中插入新数据 | 位置后移，出现重复行 | 锚点不变，新数据下次才出现 |
| 翻页中删除数据 | 后面的行前移，出现漏行 | 只跳过被删的行 |
| 深翻页成本 | 扫描并丢弃前 N 条，越翻越慢 | 走索引定位，与页码无关 |
| 能否跳到第 37 页 | 能 | 不能，只能顺序前进 |

*过滤*按字段条件缩小结果集，如 `status=paid`。*排序键*是排序所依据的字段；<u>排序键必须能唯一确定顺序，通常由业务时间和主键组成</u>，否则相同值的行顺序漂移，游标就会重复或漏行。

*批量操作*是在一次请求里处理多条记录，关键不在“快”，而在失败语义：*全或无*（atomic）表示任一条失败则整批不生效；*部分成功*表示逐条处理并分别报告结果。

| 批量语义 | 适用场景 | 调用方看到的结果 | 代价 |
| --- | --- | --- | --- |
| 全或无 | 转账、扣库存等强一致动作 | 要么全成功，要么全回滚 | 一条脏数据阻塞整批 |
| 部分成功 | 批量退款、打标、导入 | 每项一条状态，失败项可单独重试 | 需逐项读结果，重试要对齐幂等键 |

*限流*（rate limiting）限制单位时间内的请求次数，保护服务端自身；*配额*（quota）是更长时间尺度的总量限制，如“每月 100 万次”。<u>配额用尽要等下个周期，限流只要求等几秒</u>，二者常被混淆。

| 算法 | 计数方式 | 突发能力 | 典型问题 |
| --- | --- | --- | --- |
| 固定窗口 | 每窗独立计数 | 有，边界处可翻倍 | 切换瞬间放过两倍流量 |
| 滑动窗口 | 按最近 N 秒加权或分桶 | 平滑 | 实现与存储成本更高 |
| 令牌桶 | 按固定速率补令牌，攒满为止 | 有，上限即桶容量 | 参数需按容量与速率推算 |
| 漏桶 | 请求排队，按固定速率流出 | 无，只允许匀速 | 突发被排队，延迟上升 |

*令牌桶*（token bucket）最常用：*容量*决定能容忍多大突发，*补充速率*决定长期平均速率。容量 10、每秒补 1 个，表示允许瞬时 10 次、长期每秒 1 次。

## 工作原理

以客服工作台加载“待退款工单列表”为例，一次翻页请求按以下顺序发生：

1. 客户端发送 `GET /api/orders?status=paid&sort=-created_at&limit=20`，不带游标表示第一页。
2. 服务端在入口校验：`limit` 在 1 到 100、`sort` 在白名单内、`status` 是已知枚举值，任一不满足直接返回 400 与 `invalid_sort` 之类错误码，不进入查询。
3. 服务端按 `(created_at, id)` 排序并只取 `limit + 1` 条：多取的一条用来判断有没有下一页，避免多做一次 `COUNT(*)`。
4. 若拿到 21 条，丢弃第 21 条，用第 20 条的 `(created_at, id)` 编码游标，返回 `next_cursor` 与 `has_more: true`。
5. 客户端带 `cursor=...` 请求下一页；服务端解成边界值，只查“排序键小于该边界”的行，因此新插入的订单不会挤动已有位置。
6. 请求在网关层先过限流：按 `X-Api-Key` 取出对应令牌桶，有令牌就放行并扣一个，没有就返回 429 与 `Retry-After`，请求到不了业务代码。
7. 批量退款走另一条路径：客户端提交带 `operation_id` 的批次，服务端先校验批次大小（如不超过 200 项），再逐项处理。
8. 客户端按语义行动：读完 `has_more: false` 才算翻完；429 时按 `Retry-After` 等待而非立刻重试；批量失败项用同一 `operation_id` 加单项键重试。

贯穿设计的分工是：**列表接口稳定切分结果，限流挡住超额成本，批量接口把失败定位到具体一条。**

## 架构与选型

| 决策点 | 选项 | 适用 | 不适用或代价 | 判断依据 |
| --- | --- | --- | --- | --- |
| 翻页方式 | offset 分页 | 后台、结果集小、需跳页 | 深翻页慢；数据变化时重复或漏行 | 是否允许跳页，数据是否持续写入 |
| 翻页方式 | 游标分页 | 订单流、对账增量 | 不能跳页，游标需签名防篡改 | 是否要求“不漏不重” |
| 批量语义 | 部分成功 + `operation_id` | 批量退款、打标 | 调用方需实现逐项重试 | 是否允许“成功一部分” |
| 限流维度 | 按 API Key / 用户 | 多租户、开放平台 | 需维护键与配额的映射 | 成本归谁、谁会被误伤 |
| 限流维度 | 按 IP | 未认证入口、防爬 | NAT 后整栋楼共享一个桶 | 有无更稳定的身份标识 |
| 限流算法 | 令牌桶 | 允许突发但要有上限 | 参数不易向业务解释 | 是否需要容忍短时突发 |

选型顺序：先看数据是否持续写入，再看失败粒度，最后按成本归属选限流维度、按是否容忍突发选算法。反过来先挑组件，容易在深翻页和跨实例计数上翻车。

## 最小示例

先看契约形状。列表请求与响应：

```text
GET /api/orders?status=paid&sort=-created_at&limit=20 HTTP/1.1
Host: refund.sky-mall.example
X-Api-Key: erp-sync-01
```

```json
{
  "items": [{"id": "1005", "status": "paid", "amount": 199.0, "created_at": "2026-10-18T09:12:00Z"}],
  "next_cursor": "5:1005",
  "has_more": true
}
```

被限流时：

```text
HTTP/1.1 429 Too Many Requests
Retry-After: 2
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 0
```

`Retry-After` 是标准头部；`X-RateLimit-*` 不在 HTTP 规范里，属于团队自定义约定，必须写进契约，也不能指望客户端都会读。

下面的脚本验证三条性质：offset 翻页期间插入新订单后出现重复行、游标翻页不重复、令牌桶容量耗尽后返回 429。

```python
"""paging_demo.py：用标准库对比 offset 与游标分页，并观察批量语义与令牌桶限流。"""
import json                                   # 打印结构化结果，便于和真实接口报文对照

ORDERS = [                                    # 内存订单表；(created_at, id) 唯一且稳定，是游标的排序依据
    {"id": "1005", "created_at": 5, "status": "paid", "amount": 199.0},
    {"id": "1004", "created_at": 4, "status": "refunded", "amount": 99.0},
    {"id": "1003", "created_at": 3, "status": "paid", "amount": 58.0},
    {"id": "1002", "created_at": 2, "status": "paid", "amount": 120.0},
    {"id": "1001", "created_at": 1, "status": "cancelled", "amount": 30.0},
]

STATUSES = {"paid", "refunded", "cancelled"}   # 过滤值白名单，拒绝把任意字符串拼进查询
SORT_FIELDS = {"created_at", "amount"}         # 排序白名单，避免全表排序与注入

def order_rows(rows, sort_key, descending):
    """统一排序：排序值相同时用 id 兜底，保证顺序稳定且不重复。"""
    return sorted(rows, key=lambda row: (row[sort_key], row["id"]), reverse=descending)

def page_by_offset(rows, offset, limit):
    """offset 分页：第 N 页 = 跳过 offset 条再取 limit 条。"""
    ordered = order_rows(rows, "created_at", True)
    return ordered[offset:offset + limit]      # 只依赖"当前位置"，不依赖"上一行是谁"

def page_by_cursor(rows, cursor, limit):
    """游标分页：游标记录上一页最后一行的 (created_at, id)。"""
    ordered = order_rows(rows, "created_at", True)
    if cursor is not None:
        created_at, _, last_id = cursor.partition(":")           # 示例用明文，生产环境应签名后编码
        boundary = (int(created_at), last_id)
        ordered = [row for row in ordered if (row["created_at"], row["id"]) < boundary]
    page = ordered[:limit]
    next_cursor = f"{page[-1]['created_at']}:{page[-1]['id']}" if len(page) == limit else None
    return page, next_cursor                   # 返回下一页锚点，而不是让客户端自己算 offset

def validate_query(limit, sort_key, status):
    """先校验再查询：上限、白名单、枚举值都要在入口挡住。"""
    if limit < 1 or limit > 100:
        return {"error": "invalid_limit", "max": 100}
    if sort_key not in SORT_FIELDS:
        return {"error": "invalid_sort", "allowed": sorted(SORT_FIELDS)}
    if status is not None and not set(status) <= STATUSES:
        return {"error": "invalid_status", "allowed": sorted(STATUSES)}
    return None

def apply_refund_batch(items, known_orders):
    """批量退款：逐项校验并返回每项结果，一条脏数据不会让整批失败。"""
    succeeded, failed = [], []
    for item in items:
        order_id = item.get("order_id")
        if not isinstance(order_id, str) or order_id not in known_orders:
            failed.append({"order_id": order_id, "error": "order_not_found"})
        elif not isinstance(item.get("amount"), (int, float)) or item["amount"] <= 0:
            failed.append({"order_id": order_id, "error": "invalid_amount"})
        else:
            succeeded.append({"order_id": order_id, "refund_id": f"R-{order_id}"})
    return {"succeeded": succeeded, "failed": failed, "atomic": False}

class TokenBucket:
    """令牌桶：容量决定突发上限，补充速率决定长期平均速率。"""

    def __init__(self, capacity, refill_per_second, clock):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = float(capacity)          # 初始允许一次突发，上限即容量
        self.updated = clock[0]
        self.clock = clock                     # 注入时钟让结果可复现，避免真实等待

    def allow(self):
        now = self.clock[0]
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_second)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True, 0.0
        return False, (1 - self.tokens) / self.refill_per_second   # 告诉调用方还要等多久

def fresh_orders():
    """返回初始订单副本：每个实验从同一状态出发，结果才可对比。"""
    return [dict(row) for row in ORDERS if row["id"] != "1006"]

def main():
    print("== offset 分页：翻页期间新增一条更靠前的订单 ==")
    print("第 1 页:", [row["id"] for row in page_by_offset(fresh_orders(), 0, 2)])
    shifted = fresh_orders()
    shifted.insert(0, {"id": "1006", "created_at": 6, "status": "paid", "amount": 66.0})
    print("新订单 1006 到达后第 2 页:", [row["id"] for row in page_by_offset(shifted, 2, 2)])

    print("== 游标分页：同样插入新订单 ==")
    first, cursor = page_by_cursor(fresh_orders(), None, 2)
    print("第 1 页:", [row["id"] for row in first], "next_cursor:", cursor)
    second, cursor = page_by_cursor(shifted, cursor, 2)
    print("第 2 页:", [row["id"] for row in second], "next_cursor:", cursor)

    print("== 过滤与排序 ==")
    paid = order_rows([row for row in shifted if row["status"] == "paid"], "amount", True)
    print("已支付按金额降序:", [(row["id"], row["amount"]) for row in paid])
    print("非法排序参数:", json.dumps(validate_query(20, "password", None), ensure_ascii=False))
    print("非法过滤值:", json.dumps(validate_query(20, "created_at", ["shipped"]), ensure_ascii=False))

    print("== 批量退款：部分成功 ==")
    batch = apply_refund_batch(
        [{"order_id": "1001", "amount": 30.0},
         {"order_id": "9999", "amount": 10.0},
         {"order_id": "1004", "amount": -1}],
        {row["id"] for row in shifted},
    )
    print(json.dumps(batch, ensure_ascii=False))

    print("== 令牌桶限流：容量 2，每秒补 1 个令牌 ==")
    clock = [0.0]                              # 可变时钟，手动推进避免真实等待
    bucket = TokenBucket(capacity=2, refill_per_second=1, clock=clock)
    for moment in (0.0, 0.0, 0.0, 0.4, 1.2):
        clock[0] = moment
        allowed, wait = bucket.allow()
        if allowed:
            print(f"t={moment:.1f}s -> 200 剩余令牌 {bucket.tokens:.1f}")
        else:
            print(f"t={moment:.1f}s -> 429 Retry-After: {wait:.1f}s")

if __name__ == "__main__":
    main()
```

整体分四段：`order_rows` 收敛“排序稳定”，`page_by_*` 实现两种锚点，`validate_query` 拦住非法参数，`TokenBucket` 用注入时钟让限流可复现。三个设计要点：游标由排序值与主键共同构成；限流先于业务逻辑，被拒请求不消耗数据库；批量返回逐项结果而非一个布尔值。

运行 `python3 paging_demo.py`，预期输出：

```text
== offset 分页：翻页期间新增一条更靠前的订单 ==
第 1 页: ['1005', '1004']
新订单 1006 到达后第 2 页: ['1004', '1003']
== 游标分页：同样插入新订单 ==
第 1 页: ['1005', '1004'] next_cursor: 4:1004
第 2 页: ['1003', '1002'] next_cursor: 2:1002
== 过滤与排序 ==
已支付按金额降序: [('1005', 199.0), ('1002', 120.0), ('1006', 66.0), ('1003', 58.0)]
非法排序参数: {"error": "invalid_sort", "allowed": ["amount", "created_at"]}
非法过滤值: {"error": "invalid_status", "allowed": ["cancelled", "paid", "refunded"]}
== 批量退款：部分成功 ==
{"succeeded": [{"order_id": "1001", "refund_id": "R-1001"}], "failed": [{"order_id": "9999", "error": "order_not_found"}, {"order_id": "1004", "error": "invalid_amount"}], "atomic": false}
== 令牌桶限流：容量 2，每秒补 1 个令牌 ==
t=0.0s -> 200 剩余令牌 1.0
t=0.0s -> 200 剩余令牌 0.0
t=0.0s -> 429 Retry-After: 1.0s
t=0.4s -> 429 Retry-After: 0.6s
t=1.2s -> 200 剩余令牌 0.2
```

对照是重点：offset 第 2 页的 `1004` 与第 1 页重复，因为插入 `1006` 后所有位置后移一位；游标第 2 页从 `4:1004` 之后开始，`1003`、`1002` 各出现一次，新订单只在下一次拉取时出现。

## 动手实验

前置条件：安装 Python 3.9+；能写入 `/tmp`；无需外网和任何密钥。

1. 把脚本保存为 `/tmp/paging_demo.py`，运行一次，记录 offset 两页与游标两页的订单编号。
2. 把 `page_by_cursor` 的边界比较从 `<` 改成 `<=`，重跑并观察第 2 页是否又返回了一次 `1004`。
3. 把 `TokenBucket` 的 `capacity=2` 改成 `capacity=5`、补充速率保持 1，重跑并确认 5 次请求全部返回 200。
4. 把 `validate_query` 的上限从 100 改成 10，用 `limit=20` 调用，确认返回 `invalid_limit`。
5. 给批量请求增加一条 `{"order_id": "1003", "amount": 0}`，观察它落入 `invalid_amount` 而不是整批失败。
6. 全部改回原样，确认输出与上文一致。

预期结果：第 1 步 offset 段出现 `1004` 重复，游标段无重复；第 2 步改用 `<=` 后第 2 页变成 `['1004', '1003']`；第 3 步 5 次请求全为 200，剩余令牌依次为 4.0、3.0、2.0、1.4、1.2；第 5 步 `failed` 变成 3 项而 `succeeded` 仍为 1 项。

验证方法：对比 offset 两页的编号集合是否有交集（有交集即证明重复）；确认脚本退出码为 0。

清理方法：删除 `/tmp/paging_demo.py`；本次实验未启动监听端口，无需释放端口或停止进程。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 翻页时同一条记录出现两次 | 使用 offset 分页且翻页期间有新数据插入 | 记录两页的编号集合，检查是否有交集 | 改用游标分页，或按创建时间做增量拉取 |
| 翻页偶尔漏掉一行 | 排序键不唯一，相同值的行顺序漂移 | 检查排序是否只用了 `status` 这类低基数字段 | 用 `(created_at, id)` 组合排序，把主键纳入游标 |
| 客户端传 `sort=password` 居然生效 | 排序字段直接拼进 SQL 或未做白名单 | 逐个传非法字段看是否返回 400 | 固定白名单，非法值返回 `invalid_sort` |
| 429 之后客户端疯狂重试，服务更慢 | 响应缺少 `Retry-After`，或客户端忽略它 | 查看 429 响应头与客户端重试间隔 | 补 `Retry-After`，客户端加随机抖动与最大次数 |

## 安全与生产注意事项

**<u>允许 `limit` 无上限，或允许客户端传入任意过滤与排序字段。</u>** 一次请求就能拉出整张订单表、触发全表排序、打满连接池，既是可用性事故也是泄露面。缓解：截断 `limit` 并回显生效值，排序与过滤只接受白名单。

**<u>游标本身不签名，客户端可以任意篡改。</u>** 明文游标把排序键和记录边界交给调用方，攻击者可构造边界绕过租户条件、枚举他人订单。缓解：签名或加密游标，其中携带租户与过滤条件摘要，解出后校验授权上下文。

**<u>限流只在应用进程内计数，且维度只用 IP。</u>** 多副本时每个实例各算一份，实际放行量是阈值的数倍；只用 IP 会让 NAT 后整个办公区被一个爬虫连坐。缓解：网关或共享存储统一计数，按 `API Key` 分桶。

**<u>批量接口不校验批次大小，也没有幂等键。</u>** 一次提交十万条会长时间占用连接和事务，重试还会重复退款。缓解：限制批次上限（如 200 项）并要求 `operation_id`。

## 本课总结

- **offset 与游标的分水岭是数据是否在翻页期间变化**：会变就用游标，需要跳页才用 offset。
- 游标必须由稳定且唯一的排序键构成，通常写作 `(created_at, id)`；只按低基数字段排序必然漏行。
- 列表接口的健壮性来自三个前置校验：`limit` 上限、排序白名单、过滤枚举；批量操作则要先选语义再写代码。
- 限流参数要能翻译成业务语言：容量即突发上限，补充速率即平均速率；429 要带 `Retry-After`。限流让你等几秒，配额让你等下个计费周期。

## 思考题

财务对账要求“每五分钟增量拉取，不漏不重”，但订单会经历创建、支付、退款等变化，退款还可能发生在创建两小时之后。你会用 `created_at` 游标、`updated_at` 游标，还是别的方案？请说明游标字段、终止条件、如何避免漏单与重复记录，以及该接口按什么维度限流。

参考思路：`updated_at` 更接近变更流，但要处理同一秒多行与时钟回拨，通常用 `(updated_at, id)` 复合游标并允许回溯重叠窗口；只按 `created_at` 会漏掉老订单的状态变更。终止条件是返回条数小于 limit。防漏单靠重叠窗口加幂等写入（对账记录以 `order_id + version` 唯一）。限流按任务身份而非 IP，阈值取正常增量请求量的 2–3 倍。评价看三点：是否识别 `created_at` 的漏单缺陷、是否给出幂等去重手段、限流维度是否落在调用方身份上。

## 小测

1. 下列哪种情况最应该用游标分页？  
   A. 后台页需直接跳到第 50 页　B. 订单流按创建时间持续新增，要求不漏不重　C. 结果集只有 20 条　D. 需按任意字段排序
2. 游标由 `(created_at, id)` 组成而不是只用 `created_at`，主要原因是？  
   A. 让游标更短　B. 减少数据库索引　C. 保证排序值相同时顺序唯一、不重复不遗漏　D. 方便客户端解析
3. 客户端收到 429 且带 `Retry-After: 3`，正确做法是？  
   A. 立即重试直到成功　B. 换一个 API Key 继续调用　C. 等待约 3 秒后重试，并遵守最大重试次数　D. 当作 403 处理
4. 批量退款接口返回 `{"succeeded": [...], "failed": [{"order_id": "9999", "error": "order_not_found"}]}`，说明该接口的语义是？  
   A. 全或无，整批已回滚　B. 部分成功，失败项需单独处理　C. 请求参数整体非法　D. 服务端 5xx
5. 判断：接口限流阈值设得越高，系统就越安全。
6. 场景题：物流合作方每分钟配额 600 次，某天它把重试间隔写成 10 毫秒，触发大量 429 后又抱怨“接口不稳定”。请指出至少两个设计或沟通问题，并给出修正。

## 答案与解析

1. **B。** 游标锚定排序值，新增数据不挤动位置。A 要跳页，是 offset 的强项；C 数据量小，两种都行；D 任意字段排序最易漏行。
2. **C。** 只用 `created_at` 时，同一秒的多行顺序可能变化，游标会重复或跳过。A、B 与游标构成无关；D 只是附带好处。
3. **C。** `Retry-After` 就是服务端给出的等待建议。A 放大拥塞；B 属绕过限流，可能触发封禁；D 混淆了限流与权限。
4. **B。** 响应同时给出成功项与失败项，说明逐项处理、部分生效。A 与响应矛盾；C 对应 400；D 会诱使调用方整体重试，掩盖真实失败项。
5. **错。** 阈值过高等于没有保护，突发会直接打到数据库；过低则误伤正常调用方。**限流目标是把负载控制在容量之内，而不是越高越好**。
6. 参考：一是客户端重试间隔过短且无抖动，把限流当临时故障猛冲；二是契约未说明阈值、窗口与 `Retry-After`；三是可能按 IP 计数，对方出口 IP 变化导致误判。修正：客户端指数退避加抖动、设最大重试次数并优先读 `Retry-After`；服务端补齐响应头与文档，按 `API Key` 分桶，并用不同错误码区分“配额用尽”与“瞬时超速”。

动手实验参考：第 2 步改成 `<=` 后第 2 页变成 `['1004', '1003']`，边界行被再返回一次，正是“比较符写错就重复”的症状；第 3 步容量改为 5 后请求全通过，说明突发上限由容量决定；第 5 步 `amount=0` 进入 `invalid_amount`，`succeeded` 仍只含 `1001`，证明部分成功按项独立判定。

## 延伸阅读与下一课

- RFC 6585 定义了 `429 Too Many Requests`：<https://www.rfc-editor.org/rfc/rfc6585.html>。
- RFC 9110《HTTP Semantics》中关于 `Retry-After` 与状态码语义的规定：<https://www.rfc-editor.org/rfc/rfc9110.html>。
- Google API Improvement Proposals 的 [AIP-158 分页](https://google.aip.dev/158)与 [AIP-160 过滤](https://google.aip.dev/160)，可作为游标与过滤语法的参考实现约定（非 IETF 标准）。
- MDN：[429 Too Many Requests](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Status/429)。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[参数校验、错误模型与版本管理](03-validation-errors-and-versioning.md)。
- 下一课：[超时、重试、退避与幂等](05-timeout-retry-backoff-and-idempotency.md)。
