---
title: API、REST 与资源建模
slug: api-rest-and-resource-modeling
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - web-and-network-overview
outcomes:
  - 用资源、标识、表示和统一接口解释 REST 约束，并说明它不规定什么
  - 把晴空商城的退款用例改写成资源、URI 与方法的组合，并标注幂等性
  - 为一项不兼容的契约变更选择版本策略，并写出对老调用方的兼容安排
last_reviewed: 2026-10-19
---

# API、REST 与资源建模

## 为什么需要学习

晴空商城的退款服务上线三个月后，客服工作台、仓库和对账分别对接了三个“退款接口”：`POST /api/doRefund`、`POST /api/refund/operate` 和 `GET /api/refund?id=1&op=approve`。三者做同一件事，字段名各不相同，最后一个用 `GET` 改状态。开发每接一个调用方就要读别人的代码，测试判断不了哪个失败可以重试，一次缓存预热还把批量“同意退款”提前执行了。

这不是代码质量问题，而是契约问题：接口没说明“退款”是什么、能被怎样操作、失败意味着什么。REST 与资源建模就是把这句话写清楚的方法。

> **核心结论：** API 是可以独立演进的协作界面，资源模型决定这个界面能否被不同团队稳定使用。

## 学习目标

完成本课后，你能够：

- 用资源、标识、表示、统一接口解释 REST 约束，并指出它没有规定什么。
- 把“查询退款”“同意退款”改写成名词路径与方法组合，并判断是否幂等。
- 为订单、退款、发货单设计一致的 URI 层级与对应状态码。
- 比较 URI 版本、媒体类型版本与兼容演进的代价，说明选型依据。
- 用 `python3` 标准库验证路径、方法语义与幂等键的实际行为。

## 前置知识

- 回看上一单元：[Web 与网络](../02-web-and-network/00-overview.md)。
- 知道 `GET`、`POST` 及 2xx、4xx、5xx 的基本含义。
- 能读懂 JSON 对象，能在终端运行 `curl` 和 `python3 --version`。

## 业务场景

“晴空商城”的退款有两个入口：客服在工单里点“同意退款”，风控在后台批量审批超额退款。一次退款会经历受理、审核、提交支付、支付成功或失败、仓库拦截发货等状态，涉及客服工作台、退款服务、支付供应商、仓库和财务对账。

本课只处理设计侧面——在写代码和 OpenAPI 之前，先回答：

- 退款是订单下的子资源，还是可独立查询的资源？
- “同意退款”是改退款状态，还是新增一条审批记录？
- 对账任务要扫描全部退款，路径放哪一层？
- 老版本客服工作台还在跑，改字段名算破坏契约吗？

若各团队按各自习惯回答，集成成本会长期存在；design 阶段定下资源模型，是最便宜的一次修复机会。

## 核心概念

*API*（Application Programming Interface）是系统对外的调用约定：谁能调用、传什么、得到什么、失败如何表示。它不只是 URL，还包含数据结构、状态码、错误格式和变更规则。

*API 契约*把上述约定固定下来，供多方独立开发。它的价值在于调用方不必读实现就能正确集成，因此必须先于实现稳定。

*资源*是被命名、可寻址、有状态的业务实体或集合，例如订单 `1001`、它的退款集合、某张发货单。*资源建模*是把业务用例拆解成资源、层级和行为的过程。

*表示*（representation）是资源在某一时刻的序列化形态，例如一份 JSON。**资源本身不是 JSON**：同一订单可以有 JSON、CSV 或对账文件，URI 指向的是资源，不是某份报文。

*REST* 是 Fielding 提出的一组架构约束，核心是资源标识、通过表示操作资源、统一接口、无状态交互。它**不规定** URL 长什么样、用什么框架、是否用 JSON，<u>也不等于“用 HTTP 的 JSON 接口”</u>。

*统一接口*指所有资源共用同一套方法语义与状态码，客户端才能用通用逻辑处理未知资源。*URI* 标识资源：集合 URI 表示一组，元素 URI 表示其中一个。

