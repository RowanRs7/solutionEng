---
title: 反向代理、负载均衡与 CDN
slug: reverse-proxy-load-balancer-cdn
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - curl-and-network-diagnostics
outcomes:
  - 说明反向代理、负载均衡与 CDN 在请求路径上的位置和职责边界
  - 为有状态与无状态服务分别选出负载均衡算法与会话保持方案并说明代价
  - 写出一条 CDN 缓存规则并预判它的命中率与回源行为
last_reviewed: 2026-10-19
---

# 反向代理、负载均衡与 CDN

## 为什么需要学习

晴空商城秋季大促前三天，入口只有一台反向代理，流量直连订单服务唯一的一个公网实例。评审会后运维做了三件事：订单扩到 3 个副本、商品图交给 CDN、入口加健康检查。问题反而变多：客服后台每隔几分钟被踢回登录页；商品图在晚高峰出现两分钟的“旧图”；一台实例 GC 假死，进程活着、端口也通，入口仍把一半流量发给它，用户看到一串 `502`。

三条故障分属会话、缓存与故障隔离，却都由同一层决定：请求到达业务代码之前，先经过了谁、被交给了哪一台、能不能不回到源站。

> **核心结论：** 反向代理决定“请求先经过谁”，负载均衡决定“交给哪一台”，CDN 决定“哪些请求根本不用回源”；这三处配错一处，扩容当天就会以会话丢失、源站被打穿和 `502` 的形式爆发。

## 学习目标

完成本课后，你能够：

- 说出反向代理、负载均衡与 CDN 在请求路径上的位置，区分它们能解决与不能解决的问题。
- 为无状态服务选出负载均衡算法，为有状态服务选出会话保持方案并说明代价。
- 解释健康检查判定如何改变流量分配，说清主动与被动检查各拦住哪类故障。
- 写出一条可执行的 CDN 缓存规则（缓存键、TTL、回源条件），预判它命中还是回源。

## 前置知识

- 回看上一课：[curl 与网络诊断](08-curl-and-network-diagnostics.md)。
- 知道 HTTP 事务由请求行、头和体组成，会用状态码区分 `2xx`、`4xx`、`5xx`。
- 知道 DNS 把域名解析成 IP，`curl -v` 能看到连接过程和响应头。
- 能读懂简单的 `python3` 脚本：函数、字典、`for` 循环。

## 业务场景

晴空商城（自建商城、订单、支付、仓储、客服，退款流程跨这几个系统）进入大促评审，运维与客服提出四个诉求：

1. 订单服务扩到 3 个副本，客服后台的登录态不能因为请求落到另一台而失效。
2. 商品详情页与商品图九成来自未登录访问，源站带宽要压到峰值两成以内。
3. 一台实例“进程活着但不响应”时，入口要在 10 秒内停止派流量。
4. 退款详情接口属于内部系统，既不能对公网缓存开放，也不能因为入口统一而失去访问控制。

诉求 1 是会话保持，2 是缓存与回源，3 是健康检查，4 是缓存边界。它们共享同一条路径，改错一处，其余都会冒出“不相关”的故障。

## 核心概念

*反向代理*（reverse proxy）站在服务端一侧，代替后端接收客户端请求：客户端以为在和源站对话，实际先到的是代理。相对的*正向代理*站在客户端一侧，代表客户端访问外部站点。<u>“代理”不区分方向，方向只由“替谁出面”决定。</u>

*上游*（upstream）是反向代理转发目标那一侧的统称，可以是一组实例或另一个代理。*负载均衡*就是在这个集合里挑一个的过程。

*会话保持*（session affinity，也叫*粘性会话*）让同一客户端的请求稳定落到同一台上游，用“记住用户去过哪”换取状态延续。<u>它救得了遗留系统，救不了节点故障——那台一挂，粘在上面的会话一起消失。</u>

*健康检查*让入口判断上游“现在能不能接业务流量”：*主动检查*由入口定期去问，*被动检查*靠真实请求的失败次数推断。<u>两者的差别不是灵敏度，而是能否发现“端口通但业务不可用”。</u>

