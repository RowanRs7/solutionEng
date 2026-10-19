---
title: 会话、消息、状态与流式输出
slug: session-state-and-streaming
module: ai-solutions
stage: design
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - model-adapter-and-ai-gateway
outcomes:
  - 设计可持久化、可追加、可幂等的消息模型与会话状态
  - 写出符合规范的 SSE 事件帧，并说明断线续传与心跳的作用
  - 判断何时用流式、何时用轮询或 WebSocket，并说明状态该存在哪一层
last_reviewed: 2026-10-19
---

# 会话、消息、状态与流式输出

## 为什么需要学习

售后助手在第三周遇到一批“灵异问题”：客服刷新页面后，刚才的答复消失了；两个标签页同时打开同一个工单，消息顺序错乱，模型把上一轮的退款结论当成了本轮前提；网络抖动导致流式答复中断，客服点“重试”后，系统重新生成了一遍，账单上出现两次 Token 费用。

这些都不是模型问题，而是**状态放在哪里、消息如何追加、流如何恢复**没有定义。把会话当成“前端数组 + 每次全量重放”，在单用户演示时看不出问题，在多标签页与移动网络下必然出错。

> **核心结论：** 会话是服务端的追加日志，流式是这份日志的可恢复增量投影；两者都不能依赖前端内存作为唯一真相。

## 学习目标

完成本课后，你能够：

- 定义包含角色、工具调用与生成状态的消息结构，并说明哪些字段必须持久化。
- 用幂等键 + 单调序号实现“消息只追加一次、顺序稳定”。
- 写出合法的 SSE 事件帧，说明 `id`、`event`、`data`、注释行各自的作用。
- 设计断线续传：客户端携带 `Last-Event-ID`，服务端只补发缺失分片。
- 按场景选择 SSE、WebSocket 或轮询，并说明状态存放位置。

## 前置知识

- 回看上一课：[模型客户端、供应商适配层与 AI Gateway](03-model-adapter-and-ai-gateway.md)。
- 理解 HTTP 长连接与 `text/event-stream` 的基本概念。
- 知道数据库事务与唯一索引能保证“只写入一次”。
- 见过模型的 `messages` 数组格式。

## 业务场景

客服在工单页提问“订单 A1024 能退吗”，助手需要边想边输出：先给结论，再列依据，最后给操作建议。客服可能在 3 秒后切到别的标签页，再切回来时希望看到完整结果；也可能在手机上因信号中断而需要“继续”，而不是“重新生成”。

同时，主管要求：**同一个会话的任意两个客户端看到同一份历史**，且每轮答复都要能回答“这句话是哪次模型调用产生的”。这就把设计从“前端保存对话”推向“服务端事件日志”。

## 核心概念

| 概念 | 含义 | 本课做法 | 易错点 |
| --- | --- | --- | --- |
| *消息模型* | 一条对话记录的结构：角色、内容、工具调用、生成状态 | 统一表结构，含 `seq` 与 `turn_id` | 只存纯文本，丢失工具上下文 |
| *会话*（conversation） | 一段时间内的消息集合 | 一个 `session_id` 一条主记录 | 用用户 ID 当会话 ID，历史无限增长 |
| *轮次*（turn） | 一次用户提问及其答复 | 一个 `turn_id` 关联多条消息 | 一轮内多条助手消息无法排序 |
| *追加日志* | 只插入、不修改的历史记录 | 以 `seq` 单调递增 | 用“更新最后一条”实现流式，破坏审计 |
| *幂等追加* | 同一请求重复提交只产生一条记录 | 客户端 `client_msg_id` 唯一索引 | 重试导致重复提问 |
| *SSE* | 基于 HTTP 的服务端推送，`text/event-stream` | 每个分片一帧 | 用 JSON 数组一次性返回，失去流式意义 |
| *Last-Event-ID* | 浏览器重连时自动携带的最后事件 ID | 服务端据此补发 | 忽略该请求头，重放全部分片 |

消息角色与必填字段：

