---
title: 轮询、SSE、WebSocket 与回调
slug: polling-sse-websocket-and-callbacks
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - webhooks-signing-and-replay-protection
outcomes:
  - 按变化频率、延迟要求和连接规模为退款进度选择轮询、SSE、WebSocket 或回调
  - 写出可续传的 SSE 事件帧并说明 Last-Event-ID 生效的前提
  - 为回调设计兜底与去重，使通知丢失时状态仍然收敛
last_reviewed: 2026-10-19
---

# 轮询、SSE、WebSocket 与回调

## 为什么需要学习

晴空商城的退款进度在三个地方显示：会员的订单页、客服工作台、仓储备货看板。此刻这三个客户端都在用 `setInterval` 每 3 秒请求一次退款接口。日常 QPS 约 40，大促当天升到 900，服务开始超时；客服却抱怨“客户都收到退款短信了，我这边还显示审核中”。根因是“如何知道状态变了”被做成了盲目的定时询问。另一条路也不干净：支付商的回调偶尔延迟十几分钟甚至丢失，订单永久停在“退款中”。

> **核心结论：** 状态同步的几种常见手段各有明确的成本结构——轮询买的是简单，SSE 买的是单向连续的推送，WebSocket 买的是双向低延迟，回调买的是省资源；选错不是性能问题，而是“该到的事件没到，却没人负责发现”。

## 学习目标

完成本课后，你能够：

- 区分短轮询、长轮询、SSE、WebSocket 与回调的触发方向、连接形态和主要成本，并为给定场景选出最小够用的方案。
- 写出包含 `id`、`event`、`data`、`retry` 的 SSE 帧，并解释 `Last-Event-ID` 续传为什么依赖服务端的事件保留。
- 为晴空商城退款进度画出一条“推送为主、查询兜底”的读取路径，并说明回调丢失后如何收敛。
- 用 `python3` 标准库起一个三模式 mock 服务，并用 `curl` 测出长轮询的等待时间与 SSE 的续传行为。

## 前置知识

- 回看上一课：[Webhook、签名与重放保护](07-webhooks-signing-and-replay-protection.md)。
- 知道一次 HTTP 请求由方法、路径、头和体组成，且响应可能没有 `Content-Length`（参见[HTTP 请求、响应与状态码](../02-web-and-network/03-http-request-response.md)）。
- 理解超时、重试和幂等的含义（参见[超时、重试、退避与幂等](05-timeout-retry-backoff-and-idempotency.md)）。
- 了解熔断与降级的作用（参见[熔断、降级与隔离](06-circuit-breaking-degradation-and-isolation.md)）。
- 能读 50 行左右的 `python3` 脚本：`with` 语句、线程、`http.server`。

## 业务场景

晴空商城的退款单状态由退款服务持有，流转为“待审核 → 已批准 → 已退款”。三个消费方诉求不同：

1. 会员订单页：只在用户停留页面时关心，几十秒延迟可接受，但长连接不能拖慢首屏。
2. 客服工作台：一名客服同时开 8 个工单页，要求状态变化 1 秒内可见，且刷新不能打断正在填写的备注。
3. 仓储备货看板：只有“已退款”才释放库存占用，延迟影响可售数量，但看板是常驻大屏，连接数很少。

约束：全部跨公网、必经反向代理与负载均衡；退款服务已有 HTTP API，不想为此引入新中间件；丢失的通知必须能被发现，而不是靠投诉。

## 核心概念

*轮询*（polling）是客户端按固定间隔重复请求，服务端每次返回当前快照。它不理解“变化”，只理解“现在是什么”。

*长轮询*（long polling）仍是客户端发起 GET，但服务端把请求挂起，直到状态变化或超时才响应一次。<u>它没有取消请求，只是把“问”的频率交给服务端控制。</u>

*SSE*（Server-Sent Events，服务器发送事件）是客户端发一次 GET、服务端保持响应不结束、按文本帧持续写入的单向通道，其响应体就是 `Content-Type: text/event-stream` 的*事件流*。

*断线续传*指重连时只补缺失部分，靠带上最后收到的事件编号；SSE 用 `Last-Event-ID` 请求头承载它。

*WebSocket* 是通过 HTTP `Upgrade` 握手建立的全双工连接，握手后双向收发二进制或文本帧，不再有 HTTP 请求-响应的结构。*心跳*是长连接上周期发送的空帧或 ping，用来证明连接仍然可用。