*CDN*（content delivery network）把可共享的响应副本放到离用户最近的*边缘节点*（edge / PoP）上。副本缺失或过期时，边缘节点替客户端向源站再要一次，这叫*回源*（origin fetch）。

*缓存键*（cache key）是边缘判断“副本能否复用”的依据，通常由方法、规范化路径、查询串和若干被点名的头拼成：<u>少一个维度，不同内容互相顶替；多一个维度，命中率成倍下降</u>。

| 组件 | 站在谁那边 | 主要职责 | 明确不负责 |
| --- | --- | --- | --- |
| 反向代理 | 服务端 | TLS 终止、路由、改写头、限流、压缩 | 判断业务语义，如订单归谁处理 |
| 负载均衡 | 服务端内部 | 从健康的上游里按算法选一台 | 保存会话、理解业务键 |
| CDN | 服务端之前 | 就近接入、缓存可共享响应 | 返回个性化或含个人信息的内容 |

## 工作原理

一次“用户打开商品详情页”的完整路径：

1. 浏览器解析 `shop.qingkong.example`，指向 CDN 的 `CNAME` 最终解析到就近的边缘节点。
2. 边缘节点按“方法 + 规范化路径 + 查询串 + 缓存键声明的头”组装缓存键，查本地有没有副本。
3. 有副本且在 TTL 内：直接返回，响应带 `Age`（副本已存多久）与 `X-Cache: HIT`，源站零请求。
4. 没副本或已过期：边缘节点回源，并追加 `X-Forwarded-For` 记下真实客户端 IP，否则源站只看到边缘节点地址。
5. 回源请求到达入口反向代理，TLS 在这一层终止，证书也只在这一层维护。
6. 反向代理按 `server_name` 与 `location` 路由到上游组，改写 `Host`、补 `X-Forwarded-Proto`，让上游知道原始协议。
7. 负载均衡先做健康过滤，把探测失败的成员剔出候选，再按策略从剩下的里面选一台。
8. 上游执行业务并返回响应，响应沿原路回到反向代理，再回到边缘节点。
9. 边缘节点读 `Cache-Control`：`public` 且 `s-maxage` 有效就存一份，`private` 或 `no-store` 就原样透传。
10. 同时后台健康检查每 2 秒探测一次，连续失败达阈值就把节点标为不可用，恢复后重新放回。

会话保持插在第 7 步之前：上游有状态时，不能只看“谁最闲”，还要看“用户上次在哪”。<u>粘性会话让新扩容的实例分不到老用户，这正是“扩了容但吞吐没涨”的常见原因。</u>

## 架构与选型

### 选哪种负载均衡算法

| 算法 | 适合 | 不适合 | 关键代价 |
| --- | --- | --- | --- |
| 轮询 / 加权 | 上游同构、耗时接近 | 请求耗时差异大 | 慢请求堆在同一节点 |
| 最少连接 | 长请求，如导出、报表 | 长连接复用后连接数恒定 | 依赖准确的连接数统计 |
| IP 哈希 / 一致性哈希 | 需按客户端或业务键落点 | 上游集合频繁变化 | 扩缩容时键重映射，缓存击穿 |
| 最快响应 | 性能长期不均 | 冷启动、样本不足 | 流量压向偶然变快的节点 |

### 有状态服务怎么保住会话

| 方案 | 适用 | 不适用 | 代价 |
| --- | --- | --- | --- |
| 粘性会话（`ip_hash`、Cookie） | 迁移期的遗留有状态应用 | 频繁扩缩容、精确灰度 | 节点故障即会话丢失 |
| 共享会话存储（如 Redis） | 多副本、需即时登出 | 对存储延迟极敏感 | 多一个依赖，需单独高可用 |
| 无状态令牌 | 新系统、跨服务共享身份 | 需即时作废单个会话 | 难即时吊销，只能短过期 |

### CDN 该缓存什么

| 内容 | 适合缓存 | 原因 |
| --- | --- | --- |
| 商品图、JS/CSS、字体 | 是 | 字节对所有人相同，文件名带指纹 |
| 商品详情 JSON | 是，短 TTL | 可共享，但价格与库存变化快 |
| 退款详情、客服工单 | 否 | 含会员个人信息 |
| 下单、支付回调 | 否 | 状态变更，必须直达源站且不可重放 |