| 角色 | 内容 | 必填字段 | 说明 |
| --- | --- | --- | --- |
| `user` | 客服问题 | `content`、`client_msg_id` | 用客户端 ID 去重 |
| `assistant` | 模型答复或工具意图 | `content` 或 `tool_calls`、`model`、`bundle` | 记录实际模型与配置版本 |
| `tool` | 工具执行结果 | `tool_call_id`、`status` | 失败也要记录，便于回放 |
| `system` | 约束与规则 | `content`、`version` | 不随会话变化的部分单独存放 |

<u>把流式分片直接写成多条 `assistant` 消息</u>，会让历史变成几十条碎片，模型下一轮读到的是碎片而不是完整答复。正确做法是：流式期间累积到缓冲区，结束后一次性写入一条完整消息，同时把分片作为可选的传输产物单独存放。

## 工作原理

1. **创建或恢复会话**：客户端带 `session_id`；服务端校验归属（见第 8 课），无权限直接拒绝。
2. **幂等落库**：用户消息以 `client_msg_id` 为唯一键插入；重复提交返回已存在的那条，不重复计费。
3. **分配序号**：在同一会话内以 `seq` 单调递增分配位置，避免依赖时间戳排序。
4. **组装上下文**：按 `seq` 取最近若干条，按 Token 预算裁剪；裁剪规则与版本一起记录。
5. **建立流**：响应头设置 `Content-Type: text/event-stream`、`Cache-Control: no-cache`，并关闭代理缓冲。
6. **推送分片**：每个分片生成一帧，`id` 单调递增，`data` 为 JSON；每 15–30 秒发送一行以 `:` 开头的注释作为心跳。
7. **客户端处理**：`EventSource` 自动重连并带上 `Last-Event-ID`；服务端只补发该 ID 之后的分片。
8. **结束与落库**：收到 `done` 事件后，把累积内容写成一条完整 `assistant` 消息，记录 Token 用量与结束原因。
9. **中断处理**：客户端断开时，服务端可选择继续生成（结果仍落库）或取消；两者都要在消息上记录 `finish_reason`，避免“半条消息”被当成完整答复。
10. **历史重建**：新客户端打开会话时，只读完整消息与最后一轮的分片状态，不重放全部历史帧。

SSE 的帧格式很小，但语义严格：`data:` 行可重复出现并拼接，空行表示事件结束，`:` 开头是注释。

## 架构与选型

| 存储方案 | 适用 | 不适用 | 权衡 |
| --- | --- | --- | --- |
| 进程内字典 | 单实例原型、演示 | 多副本、重启不能丢 | 零依赖；无法水平扩展 |
| Redis（列表/流） | 需要低延迟、短期会话 | 需要长期审计与复杂查询 | 快；持久化与容量需规划 |
| 关系库（Postgres 等） | 需要审计、查询、合规留存 | 极高写入频率 | 强一致、可查询；需索引设计 |
| 对象存储 + 索引 | 长历史归档 | 在线低延迟读取 | 便宜；读取路径复杂 |

| 传输方式 | 适用 | 不适用 | 权衡 |
| --- | --- | --- | --- |
| SSE | 单向增量输出（绝大多数生成场景） | 需要双向实时协作 | 简单、可断线续传；只支持服务端推送 |
| WebSocket | 双向、语音、协同编辑 | 只需单向输出 | 灵活；连接管理与重连逻辑更复杂 |
| 轮询 | 后台长任务进度（见第 5 课） | 需要逐字输出 | 最稳；延迟与请求量较高 |

选型依据：**输出是否单向**（是则 SSE 足够）；**是否需要跨标签页一致**（是则状态必须服务端化）；**保留期要求**（决定存储介质）。若前端在浏览器内使用 `EventSource`，注意它不能自定义请求头，鉴权通常依赖同站 Cookie 或短期一次性票据，<u>不要把长期访问令牌放进 URL 查询串</u>——它会进入代理日志与浏览器历史。

## 最小示例

下面的脚本用标准库生成并解析 SSE 帧，演示断线续传：客户端声明已收到 `2` 号事件，解析器只返回其后的分片。