*回调*（callback）由服务端在事件发生后主动向事先登记的地址发起一次 HTTP 请求，方向与查询相反。对提供方叫回调，对接入方通常叫 Webhook；<u>它是通知，不是账本</u>。

| 方式 | 触发方 | 连接形态 | 典型延迟 | 主要成本 |
| --- | --- | --- | --- | --- |
| 短轮询 | 客户端定时 | 每次短连接 | 0 到间隔 | 请求数 ≈ 时长 ÷ 间隔，与变化次数无关 |
| 长轮询 | 客户端发起、服务端决定何时回 | 挂起的 HTTP 请求 | 近实时 | 每客户端占一个连接与执行资源 |
| SSE | 服务端 | 一条长期 GET 响应 | 近实时 | 单向；需事件存储才能续传 |
| WebSocket | 双方 | 升级后的长连接 | 最低 | 自建协议、心跳、重连、代理兼容 |
| 回调 | 服务端（第三方） | 每次事件一个 POST | 取决于对方 | 会丢、会重、会乱序，必须兜底 |

## 工作原理

### 短轮询与长轮询

1. 客户端每 3 秒 `GET /refund/R-1001`，服务端读库返回当前状态。
2. 客户端比较 `version` 字段决定是否重绘。
3. 长轮询把第 1 步改成带 `timeout` 的请求，服务端记录进入时的版本号。
4. 服务端在条件变量上等待，状态变化时立即返回，超时则返回旧版本（仍用 `200`，让客户端自己比较）。
5. 客户端收到响应后立刻发起下一次长轮询，因此请求数约等于“变化次数 + 超时次数”。<u>服务端超时必须短于代理的空闲超时</u>，否则中间层先断开，客户端只会看到 `502` 或 `504`。

### SSE 与断线续传

1. 客户端发 `GET /refund/R-1001/events`，期望 `text/event-stream`。
2. 服务端返回 200，不设置 `Content-Length`，持续写入帧；每帧由若干 `字段: 值` 行加一个空行结束。
3. 事件帧形如 `id: 2` / `event: status` / `data: {...}`；`retry: 3000` 告诉浏览器重连间隔。
4. 连接断开后，浏览器自动重连，并在请求头带上最后收到的 `id`，即 `Last-Event-ID`。
5. 服务端从该编号之后重放事件。<u>没有持久化事件日志，就没有真正的续传</u>——重放只能退回“返回当前快照”，客户端务必自己按 `id` 去重。
6. 连接长时间没有事件时，服务端应发注释行（以 `:` 开头的空帧）当*心跳*，防止代理按空闲超时切断。

### WebSocket 与回调

1. WebSocket 先发一次带 `Upgrade: websocket` 与 `Sec-WebSocket-Key` 的 HTTP 请求，服务端回 `101 Switching Protocols`。
2. 之后双方按帧收发，应用必须自己定义消息类型、序号、心跳和断线重连后的补数据策略。
3. 回调则是反向的：接入方注册 URL，提供方在事件发生时 `POST` 一次。
4. 接收方验签、按事件 `id` 去重、立即返回 `200`，把处理放进后台任务。
5. 回调会丢会重，读取路径必须另有定时对账或主动查询，状态以自有 API 为准。

## 架构与选型

| 方案 | 适用 | 不适用 | 权衡要点 |
| --- | --- | --- | --- |
| 短轮询 | 状态几乎不变、客户端少、实现越简单越好；内部管理后台 | 变化频繁、连接数大、要求秒级可见 | 实现零成本，代价随“人数 × 页面数 ÷ 间隔”线性增长 |
| 长轮询 | 只需要“有新状态时通知”、又不想处理事件流格式 | 每客户端都要占一个连接，高并发下线程/协程压力大 | 兼容性最好，只要 HTTP；注意超时、连接数与代理限制 |
| SSE | 单向推送：订单进度、通知、日志尾随、大屏看板 | 需要客户端上行、需要二进制、需要极低延迟 | 自动重连 + `id` 续传是白送的能力；受浏览器同域连接数限制 |
| WebSocket | 双向高频：协同编辑、聊天、实时竞价的买卖盘 | 只有单向通知；连接数远超服务端承受能力 | 延迟最低但运维成本最高：心跳、重连、鉴权刷新、代理升级 |
| 回调 | 第三方事件通知，无法让对方向自己发请求 | 要求强一致、要求绝对不丢、对方无重试 | 省自己的连接，但必须验签、去重、乱序容忍和兜底对账 |

