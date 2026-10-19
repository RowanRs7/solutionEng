---
title: HTTP 请求、响应与状态码
slug: http-request-response
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 60m
prerequisites:
  - tcp-ip-dns-and-firewall
outcomes:
  - 写出 HTTP 请求报文与响应报文的四个组成部分，并说明每部分承载什么
  - 为晴空商城的读、创建、状态回写操作选择方法，并判断该请求是否幂等
  - 根据状态码类别决定客户端应继续、重试、修改请求还是告警
last_reviewed: 2026-10-19
---

# HTTP 请求、响应与状态码

## 为什么需要学习

晴空商城退款集成上线第一周，客服在工单页面点击“同意退款”，页面转圈 40 秒后提示失败。客服又点了一次，买家收到两笔退款。开发打开日志只看到一行“请求失败”，既不知道发出去的请求长什么样，也不知道对方回了什么。三天后，同样的故事在仓库状态回写接口上重演。

问题不在网络，而在接口契约：请求没有幂等键，错误被包装成 200，客户端把 4xx 也当成临时故障重试。HTTP 是这些系统之间最具体的约定，读懂它才能判断一次失败到底该由谁处理。

> **核心结论：** HTTP 的可预测性来自方法语义与状态码契约；两者一旦用错，重试、监控和告警都会给出错误答案。

## 学习目标

完成本课后，你能够：

- 写出一个 HTTP 请求报文和响应报文的起始行、头部、空行与主体，并说明每部分放什么。
- 为“查询订单”“创建退款”“把订单状态改为已退款”选择方法，并判断其安全性与幂等性。
- 把 2xx、3xx、4xx、5xx 映射到客户端和服务端的具体行动：继续、重试、改请求或告警。
- 指出“200 里包着错误”“用 5xx 表示参数错误”“用 404 掩盖无权限”三类误用的后果。
- 用 python3 标准库启动最小服务，验证 200、201、400、404、405 与重复提交的 200。

## 前置知识

- 回看上一课：[TCP/IP、DNS 与防火墙](02-tcp-ip-dns-and-firewall.md)。
- 知道客户端发起连接、服务端监听端口的基本分工。
- 能读懂 `key: value` 形式的配置和简单 Python 函数。
- 能在本机运行 `python3 --version`；本课示例只使用标准库。

## 业务场景

“晴空商城”的退款集成服务连接客服工作台、支付供应商和仓库系统。本单元只关注它们之间的 HTTP 侧面：

- 客服工作台在浏览器里调用 `POST /refunds`，业务要求 2 秒内给出受理结果。
- 退款服务调用支付供应商的 HTTPS 接口，供应商响应时间在 1–90 秒之间波动，偶尔返回 429 或 503。
- 仓库系统用 `PUT /orders/{id}/status` 回写发货与退款状态。
- 客服工单要展示可理解的失败原因，并支持人工接管。

架构师需要先回答：超时算成功还是失败？客服再点一次会不会重复退款？供应商返回 503 时能不能重试？“订单不存在”和“无权查看”要不要返回不同状态码？答案都要写进接口契约，而不是上线后靠日志猜。

## 核心概念

*HTTP*（HyperText Transfer Protocol）是客户端与服务端交换请求和响应的文本协议，规定报文格式、方法语义和状态码含义。

*请求报文*是客户端发给服务端的一条消息，由起始行、头部、空行、主体四部分组成。*响应报文*结构相同，只是起始行换成状态行。

| 组成部分 | 请求报文 | 响应报文 | 作用 |
| --- | --- | --- | --- |
| 起始行 | `POST /refunds HTTP/1.1` | `HTTP/1.1 201 Created` | 声明方法、目标与协议版本；或状态码与原因短语 |
| 头部 | `Content-Type: application/json` | `Location: /refunds/R-1` | 描述主体类型、长度、缓存、认证等元数据 |
| 空行 | 必须存在 | 必须存在 | 分隔头部与主体，没有它报文就解析错位 |
| 主体 | `{"order_id":"1001"}` | `{"id":"R-1"}` | 承载业务数据，也可以为空 |