| 需求 | 动词式设计 | 资源式设计 | 差别 |
| --- | --- | --- | --- |
| 查订单 | `POST /api/getOrder` | `GET /orders/1001` | 可缓存、可安全重试，语义自解释 |
| 同意退款 | `GET /api/refund/approve?id=R-1` | `POST /refunds/R-1/approvals` | 明确新增审批记录，而非偷偷改状态 |
| 修改收货地址 | `POST /api/updateAddress` | `PATCH /orders/1001` | 只改提交的字段，可做冲突检测 |
| 查某订单退款 | `POST /api/queryRefunds` | `GET /orders/1001/refunds` | 层级直接表达从属关系 |

| 方法 | 语义 | 幂等 | 晴空商城示例 | 成功状态码 |
| --- | --- | --- | --- | --- |
| `GET` | 读取资源或其集合 | 是 | `GET /orders/1001` | `200` |
| `POST` | 在集合下创建，或提交一次动作 | 否 | `POST /orders/1001/refunds` | `201` + `Location` |
| `PUT` | 用完整表示替换资源 | 是 | `PUT /orders/1001/shipping-address` | `200` 或 `204` |
| `PATCH` | 局部修改资源 | 通常否 | `PATCH /refunds/R-1` | `200` |
| `DELETE` | 删除资源 | 是 | `DELETE /carts/C-9/items/I-3` | `204` |

## 工作原理

从一句业务需求到一个可交付契约，按顺序做六件事：

1. **抽名词**：把用例里的业务名词列出来——订单、退款、审批、发货单、对账批次，动词（同意、取消、重发）先放在一边。
2. **筛资源**：有稳定标识、可独立查询、有生命周期的才建模为资源。“同意”不是资源，它产生的“审批记录”才是；因此用 `POST /refunds/R-1/approvals` 表达动作，而不是把 `/approve` 写进路径。
3. **排层级**：从属关系唯一且查询总带父级时用嵌套，如 `/orders/1001/refunds`；跨父级检索时用平铺集合加过滤，如 `/refunds?status=pending`。层级超过三层，通常说明模型没拆对。
4. **定方法**：读取用 `GET`，创建用 `POST`（返回 `201` 和 `Location`），整体替换用 `PUT`，局部修改用 `PATCH`，删除用 `DELETE`。只有重复执行结果相同的操作，才敢让客户端自动重试。
5. **定表示**：字段名、类型、单位一次说清：金额用整数分或字符串，时间用 UTC 的 RFC 3339，ID 当作不透明字符串，枚举预留未知值处理规则。
6. **定错误与版本**：用状态码表达错误类别、用响应体表达原因（如 RFC 9457 的 `application/problem+json`）；同时在契约里写明哪些变更算兼容、哪些必须升版本。

顺序不能颠倒：先定资源和方法，再谈字段；先定兼容规则，再谈版本号。反过来做，往往得到一个路径里全是动词、字段名靠猜、每次发版都要通知所有调用方的接口。

## 架构与选型

| 决策点 | 选项 | 适用 | 不适用或代价 | 判断依据 |
| --- | --- | --- | --- | --- |
| 接口风格 | 资源式 REST | 多消费方、资源生命周期清晰、需要缓存与通用重试 | 强事务、低延迟内部调用时表达绕 | 是否有多个独立团队读写同一批资源 |
| 接口风格 | 动作式 RPC（如 `/refundService`） | 内部单一调用方、动作难以映射到资源 | 通用网关与监控无法按资源归类 | 动作是否真的没有可标识的状态载体 |
| 版本位置 | URI 大版本 `/v1/...` | 对外公开、调用方难以协调升级 | 同一资源出现多套 URI，路由与文档翻倍 | 是否存在无法同步升级的外部调用方 |
| 版本位置 | 媒体类型版本 `Accept: application/vnd.qingkong.v2+json` | 内部服务、希望 URI 稳定 | 调试与网关配置更复杂 | 团队是否具备统一的内容协商能力 |
| 变更方式 | 只做兼容演进（加字段、加可选参数） | 绝大多数迭代 | 无法表达语义变更 | 是否只是新增能力 |
| 变更方式 | 破坏性变更升版本 + 弃用期 | 删除字段、改语义、改状态码 | 需要双写、双跑和调用方清单 | 老客户端是否真的无法修改 |

选型顺序：先确认是否有无法协调升级的调用方（决定版本号），再确认资源是否有稳定标识（决定 REST 还是 RPC），最后讨论路径细节。**版本号是成本，不是成熟度标志**；能用兼容演进解决的变更不要升版本。