```python
import json

def stream(turn_id, chunks, start=0):
    # 每个分片一帧：id 单调递增，客户端据此判断缺失范围
    for i, text in enumerate(chunks, start=1):
        payload = json.dumps({"turn": turn_id, "text": text}, ensure_ascii=False)
        yield f"id: {i}\nevent: delta\ndata: {payload}\n\n"
    yield f"id: {len(chunks)+1}\nevent: done\ndata: {json.dumps({'finish': 'stop'})}\n\n"

def parse(frames, last_event_id=0):
    # 解析器：跳过已确认的分片，实现断线续传（Last-Event-ID 语义）
    out = []
    for raw in frames:
        fields = {}
        for line in raw.strip().splitlines():
            if line.startswith(":"):
                continue                       # 注释行：心跳，不产生事件
            key, _, value = line.partition(": ")
            fields[key] = value
        if int(fields["id"]) <= last_event_id:
            continue
        out.append(fields)
    return out

frames = list(stream("t-1", ["订单 A1024 ", "支持 7 天", "无理由退货。"]))
print(frames[0])                               # 展示一帧的原始格式
resumed = parse(frames, last_event_id=2)       # 模拟浏览器重连时携带的 Last-Event-ID
print("resumed events:", [(f["id"], f["event"]) for f in resumed])
print("joined text:", "".join(json.loads(f["data"])["text"]
                              for f in resumed if f["event"] == "delta"))
```

预期输出（已实跑）：

```text
id: 1
event: delta
data: {"turn": "t-1", "text": "订单 A1024 "}

resumed events: [('3', 'delta'), ('4', 'done')]
joined text: 无理由退货。
```

注意输出里 `joined text` 只有最后一个分片：这是**正确**的续传行为——前两个分片客户端已经拿到，必须由客户端与本地缓冲拼接。真实实现中，服务端还要在 `done` 之前发一个 `event: usage` 帧，携带 Token 用量，便于计费与审计对齐。

## 动手实验

**前置条件**：`python3`（3.9+）；可选：安装 `fastapi` 与 `uvicorn` 以验证真实 HTTP 流。

**步骤**：

1. 保存脚本为 `/tmp/aiarch/sse.py`，运行 `python3 /tmp/aiarch/sse.py`。
2. 把 `last_event_id` 改为 `0`，观察是否重放全部分片。
3. 把 `last_event_id` 改为 `4`，观察是否只剩空结果。
4. 可选：用 FastAPI 的 `StreamingResponse` 包装 `stream()`，用 `curl -N` 观察逐帧到达。

**预期结果**：第 1 步输出 3 号与 4 号事件；第 2 步输出 1、2、3、4；第 3 步输出空列表。

**验证方法**：检查 `id` 是否严格递增且无重复；用 `curl -N -H 'Last-Event-ID: 2'` 验证服务端是否只发送剩余帧；确认响应头包含 `text/event-stream`。

**清理方法**：删除 `/tmp/aiarch/sse.py`；若启动了 `uvicorn`，用 `kill` 停止进程。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 刷新页面后答复消失 | 会话只存在前端内存 | 打开浏览器隐私模式复现 | 服务端持久化 + 打开时拉取历史 |
| 两个标签页消息错乱 | 前端各自追加，未用服务端 `seq` | 对比两侧消息 ID | 以服务端序号为准，前端只做投影 |
| 流式看似成功但内容截断 | 代理缓冲或提前关闭连接 | `curl -N` 观察是否一次性到达 | 关闭代理缓冲、设置 `X-Accel-Buffering: no` |
| 重试后重复计费 | 重试未带幂等键，生成两次 | 查审计中同 `turn_id` 的模型调用数 | 幂等键 + 复用已生成结果 |
| 长会话变慢、成本升高 | 历史全量重放，未裁剪 | 统计每轮输入 Token 数 | 按预算裁剪 + 摘要旧轮次 |
| 重连后重复显示同一段文字 | 服务端忽略 `Last-Event-ID` | 抓包看重连请求头 | 按 ID 补发，客户端按 ID 去重 |

## 安全与生产注意事项