*方法*是请求动作的语义声明，而不只是“用哪个函数”。*安全方法*指不修改服务端状态的读操作，如 GET、HEAD。*幂等*指同一请求执行一次和执行多次，服务端最终状态相同；<u>幂等并不等于只执行一次</u>，它只保证重复执行不产生额外效果。*幂等键*是客户端生成、服务端用于去重的唯一标识。

| 方法 | 语义 | 安全 | 幂等 | 晴空商城示例 |
| --- | --- | --- | --- | --- |
| GET / HEAD | 读取资源 | 是 | 是 | 查询订单 1001 的退款状态 |
| POST | 创建子资源或触发处理 | 否 | 否 | 创建一笔退款 |
| PUT | 整体替换资源状态 | 否 | 是 | 将订单状态设为 `refunded` |
| PATCH | 局部修改资源 | 否 | 通常否 | 只改收货地址中的手机号 |
| DELETE | 删除资源 | 否 | 是 | 删除未支付的购物车条目 |

*状态码*是三位数字，第一位表示类别，决定客户端下一步该做什么。*原因短语*只是给人看的说明，客户端不得依赖它判断结果。

| 类别 | 含义 | 客户端动作 | 典型状态码 |
| --- | --- | --- | --- |
| 1xx | 中间信息 | 继续等待 | `100 Continue` |
| 2xx | 成功 | 读取结果 | `200`、`201`、`202`、`204` |
| 3xx | 重定向或缓存有效 | 按 `Location` 或缓存策略处理 | `301`、`304` |
| 4xx | 请求本身有问题 | 修改请求，通常不重试 | `400`、`401`、`403`、`404`、`405`、`409`、`429` |
| 5xx | 服务端或依赖有问题 | 退避重试或告警 | `500`、`502`、`503`、`504` |

几个最容易被混淆的码：`401` 是未认证（缺凭据或凭据失效），`403` 是已认证但无权限；`405` 表示资源存在但不支持该方法，响应必须带 `Allow` 头；`409` 表示与当前资源状态冲突，例如重复退款或版本过期；`429` 表示被限流，通常带 `Retry-After`。

## 工作原理

以客服点击“同意退款”为例，一次请求按以下顺序发生：

1. 浏览器与退款服务完成 TCP 连接与 TLS 握手（上一课内容），随后发送请求行 `POST /refunds HTTP/1.1`。
2. 头部携带 `Host`、`Authorization`、`Content-Type: application/json`、`Content-Length` 和 `Idempotency-Key: refund-1001-1`。
3. 空行之后是 JSON 主体 `{"order_id":"1001","amount":199.0}`。服务端按 `Content-Length` 读取指定字节数，不能“读到连接关闭”为止。
4. 服务端解析起始行并路由到退款处理器；先认证（失败返回 401），再鉴权（失败返回 403）。
5. 校验参数：缺字段或类型错误返回 400；订单不存在返回 404；金额超过 500 元转入人工审核，返回 202 与任务地址，而不是让连接空挂。
6. 服务端用幂等键查重：键已存在就直接复用上次结果，不再调用支付供应商。
7. 新退款创建成功后返回 201，并用 `Location` 指向该退款资源，客服后续可查询它。
8. 支付供应商返回 503：退款服务不能把它包装成 200，而应记录失败、返回可重试的 5xx 或转为异步任务状态。
9. 客户端按类别决策：2xx 结束并展示结果；4xx 提示客服修改；429 与 5xx 按 `Retry-After` 退避重试，且必须复用同一个幂等键。
10. 仓库回写使用 `PUT /orders/1001/status`，重复执行后状态仍是 `refunded`，因此网络超时后重试是安全的。

这里有一条贯穿始终的分工：**状态码表达协议层结果，业务错误码表达具体原因**，两者同时存在而不是互相替代。外层返回 409，响应体再写 `{"error":"refund_already_exists","refund_id":"R-1"}`，网关、监控和客服页面才能各取所需。

## 架构与选型