## 最小示例

问题：验证“名词路径 + 方法语义”如何落地，以及同一幂等键重复提交为什么不会重复退款。

环境：Python 3.8 及以上（用到海象运算符），只用标准库，监听 `127.0.0.1:8000`。

```python
"""rest_demo.py：最小资源路由，只监听本机回环地址。"""
import json                             # 解析与序列化 JSON 表示
import re                               # 把路径模式匹配成资源标识
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORDERS = {"1001": {"id": "1001", "status": "paid", "amount": 199.0}}  # 模拟订单表
REFUNDS = {}                            # 退款号 -> 退款资源，模拟退款表
IDEMPOTENCY = {}                        # 幂等键 -> 退款号，模拟去重表

ORDER_PATH = re.compile(r"^/orders/(?P<order_id>[\w-]+)$")            # 单个订单
REFUNDS_PATH = re.compile(r"^/orders/(?P<order_id>[\w-]+)/refunds$")  # 订单下的退款集合


def handle(method, path, headers, body):
    """把「方法 + 名词路径」映射到资源操作，返回 (状态码, 表示, 额外响应头)。"""
    match = ORDER_PATH.match(path)
    if match:
        if method != "GET":             # 订单当前只读：其他方法明确拒绝，而不是假装 404
            return 405, {"error": "method_not_allowed"}, {"Allow": "GET"}
        order = ORDERS.get(match["order_id"])
        if order is None:               # 资源不存在是客户端可修正的问题，用 404
            return 404, {"error": "order_not_found"}, {}
        return 200, order, {}

    match = REFUNDS_PATH.match(path)
    if match:
        order = ORDERS.get(match["order_id"])
        if order is None:
            return 404, {"error": "order_not_found"}, {}
        if method != "POST":            # 集合只接受 POST 创建退款
            return 405, {"error": "method_not_allowed"}, {"Allow": "POST"}
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:    # 报文不是合法 JSON：请求本身有问题，用 400
            return 400, {"error": "invalid_json"}, {}
        if not payload.get("reason"):   # 必填字段缺失同样是 400，不能落到 500
            return 400, {"error": "reason_required"}, {}
        key = headers.get("Idempotency-Key")   # 客户端为重试生成的稳定标识
        if key and key in IDEMPOTENCY:         # 同键再次提交：复用上次结果，不新建退款
            return 200, REFUNDS[IDEMPOTENCY[key]], {}
        refund_id = f"R-{len(REFUNDS) + 1}"
        REFUNDS[refund_id] = {"id": refund_id, "order_id": order["id"], "status": "accepted"}
        if key:
            IDEMPOTENCY[key] = refund_id
        order["status"] = "refund_pending"
        return 201, REFUNDS[refund_id], {"Location": f"/refunds/{refund_id}"}

    return 404, {"error": "not_found"}, {}   # 路径本身不存在


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"           # 明确协议版本，响应必须带 Content-Length

    def _respond(self, status, payload, extra):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for name, value in extra.items():
            self.send_header(name, value)   # 把 Allow、Location 等语义头写回客户端
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._respond(*handle("GET", self.path, self.headers, b""))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self._respond(*handle("POST", self.path, self.headers, self.rfile.read(length)))

    def do_DELETE(self):
        self._respond(*handle("DELETE", self.path, self.headers, b""))

    def log_message(self, *args):
        pass                                # 关掉访问日志，保持输出干净


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
```

整体流程：请求按“方法 + 路径”进入 `handle`，正则只认名词层级，方法决定动作；命中资源后校验状态与参数，再写资源与幂等表，最后用状态码和 `Location` 表达结果。关键取舍是**把动作藏在集合的 `POST` 里，把重试安全交给幂等键**，而不是在 URL 里加 `?op=approve`。

启动服务并验证：

```bash
python3 rest_demo.py &
curl -i http://127.0.0.1:8000/orders/1001
curl -i -X POST -H 'Content-Type: application/json' -H 'Idempotency-Key: k-1' \
     -d '{"reason":"customer_request"}' http://127.0.0.1:8000/orders/1001/refunds
curl -i -X DELETE http://127.0.0.1:8000/orders/1001
```

预期输出（节选，`Date`、`Server` 头随环境变化）：

