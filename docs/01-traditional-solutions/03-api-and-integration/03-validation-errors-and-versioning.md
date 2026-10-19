---
title: 参数校验、错误模型与版本管理
slug: validation-errors-and-versioning
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - openapi-and-contracts
outcomes:
  - 为一个字段判定它属于传输、结构、语义还是一致性校验层
  - 写出带稳定错误码、字段定位和请求追踪标识的统一错误响应
  - 用兼容性规则判断一次接口变更是否破坏现有调用方，并设计带弃用期的演进方案
last_reviewed: 2026-10-19
---

# 参数校验、错误模型与版本管理

## 为什么需要学习

晴空商城的退款集成服务接入支付网关后，客服工作台连续两周收到同一类工单：点完"提交退款"只看到"操作失败"。开发排查发现三件互不相干的事同时发生——支付网关在金额超过上限时返回 HTML 错误页，退款服务把响应原样透传，前端截到的是半页栈信息；退款服务对参数只做了"非空"检查，`amount_cents` 传成字符串也能进业务；上周有人把事件里的 `amount` 从"元"改成"分"，仓库服务按旧单位解释，发货判断全错。这三件事分别对应校验、错误和版本，但用户感受到的是同一句话：说不清哪里错了。

> **核心结论：** 校验决定什么样的请求能进入业务，错误模型决定失败能否被理解和自动处理，版本规则决定已经跑起来的调用方会不会被你的改动打碎。

## 学习目标

完成本课后，你能够：

- 为一个字段判定它属于传输、结构、语义还是一致性校验层，并说明失败时应返回什么状态码。
- 写出含稳定错误码、字段定位和 `request_id` 的统一错误响应。
- 用兼容性规则判断一次字段或语义变更是否破坏现有调用方。
- 为一次字段重命名或单位调整设计带弃用期的演进方案。

## 前置知识

- 回看上一课：[OpenAPI 与接口契约](02-openapi-and-contracts.md)。
- 能读懂 HTTP 请求方法、路径以及 4xx 与 5xx 的日常区别。
- 了解 JSON 基本类型，能区分字符串、整数、`null` 和布尔值。
- 不需要框架经验，本课示例只用 Python 3 标准库。

## 业务场景

晴空商城（商城、订单、支付、仓储、客服）的退款集成服务已经上线，同一条 `POST /api/v1/refunds` 被三种调用方使用：

| 调用方 | 调用方式 | 最需要的失败形式 |
| --- | --- | --- |
| 客服工作台 | 客服点击提交，同步等待 | 字段级提示，能直接高亮输入框 |
| 批量导入脚本 | 每晚批量提交历史退款 | 逐条结果 + 错误码，可自动重试或人工分流 |
| 支付网关回调 | 收到退款结果后回调退款服务 | 明确的拒绝原因，不能靠文本推断 |

业务规则是：单笔退款不得超过 500 元；超过必须走主管审核；订单状态不是"已支付"或"部分退款"时不允许退款；内部金额统一以"分"为单位的整数存储。客服、财务和仓库对同一次失败的关注点完全不同——这三条规则和三个调用方，就是本课要设计的对象。

## 核心概念

| 概念 | 本课程中的含义 | 晴空商城示例 |
| --- | --- | --- |
| *参数校验* | 在业务执行前判断输入是否可接受 | 拒绝 `amount_cents: -1` |
| *校验分层* | 按请求形状、数据合法性、业务允许、与现存数据一致逐层检查 | 网关看体积，服务看上限，数据库看约束 |
| *错误码* | 稳定、机器可读、不随文案变化的失败标识 | `AMOUNT_EXCEEDS_LIMIT` |
| *错误模型* | 所有失败共享的响应结构 | `{"error": {"code", "message", "request_id", "field"}}` |
| *破坏性变更* | 会让现有调用方按旧约定失败或误读的改动 | 把 `amount` 的单位从元改为分 |
| *兼容性承诺* | 对外明确"哪些改动不会破坏调用方" | 允许新增可选字段，禁止改字段语义 |
| *弃用期* | 旧用法仍然工作、但已标注将被移除的时间窗 | `v1` 保留一个发布周期 |

校验分层是后面所有判断的基础：

