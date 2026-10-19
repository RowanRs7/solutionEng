---
title: FastAPI 接入模型服务
slug: fastapi-and-model-integration
module: ai-solutions
stage: design
type: core
difficulty: intermediate
duration: 55m
prerequisites:
  - production-ai-request-path
outcomes:
  - 用 FastAPI 写一个带超时与错误边界的最小模型接入服务
  - 把密钥、端点与超时预算从代码外注入并说明注入失败时的行为
  - 将供应商错误映射为可被前端与监控处理的稳定错误码
last_reviewed: 2026-10-19
---

# FastAPI 接入模型服务

## 为什么需要学习

很多 AI 功能的第一版诞生在一个脚本里：密钥写在文件顶部，`requests.post` 不带超时，返回值直接 `print`。当它变成晴空商城售后助手的后端时，问题会集中爆发：一个上游卡住的请求占住工作进程，后续客服全部排队；供应商返回 `429` 时前端只看到 `500 Internal Server Error`；想调大超时，必须改代码重新发版。

这些问题不是 FastAPI 的缺陷，而是**服务边界没有定义**。接入层要回答三个问题：一次调用最多等多久、失败如何分类、配置从哪里来。

> **核心结论：** 模型接入层的价值在于把“不可控的外部服务”转换成“有超时、有错误码、有配置契约的内部接口”。

## 学习目标

完成本课后，你能够：

- 写出一个 FastAPI 端点，用共享的异步 HTTP 客户端调用模型服务，并设置连接、读取与总预算超时。
- 把供应商的超时、限流、4xx 参数错误、5xx 故障映射为稳定的内部错误码。
- 用环境变量与配置对象注入密钥、端点和超时，并验证缺少配置时启动即失败。
- 解释为什么不能在请求处理函数里创建客户端，也不能把上游响应体原样返回。

## 前置知识

- 回看上一课：[生产级 AI 请求的完整链路](01-production-ai-request-path.md)。
- 能读懂 Python 的 `async def` 与 `await`，知道异步函数里不能调用阻塞库。
- 了解 HTTP 状态码语义：`4xx` 是调用方问题，`5xx` 是服务方问题。
- 用过 `curl` 或 Postman 发送 JSON 请求。

## 业务场景

售后助手需要一个后端端点 `POST /v1/assist`：接收 `session_id` 与客服问题，返回答复文本与引用列表。模型供应商在境外，网络抖动时首字延迟可达 20 秒；供应商会在高峰期返回 `429` 并附带 `Retry-After`。客服页面需要区分“稍后重试”“参数有误”“系统故障”三种情况，因为处理动作完全不同：等待重试、修改输入、转人工。

本课只做接入层的骨架：路由、超时、错误边界、配置注入。检索与工具在后续课程接入。

## 核心概念

| 概念 | 含义 | 本课的做法 | 反面做法 |
| --- | --- | --- | --- |
| *ASGI 应用* | 异步 Python Web 服务接口规范，FastAPI 基于它 | 用 `async def` 路径函数 | 在异步函数里调用阻塞 SDK |
| *客户端复用* | 一个连接池服务所有请求 | 在 `lifespan` 中创建 `httpx.AsyncClient` | 每个请求 `new` 一个客户端 |
| *错误边界* | 把外部异常收敛为内部稳定错误码的代码位置 | 一个 `try/except` 包裹上游调用 | 让异常冒泡成 `500` |
| *配置注入* | 从环境或密钥管理服务读取运行参数 | `pydantic-settings` 读取环境变量 | 常量写死在源码 |
| *预算超时* | 按剩余时间而非固定值设置超时 | 由调用方传入 `timeout_s` | 全局一个 60 秒常量 |
| *启动即失败* | 配置缺失时拒绝启动 | 启动时校验必填字段 | 运行到第一次请求才报错 |

需要区分两种超时：*连接超时*（TCP/TLS 建连）与*读取超时*（等待响应数据）。模型推理时间长，读取超时要按业务预算设；连接超时则应短，因为建连失败重试代价低。<u>只设一个总超时而不区分连接与读取，会让你在“网络不通”和“模型慢”之间无法判断</u>。

## 工作原理

