---
title: API Gateway 与服务发现
slug: api-gateway-and-service-discovery
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 50m
prerequisites:
  - monolith-microservices-and-serverless
outcomes:
  - 区分 API 网关与反向代理、服务网格 sidecar 的职责，说出不该放进网关的职责
  - 写出一条含路径匹配、鉴权策略、限流键与突发参数的网关规则，并预判 401、429、503 的出现顺序
  - 按注册、心跳、过滤、摘除描述一次实例扩容与下线，说明租约窗口为什么造成短暂 502
last_reviewed: 2026-10-19
---

# API Gateway 与服务发现

## 为什么需要学习

晴空商城把单体拆成五个服务后，客服后台要同时访问其中四个：三个客户端各维护五份地址、各抄一份令牌校验。退款服务从 2 个副本扩到 4 个时，地址列表还是旧的：新副本空转，已停机的旧地址仍被调用，客服每十几分钟撞上一批 `502`。仓储又被批量查询打满，几个服务各写一套限流，阈值互不相同。

三个症状分属三件事：谁可以被放行、请求算在谁头上、服务还有哪些实例能接流量，而它们都发生在业务代码之前。

> **核心结论：** 网关把“能不能进来、算谁的额度、发往哪个服务”收敛成一份配置，服务发现把“该发往哪一台”从硬编码地址换成自更新列表。

## 学习目标

完成本课后，你能够：

- 区分 API 网关与反向代理、服务网格 sidecar 的职责，说出两类不该放进网关的职责。
- 写出一条含路径匹配、鉴权策略、限流键与突发参数的网关规则，并按顺序预判 `401`、`429`、`503`。
- 按“注册—心跳—过滤—摘除”描述一次实例扩容与下线，说明租约窗口为什么会造成短暂 `502`。
- 在客户端发现与服务端发现之间作出选择并说明代价。

## 前置知识

- 回看上一课：[单体、微服务与无服务器架构](07-monolith-microservices-and-serverless.md)。
- 知道 HTTP 方法、常用状态码和请求头的含义，能读懂 `curl -D -` 的输出。
- 知道反向代理会终止 TLS 并转发请求，可回看[反向代理、负载均衡与 CDN](../02-web-and-network/09-reverse-proxy-load-balancer-cdn.md)。
- 能读懂简单的 `python3` 脚本：字典、函数、`threading`。

## 业务场景

晴空商城（自建商城、订单、支付、仓储、客服，退款流程横跨这几个系统）要做一次入口改造，评审提出四条要求：

1. 三个客户端只保留一个入口地址，令牌校验只做在一处。
2. 退款详情含会员账户尾号，只允许持客服角色的令牌访问；支付方回调没有用户令牌，必须放行但要能验真。
3. 退款服务随时扩缩容，扩容出的副本不要求客户端改配置。
4. 仓储的批量查询要被限制在容量内，且只限制发起方，不影响 App 下单链路。

四条要求分别落在路由与鉴权、服务发现、限流三处，且都在业务代码之前。

## 核心概念

*API 网关*（API gateway）是面向所有客户端的统一入口，按配置完成路由、鉴权、限流与改写，再转发给具体服务，替掉“客户端各拼地址、服务各写校验”。

*路由*（route）是一条“匹配条件 → 目标服务”的规则，条件由方法、路径前缀和被点名的头组成。

*限流键*（rate limit key）决定谁和谁共用一份额度：按身份分桶保护租户，按 IP 分桶会让 NAT 后整片共用一个桶。

*服务发现*（service discovery）让调用方按服务名找目标：登记自己、查出别人；清单存在*注册表*（registry）里，至少记录地址、服务名与就绪状态。

*租约*（lease）是注册表给条目设的到期时间，实例须周期性*续期*（heartbeat）。**租约过期即视为下线，因此强杀后条目仍会多活一个租约周期。**

*健康检查*（health check）分两类：*就绪*（readiness）表示能接业务流量，*存活*（liveness）表示进程没死。<u>只探端口的就绪检查等于承认“进程活着就算健康”</u>。