选型只需回答三个问题：上游有没有状态、响应是否对所有人相同、能容忍多少秒流量误发。

## 最小示例

问题：不上真机集群，先看清三种策略实际怎样分配流量。

环境：Python 3.8 以上，只用标准库 `hashlib`。输入是三条带权重与健康状态的上游，输出是每次选择结果。

```python
"""比较三种上游选择策略：加权轮询、最少连接、一致性哈希。"""
import hashlib  # 标准库，为一致性哈希的虚节点和 key 生成稳定的十六进制位置

UPSTREAMS = [                      # 元组含义：名字、权重、当前连接数、是否通过健康检查
    ("order-a", 3, 0, True),       # 大促主力机，权重 3
    ("order-b", 1, 0, True),       # 小规格实例，权重 1
    ("order-c", 1, 0, False),      # 健康检查已连续失败，本轮不参与候选
]


def healthy(upstreams):
    """先做健康过滤：不健康的实例连候选都不算，权重再高也不选。"""
    return [u for u in upstreams if u[3]]


def weighted_round_robin(upstreams, rounds):
    """加权轮询：把权重展开成槽位，按槽位循环，分配比例等于权重比例。"""
    slots = []
    for name, weight, _, _ in healthy(upstreams):
        slots.extend([name] * weight)          # 权重 3 就占 3 个槽
    return [slots[i % len(slots)] for i in range(rounds)]


def least_connections(upstreams, rounds):
    """最少连接：每次挑当前连接数最少的，适合请求耗时长且差异大的场景。"""
    loads = {u[0]: u[2] for u in healthy(upstreams)}  # 复制连接数，避免改到原始数据
    picked = []
    for _ in range(rounds):
        name = min(loads, key=loads.get)      # 连接数相同时按名字字典序，结果可复现
        loads[name] += 1                      # 选中即视为派发了一个请求
        picked.append(name)
    return picked


def consistent_hash(upstreams, keys):
    """一致性哈希：按业务键把同一用户的请求稳定映射到同一台。"""
    ring = {}
    for name in sorted(u[0] for u in healthy(upstreams)):
        for i in range(3):                    # 每个上游放 3 个虚节点，摊薄环上的空隙
            ring[hashlib.md5(f"{name}#{i}".encode()).hexdigest()] = name
    positions = sorted(ring)                  # 环上位置统一用十六进制字符串排序
    result = {}
    for key in keys:
        h = hashlib.md5(key.encode()).hexdigest()
        target = next((p for p in positions if p >= h), positions[0])  # 顺时针找第一个虚节点
        result[key] = ring[target]
    return result


if __name__ == "__main__":
    print("加权轮询 8 次:", weighted_round_robin(UPSTREAMS, 8))
    print("最少连接 8 次:", least_connections(UPSTREAMS, 8))
    users = [f"member-{i}" for i in range(1, 6)]
    print("一致性哈希:", consistent_hash(UPSTREAMS, users))
```

整体分三段：`healthy()` 做与算法无关的过滤，三个策略函数只管“怎么选”，`__main__` 统一打印。关键设计是**把健康过滤放在选择之前并独立成函数**——真实系统里这一步由 `proxy_next_upstream` 与健康检查完成，算法不该关心谁健康。

运行与输出（Python 3.14 实测）：

```bash
$ python3 pick_upstream.py
加权轮询 8 次: ['order-a', 'order-a', 'order-a', 'order-b', 'order-a', 'order-a', 'order-a', 'order-b']
最少连接 8 次: ['order-a', 'order-b', 'order-a', 'order-b', 'order-a', 'order-b', 'order-a', 'order-b']
一致性哈希: {'member-1': 'order-a', 'member-2': 'order-b', 'member-3': 'order-a', 'member-4': 'order-b', 'member-5': 'order-b'}
```

同一个入口的真实配置通常长这样，可以对照上面的策略读：