```text
HTTP/1.1 200 OK
{"id": "1001", "status": "paid", "amount": 199.0}

HTTP/1.1 201 Created
Location: /refunds/R-1
{"id": "R-1", "order_id": "1001", "status": "accepted"}

HTTP/1.1 405 Method Not Allowed
Allow: GET
{"error": "method_not_allowed"}
```

把第二个 `curl` 原样再执行一次，会得到 `200` 和同一个 `R-1`，这就是幂等键在契约层的保证。

## 动手实验

### 任务：为退款设计契约表并验证

前置条件：Python 3.8 及以上、`curl`、本机 `8000` 端口空闲；把最小示例保存为 `/tmp/rest_demo.py`。

1. 补齐表格中的 4 行，写清资源、URI、方法、成功状态码和是否幂等。
2. 启动服务：`python3 /tmp/rest_demo.py &`。
3. 依次请求 `GET /orders/1001`、`GET /orders/9999`、两次同键 `POST /orders/1001/refunds`、`DELETE /orders/1001`、空体 `POST`。
4. 对照实际响应修正契约表，把与预期不符的行标出来。

| 资源/动作 | URI | 方法 | 成功码 | 幂等 |
| --- | --- | --- | --- | --- |
| 单个订单 | `/orders/1001` |  |  |  |
| 订单的退款集合 |  | `POST` |  |  |
| 单个退款 |  | `GET` |  |  |
| 退款审批记录 |  | `POST` |  |  |

预期结果：查询返回 `200`；不存在的订单返回 `404`；首次创建返回 `201` 且带 `Location`；同键重放返回 `200` 与同一 `R-1`；不支持的方法返回 `405` 且带 `Allow`；缺少 `reason` 返回 `400`。

验证方法：用 `curl -i` 看状态行与响应头；重放时核对响应体 `id` 是否一致；`GET /orders/1001` 应看到 `status` 变为 `refund_pending`。

清理方法：`kill %1` 结束后台服务并删除 `/tmp/rest_demo.py`；这是无认证的示例服务，不要留在共享主机或生产环境。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 路径里出现 `/getOrder`、`/doRefund` | 把用例动词直接抄进 URI | 检查路径末段是否为动词或含 `op=` | 改为名词资源 + 方法，动作改为创建子资源 |
| 网关或浏览器重复触发退款 | 用 `GET` 承载状态变更，被预取或缓存 | 查日志中该 URI 是否被非人工来源调用 | 状态变更只走 `POST`/`PUT`/`PATCH`/`DELETE` |
| 超时重试后出现两笔退款 | `POST` 无幂等键，服务端无去重 | 用同一键重放两次，比较响应与记录 | 契约要求幂等键，服务端加唯一约束 |
| 老客户端在小版本发布后报错 | 删字段、改类型或改状态码含义 | 对比新旧响应，检查字段是否消失 | 只做兼容新增；破坏性变更升版本并给弃用期 |
| 同一资源出现 `/refund`、`/refunds`、`/Refund` | 缺少 URI 命名约定 | 导出全部路径查大小写与单复数 | 集合用复数、全小写、连字符分词并写入规范 |

## 安全与生产注意事项

**<u>把自增主键直接放进 URI，会让攻击者顺序枚举全量订单和退款。</u>** 后果是批量数据泄露与业务被爬取。缓解方式是使用不可猜测的公开标识（UUID、ULID），并在每个资源上执行对象级授权，而不只校验“已登录”。

**<u>用 `GET` 或可重放的 `POST` 承载状态变更，会在缓存、爬虫或代理重试下产生未授权退款。</u>** 缓解方式是把写操作限制在明确方法上，校验 `Content-Type` 与来源，并加幂等键和审计记录。

**<u>删除旧版本接口前未确认调用方，发布瞬间会打断仍在运行的老客户端。</u>** 缓解方式是维护调用方清单、按版本统计流量、返回 `Deprecation` 与 `Sunset`（RFC 8594）响应头，先灰度再下线。

另外，URI 与错误信息不应包含手机号、身份证号或内部主机名，它们会进入浏览器历史、访问日志和第三方监控。

## 本课总结