*客户端发现*由调用方查注册表再选实例；*服务端发现*只认一个稳定地址（虚拟 IP 或域名），由平台解析。*服务网格*（service mesh）把流量决策下沉到实例旁的 *sidecar* 代理。

| 组件 | 主要决策 | 典型能力 | 不该承担 |
| --- | --- | --- | --- |
| 反向代理 | 请求先经过谁 | TLS 终止、静态路由、压缩 | 理解租户与角色 |
| API 网关 | 能不能进、算谁的额度、发往哪个服务 | 鉴权、限流、版本路由、改写 | 业务编排与长事务 |
| 服务网格 sidecar | 实例之间怎么通信 | mTLS、重试、熔断、镜像 | 面向客户端的鉴权 |

## 工作原理

### 一次请求穿过网关

1. 客户端把请求发到 `api.qingkong.example`，不再持有服务地址。
2. 网关按“方法 + 路径前缀 + 头”匹配路由，**第一条命中即停止**，故具体路径须排在宽前缀之前；未命中返回 `404`。
3. 读路由的鉴权策略：`required` 校验令牌并解析租户与角色，`none` 只留给验过签的回调路径。
4. 用令牌里的调用方标识组装限流键，取不到令牌就回 `429` 与 `Retry-After`，不再往下走。
5. 按目标服务向注册表要候选，只保留租约有效且就绪的实例。
6. 轮询或按权重选一台，转发时覆盖身份头、追加 `X-Request-Id`。
7. 响应回到网关，只做错误码归一与头改写；含个人信息的响应不缓存。
8. 记录路由名、限流键、目标实例与耗时，进日志与指标。

顺序本身就是设计：<u>鉴权先于限流，未认证的请求不该占额度；限流先于发现，被拒的请求不必查注册表</u>。

### 实例上线与下线

1. 实例启动、就绪后登记“服务名 + 地址 + 元数据”，同时开始心跳。
2. 心跳按间隔推后租约到期时间；注册表不主动探活，只认租约。
3. 调用方按服务名查询，过滤掉租约过期与未就绪的实例。
4. 网关缓存实例列表并定期刷新，避免每个请求都打注册表。
5. 实例收到终止信号后先停止续期或主动注销，等连接排空再退出。
6. 进程被强杀时没人心跳，租约到期后条目失效，这段延迟就是*租约窗口*。
7. 窗口内的请求仍可能被派到已死实例，表现为一小段 `502`。

## 架构与选型

### 网关放什么、不放什么

| 场景 | 是否适合放进网关 | 原因 |
| --- | --- | --- |
| 令牌校验、租户识别、按调用方限流 | 适合 | 横切关注点，放一处才不会各写一版 |
| 路径与版本路由、按头或比例灰度 | 适合 | 决策只依赖请求本身 |
| 响应裁剪、REST 与 gRPC 互转 | 适合，但要克制 | 改写越多，网关越像业务代码 |
| 跨服务的退款状态编排与补偿 | 不适合 | 需要业务状态与重试语义，应留在服务层 |
| 聚合多个服务的结果 | 谨慎 | 一次慢下游拖慢整条链路，通常交给 BFF |
| 访问数据库、缓存业务对象 | 不适合 | 无状态才能水平扩展与快速替换 |

### 服务发现怎么选

| 方案 | 适合 | 代价 |
| --- | --- | --- |
| 静态地址 + 网关健康检查 | 实例少、发布频率低 | 扩容要改配置，靠检查兜底 |
| 客户端发现 + 注册中心 | 多语言、跨机房、需精细路由 | 每个调用方都要实现查询与缓存 |
| 服务端发现（虚拟 IP、Kubernetes Service） | 平台统一、不想碰注册细节 | 健康语义受平台定义约束 |
| 服务网格 | 实例多、需 mTLS 与细粒度流量控制 | 运维复杂度与每跳延迟上升 |

选型先回答三问：实例变更多频繁、调用方能否改代码、平台是否已有稳定入口。<u>先挑组件再问，通常会在“扩容后流量不进来”上翻车</u>。

## 最小示例

问题：不上真集群，先看清网关在一次请求里依次做哪些判断。环境：Python 3.8 以上，只用标准库；输入是六条模拟请求与一个注册表，输出是每条请求的终态。