选型按顺序问四个问题：状态多久变一次？延迟要求秒级还是分钟级？只有服务端→客户端，还是也要上行？同时在线客户端规模多大？答案通常直接排除三个选项。组合是常态：SSE 推主路、打开页面查一次全量、每 5 分钟对账兜底。

## 最小示例

问题：需要一个服务，用同一份状态同时演示短轮询、长轮询和 SSE，并能验证续传。环境：`python3` 3.9 以上、`curl`，本机端口 `8931`（若被占用，改脚本里的端口即可）。输入：`GET /advance` 推进一步；输出：三种读取方式的数据与等待时间。

```python
#!/usr/bin/env python3
"""晴空商城退款进度 mock：一个端口同时提供短轮询、长轮询与 SSE 三种读取方式。"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOCK = threading.Condition()  # 保护 STATE 与 EVENTS，同时用于唤醒长轮询和 SSE
STATE = {"status": "reviewing", "version": 1}
EVENTS = [{"id": 1, "event": "status",
           "data": json.dumps({"status": "reviewing", "version": 1})}]
STEPS = [("approved", 2), ("refunded", 3)]  # 待审核 → 已批准 → 已退款


def advance():
    """模拟仓储/支付侧推进一次状态，并追加一条事件。"""
    with LOCK:  # 状态与事件必须一起改，否则推送与快照会不一致
        if len(EVENTS) > len(STEPS):
            return STATE
        status, version = STEPS[len(EVENTS) - 1]
        STATE.update(status=status, version=version)
        EVENTS.append({"id": version, "event": "status",
                       "data": json.dumps({"status": status, "version": version})})
        LOCK.notify_all()  # 唤醒所有阻塞中的长轮询与 SSE 连接
        return STATE


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # 允许连接复用，SSE 才能持续写

    def log_message(self, *args):
        pass  # 关掉访问日志，实验输出更干净

    def reply(self, code, body):
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))  # 一次性响应必须声明长度
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/refund/R-1001":                 # 短轮询：立即返回当前快照
            self.reply(200, json.dumps(STATE))
        elif url.path == "/refund/R-1001/wait":          # 长轮询：挂起等版本变化
            self.long_poll(float(query.get("timeout", ["5"])[0]))
        elif url.path == "/refund/R-1001/events":        # SSE：同一连接连续推送
            self.sse(int(self.headers.get("Last-Event-ID", "0")))
        elif url.path == "/advance":                     # 演示用：手动推进一步
            self.reply(200, json.dumps(advance()))
        else:
            self.reply(404, '{"error":"not found"}')

    def long_poll(self, timeout):
        with LOCK:
            start_version = STATE["version"]  # 只等“比自己进入时更新”的状态
            deadline = time.monotonic() + timeout
            while STATE["version"] == start_version:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                LOCK.wait(remaining)  # 等锁时释放锁，被 notify_all 唤醒后重新判断
            body = json.dumps(STATE)
        self.reply(200, body)  # 超时也回 200，客户端靠 version 判断有没有变化

    def sse(self, last_id):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")  # 声明这是事件流
        self.send_header("Cache-Control", "no-store")          # 不许任何层缓存
        self.send_header("Connection", "close")  # 不设长度，靠关闭连接结束流
        self.end_headers()
        self.close_connection = True
        sent = last_id  # 从这里之后开始补，续传的关键状态
        try:
            self.wfile.write(b"retry: 3000\n\n")  # 告知客户端断线 3 秒后再来
            while True:
                with LOCK:
                    pending = [e for e in EVENTS if e["id"] > sent]
                    if not pending:
                        LOCK.wait(timeout=10)  # 无新事件时挂起，避免空转
                        continue
                for event in pending:
                    frame = (f"id: {event['id']}\nevent: {event['event']}\n"
                             f"data: {event['data']}\n\n")
                    self.wfile.write(frame.encode())
                    sent = event["id"]  # 推进游标，重连时它决定从哪补
        except (BrokenPipeError, ConnectionResetError):
            return  # 客户端断开是常态，不是错误


if __name__ == "__main__":
    print("listening on http://127.0.0.1:8931")
    ThreadingHTTPServer(("127.0.0.1", 8931), Handler).serve_forever()
```

整体流程：`advance()` 在锁内同时更新快照与事件列表，再用 `notify_all()` 唤醒等待者；长轮询按“进入时版本”判断是否返回，SSE 按 `sent` 游标逐条推送。三个关键选择：状态与事件同锁，保证快照与推送不矛盾；长轮询超时返回 `200` 而非 `204`，免得客户端把超时当失败；SSE 用游标而非当前状态响应重连，才有真正的续传。