1. **进程启动**：读取环境变量，构造配置对象；缺少 `ASSIST_API_KEY` 或 `ASSIST_UPSTREAM_BASE_URL` 时直接抛错退出。
2. **建立客户端**：在 `lifespan` 中创建带连接池与默认超时的 `AsyncClient`，退出时关闭，避免连接泄漏。
3. **接收请求**：校验请求体（`session_id`、`question`），非法输入返回 `422` 或 `400`，不消耗上游配额。
4. **设置预算**：从入口配置或调用方取得剩余预算，换算成本次调用的 `read` 超时。
5. **调用上游**：带上 `Authorization` 与 `X-Request-Id`，请求体只包含必要字段，避免把内部调试信息送出去。
6. **分类异常**：先捕获超时，再捕获 HTTP 状态错误，最后捕获连接错误，分别映射为内部错误码。
7. **裁剪响应**：只取需要的字段（文本、引用、Token 用量），不把供应商原始 JSON 返回给前端。
8. **记录指标**：上游耗时、状态码、Token 用量写入日志与指标，并关联 `request_id`。

## 架构与选型

| 方案 | 适用 | 不适用 | 权衡 |
| --- | --- | --- | --- |
| 路径函数里直接调供应商 SDK | 单端点原型、内部工具 | 需要统一超时、重试、多供应商 | 最快；但超时与错误处理散落各处 |
| FastAPI + 共享 `httpx` 客户端 | 多数生产接入层 | 需要长任务与排队 | 控制力强；需要自己维护错误映射 |
| FastAPI + 队列 + worker | 生成耗时超过 10 秒、需要重试与进度 | 需要即时首字（改用流式，见第 4 课） | 稳定；交互复杂度上升 |
| 配置用环境变量 | 容器化部署、密钥由平台注入 | 需要动态调整且不可重启 | 简单、可审计；改动需重启或热加载 |

选型依据：**交互是否需要“边生成边看”**（是则流式，否可排队）；**供应商数量**（多于两个就该抽适配层，见第 3 课）；**密钥存放位置**（能否用平台的 Secret 管理，决定配置方案）。

不适用的情况也要写明：FastAPI 不负责重试、熔断与配额，这些属于下一课的适配层与网关；也不负责长任务的可靠性，那是第 5 课的队列。

## 最小示例

第一部分用标准库验证“超时是可观察的行为”，无需安装任何依赖：

```python
import json, socket, time, urllib.request

def call(delay_s, timeout_s):
    # 用本地模拟上游替代真实模型服务，避免付费与密钥
    req = urllib.request.Request("http://127.0.0.1:18080/v1/chat/completions",
        data=json.dumps({"messages": [], "mock_delay": delay_s}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read())          # 成功路径：解析上游 JSON

start = time.perf_counter()
try:
    print("ok", call(2.0, 0.5)["usage"])        # 上游需 2s，只给 0.5s 预算
except socket.timeout:
    # 超时必须被识别为独立分支，而不是变成 500
    print(f"timeout after {time.perf_counter()-start:.2f}s -> 504")
```

预期输出（已实跑，上游为本机 `http.server` 模拟）：

```text
timeout after 0.51s -> 504
```

第二部分是接入层的骨架，需要 `pip install fastapi uvicorn httpx pydantic-settings`：

```python
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 配置注入：缺失必填项时启动即失败，而不是首请求才报错
    upstream_base_url: str
    api_key: str
    chat_model: str = "chat-default"
    connect_timeout_s: float = 2.0
    default_read_timeout_s: float = 20.0
    class Config:
        env_prefix = "ASSIST_"          # 环境变量形如 ASSIST_API_KEY、ASSIST_UPSTREAM_BASE_URL


class AssistRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)   # 只接受必要字段
    question: str = Field(min_length=1, max_length=2000)


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 客户端在进程级复用：连接池、默认超时、关闭时机集中管理
    app.state.client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.default_read_timeout_s,
                              connect=settings.connect_timeout_s),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    try:
        yield
    finally:
        await app.state.client.aclose()      # 不关闭会泄漏连接直至耗尽


app = FastAPI(lifespan=lifespan)


@app.post("/v1/assist")
async def assist(body: AssistRequest, request: Request):
    request_id = request.headers.get("X-Request-Id", "unknown")
    try:
        resp = await app.state.client.post(
            f"{settings.upstream_base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.api_key}",
                     "X-Request-Id": request_id},       # 透传用于对账
            json={"model": settings.chat_model,
                  "messages": [{"role": "user", "content": body.question}]},
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        # 超时是 504：调用方可以重试，监控应计入“上游慢”
        raise HTTPException(status_code=504, detail="model_timeout")
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 429:                                  # 供应商限流：不要假装成 500
            raise HTTPException(status_code=429, detail="model_rate_limited",
                                headers={"Retry-After": exc.response.headers.get("Retry-After", "5")})
        if 400 <= code < 500:
            raise HTTPException(status_code=400, detail="model_rejected_request")
        raise HTTPException(status_code=502, detail="model_upstream_error")
    except httpx.HTTPError:
        # 连接/协议错误同样属于上游问题，统一 502
        raise HTTPException(status_code=502, detail="model_unavailable")

    data = resp.json()
    # 只返回需要的字段，避免泄漏供应商内部结构与调试信息
    return {"reply": data["choices"][0]["message"]["content"],
            "usage": data.get("usage", {}),
            "request_id": request_id}
```