```python
"""最小 API 网关决策模拟：路由 → 鉴权 → 限流 → 服务发现 → 选实例。"""
import itertools  # 轮询选择实例：顺序固定，输出才可复现

ROUTES = [  # 路由表自上而下匹配，第一条命中即生效，顺序本身就是设计决策
    {"name": "payment-notify", "method": "POST", "prefix": "/api/payments/notify",
     "auth": "none", "limit": None, "service": "payments"},  # 回调不带用户会话，靠签名而非令牌
    {"name": "refund-query", "method": "GET", "prefix": "/api/refunds",
     "auth": "required", "limit": (2, 0.5), "service": "refunds"},  # 容量 2，每秒补 0.5 个
]

REGISTRY = {  # 注册表：地址、租约到期时间、就绪标记，三者缺一不可
    "refunds": [
        {"url": "10.0.5.11:8080", "lease_until": 1030, "ready": True},
        {"url": "10.0.5.12:8080", "lease_until": 995, "ready": True},    # 进程已退出，租约过期
        {"url": "10.0.5.13:8080", "lease_until": 1030, "ready": False},  # 已注册但未就绪
        {"url": "10.0.5.14:8080", "lease_until": 1030, "ready": True},
    ],
    "payments": [{"url": "10.0.5.21:8080", "lease_until": 1030, "ready": True}],
}

BUCKETS = {}  # 限流状态：键是“路由名 + 调用方身份”，不是 IP
CYCLES = {}   # 每个服务的轮询器，实例集合变化时重建
SKIPPED = {}  # 记录被跳过的实例与原因，便于排查“流量为什么不进来”


def match_route(method, path):
    """按方法与路径前缀匹配，返回路由或 None。"""
    for route in ROUTES:                                     # 自上而下，先命中者优先
        if route["method"] == method and path.startswith(route["prefix"]):
            return route
    return None                                              # 没有规则命中就不转发


def authorize(route, caller):
    """鉴权策略写在路由上：none 是显式放行，而不是“默认不校验”。"""
    if route["auth"] == "none":
        return True
    return caller.get("token") == "valid"                    # 真实系统在这里校验 JWT


def allow(route, caller, now):
    """网关侧令牌桶：容量决定突发上限，补充速率决定长期平均速率。"""
    if route["limit"] is None:
        return True
    capacity, rate = route["limit"]
    key = f'{route["name"]}:{caller.get("api_key", "anonymous")}'  # 按调用方分桶
    tokens, last = BUCKETS.get(key, (capacity, now))
    tokens = min(capacity, tokens + (now - last) * rate)     # 先按流逝时间补令牌
    if tokens < 1:
        BUCKETS[key] = (tokens, now)                         # 拒绝也要回写时钟，否则会立刻攒满
        return False
    BUCKETS[key] = (tokens - 1, now)
    return True


def pick_instance(service, now):
    """服务端发现：先过滤租约过期与未就绪，再在剩余实例里轮询。"""
    alive = []
    for inst in REGISTRY.get(service, []):
        if inst["lease_until"] < now:
            SKIPPED[inst["url"]] = "lease expired"           # 强杀留下的条目靠租约清除
        elif not inst["ready"]:
            SKIPPED[inst["url"]] = "not ready"               # 已注册但还没准备好接流量
        else:
            alive.append(inst["url"])
    if not alive:
        return None                                          # 候选为空，由调用方回 503
    members = tuple(alive)
    if service not in CYCLES or CYCLES[service][0] != members:  # 集合变了就重建轮询器
        CYCLES[service] = (members, itertools.cycle(members))
    return next(CYCLES[service][1])


def handle(method, path, caller, now):
    """一次请求穿过网关的全部判断，返回一行决策记录。"""
    route = match_route(method, path)
    if route is None:
        return f"{method} {path} -> 404 no route"
    if not authorize(route, caller):                         # 鉴权先于限流
        return f"{method} {path} -> 401 auth required ({route['name']})"
    if not allow(route, caller, now):                        # 限流先于服务发现
        return f"{method} {path} -> 429 rate limited ({route['name']})"
    inst = pick_instance(route["service"], now)
    if inst is None:
        return f"{method} {path} -> 503 no healthy instance ({route['service']})"
    return f"{method} {path} -> 200 via {inst} ({route['name']})"


if __name__ == "__main__":
    now = 1000                                               # 固定时钟，让租约与限流可复现
    cases = [
        ("GET", "/api/refunds/9831", {"token": "valid", "api_key": "cs-01"}),
        ("GET", "/api/refunds/9832", {"token": "valid", "api_key": "cs-01"}),
        ("GET", "/api/refunds/9833", {"token": "valid", "api_key": "cs-01"}),
        ("GET", "/api/refunds/9834", {"token": "bad", "api_key": "cs-02"}),
        ("POST", "/api/payments/notify", {"api_key": "pay-provider"}),
        ("GET", "/api/orders/1001", {"token": "valid", "api_key": "cs-01"}),
    ]
    for method, path, caller in cases:
        print(handle(method, path, caller, now))
    print("被跳过实例:", SKIPPED)
```