| 决策点 | 选项 | 适用 | 不适用或代价 | 判断依据 |
| --- | --- | --- | --- | --- |
| 错误表达 | HTTP 状态码 + 响应体 `error` 字段 | 所有对外接口 | 需要维护两套文档 | 网关、监控、重试库都按状态码工作 |
| 创建退款 | 同步等待并返回 201 | 供应商 P99 小于 2 秒 | 供应商 1–90 秒波动，连接与页面都会超时 | 页面等待预算与下游稳定性 |
| 创建退款 | 返回 202 + 任务地址 | 长耗时、可人工接管 | 前端要轮询，状态机更复杂 | 能否把“受理”和“完成”分开 |
| 重试策略 | 客户端携带幂等键重试 | 超时、429、5xx | 服务端要实现去重存储与过期清理 | 该操作是否允许重复副作用 |
| 状态回写 | `PUT` 整体替换 | 字段少、状态机简单 | 并发覆盖风险，需要版本号或 `ETag` | 是否存在并发写同一资源 |
| 传输格式 | HTTPS 上的 JSON | 浏览器与跨组织集成 | 高频内部调用有解析开销 | 可读性、调试成本与团队熟悉度 |

选型顺序：先确认操作是否可重复（决定方法），再确认等待预算（同步还是 202），最后定义失败状态码与重试边界。反过来先挑框架，容易把“超时后不知道成功没有”留成永久缺陷。

## 最小示例

问题：用标准库程序观察请求如何变成响应、状态码如何随语义变化，以及幂等键如何阻止重复退款。

环境：Python 3.9 及以上（用到 `str.removeprefix`），无第三方依赖，仅监听 `127.0.0.1` 的系统分配端口。

```python
"""http_demo.py：用标准库观察请求、响应与状态码语义，只监听本机回环地址。"""
import http.client                       # 标准库 HTTP 客户端，用来构造请求报文
import json                             # 序列化 JSON 主体
import threading                        # 在后台线程运行服务端
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORDERS = {"1001": {"status": "paid", "amount": 199.0}}  # 内存订单，模拟数据库
REFUNDS = {}                            # 幂等键 -> 已创建的退款，模拟去重表


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"       # 声明 HTTP/1.1，响应需要明确的长度

    def log_message(self, *args):
        pass                            # 关掉默认访问日志，输出只保留我们关心的结果

    def _json(self, code, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 主体是字节而不是字符串
        self.send_response(code)        # 写状态行：HTTP/1.1 201 Created
        self.send_header("Content-Type", "application/json; charset=utf-8")  # 声明主体类型
        self.send_header("Content-Length", str(len(body)))  # 客户端靠长度判断主体到哪里结束
        self.send_header("Connection", "close")             # 示例使用短连接，避免残留连接干扰
        for key, value in (headers or {}).items():
            self.send_header(key, value)  # 追加 Location、Allow、Idempotency-Replayed 等语义头
        self.end_headers()                # 发送空行，结束头部
        self.close_connection = True
        self.wfile.write(body)            # 最后写主体

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))  # 按头部长度读，不能读到连接关闭
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/orders":
            self._json(200, {"items": sorted(ORDERS)})  # 集合可读，返回 200
        elif self.path.startswith("/orders/"):
            order_id = self.path.rsplit("/", 1)[-1]      # 从路径取出资源标识
            order = ORDERS.get(order_id)
            if order is None:
                self._json(404, {"error": "order_not_found", "order_id": order_id})  # 资源不存在用 404
            else:
                self._json(200, {"id": order_id, **order})  # 读取成功用 200
        else:
            self._json(404, {"error": "not_found", "path": self.path})

    def do_POST(self):
        if self.path == "/orders":
            self._json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})  # 方法不对用 405，并告知可用方法
            return
        if self.path != "/refunds":
            self._json(404, {"error": "not_found", "path": self.path})
            return
        key = self.headers.get("Idempotency-Key")  # 客户端生成的幂等键
        if not key:
            self._json(400, {"error": "idempotency_key_required"})  # 缺必需头部属于客户端问题
            return
        if key in REFUNDS:
            self._json(200, REFUNDS[key], {"Idempotency-Replayed": "true"})  # 重复提交复用结果，不再创建
            return
        payload = self._read_json()
        refund = {"id": f"R-{len(REFUNDS) + 1}", "order_id": payload.get("order_id"), "status": "accepted"}
        REFUNDS[key] = refund
        self._json(201, refund, {"Location": f"/refunds/{refund['id']}", "Idempotency-Key": key})  # 201 表示新建了资源

    def do_PUT(self):
        if not self.path.startswith("/orders/"):
            self._json(404, {"error": "not_found", "path": self.path})
            return
        order_id, _, action = self.path.removeprefix("/orders/").partition("/")
        if order_id not in ORDERS or action != "status":
            self._json(404, {"error": "order_not_found", "order_id": order_id})
            return
        ORDERS[order_id]["status"] = self._read_json().get("status", ORDERS[order_id]["status"])  # 整体替换状态
        self._json(200, {"id": order_id, **ORDERS[order_id]})


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # 端口 0 交给系统分配空闲端口
    host, port = server.server_address
    threading.Thread(target=server.serve_forever, daemon=True).start()  # 后台线程接收请求

    def call(method, path, body=None, headers=None):
        conn = http.client.HTTPConnection(host, port, timeout=5)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload,
                     headers={"Content-Type": "application/json", **(headers or {})})  # 起始行 + 头部 + 主体
        resp = conn.getresponse()                          # 读取状态行与头部
        text = resp.read().decode("utf-8")                 # 按声明长度读取主体
        extra = {k: resp.getheader(k) for k in ("Location", "Allow", "Idempotency-Replayed")
                 if resp.getheader(k)}                     # 只打印与语义相关的响应头
        print(f"{method} {path} -> {resp.status} {resp.reason} {extra}")
        print(f"  body: {text}")
        conn.close()

    call("GET", "/orders/1001")                            # 200：读取存在的资源
    call("GET", "/orders/9999")                            # 404：资源不存在
    call("POST", "/orders", {"order_id": "1001"})           # 405：集合资源不接受 POST
    call("POST", "/refunds", {"order_id": "1001"})          # 400：缺少幂等键
    call("POST", "/refunds", {"order_id": "1001", "amount": 199.0},
         {"Idempotency-Key": "refund-1001-1"})              # 201：首次创建退款
    call("POST", "/refunds", {"order_id": "1001", "amount": 199.0},
         {"Idempotency-Key": "refund-1001-1"})              # 200：重复提交复用原结果
    call("PUT", "/orders/1001/status", {"status": "refunded"})   # 200：状态改为已退款
    call("PUT", "/orders/1001/status", {"status": "refunded"})   # 200：再执行一次，结果相同
    server.shutdown()                                       # 主动停止后台服务


if __name__ == "__main__":
    main()
```