```nginx
upstream qk_orders {
    least_conn;                                  # 选当前连接数最少的实例
    server 10.0.2.11:8080 weight=3 max_fails=2 fail_timeout=10s;
    server 10.0.2.12:8080 weight=1 max_fails=2 fail_timeout=10s;
    keepalive 32;                                # 与上游保持长连接，省掉反复握手
}

server {
    listen 443 ssl;                              # TLS 在反向代理这一层终止
    server_name shop.qingkong.example;
    location /api/ {
        proxy_pass http://qk_orders;
        proxy_set_header Host $host;                                  # 保留原始域名
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;  # 追加客户端 IP
        proxy_set_header X-Forwarded-Proto $scheme;                   # 告诉上游原始协议
        proxy_next_upstream error timeout http_502 http_503;          # 失败自动换台
        proxy_connect_timeout 2s;
        proxy_read_timeout 10s;
    }
}
```

一次经过 CDN 与入口的商品请求，预期报文如下（`Age`、`X-Cache`、`X-Upstream` 的取值随真实命中情况变化）：

```http
GET /api/products/sku-1001 HTTP/1.1
Host: shop.qingkong.example
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: public, max-age=60, s-maxage=600, stale-while-revalidate=30
Age: 128
X-Cache: HIT
X-Upstream: http://10.0.2.11:8080
```

`Age: 128` 说明副本已存 128 秒、仍在 `s-maxage=600` 内；`X-Cache: HIT` 说明这次没有回源。

## 动手实验

前置条件：已装 `python3` 与 `curl`；端口 `9100` 到 `9102` 未被占用；不需要网络与账号。

1. 建实验目录，准备两个内容不同的“上游”：
   ```bash
   mkdir -p /tmp/qk-lb/a /tmp/qk-lb/b && cd /tmp/qk-lb
   printf 'backend A\n' > a/index.html
   printf 'backend B\n' > b/index.html
   ```
2. 起两个静态服务充当上游：
   ```bash
   python3 -m http.server 9101 --directory a &
   python3 -m http.server 9102 --directory b &
   ```
3. 把下面的 `proxy.py` 存到 `/tmp/qk-lb/proxy.py`，再运行 `python3 proxy.py`：
   ```python
   """最小反向代理：轮询分发 + 后台健康检查，只用于本机实验。"""
   import http.server      # 提供 HTTP 服务端骨架
   import itertools        # 提供无状态轮询器
   import threading        # 让健康检查在后台独立运行
   import time             # 控制探测间隔
   import urllib.request   # 用标准库客户端向上游发起请求

   UPSTREAMS = ["http://127.0.0.1:9101", "http://127.0.0.1:9102"]  # 上游组
   alive = {u: True for u in UPSTREAMS}   # 健康状态表，初始全部视为可用
   rr = itertools.cycle(UPSTREAMS)        # 轮询器：每次 next() 拿到下一台


   def probe():
       """主动健康检查：定期访问上游根路径，失败就摘除，恢复就放回。"""
       while True:
           for u in UPSTREAMS:
               try:
                   urllib.request.urlopen(u + "/", timeout=1)
                   alive[u] = True
               except Exception:          # 连接拒绝、超时都说明这台不能接流量
                   alive[u] = False
           time.sleep(2)


   class Handler(http.server.BaseHTTPRequestHandler):
       def do_GET(self):
           for _ in range(len(UPSTREAMS)):        # 最多试一轮，避免无限重试
               upstream = next(rr)
               if not alive[upstream]:            # 健康过滤：跳过已被摘除的实例
                   continue
               try:
                   with urllib.request.urlopen(upstream + self.path, timeout=2) as resp:
                       body = resp.read()
                   self.send_response(200)
                   self.send_header("X-Upstream", upstream)   # 让客户端看见流量落到了哪台
                   self.send_header("Content-Length", str(len(body)))
                   self.end_headers()
                   self.wfile.write(body)
                   return
               except Exception:                  # 转发失败：标记不可用，换下一台重试
                   alive[upstream] = False
           self.send_error(502, "no healthy upstream")     # 一轮都没有可用上游


   if __name__ == "__main__":
       threading.Thread(target=probe, daemon=True).start()
       http.server.ThreadingHTTPServer(("127.0.0.1", 9100), Handler).serve_forever()
   ```