整体分四段：`match_route` 只做匹配，`authorize` 与 `allow` 回答“能不能进”和“还有没有额度”，`pick_instance` 在过滤后的候选里轮询。三个设计点：鉴权策略写在路由上，才能解释回调为何放行；限流键带调用方标识；先过滤再轮询。

运行 `python3 gateway_sim.py`，实测输出：

```text
GET /api/refunds/9831 -> 200 via 10.0.5.11:8080 (refund-query)
GET /api/refunds/9832 -> 200 via 10.0.5.14:8080 (refund-query)
GET /api/refunds/9833 -> 429 rate limited (refund-query)
GET /api/refunds/9834 -> 401 auth required (refund-query)
POST /api/payments/notify -> 200 via 10.0.5.21:8080 (payment-notify)
GET /api/orders/1001 -> 404 no route
被跳过实例: {'10.0.5.12:8080': 'lease expired', '10.0.5.13:8080': 'not ready'}
```

输出里三条值得注意：前两条落在 `.11` 与 `.14`，说明轮询只在健康集合内进行；第三条是 `429` 而非 `503`，说明限流先于发现；`.12` 与 `.13` 因租约过期与未就绪被跳过——<u>两者都会让副本数看起来够用、实际接不了流量</u>。

真实网关的规则通常是声明式配置，字段语义与代码一一对应：

```yaml
route: refund-query                    # 路由名，出现在日志与指标标签里
match: {method: GET, prefix: /api/refunds}
auth: required                         # 校验令牌并解析租户与角色
rate_limit: {key: caller, capacity: 2, refill_per_second: 0.5}
upstream: refunds                      # 目标服务名，由发现解析成实例
```

一条被限流的响应，关键是让调用方能自己算出让步：

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
Content-Type: application/json