| 层 | 检查什么 | 典型失败 | 负责方 |
| --- | --- | --- | --- |
| 传输 | `Content-Type`、体积、字符编码 | 415 / 413 | 网关 |
| 结构 | 字段存在、类型、长度、枚举、格式 | 400 | 服务，依据契约 |
| 语义 | 取值范围、状态机、角色权限 | 422 | 服务，规则所有者定义 |
| 一致性 | 幂等键重复、版本冲突、关联对象存在 | 409 / 404 | 服务与数据库约束 |

<u>结构校验可以由契约自动生成，语义校验永远需要有人负责：把"单笔上限 500 元"写进 schema 的 `maximum` 也能跑，但规则一改就要改契约、改生成代码、重新发版，而不是改一条配置。</u>

## 工作原理

按一次退款请求的路径展开：

1. 网关收到请求，检查 `Content-Type`、请求体大小和认证信息；不合格直接返回 415、413 或 401，不进入业务代码。
2. 服务按 OpenAPI 契约做结构校验：反序列化、必填字段、类型、枚举、长度。失败返回 400，并指出第一个出错的字段。
3. 语义校验：金额是否大于 0 且不超过 500 元、订单状态是否允许退款、当前客服是否有该订单的操作权限。失败返回 422。
4. 一致性校验：用 `Idempotency-Key` 查重，读订单当前版本号做乐观锁。重复提交返回首次结果而不是再退一次；版本冲突返回 409。
5. 业务执行：写退款单，事务提交后发出 `refund.created` 事件。
6. 无论成功还是失败，服务把结果映射成一个信封：成功返回业务对象，失败返回 `error` 对象，两者都带 `request_id`。
7. 日志与指标按错误码打点、按状态码分桶；`request_id` 同时出现在服务日志和客服工单里，用于跨系统对账。

状态码和错误码回答两个不同的问题：状态码告诉网关和通用客户端这类失败该怎么处理（要认证、要改参数、可重试），错误码告诉业务方具体哪条规则没过。<u>只返回 400 加一句"参数错误"，等于把猜谜工作转嫁给调用方。</u>

错误信封的字段约定：

| 字段 | 用途 | 约束 |
| --- | --- | --- |
| `code` | 程序分支判断 | 大写加下划线，发布后不改 |
| `message` | 人读说明 | 文案可随时调整，不参与判断 |
| `field` | 定位到具体参数 | 只在能定位时出现 |
| `request_id` | 关联服务端日志 | 每个请求必带 |
| `details` | 多条字段错误的数组 | 批量导入时使用 |

## 架构与选型

版本策略对比：

| 策略 | 形式 | 适用场景 | 代价 |
| --- | --- | --- | --- |
| URL 版本 | `/api/v1/refunds` | 对外集成、跨公司调用、较大结构调整 | 路由、文档和测试要并行维护多份 |
| Header 版本 | `Accept-Version: 2026-10-19` | 内部服务、需要按调用方灰度 | 浏览器和 curl 调试不直观 |
| 媒体类型版本 | `application/vnd.qingkong.v2+json` | 严格内容协商的 API | 客户端实现成本高 |
| 无版本演进 | 只做兼容性新增 | 内部消费者可控、移动端长尾 | 依赖契约测试和发布纪律 |

选型依据：

- 对外或跨公司 → URL 版本加明确弃用期，调用方不必读懂你的内部约定。
- 内部且能同步发版 → 无版本演进加契约测试，减少维护面。
- 不确定时选"将来能删得掉"的那一层，<u>不要为了显得规范给每个服务都挂版本号，然后一次都没下线过旧版本。</u>

不适用的情况：

- 用版本号替代兼容性纪律：`v1`、`v2`、`v3` 同时在线且语义各不相同，维护成本远高于一次小心演进。
- 把校验全部交给前端：绕过页面直接调 API 就完全失效。
- 把业务规则写进网关：网关团队会成为每次调价的瓶颈，规则变更排期不可控。

## 最小示例

问题：让退款接口对所有失败返回同一种结构，并能区分"结构错误"和"业务规则拒绝"。

环境：Python 3.9 及以上，标准库，无第三方依赖，监听 `127.0.0.1:8080`。

保存为 `refund_api.py`：