4. 新开终端连续发 4 次请求，只看 `X-Upstream`；
   ```bash
   for i in 1 2 3 4; do curl -s -D - http://127.0.0.1:9100/ -o /dev/null | grep -i x-upstream; done
   ```
5. 停掉 `9102` 的服务（`kill` 该进程或按 `Ctrl+C`），等 3 秒再发 3 次同样的请求。
6. 再把 `9101` 也停掉，等 3 秒后用 `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9100/` 看状态码。

预期结果：步骤 4 的 `X-Upstream` 在 `9101` 与 `9102` 之间交替；步骤 5 全部变成 `9101`；步骤 6 返回 `502`。

验证方法：交替出现证明轮询生效；停掉一台仍返回 `200` 证明健康过滤生效；两台都停返回 `502` 而非挂起，说明失败路径是明确的。

清理方法：停掉 `proxy.py` 与两个 `http.server`，再 `rm -rf /tmp/qk-lb`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 扩容后用户被反复踢回登录页 | 会话在单机内存，入口无会话保持 | 连续请求看 `X-Upstream` 是否变化 | 会话外置到共享存储，或改用签名令牌 |
| 实例假死期间持续 `502` | 只配被动检查，或探 TCP 端口而非业务就绪 | 手动 `curl` 该实例的 `/healthz` | 探业务就绪点、缩短 `fail_timeout`，开 `proxy_next_upstream` |
| 命中率接近 0，源站带宽不减 | 响应带 `Set-Cookie`，或写成 `private`、`no-store` | `curl -sI` 看该 URL 的响应头 | 补 `s-maxage`，并从响应中移除 `Set-Cookie` |
| 大促开始瞬间源站被打穿 | 大量副本同一秒到期，回源集中 | 看回源曲线是否是整齐的尖峰 | 加 `stale-while-revalidate`，给 TTL 加随机抖动 |
| 源站日志里客户端 IP 全是边缘节点地址 | 回源没带 `X-Forwarded-For`，或应用取了最左值 | 看日志 IP 字段与代理配置 | 入口追加该头，应用按可信跳数从右往左取值 |

## 安全与生产注意事项

**<u>入口默认信任客户端传来的 `X-Forwarded-For`，等于允许任何人伪造来源 IP。</u>** 后果是限流、封禁、风控与审计归因同时失效，一个伪造头就能绕过按 IP 的防护。缓解：只信任自己这一跳追加的值，按“可信代理跳数”从右往左解析，并在入口覆盖而非拼接。

**<u>把退款详情或客服工单挂在带缓存规则的路径下，共享缓存会把含个人信息的响应发给下一个访问者。</u>** 这类事故在日志里全是 `200`，只有缓存头审计和 `X-Cache` 能看出来。缓解：按路径前缀显式声明 `no-store`，CDN 侧排除个性化接口，发布前用脚本断言这些路径的响应头。

**<u>健康检查返回 `200` 但数据库连接池已耗尽时，入口仍会把流量发给它。</u>** 后果是“扩容了却更慢”，故障沿连接池扩散。缓解：就绪检查覆盖关键依赖，并对连接池饱和度告警。

另外两点是日常约束：上游生成的重定向与绝对链接要用原始域名，否则 HTTPS 后会退化成 `http://`；回源的 `Host` 与证书 `SNI` 必须与源站对齐，否则出现 `421` 或证书不匹配。

## 本课总结

- 反向代理、负载均衡、CDN 是路径上三个决策点：谁先接、交给哪台、要不要回源。
- 算法看单请求耗时分布，会话保持看上游有没有状态；<u>粘性会话是迁移手段，不是长期架构</u>。
- 主动检查能发现“端口通但业务不可用”，被动检查只能等真实请求失败，两者应同时存在。
- 命中率由缓存键与响应头决定：`s-maxage` 给共享有效期，`private`、`no-store`、`Set-Cookie` 挡住副本。
- 任意一层配错，症状都从另一层冒出来：会话丢失像登录 bug，命中率归零像源站性能问题。

## 思考题