**<u>把长期访问令牌放进 SSE 的 URL 查询参数，会经代理、网关与浏览器历史泄露。</u>**应使用同站 Cookie 或一次性短期票据，并在服务端校验该票据只能用于指定会话。

**<u>会话历史包含订单号、电话与地址等个人信息，默认无限期保存会扩大泄露面并违反留存约定。</u>**应按用途设定保留期，敏感字段加密或脱敏存储，删除请求要能真正删除而不是仅隐藏。

**<u>多标签页共享同一会话时，若服务端不校验写入顺序，可能把并发提问拼成一段虚假上下文。</u>**应给每轮分配独立 `turn_id`，并在写入时检测并发冲突。

## 本课总结

- **会话是服务端追加日志**，`seq` 与 `client_msg_id` 保证顺序与幂等。
- **流式分片不是消息**：累积完成后写一条完整消息，分片只是传输产物。
- **SSE 的 `id` 是续传契约**，`Last-Event-ID` + 心跳让弱网可恢复。
- **存储与传输分开选型**：会话可以进关系库，推送用 SSE，长任务用轮询。
- **状态放错层**是这类问题最常见的根因，前端内存不能作为唯一真相。

## 思考题

客服在手机上提问后立即锁屏，五分钟后回来。此时服务端可能已经生成完毕，也可能被中断。请设计一套行为，使客服既不丢失结果，也不重复计费，并能区分“已完成”“部分完成”“已取消”三种状态。

参考思路：服务端的生成任务与连接解耦，结果落库并标记 `finish_reason`；客户端重连时先拉取该 `turn_id` 的最终状态，再决定是续传剩余分片还是直接展示完整消息；若仍在生成则用 `Last-Event-ID` 续传；重复提交以 `client_msg_id` 去重。

## 小测

1. 为什么不能把每个流式分片写成一条 `assistant` 消息？  
   A. 数据库不允许　B. 历史会变成碎片，破坏后续上下文与审计  
   C. SSE 规范禁止　D. 只有 WebSocket 可以存消息
2. SSE 中以 `:` 开头的行有什么作用？
3. `Last-Event-ID` 由谁发送、服务端应如何使用？
4. 消息表为什么需要 `client_msg_id` 唯一索引？
5. 场景题：产品要求“客服能看到同事正在看的同一会话的实时进展”。基于本课设计，你会增加哪些机制？请说明状态、权限与并发三方面的处理。

## 答案与解析

1. **B。**模型下一轮会把碎片当作多条独立消息，上下文语义被破坏，审计也无法对应“一次生成”。A、C 都不是原因；D 与传输方式无关。
2. 它是注释，不产生事件，通常用作心跳或调试信息，防止中间代理因长时间无数据而断开连接。
3. 由客户端（浏览器 `EventSource`）在重连时自动发送，值为最后收到的事件 `id`；服务端应只补发该 ID 之后的分片，避免重复与遗漏。
4. 保证同一用户消息在重试、双击、网络重发时只落库一次，从而不重复触发模型调用与计费。
5. 需要：服务端保存生成状态并支持多订阅者（如把分片写入流式存储，多个连接各自读取）；权限上校验同事是否有权访问该会话（见第 8 课），不能只凭 `session_id`；并发上给每轮独立 `turn_id`，避免两个提问交叉写入同一上下文。

## 延伸阅读与下一课

- [WHATWG HTML 标准：Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)（SSE 帧格式与重连语义的权威定义）。
- [MDN：EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)（浏览器端 API、`Last-Event-ID` 与重连行为）。
- [FastAPI：Server-Sent Events (SSE)](https://fastapi.tiangolo.com/tutorial/server-sent-events/)（官方教程，含 `EventSourceResponse` 用法）。
- [OpenAI：Streaming API responses](https://developers.openai.com/api/docs/guides/streaming-responses)（供应商侧流式事件的组织方式，2026-10 复核）。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[模型客户端、供应商适配层与 AI Gateway](03-model-adapter-and-ai-gateway.md)。
- 下一课：[队列、后台任务与长任务进度](05-queues-background-jobs-and-progress.md)。