```python
"""最小退款接口：演示校验分层与统一错误响应。仅用于教学，无认证、无持久化。"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# 业务规则集中成常量：上限变动时只改一处，避免校验与文档各说一套
MAX_REFUND_CENTS = 50_000  # 500 元；金额统一用"分"的整数传输，避免浮点误差


def error(status, code, message, field=None):
    """所有失败路径都从这里返回同一个信封，调用方只需实现一种解析逻辑。"""
    detail = {"code": code, "message": message, "request_id": "req-demo-001"}
    if field:  # 只有能定位到具体字段时才附带，方便客户端高亮对应输入
        detail["field"] = field
    return status, {"error": detail}


def validate(payload):
    """结构校验在前、语义校验在后：先确认形状，再判断业务是否允许。"""
    if not isinstance(payload, dict):  # 结构层：JSON 合法但不是对象
        return error(400, "REQUEST_BODY_INVALID", "请求体必须是 JSON 对象")
    amount = payload.get("amount_cents")  # 字段缺失得到 None，交给类型检查统一处理
    if not isinstance(amount, int) or isinstance(amount, bool):  # bool 是 int 子类，必须排除
        return error(422, "FIELD_TYPE_INVALID", "amount_cents 必须是整数", "amount_cents")
    if amount <= 0:  # 语义层：业务不接受的取值范围
        return error(422, "AMOUNT_NOT_POSITIVE", "退款金额必须大于 0", "amount_cents")
    if amount > MAX_REFUND_CENTS:  # 语义层：风控规则，只有业务所有者能定义
        return error(422, "AMOUNT_EXCEEDS_LIMIT", "单笔退款不得超过 500 元", "amount_cents")
    if payload.get("order_id") is None:  # 结构层：必填字段缺失，单独给出可读提示
        return error(400, "REQUIRED_FIELD_MISSING", "order_id 为必填字段", "order_id")
    return None  # 返回 None 表示通过，调用方据此进入业务处理


class RefundHandler(BaseHTTPRequestHandler):
    """只实现 POST /api/v1/refunds；路径里的 v1 就是显式版本标识。"""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))  # 按声明长度读取，避免读到连接关闭
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)  # 反序列化失败也必须走同一个信封
        except json.JSONDecodeError:
            status, body = error(400, "JSON_PARSE_ERROR", "请求体不是合法 JSON")
        else:
            problem = validate(payload)
            # 通过则返回 201 加业务对象；失败则复用 validate 给出的状态码和信封
            status, body = problem or (
                201,
                {"refund_id": "rf-demo-001", "status": "accepted",
                 "amount_cents": payload["amount_cents"]},
            )
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))  # 显式长度，客户端不会挂起等关闭
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass  # 关掉默认访问日志，终端输出只保留我们关心的内容


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8080), RefundHandler).serve_forever()
```

保存为 `client_demo.py`：

```python
"""两个请求验证同一条错误信封：一个成功，一个被业务规则拒绝。"""

import json
import urllib.error
import urllib.request


def call(amount_cents):
    """发一次退款请求，并把 4xx 也当作可解析的结构化响应返回。"""
    request = urllib.request.Request(
        "http://127.0.0.1:8080/api/v1/refunds",
        data=json.dumps({"order_id": "SO-20261019-001",
                         "amount_cents": amount_cents}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:  # 4xx 与 5xx 是业务结果，不是网络故障
        return exc.code, json.load(exc)


for value in (12_000, 80_000):  # 120 元应当通过；800 元超过 500 元上限
    print(value, call(value))
```

运行命令：

```bash
python3 refund_api.py &   # 终端一：启动服务
python3 client_demo.py    # 终端二：发两个请求
```

预期输出：

```text
12000 (201, {'refund_id': 'rf-demo-001', 'status': 'accepted', 'amount_cents': 12000})
80000 (422, {'error': {'code': 'AMOUNT_EXCEEDS_LIMIT', 'message': '单笔退款不得超过 500 元', 'request_id': 'req-demo-001', 'field': 'amount_cents'}})
```

整体流程：

1. `do_POST` 只做三件事——读原始字节、反序列化、把校验结果和业务结果交出去。
2. `error()` 是唯一的失败出口，保证成功与失败不会各写一套字段名。
3. `validate()` 按结构后语义的顺序返回第一个可定位问题，避免一次抛出十条互相矛盾的提示。
4. 客户端把 `HTTPError` 当普通响应解析，说明错误码是可编程的，而不是给人读的字符串。