支付回调 `/api/payments/notify` 要经过 CDN 与反向代理才到订单服务。支付方会重试同一条通知，订单服务有 3 个副本。请判断：这条回调该被 CDN 缓存吗？该做会话保持吗？重试被分到另一台时，业务靠什么保证不出错？并说明最该监控的两个指标。

参考思路：回调是状态变更类请求，不应缓存，应显式 `no-store` 或按路径绕开；重试不携带用户会话，会话保持对它没有意义，真正需要的是按订单号做幂等，让“分到哪一台”不影响结果；最该监控回调失败率与“重复通知被幂等拦下”的次数。

## 小测

1. 反向代理与正向代理最本质的区别是什么？  
   A. 是否使用 HTTPS　B. 代表客户端还是代表服务端出面　C. 是否缓存内容　D. 是否部署在云上
2. 上游有状态且会话存在单机内存里时，把负载均衡改成最少连接就能解决会话丢失。对还是错？
3. 下列哪项最可能让 CDN 命中率降到接近 0？  
   A. 响应带 `public, s-maxage=600`　B. 响应带 `Set-Cookie` 与 `private`　C. 图片名带内容指纹　D. 开启 `stale-while-revalidate`
4. 主动健康检查相比被动检查，多解决了哪一类故障？
5. 场景题：商品详情接口 `GET /api/products/{sku}` 含价格与库存，数据约 5 分钟变一次，九成访问未登录。请写出一条缓存规则（缓存键、TTL、一致性处理），并说明它为什么不会泄漏会员信息。

## 答案与解析

1. **B。**方向只由“替谁出面”决定。A 两者都能用；C 的正向代理通常不缓存，但不构成区别；D 与部署位置无关。
2. **错。**最少连接只改变“选谁”，不改变“会话存在哪”。会话还在单机内存里，落到另一台就会丢。<u>正确做法是外置会话或改用无状态令牌。</u>
3. **B。**`private` 与 `Set-Cookie` 都会让共享缓存拒绝存储或复用。A 是标准可缓存声明；C 是提高命中率的常见手段；D 只在副本过期后减少回源阻塞。
4. 它能发现“端口通但业务不可用”，如进程假死、依赖耗尽、就绪未完成；被动检查要等真实请求失败才调整，这期间用户已在承担错误。
5. 参考规则：缓存键取“方法 + 规范化路径 + `Accept-Encoding`”，不把 `Authorization`、`Cookie` 纳入键；`s-maxage=300` 略小于 5 分钟变更周期，并加 `stale-while-revalidate=60`，过期后先返回旧副本再后台回源；库存若要求强实时，就单独走一个不缓存的接口。它不泄漏会员信息，是因为响应与用户无关：不含 `Set-Cookie` 与个人信息，任何人拿到的都是同一份价格与库存。

### 动手实验参考

步骤 4 的 `X-Upstream` 在 `9101` 与 `9102` 间交替，因为 `itertools.cycle` 按顺序轮转；步骤 5 全部落 `9101`，因为 `9102` 探测失败后被标不可用并跳过；步骤 6 返回 `502`，因为上游全不可用且一轮重试耗尽。把探测间隔改大，摘除会变慢，这就是 `fail_timeout` 对故障窗口的影响。

## 延伸阅读与下一课

- [MDN：代理服务器与隧道](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Proxy_servers_and_tunneling)——正向与反向代理的概念区分。
- [MDN：HTTP 缓存](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Caching)——共享缓存与私有缓存的判定规则。
- [nginx：ngx_http_upstream_module](https://nginx.org/en/docs/http/ngx_http_upstream_module.html)——`least_conn`、`ip_hash`、`max_fails`、`fail_timeout` 的权威说明。
- [nginx：ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)——`proxy_next_upstream` 等转发指令。
- [RFC 9111：HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)——`s-maxage`、`Age`、`stale-while-revalidate` 的规范定义。
- [RFC 7239：Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html)——代理链传递来源信息的标准头。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[curl 与网络诊断](08-curl-and-network-diagnostics.md)。
- 下一课：[Web 与网络阶段综合测评](10-stage-assessment.md)。