启动命令（配置通过环境变量注入，密钥不写进命令历史之外的任何文件）：

```bash
export ASSIST_UPSTREAM_BASE_URL=http://127.0.0.1:18080
export ASSIST_API_KEY=test-only
uvicorn app:app --port 8000

curl -s localhost:8000/v1/assist \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: req-1' \
  -d '{"session_id":"s-91","question":"订单 A1024 能退吗"}'
```

预期输出（本机未安装 `fastapi`，以下为按代码推断的预期结果）：`{"reply":"已核实订单 A1024","usage":{"prompt_tokens":812,"completion_tokens":96},"request_id":"req-1"}`。

设计要点有三处：客户端只在 `lifespan` 创建一次；错误按“超时 / 限流 / 参数 / 上游故障”四类收敛；配置通过 `ASSIST_` 前缀从环境注入，密钥不进入代码与仓库。

## 动手实验

**前置条件**：`python3`（3.9+）；第二部分需要能 `pip install fastapi uvicorn httpx pydantic-settings`。无真实密钥，实验只用本地模拟上游。

**步骤**：

1. 启动模拟上游：把下面的代码保存为 `/tmp/aiarch/upstream.py`，运行 `python3 /tmp/aiarch/upstream.py &`（监听 `127.0.0.1:18080`）。

   ```python
   import json, time
   from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

   class Handler(BaseHTTPRequestHandler):
       def do_POST(self):
           length = int(self.headers.get("Content-Length", 0))
           body = json.loads(self.rfile.read(length) or b"{}")
           time.sleep(float(body.get("mock_delay", 0)))     # 模拟推理耗时
           raw = json.dumps({"choices": [{"message": {"content": "已核实订单 A1024"}}],
                             "usage": {"prompt_tokens": 812, "completion_tokens": 96}}).encode()
           self.send_response(200)
           self.send_header("Content-Type", "application/json")
           self.send_header("Content-Length", str(len(raw)))
           self.end_headers()
           self.wfile.write(raw)
       def log_message(self, *args):
           pass                                             # 静默访问日志，便于观察客户端输出

   ThreadingHTTPServer(("127.0.0.1", 18080), Handler).serve_forever()
   ```

2. 保存上面的 `call()` 脚本为 `/tmp/aiarch/client.py`，运行 `python3 /tmp/aiarch/client.py`。
3. 安装依赖后启动服务，用两条 `curl` 分别发送合法请求与空 `question` 请求。
4. 故意不设置 `ASSIST_API_KEY` 启动一次，观察启动报错。

**预期结果**：第 2 步输出 `timeout after 0.51s -> 504`；第 3 步合法请求返回 `200` 与精简 JSON，空问题返回 `422`；第 4 步进程在启动阶段因缺少必填配置直接退出，而不是接受请求。

**验证方法**：用 `curl -i` 查看状态码与 `detail` 字段是否为预期错误码；检查日志里 `Authorization` 是否出现（不应出现）；用 `ps` 确认实验结束后没有残留的 `uvicorn` 进程。

**清理方法**：`kill %1` 停止模拟上游；删除 `/tmp/aiarch/`；若安装了依赖，可在虚拟环境中 `pip uninstall` 或直接删除虚拟环境。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 高并发下服务整体卡死 | 在 `async def` 里调用同步 SDK，阻塞事件循环 | 用 `top` 看 CPU 不高但请求排队；日志显示耗时集中 | 改用异步客户端，或用 `run_in_threadpool` 包装阻塞调用 |
| 前端只看到 `500` | 未捕获供应商异常，直接冒泡 | 查看响应 `detail` 是否为空 | 增加错误边界并按类别映射状态码 |
| 报 `transport error` 却定位不到原因 | 只设了总超时，连接与读取未区分 | 打印异常类型与阶段耗时 | 分别设置 `connect` 与 `read` 超时 |
| 修改超时后必须重新发版 | 参数写死在代码常量中 | 搜索源码中的数字字面量 | 用配置对象 + 环境变量注入 |
| 日志里出现完整密钥 | 记录了请求头或整个异常对象 | 在日志中搜索 `Bearer` | 只记录 `request_id` 与错误码，密钥做脱敏 |