{"error":"rate_limited","route":"refund-query","limit":2}
```

`Retry-After` 是服务端给出的建议等待秒数，<u>客户端若无视它并在毫秒级重试，会把一次限流放大成一场雪崩</u>。

## 动手实验

前置条件：已装 `python3` 与 `curl`；端口 `9101`、`9102`、`9200` 空闲；不需要网络与账号。

1. 建实验目录：
   ```bash
   mkdir -p /tmp/qk-gw && cd /tmp/qk-gw
   ```
2. 把下面两个脚本分别存为 `upstream.py` 和 `gateway.py`：

   ```python
   """假上游：启动即写心跳文件，被强杀时靠租约过期摘除。"""
   import http.server          # 标准库 HTTP 服务端骨架
   import json                 # 心跳文件用 JSON，网关直接解析
   import pathlib              # 拼心跳文件路径
   import sys                  # 读取端口与实例名
   import threading            # 心跳线程与请求线程并行
   import time                 # 租约用绝对时间戳

   PORT = int(sys.argv[1])     # 9101 / 9102
   NAME = sys.argv[2]          # refunds-a / refunds-b，便于从响应看落点
   LEASE_SECONDS = 4           # 4 秒没续期就视为下线
   HEARTBEAT = pathlib.Path(f"/tmp/qk-gw/reg-{PORT}.json")


   def renew():
       """每秒续期一次：注册表只看 lease_until，不关心进程内部是否健康。"""
       while True:
           HEARTBEAT.write_text(json.dumps({
               "url": f"http://127.0.0.1:{PORT}",   # 注册可路由地址，而非容器名
               "instance": NAME,
               "lease_until": time.time() + LEASE_SECONDS,
           }))
           time.sleep(1)


   class Handler(http.server.BaseHTTPRequestHandler):
       def do_GET(self):
           body = b"ok" if self.path == "/healthz" else NAME.encode()  # 就绪端点与业务共用进程
           self.send_response(200)
           self.send_header("X-Instance", NAME)
           self.send_header("Content-Length", str(len(body)))
           self.end_headers()
           self.wfile.write(body)

       def log_message(self, *args):
           pass                                            # 静音访问日志，避免干扰观察


   if __name__ == "__main__":
       threading.Thread(target=renew, daemon=True).start()
       try:
           http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
       finally:
           HEARTBEAT.unlink(missing_ok=True)  # 前台按 Ctrl+C 才走这里；kill 不会执行
   ```

   ```python
   """最小网关：路径路由 + 鉴权白名单 + 令牌桶 + 注册表发现。"""
   import http.server          # 提供入口服务
   import json                 # 解析心跳文件
   import pathlib              # 扫描注册目录
   import time                 # 令牌补充与租约判定
   import urllib.error         # 捕获上游不可达
   import urllib.request       # 用标准库客户端转发请求

   REG_DIR = pathlib.Path("/tmp/qk-gw")
   CAPACITY, RATE = 2, 0.5     # 容量 2 个突发，每秒补 0.5 个
   BUCKET = {"tokens": float(CAPACITY), "last": time.time()}  # 单进程内存桶，仅实验用
   CURSOR = {"i": 0}           # 轮询游标


   def discover():
       """读取全部心跳文件，过滤租约过期的，返回当前可路由的实例地址。"""
       alive = []
       for path in sorted(REG_DIR.glob("reg-*.json")):
           try:
               info = json.loads(path.read_text())
           except (json.JSONDecodeError, FileNotFoundError):
               continue                     # 文件正在被重写，这一轮跳过
           if info["lease_until"] > time.time():
               alive.append(info["url"])
       return alive


   def take_token():
       """返回 (是否放行, Retry-After 秒数)；被拒也要更新时间，否则桶会瞬间回满。"""
       now = time.time()
       BUCKET["tokens"] = min(CAPACITY, BUCKET["tokens"] + (now - BUCKET["last"]) * RATE)
       BUCKET["last"] = now
       if BUCKET["tokens"] < 1:
           return False, str(int((1 - BUCKET["tokens"]) / RATE) + 1)
       BUCKET["tokens"] -= 1
       return True, "0"


   class Handler(http.server.BaseHTTPRequestHandler):
       def do_GET(self):
           if not self.path.startswith("/api/"):          # 路由不匹配就不转发
               return self.reply(404, b"no route", "none")
           if self.path.startswith("/api/payments/notify"):
               pass              # 回调进白名单：不校验用户令牌，改由签名验真
           elif self.headers.get("Authorization") != "Bearer demo":
               return self.reply(401, b"auth required", "none")
           ok, retry_after = take_token()
           if not ok:
               return self.reply(429, b"rate limited", "none", {"Retry-After": retry_after})
           upstreams = discover()
           if not upstreams:
               return self.reply(503, b"no healthy instance", "none")
           CURSOR["i"] += 1
           target = upstreams[CURSOR["i"] % len(upstreams)]  # 只在健康集合内轮询
           try:
               with urllib.request.urlopen(target + self.path, timeout=2) as resp:
                   body = resp.read()
           except urllib.error.URLError:
               return self.reply(502, b"upstream unreachable", target)  # 摘除靠下次心跳
           self.reply(200, body, target)

       do_POST = do_GET          # 实验不区分方法，统一走同一套判断

       def reply(self, status, body, upstream, extra=None):
           self.send_response(status)
           self.send_header("X-Upstream", upstream)  # 让客户端看到这次落到哪台
           self.send_header("Content-Length", str(len(body)))
           for key, value in (extra or {}).items():
               self.send_header(key, value)
           self.end_headers()
           self.wfile.write(body)

       def log_message(self, *args):
           pass


   if __name__ == "__main__":
       http.server.ThreadingHTTPServer(("127.0.0.1", 9200), Handler).serve_forever()
   ```

3. 启动两个上游，确认注册文件出现：
   ```bash
   python3 upstream.py 9101 refunds-a &
   python3 upstream.py 9102 refunds-b &
   sleep 2 && ls reg-*.json
   ```
4. 启动网关，连发三次请求：
   ```bash
   python3 gateway.py &
   for i in 1 2 3; do
     curl -s -D - -H 'Authorization: Bearer demo' \
       http://127.0.0.1:9200/api/refunds/$i -o /dev/null \
       | grep -i -E 'HTTP/|X-Upstream|Retry-After'
   done
   ```
5. 验证鉴权与回调白名单：
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9200/api/refunds/9
   curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:9200/api/payments/notify
   ```