整体流程分三段：`_json` 负责按“状态行—头部—空行—主体”的顺序拼响应；`do_*` 方法把 URL 与 HTTP 方法映射到处理逻辑，并在语义不匹配时返回 4xx；`call` 构造请求并打印状态行、语义头和主体。关键设计：状态码由语义决定；幂等键在进入业务逻辑前查重；每个响应都给 `Content-Length`。

运行 `python3 http_demo.py` 后，预期输出（地址与端口每次不同）：

```text
GET /orders/1001 -> 200 OK {}
  body: {"id": "1001", "status": "paid", "amount": 199.0}
GET /orders/9999 -> 404 Not Found {}
  body: {"error": "order_not_found", "order_id": "9999"}
POST /orders -> 405 Method Not Allowed {'Allow': 'GET'}
  body: {"error": "method_not_allowed"}
POST /refunds -> 400 Bad Request {}
  body: {"error": "idempotency_key_required"}
POST /refunds -> 201 Created {'Location': '/refunds/R-1'}
  body: {"id": "R-1", "order_id": "1001", "status": "accepted"}
POST /refunds -> 200 OK {'Idempotency-Replayed': 'true'}
  body: {"id": "R-1", "order_id": "1001", "status": "accepted"}
PUT /orders/1001/status -> 200 OK {}
  body: {"id": "1001", "status": "refunded", "amount": 199.0}
PUT /orders/1001/status -> 200 OK {}
  body: {"id": "1001", "status": "refunded", "amount": 199.0}
```

注意第二次 `POST /refunds` 返回的是 200 而不是 201，且退款编号仍是 `R-1`：这正是“重试安全”的证据。

## 动手实验

前置条件：已安装 Python 3.9+；本机可监听回环端口；有 `curl`；不需要外网和任何密钥。