## 安全与生产注意事项

**<u>把供应商密钥写进源码或镜像，等同于把密钥发布给所有能拉取镜像的人。</u>**密钥应由平台的 Secret 机制注入，并且只挂载给接入层容器；轮换密钥时保留双密钥过渡窗口，避免换钥即中断。

**<u>把上游响应体原样透传给前端，可能泄漏供应商内部提示、账号信息或调试堆栈。</u>**只返回白名单字段，异常详情写入服务端日志，不写入响应。

**<u>返回 `500` 处理供应商限流，会让重试风暴被放大。</u>**`429` 必须保留 `Retry-After` 语义，让调用方退避，而不是立刻重试。

另外，模型调用的请求体可能包含客服问题中的个人信息。接入层应记录“是否调用模型、耗时、Token 数”，而不是记录完整问题文本；确需采样时单独加密保存并设置保留期。

## 本课总结

- **接入层要定义三件事**：最长等多久、失败如何分类、配置从哪里来。
- **客户端在进程级复用**，超时区分连接与读取，预算由调用方传入。
- **错误边界把外部异常收敛为稳定错误码**，`429` 与 `504` 必须可被调用方识别。
- **配置通过环境注入并在启动时校验**，密钥不进代码、不进日志、不进响应。
- FastAPI 只负责 HTTP 契约，重试、熔断、配额与长任务分别由后续课程解决。

## 思考题

如果客服页面与模型服务之间有 CDN 或反向代理，代理的超时（如 60 秒）大于应用预算（20 秒），而应用预算又大于客服可接受的首字时间（3 秒），你会如何设计整条链路的超时与提示？请说明读超时、写超时与用户提示之间的关系，以及流式输出是否会改变这个设计。

参考思路：三层超时必须从外向里递减，且最内层的上游预算由最外层用户期望反推；应用在剩余预算不足时主动降级而不是等代理断开。流式输出改变的是“首字时间”的定义：只要首个事件能在 3 秒内到达，总生成时间可以更长，此时读超时要按“事件间隔”而非“完整响应”设置。

## 小测

1. 为什么不应该在每个请求处理函数里创建 `httpx.AsyncClient`？  
   A. 语法上不允许　B. 连接池无法复用，频繁建连增加延迟并可能耗尽端口  
   C. 会导致 JSON 解析失败　D. 只影响测试环境
2. 供应商返回 `429` 时，接入层最合适的做法是？
3. 配置缺失时“启动即失败”的好处是什么？
4. 在 `async def` 路径函数中调用同步 HTTP 库会发生什么？
5. 场景题：线上出现“部分请求 20 秒后 504，部分请求 200 但内容为空”。请写出你的排查顺序与最可能的两个原因。

## 答案与解析

1. **B。**客户端持有连接池，每请求新建会重复 TCP/TLS 握手，延迟升高且可能耗尽本地端口。A 错在语法允许；C 错在 JSON 解析与客户端生命周期无关；D 错在该问题在生产环境更严重。
2. 映射为 `429` 并把上游的 `Retry-After` 传回去，同时记录指标。若把 `429` 变成 `500`，调用方无法区分“你该退避”和“你出故障了”；若立刻重试，会把供应商的过载放大成重试风暴。
3. 让错误在部署阶段暴露，而不是在首个用户请求时暴露；容器编排会因启动失败而停止滚动发布，避免“带着缺配置的实例接流量”。
4. 阻塞事件循环。`async def` 中的同步网络调用会占住线程，其他协程无法推进，表现为 CPU 不高但吞吐骤降。
5. 先按 `request_id` 对齐上游日志，区分“上游超时”与“上游返回成功但无内容”。最可能的两个原因：读取超时设置偏短导致长尾请求被切断；上游返回了空 `choices` 或内容过滤后为空，而接入层未校验字段就返回。

## 延伸阅读与下一课

- [FastAPI：并发与 `async` / `await`](https://fastapi.tiangolo.com/async/)（官方文档，2026-10 复核）。
- [FastAPI：Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)（应用启动/关闭时管理资源）。
- [FastAPI：Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/)（配置注入官方说明）。
- [HTTPX：Timeouts](https://www.python-httpx.org/advanced/timeouts/)（连接、读取、写入、池超时的区别）。
- [Pydantic Settings 文档](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)（`BaseSettings` 与环境变量前缀）。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[生产级 AI 请求的完整链路](01-production-ai-request-path.md)。
- 下一课：[模型客户端、供应商适配层与 AI Gateway](03-model-adapter-and-ai-gateway.md)。