6. 用 `kill -9` 强杀一个上游，观察租约窗口：
   ```bash
   pkill -9 -f 'upstream.py 9102'
   for i in 1 2 3 4 5; do
     sleep 1
     curl -s -o /dev/null -w '%{http_code}\n' \
       -H 'Authorization: Bearer demo' http://127.0.0.1:9200/api/refunds/$i
   done
   ```

预期结果：步骤 3 出现两个 `reg-*.json`；步骤 4 前两条 `200` 且落点交替，第三条 `429` 并带 `Retry-After`；步骤 5 第一条固定 `401`，第二条 `200` 或 `429`——两份额度共用一个桶，这是示例的已知缺陷；步骤 6 可能有 1 至 2 次 `502`，租约到期后全部 `200` 且只落 `9101`。

验证方法：交替出现说明发现生效；`401` 说明鉴权在转发之前；`502` 只落在停止后约 4 秒内，说明摘除依据是租约而非实时探活。

清理方法：`pkill -f upstream.py; pkill -f gateway.py; rm -rf /tmp/qk-gw`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 扩容后新副本空转 | 新实例没注册、未就绪，或列表缓存未刷新 | 对比注册表条目与实际实例 | 补心跳、就绪检查接入发现、缩短刷新间隔 |
| 停机后一小段 `502` | 强杀未注销，租约内仍被选中 | 看 `502` 是否集中在停机后一个租约周期 | 先摘流量再退出，缩短租约 |
| 网关 `429` 但后端日志一条都没有 | 请求在网关被拒，或限流键取成了 IP | 打印 `429` 的限流键与桶余量 | 按调用方身份分桶，按路由设阈值 |
| 支付回调被拦成 `401` | 全局鉴权未给回调路径开白名单 | 用回调的真实报文回放 | 最小白名单 + 验签 + 来源允许列表 |
| 后端看到的用户与令牌不一致 | 网关未覆盖客户端自带的身份头 | 抓包看转发前的头 | 剥除外部身份头，只注入校验后的值 |
| 接入后所有接口 P99 上升 | 每跳新建连接、日志同步写、策略查库 | 对比直连与经网关的分位数 | 复用连接、异步日志、策略缓存 |

## 安全与生产注意事项

**<u>网关校验完令牌却不覆盖客户端自带的身份头，后端又直接信任 `X-User-Id`，手写一个头就能扮演他人。</u>** 后果是越权查看他人订单与退款，日志里却全是“合法”请求。缓解：转发前剥除外部身份头，只注入校验后的值；内部调用加 mTLS，后端只认自己这一跳。

**<u>把支付回调、健康检查与管理接口一并放进白名单，等于在公网留了一个不校验身份的内部入口。</u>** 后果是伪造回调能把订单标成已支付，健康检查还会暴露版本号。缓解：白名单按路径最小化，回调必须验签并校验时间戳；管理接口单独监听。

**<u>限流按 IP 且每个网关副本各自计数，实际放行量是阈值的数倍。</u>** 这种配置会让下游按三倍设计容量被打穿。缓解：按调用方身份分桶，计数放共享存储或集群同步，并按下游可承受 QPS 反推阈值。