关键设计选择：金额用整数"分"而非浮点"元"，因为 <u>浮点数在跨语言比较时会出现 `0.1 + 0.2 != 0.3` 这类误差，金额相等判断会静默出错</u>。

## 动手实验

前置条件：Python 3.9 及以上；上面两个文件；`8080` 端口空闲。

步骤：

1. 启动 `refund_api.py`，另开终端执行 `python3 client_demo.py`，记录两个响应。
2. 发送非法 JSON：`curl -s -X POST http://127.0.0.1:8080/api/v1/refunds -H 'Content-Type: application/json' -d 'not-json'`。
3. 发送缺少 `order_id` 的请求：把上一条的 `-d` 换成 `'{"amount_cents": 100}'`。
4. 把 `MAX_REFUND_CENTS` 改成 `100000` 并重启，再跑一次客户端。
5. 增加一条语义校验：`order_id` 不以 `SO-` 开头时返回 `ORDER_NOT_FOUND`（状态码 404），并把它补进错误码表。

预期结果：

- 步骤 2 返回 400 和 `JSON_PARSE_ERROR`。
- 步骤 3 返回 400、`REQUIRED_FIELD_MISSING` 且 `field` 为 `order_id`。
- 步骤 4 中 80000 变成 201，说明校验依据的是配置而不是硬编码文案。
- 步骤 5 中 `order_id` 为 `XX-1` 时返回 404，而不是 500。

验证方法：

- 每次响应用 `python3 -c 'import json,sys;print(json.load(sys.stdin)["error"]["code"])'` 取出错误码，确认可被程序消费。
- 所有失败响应的键集合一致，只有 `field` 允许缺失。
- <u>用 `curl -i` 确认状态码与 `code` 含义一致，不出现 200 加 error 体的组合。</u>

清理方法：执行 `pkill -f refund_api.py`，删除两个演示文件；本实验不涉及数据库或云资源。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 前端拿到 HTML 或空响应 | 异常未被捕获，Web 服务器返回默认错误页 | `curl -i` 看 `Content-Type` 是否为 JSON | 在框架层加统一异常处理器，兜底返回错误信封 |
| 错误能看懂却无法分支处理 | 只有 `message`，没有稳定错误码 | 搜索客户端是否在匹配中文文案 | 补 `code`，把文案与判断解耦 |
| 同一类错误有时 400 有时 422 | 校验层职责不清，随手写状态码 | 对照四层分工表逐条核对 | 结构错误 400、业务规则 422、冲突 409 |
| 老客户端在新版上线后报错 | 删字段、改字段语义或收紧枚举 | 用上一版客户端跑契约测试 | 先加新字段双写一段时间，再下线旧字段 |
| 批量导入只看到第一条错误 | 校验遇到第一个问题就返回 | 观察单次导入返回的错误条数 | 提供 `details` 数组，明确"首错即停"还是全量收集 |
| 重试导致重复退款 | 没有幂等键或不校验重复 | 用同一 `Idempotency-Key` 连发两次 | 幂等键落库并建唯一索引，重复请求返回首次结果 |

## 安全与生产注意事项

**<u>错误响应回显原始请求体、堆栈或数据库语句会泄露敏感信息。</u>** 后果是身份证号、银行卡尾号、内部表结构进入前端页面和客服工单截图，攻击者还能用不同错误码探测哪些订单号存在。缓解：对外只返回 `code`、`message`、`field`、`request_id`，堆栈与 SQL 仅写服务端日志并按 `request_id` 关联；"不存在"与"无权限"统一返回同一个 404 语义。

**<u>只在前端或网关校验、服务端默认信任上游，会让金额上限形同虚设。</u>** 后果是直接调用 API 即可越权超额退款，财务对账出现无法解释的差额。缓解：服务端强制校验业务规则，数据库再加 `amount_cents > 0` 与上限约束作为最后防线，关键操作写入审计记录（操作人、请求号、原始入参摘要）。

**<u>删除旧版本或修改错误码含义却不留弃用期，会让调用方在没有任何告警的情况下静默失败。</u>** 后果是仓库服务按旧语义解释金额，重复发货或漏发。缓解：错误码与字段语义只增不改；下线前至少保留一个发布周期的双版本，用 `Deprecation` 响应头、调用量监控和契约测试确认无流量后再移除。