运行 `python3 refund_feed.py`，预期第一行是 `listening on http://127.0.0.1:8931`。另一个窗口执行 `curl -sN http://127.0.0.1:8931/refund/R-1001/events`，预期输出（首块是 `retry` 指令，不派发事件）：

```text
retry: 3000

id: 1
event: status
data: {"status": "reviewing", "version": 1}
```

## 动手实验

前置条件：本机 `python3` 3.9+、`curl`，端口 `8931` 空闲。实验只用回环地址，不访问外网。

1. 把上面的脚本保存为 `refund_feed.py`，在终端 A 运行 `python3 refund_feed.py`，看到监听提示。
2. 短轮询：在终端 B 执行 `for i in 1 2 3; do curl -s http://127.0.0.1:8931/refund/R-1001; echo; sleep 1; done`。预期三次都返回 `{"status": "reviewing", "version": 1}`，即 3 次请求换到 0 次变化。
3. 长轮询：终端 B 执行 `curl -s -w 'time=%{time_total}s\n' 'http://127.0.0.1:8931/refund/R-1001/wait?timeout=5'`，它会挂住；1 秒后在终端 C 执行 `curl -s http://127.0.0.1:8931/advance`。
4. 预期终端 B 打印 `{"status": "approved", "version": 2}` 与 `time=1.0` 左右的耗时：一次请求、一次变化，等待由服务端承担。
5. SSE：终端 B 执行 `curl -sN http://127.0.0.1:8931/refund/R-1001/events`，会先补发 `id: 1`、`id: 2` 然后挂住；终端 C 再执行一次 `/advance`，B 应立刻多出 `id: 3`。按 `Ctrl-C` 断开。
6. 续传：终端 B 执行 `curl -sN -H 'Last-Event-ID: 1' http://127.0.0.1:8931/refund/R-1001/events`，预期只收到 `id: 2` 与 `id: 3`，没有 `id: 1`。这证明服务端按编号补齐，而不是从头重放。
7. 验证：核对请求数（短轮询 3 次 0 变化，长轮询 1 次 1 变化）与 `id` 是否重复；把 `Last-Event-ID` 改成 `99`，应只收到 `retry` 块并挂住，说明“没有新事件”不等于“报错”。
8. 清理：在终端 A 按 `Ctrl-C`，删除 `refund_feed.py`；脚本不写文件、不连数据库，没有残留状态。

若第 5 步在 `id: 1` 后连接就结束，通常是 `curl` 没加 `-N`（看不到流式写入）或中间层改写了 `Content-Length`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 长轮询偶发 `502`/`504` | 服务端超时长于代理空闲超时 | 对比应用 `timeout` 与负载均衡空闲超时，看失败是否总在固定秒数 | 服务端超时留余量（如 25 秒对 30 秒），超时正常返回旧快照 |
| SSE 每 30 秒自动重连一次 | 代理缓冲响应或空闲超时切断 | 用 `curl -N` 直连与经代理各跑一次，比较连接存活时长 | 关闭代理缓冲、加注释行心跳、设置 `Cache-Control: no-store` |
| 重连后收到重复事件 | 服务端忽略 `Last-Event-ID`，或客户端没按 `id` 去重 | 日志打印请求头与服务端实际起始游标 | 服务端按编号过滤，客户端按 `id` 幂等处理 |
| WebSocket 在部分网络握手失败 | 代理未透传 `Upgrade`/`Connection` 头 | 看响应是否为 `101`，缺哪个头 | 配置代理升级支持，或降级为 SSE/轮询 |
| 回调丢了，订单永久“退款中” | 把回调当唯一状态源 | 统计回调到达数与应用侧状态变化数的差额 | 定时对账 + 主动查询 + 超时告警 |

## 安全与生产注意事项

**<u>SSE 与 WebSocket 通常在建立连接时鉴权一次，长连接内撤权不会自动生效。</u>**后果是被停权、调岗的人仍能持续收到退款金额与会员手机号，直到关页面。缓解：连接设最长寿命（如 15 分钟），重连时重校令牌，每次派发事件前按订阅关系再判一次权限，而不是信任建连时的身份。

**<u>把第三方回调当作可信状态源，等于把“已退款”的写入权交给任何能构造 POST 的人。</u>**伪造或重放一次通知就可能造成资金损失。缓解：验签、校验时间戳窗口、按事件 `id` 去重，回调只用来触发查询，最终状态以自查对方 API 的版本为准；签名与重放保护复用上一课。