- API 是协作契约，不只是 URL 集合；契约先说明资源、方法、状态码和变更规则。
- REST 的核心是可寻址资源、通过表示操作、统一接口和无状态；它不规定 URL 形态与序列化格式。
- 资源建模先抽名词再筛资源，动词通过创建子资源或修改状态来表达。
- 方法语义决定能否安全重试，幂等键补上 `POST` 的缺口。
- 版本号是成本：优先兼容演进，只有无法协调升级的破坏性变更才升版本并给弃用期。

## 思考题

“同意退款”应建模为 `PATCH /refunds/R-1`（把 `status` 改成 `approved`），还是 `POST /refunds/R-1/approvals`（新增审批记录）？请从审计、幂等、并发冲突、通知和扩展性（多级审批、撤销审批）五个角度分析，给出你的契约和理由。

参考思路：若审批是必须留存“谁、何时、依据什么”的业务事实，子资源更自然，`POST` 可追加且能用幂等键防重；`PATCH` 更简洁，但会丢审批历史，并发下还需版本号或 `ETag` 才不覆盖。也可组合：`POST` 写审批记录，退款 `status` 由服务端按审批结果推进，客户端只读。

## 小测

1. 关于 REST，下列哪项正确？  
   A. 要求 URL 以 `/api` 开头　B. 要求使用 JSON　C. 核心是资源与统一接口　D. 是一种编程语言
2. `PUT /orders/1001` 与 `PATCH /orders/1001` 的主要区别是什么？
3. 为什么“创建退款”通常返回 `201` 而不是 `200`？
4. 下列哪个 URI 最符合资源式设计？  
   A. `POST /api/refund/create`　B. `GET /orders/1001/refunds`　C. `GET /api/refund?op=list`　D. `POST /getRefunds`
5. 场景题：团队要把退款响应的 `amount` 从元改成分（数值含义变化），并删除已废弃的 `operator_name` 字段，还打算直接改 `/v1`。这个决定合适吗？

## 答案与解析

1. **C。** REST 约束落在资源标识、表示、统一接口和无状态上。A、B 是常见误传，REST 不规定路径前缀或数据格式；D 混淆了架构风格与语言。
2. `PUT` 用完整表示替换资源，未提交的字段会被清除或置默认，必须幂等；`PATCH` 只改提交字段，报文更小，但**语义上不保证幂等**，并发下需要版本号或 `ETag`。
3. `201` 说明服务端新建了资源，并用 `Location` 告知后续地址；`200` 只说明请求成功，客户端无法判断重试是否会重复创建。
4. **B。** 纯名词层级加读取方法。A 路径含创建动词；C 用查询参数承载动作；D 方法错、路径含动词且命名不一致。
5. 不合适。`amount` 单位变化会让老客户端把 19900 元显示成 19900 分；删字段会让强校验客户端反序列化失败。应升到 `/v2`（或媒体类型版本），保留 `/v1` 并双跑；用调用方清单与分版本流量确认迁移，通过 `Deprecation`、`Sunset` 头公告后灰度下线。

### 动手实验参考

合理答案不唯一。参考填写：订单 `/orders/1001` + `GET` + `200` + 幂等；退款集合 `/orders/1001/refunds` + `POST` + `201` + 非幂等（靠幂等键去重）；单个退款 `/refunds/R-1` + `GET` + `200` + 幂等；审批记录 `/refunds/R-1/approvals` + `POST` + `201` + 非幂等（可用幂等键）。若写成 `PATCH /refunds/R-1`，需说明如何保留审批历史与控制并发。

## 延伸阅读与下一课

- RFC 9110《HTTP Semantics》：方法与状态码的权威定义，<https://www.rfc-editor.org/rfc/rfc9110.html>。
- RFC 9457《Problem Details for HTTP APIs》：错误响应体的通用结构，<https://www.rfc-editor.org/rfc/rfc9457.html>。
- Roy Fielding 博士论文第 5 章：REST 约束的原始表述，<https://www.ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm>。
- OpenAPI Specification：把资源模型落成机器可读契约，<https://spec.openapis.org/oas/latest.html>。
- RFC 8594《The Sunset HTTP Header Field》：接口下线时如何告知调用方，<https://www.rfc-editor.org/rfc/rfc8594.html>。

- 返回[本单元目录](00-overview.md)。
- 回看上一单元：[Web 与网络](../02-web-and-network/00-overview.md)。
- 下一课：[OpenAPI 与接口契约](02-openapi-and-contracts.md)。