## 本课总结

- **校验要分层**：传输、结构、语义、一致性各有负责方，混在一起就无法判断该返回 400 还是 422。
- **错误模型的价值在稳定**：状态码给通用客户端，错误码给业务分支，`request_id` 给排查。
- 兼容性规则的本质是"只增不改"：新增可选字段安全，改语义、删字段、收紧枚举都是破坏性变更。
- 版本号不能替代纪律；对外用 URL 版本加弃用期，内部用契约测试加兼容性新增。
- 金额和标识符先定单位与类型，再谈校验细节。

## 思考题

仓库服务订阅 `refund.created` 事件，其中 `amount` 字段当前单位是"元"（浮点数），业务要求改为"分"（整数）。请在"原地改字段含义""新增字段双写""发布新事件版本"三种做法之间选择一种，并说明：老消费者如何不被破坏、什么时候可以删掉旧字段、用什么证据判断可以下线。

参考思路：不要原地改语义。可以新增 `amount_cents` 并在一段时间内与 `amount` 双写，事件里带 `schema_version`；老消费者读旧字段，新消费者读新字段；用消费端日志与字段读取率确认旧字段无人使用，再按弃用期移除。若消费者不可枚举（对外集成），优先发布新事件类型而不是修改旧结构。

## 小测

1. 请求体是合法 JSON，但 `amount_cents` 的值是字符串，最合适的状态码是？  
   A. 400　B. 422　C. 500　D. 409
2. 把退款金额上限从 500 元调到 800 元，是否需要新版本？为什么？
3. 错误响应中的 `message` 字段能否作为程序分支判断的依据？
4. 下列哪项属于破坏性变更？  
   A. 新增可选字段 `channel`　B. 把 `amount` 的单位从元改为分　C. 新增错误码 `ORDER_LOCKED`　D. 在文档中补充请求示例
5. 场景题：客服系统需要在批量导入失败时展示"第 3 行、第 7 行金额超限"，同时不能破坏只解析 `code` 的老客户端。你会怎样设计错误响应？

## 答案与解析

1. **A。** 类型不符合契约属于结构校验失败，客户端改数据即可修复。B 用于数据形状正确但业务规则拒绝的情况；C 会把客户端错误记成服务端故障并触发错误告警；D 表示与现有资源状态冲突，与类型无关。
2. 不需要新版本。放宽限制不会让原本成功的请求开始失败，属于非破坏性变更；但要在文档和变更记录里写明生效时间，并确认没有调用方依赖"必定被拒"这一隐含假设。<u>收紧限制才是破坏性变更，需要版本或弃用期。</u>
3. 不能。文案会为了可读性被修改、被翻译，程序判断必须依赖 `code`。这也是很多 SDK 把错误码暴露成常量枚举的原因。
4. **B。** 语义变化会让按旧单位解释的调用方算错金额，而且不会报错。A 和 C 都是纯新增，D 只改文档，三者对现有调用方没有影响。
5. 参考方向：保持顶层 `error` 结构和 `code` 不变，追加 `details` 数组，每项含 `index`、`field`、`code`；老客户端忽略未知字段仍能工作，新客户端按行渲染。同时约定 `details` 上限（例如 100 条）并给出总数，避免超大响应拖垮客服页面。

### 动手实验参考

步骤 5 的一种实现：在 `validate()` 末尾加 `if not str(payload.get("order_id", "")).startswith("SO-"): return error(404, "ORDER_NOT_FOUND", "订单不存在", "order_id")`，并把 `ORDER_NOT_FOUND` 写进错误码表，注明"用 404 同时覆盖不存在与无权限，避免资源枚举"。判断标准：新错误码能被客户端按码分支、`field` 正确指向 `order_id`、日志里能用同一个 `request_id` 串起整条链路。

## 延伸阅读与下一课

- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)：IETF 的错误响应标准，可用来对照本课信封。
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)：状态码的权威定义，判断 400、409、422 时查原文。
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)：结构校验与契约演进的机器可读描述。
- [Semantic Versioning 2.0.0](https://semver.org/)：库版本约定的参考，注意它不等同于 API 版本策略。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[OpenAPI 与接口契约](02-openapi-and-contracts.md)。
- 下一课：[分页、过滤、批量与限流](04-pagination-filtering-and-rate-limits.md)。