1. 将上面的代码保存为 `/tmp/http_demo.py`，先原样运行一次，记录 8 行状态码序列。
2. 启动一个静态文件服务：在任意空目录运行 `python3 -m http.server 8000`，另开终端执行 `curl -i http://127.0.0.1:8000/`，观察状态行、`Content-Type` 与 `Content-Length`。
3. 继续执行 `curl -i http://127.0.0.1:8000/missing`，应看到 404；再执行 `curl -i -X POST http://127.0.0.1:8000/`，观察标准库对未实现方法返回的 501：它**不带** `Allow` 头（RFC 9110 只对 405 强制要求 `Allow`），与前面 `405` 带 `Allow: GET` 正好形成对照。
4. 把演示脚本中重复提交分支的 `self._json(200, ...)` 改成 `self._json(409, {"error": "refund_exists"})`，重跑并对比客服端可读到的结果。
5. 恢复改动，确认最终状态码序列与预期一致。

预期结果：演示脚本依次输出 200、404、405、400、201、200、200、200；`curl` 分别得到 200、404、501；`201` 响应带 `Location`，`405` 响应带 `Allow: GET`，重复提交响应带 `Idempotency-Replayed: true`。`501` 不带 `Allow`，与 `405` 带 `Allow` 形成对照，说明“未实现”与“方法不允许”是两种语义。

验证方法：用 `curl -i` 逐条核对状态行与关键头部；检查重复 `POST` 后 `REFUNDS` 只含一个键；确认脚本退出码为 0。

清理方法：在静态服务终端按 `Ctrl+C`；删除 `/tmp/http_demo.py`；用 `lsof -i :8000` 确认端口已释放。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 页面提示“成功”，业务其实失败 | 所有响应都返回 200，用响应体表示失败 | 在开发者工具查看状态码与响应体是否矛盾 | 失败改返回 4xx/5xx，保留业务 `error` 码 |
| 同一订单退了两笔款 | `POST` 无幂等键，超时后客户端重试 | 对比退款单数量与请求日志中的 `Idempotency-Key` | 要求幂等键并落去重表，重复请求复用结果 |
| 监控里错误率长期为零 | 错误被包装成 200 | 统计状态码分布，抽查 200 响应体 | 按类别返回状态码，网关按 5xx 与 429 告警 |
| 客户端对 400 反复重试 | 把 4xx 当成临时故障 | 看重试日志中的请求参数是否完全相同 | 只对 429、5xx 退避重试；4xx 修正请求 |
| `405` 响应没有 `Allow` | 方法契约缺失 | `curl -i -X POST` 查看响应头 | 补 `Allow`，并在接口文档中写明支持的方法 |
| 响应体被截断或请求一直挂起 | 缺少 `Content-Length` 或未处理分块传输 | 对照响应头长度与实际接收字节数 | 明确长度，或正确实现 `Transfer-Encoding: chunked` |

## 安全与生产注意事项

**<u>用 404 隐藏“无权访问”，却在响应体、响应时间或错误文案上泄露资源是否存在。</u>** 攻击者可以枚举订单号，推断他人订单是否真实存在，甚至利用时序差异做侧信道。缓解方式是统一 403/404 策略、统一错误体与响应时间，服务端记录审计日志，并对订单 ID 使用不可枚举的标识。

**<u>把 5xx 的原始异常、堆栈或上游响应体直接返回给客户端。</u>** 这会泄露内网地址、SQL 片段或密钥信息。对外只返回稳定的 `error` 码和 `request_id`，详细堆栈写日志；由网关统一改写 5xx 响应体。

**<u>对非幂等 POST 无条件重试，而服务端没有幂等键去重。</u>** 后果是重复退款、重复扣款和对账困难。重试必须限定在超时、429 与 5xx，并复用同一幂等键；服务端用唯一约束加结果复用兜底。

## 本课总结

- HTTP 报文由起始行、头部、空行、主体组成；响应把起始行换成状态行。
- 方法表达语义：GET 与 HEAD 安全，GET、PUT、DELETE 幂等，POST 通常不幂等。
- 状态码类别决定客户端动作：2xx 读结果，4xx 改请求，429 与 5xx 才考虑退避重试。
- 幂等键把“重试”从危险动作变成安全动作，但前提是服务端真的去重。
- 状态码是协议层契约，业务错误码补充原因，二者不能互相替代。

## 思考题