另外两件事要提前定：长轮询的挂起连接数与在线人数同量级，必须设每账号、每 IP 配额，否则重连风暴会打穿服务；事件不要夹带内部堆栈或他人数据，SSE 是明文流，订阅校验一有漏洞，泄露比普通接口更快。

## 本课总结

- 短轮询的成本由“时间 ÷ 间隔 × 客户端数”决定，与变化次数无关；简单，但不便宜。
- 长轮询把等待搬到服务端，请求数约等于“变化次数 + 超时次数”，必须让服务端超时小于代理超时。
- SSE 的价值不在“推”，而在 `id` 加 `Last-Event-ID` 带来的可重放续传；前提是服务端保留了事件。
- WebSocket 只在需要双向、高频、极低延迟时才划算，代价是自建心跳、重连、鉴权刷新和代理配置。
- 回调是通知不是账本：验签、去重、立即应答、异步处理，再加对账兜底，状态才会收敛。

## 思考题

客服工作台目前每 3 秒轮询一次，团队提议改成 WebSocket。请判断这个改动是否值得：分别说明数据方向、同时在线连接数、断线期间的补偿、鉴权刷新和运维成本，并给出一个更小改动就能达标的替代方案。

参考思路：只需服务端推、客户端不持续上行时，SSE 或“长轮询 + 对账”通常比 WebSocket 便宜；WebSocket 的收益在双向协作。无论选哪种，都要回答“断开的两分钟里错过了什么”，答案是版本号查询或事件补拉，而不是更频繁地推。

## 小测

1. 状态每秒可能变化、要求 1 秒内可见、客户端只读，最合适的是？  
   A. 1 秒短轮询　B. 长轮询　C. SSE　D. WebSocket
2. 判断：SSE 只能给浏览器用，Python 或 Go 服务端无法消费。
3. `Last-Event-ID` 解决什么问题？它生效需要服务端满足哪两个前提？
4. 判断：长轮询的 `timeout` 设得越短，服务端资源越省。
5. 场景题：支付商回调偶发延迟或丢失，订单长时间停在“退款中”。请给出一个不依赖“回调必达”的读取路径。

## 答案与解析

1. **C。**SSE 一条连接持续推，延迟取决于服务端写入。A 每秒一次请求会放大成 QPS；B 每次变化都要重连，头部与建连开销高；D 能力足够但引入不必要的双向协议、心跳与运维成本。
2. **错。**SSE 就是普通 HTTP 响应，任何能读流的客户端都能消费，`EventSource` 只是其中一种封装。这条误解常导致“服务端之间只能用 WebSocket”。
3. 解决断线后只补缺失事件、不重复不遗漏。前提一是事件有单调递增的 `id` 且能从任意 `id` 之后重放；二是保留窗口覆盖最长断线时长，超出时应退回全量快照，而不是静默丢事件。
4. **错。**过短会退化成短轮询，请求数随超时次数膨胀；过长则先被代理的空闲超时切断，客户端只看到网关错误。应让服务端超时略小于链路中最短的空闲超时。
5. 回调只当“有新状态的信号”：接收后立即验签、去重、回 `200`，再查自有退款 API 拿权威状态；同时定时对账（如每 5 分钟扫描停留超 10 分钟未终态的单据），对差额主动查询并告警。写入以查询结果为准，回调重复或乱序都不改变最终状态。

### 动手实验参考

第 2 步三次相同快照说明轮询分不清“没变化”和“没请求”；第 3、4 步的 `time=1.0` 说明等待成本转移到了服务端；第 6 步只出现 `id: 2`、`id: 3` 说明按编号补齐；第 7 步的 `Last-Event-ID: 99` 只收到 `retry` 块，说明服务端正确地“没有可补的内容”。第 5 步若没看到 `id: 3`，先确认 `/advance` 的版本已到 3，再确认 `curl` 加了 `-N`。

## 延伸阅读与下一课

- [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)：握手、帧格式与关闭码。
- [HTML Living Standard: Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)：`text/event-stream` 的字段语义、重连与 `Last-Event-ID` 规则。
- [MDN: Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)：`EventSource` 的用法与注意事项。
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)：幂等方法、`Retry-After` 与条件请求。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Webhook、签名与重放保护](07-webhooks-signing-and-replay-protection.md)。
- 下一课：[邮件、短信、定时任务与文件交换](09-email-sms-jobs-and-file-exchange.md)。