另两条约束：注册表条目若全凭实例自报，恶意进程能把流量劫走，需要注册鉴权与网络策略；<u>单副本网关会在发布窗口整体不可用</u>。

## 本课总结

- 网关收敛三件事：能不能进来、算谁的额度、发往哪个服务；不承担业务编排。
- 鉴权先于限流、限流先于发现，顺序决定了误拒与故障放大的方向。
- 路由按“第一条命中”生效，规则顺序与路径具体程度就是契约。
- 服务发现用租约表达存活：注册、续期、过滤、摘除，窗口内必然短暂不一致。
- 就绪与存活语义不同，只探端口会把“依赖耗尽”当成健康。

## 思考题

客服后台与商城 App 共用同一个网关和一套限流阈值。大促期间客服导出报表把仓储打满，App 下单也开始超时。你会把方案落在哪一层：拆两个网关、加路由级限流、把报表改成异步任务，还是限制客服并发？请说明判断依据、要改的配置，以及用什么数据验证有效。

参考思路：先分清是“容量竞争”还是“单次请求过重”。报表导出是长耗时批量任务，优先异步化（提交任务、轮询结果）；其次按调用方与路由分别设阈值，让客服额度独立于下单链路；拆网关能隔离故障，但多一份配置与证书成本，只有隔离不了时才值得。验证看仓储 P99、两类业务的 `429` 比例与下单成功率。

## 小测

1. 下列哪项最不适合放进 API 网关？  
   A. 令牌校验　B. 按调用方限流　C. 跨服务的退款状态编排　D. 版本路由
2. 网关先限流后鉴权，会让未认证的请求也消耗额度。对还是错？
3. 实例被强杀后，注册表里的条目会立刻消失。对还是错？
4. 就绪检查与存活检查的区别是什么？各自失败应触发什么动作？
5. 场景题：客服后台调用退款服务出现间歇 `502`，退款刚扩到 4 个副本，网关日志显示失败请求落在 `10.0.5.12`。请给出两个最可能的原因与验证方法。

## 答案与解析

1. **C。**编排需要业务状态与重试语义，属于服务或编排层。A、B、D 只依赖请求本身，适合收敛到网关。
2. **错。**未认证的请求不该占额度，否则伪造请求能耗光真实用户的配额。顺序应为鉴权、限流、发现。
3. **错。**条目按租约失效，窗口长度等于租约剩余时间，这正是强杀后出现短暂 `502` 的原因。
4. 就绪回答“能否接业务流量”，失败只摘流量；存活回答“进程是否活着”，失败才重启。<u>用存活代替就绪，会把依赖故障升级成反复重启</u>。
5. 参考：一是 `10.0.5.12` 已停机但租约未到期，网关仍把它当候选，验证看停机时间与 `502` 是否同处一个租约窗口；二是已注册但未就绪，验证 `curl` 实例的就绪端点并读启动日志。修复分别是先摘流量再停机、就绪检查接入发现。

### 动手实验参考

步骤 4 的两次 `200` 落在不同实例，因为 `pick_instance` 在健康集合内轮询；第三次 `429` 是容量 2 耗尽。步骤 5 的 `401` 证明鉴权先于转发；回调那条若回 `429`，说明它虽放行却与业务共用一个桶。步骤 6 的 `502` 落在租约窗口内，窗口结束后流量回到唯一存活实例。

## 延伸阅读与下一课

- [Kubernetes：Service](https://kubernetes.io/docs/concepts/services-networking/service/)——服务端发现的虚拟 IP 与 Endpoint。
- [Kubernetes：Liveness、Readiness 与 Startup 探针](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)——就绪与存活语义差异。
- [nginx：ngx_http_limit_req_module](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)——网关侧限流实现。
- [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html)——`429 Too Many Requests` 与 `Retry-After` 的规范出处。
- [Envoy 文档](https://www.envoyproxy.io/docs/envoy/latest/)——服务网格的流量管理边界。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[单体、微服务与无服务器架构](07-monolith-microservices-and-serverless.md)。
- 下一课：[高可用、容错与灾难恢复](09-high-availability-and-disaster-recovery.md)。