客服工作台要求 2 秒内给出结果，而支付供应商的 P99 是 90 秒。你会让 `POST /refunds` 同步等待并返回 201，还是返回 202 加任务地址？请写出报文的关键字段（状态码、头部、主体）、供应商失败时的状态码，以及客服重复点击时如何保证只退一次。

参考思路：把“受理”和“完成”分开，用 202、`Location` 与幂等键表达受理，用任务状态表达完成；供应商 5xx 时任务标记为可重试，而不是把异常直接抛给客服；重复点击携带同一幂等键，返回同一任务地址。评价时看三点：是否区分受理成功与处理成功，是否说明重试边界，是否指出 202 的语义不是“已完成”。

## 小测

1. 下列哪组方法都是幂等的？  
   A. GET、POST　B. PUT、DELETE　C. POST、PATCH　D. GET、POST、PATCH
2. 服务端成功创建退款并要指向新资源，最合适的状态码与头部是？  
   A. 200 + `ETag`　B. 201 + `Location`　C. 202 + `Retry-After`　D. 204 + `Allow`
3. 客户端收到 403 后应当？  
   A. 立即重试　B. 换一个幂等键重试　C. 停止并检查权限或凭据　D. 当作 404 处理
4. 429 与 503 的共同点是？  
   A. 都表示客户端参数错误　B. 都可能在退避后恢复　C. 都表示资源不存在　D. 都要求更换方法
5. 判断：PUT 幂等意味着同一个请求发送两次，服务端只执行一次。
6. 场景题：仓库回写接口 `POST /orders/1001/status` 超时后被重试，订单被重复标记为“已退款”，库存也被回补两次。请指出至少两个设计问题并给出修正。

## 答案与解析

1. **B。** PUT 与 DELETE 重复执行后最终状态不变。A、C、D 都含 POST，创建类操作会生成新资源，不具幂等性；PATCH 是否幂等取决于实现，不能默认安全。
2. **B。** 201 表示已创建，`Location` 指向新资源。A 的 200 不表达“新建”，`ETag` 用于缓存与并发控制；C 的 202 是已受理未完成；D 的 204 无响应体，`Allow` 属于 405 场景。
3. **C。** 403 是已认证但无权限，原样重试仍会被拒。A、B 会放大无效请求；D 会把权限问题误报成不存在，除非团队有意采用防枚举策略并统一处理。
4. **B。** 两者都是临时性失败，可按 `Retry-After` 退避重试。A 错在它们不是参数问题；C 对应 404；D 与状态码类别无关。
5. **错。** 幂等只保证最终状态相同，不保证只执行一次；服务端可能真的处理了两次。要做到“只执行一次”，需要幂等键加去重记录。
6. 参考：一是用 POST 表达状态替换，语义上应为 PUT；二是没有幂等键或版本号，超时重试无法识别重复；三是库存回补缺少唯一约束，产生两次副作用；四是超时后客户端无法判断是否成功。修正：改用 `PUT /orders/1001/status` 并带 `If-Match` 版本号，增加幂等键与唯一约束，回补动作去重，超时后先 `GET` 查询再决定是否重试。

动手实验参考：脚本应依次得到 200、404、405、400、201、200、200、200；把重复分支改成 409 后，第二次提交变为冲突，客服端需要提示“已受理”而不是“失败”。`python3 -m http.server` 对 POST 返回 501，且**不带** `Allow` 头；这正好与 405 带 `Allow` 形成对照：501 表示“服务端没有实现这个方法”，405 表示“资源存在、但不允许这个方法”，两者是不同语义（RFC 9110 只对 405 强制要求 `Allow`）。

## 延伸阅读与下一课

- MDN：[HTTP 请求方法](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Methods)与[HTTP 响应状态码](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Status)。
- RFC 9110：《HTTP Semantics》，方法与状态码的权威定义：<https://www.rfc-editor.org/rfc/rfc9110.html>。
- RFC 9112：《HTTP/1.1》，报文格式与消息长度的权威定义：<https://www.rfc-editor.org/rfc/rfc9112.html>。
- Python 官方文档：[http.server](https://docs.python.org/3/library/http.server.html)与[http.client](https://docs.python.org/3/library/http.client.html)。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[TCP/IP、DNS 与防火墙](02-tcp-ip-dns-and-firewall.md)。
- 下一课：[Header、Cookie 与缓存](04-headers-cookies-and-caching.md)。
