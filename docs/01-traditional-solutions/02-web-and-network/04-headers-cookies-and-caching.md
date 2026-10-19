---
title: Header、Cookie 与缓存
slug: headers-cookies-and-caching
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - http-request-response
outcomes:
  - 按用途把常见 Header 分类并说明各自的作用方向
  - 为登录态 Cookie 选择 HttpOnly、Secure 与 SameSite 的正确组合
  - 读取 Cache-Control、ETag 与 Vary 并判断响应能否被共享缓存复用
last_reviewed: 2026-10-19
---

# Header、Cookie 与缓存

## 为什么需要学习

晴空商城大促上线前一天，四件事同时报障：商品详情页走 CDN 后命中率只有 12%，源站带宽被打满；客服后台的登录态存在 `localStorage` 里，安全评审标了红；顾客投诉退出登录后仍能在公用电脑上看到上一位会员的退款金额；海外站点用英文浏览器打开，看到的还是中文。这四条分属性能、安全、隐私和国际化，实际改的都是同一层东西——HTTP 头部。

> **核心结论：** Header 不改业务逻辑，却决定一次请求“能不能被缓存、该返回哪种表示、带不带登录态”；同一段业务代码，头部写对是省带宽又安全，写错就是泄露又拖垮源站。

## 学习目标

完成本课后，你能够：

- 按用途把常见 Header 归入表示、协商、状态、缓存、追踪五类，并说出各自的作用方向。
- 为晴空商城的登录态 Cookie 选出 `HttpOnly`、`Secure`、`SameSite` 的组合，并说明每个属性拦住哪类攻击。
- 读一条响应的 `Cache-Control`、`ETag`、`Vary`，判断它能被浏览器缓存多久、能否被 CDN 复用。
- 用 `python3` 标准库写脚本，批量审计 `Set-Cookie` 与 `Cache-Control` 是否符合基线。

## 前置知识

- 回看上一课：[HTTP 请求、响应与状态码](03-http-request-response.md)。
- 知道一次请求由方法、路径、头和体组成，一次响应由状态码、头和体组成。
- 能读懂简单的 `python3` 脚本：字典、函数、`if not x` 判空。
- 本课不要求 TLS 与 CDN 细节，这些在后续课程展开。

## 业务场景

晴空商城（商城、订单、支付、仓储、客服，退款跨这几个系统）进入秋季大促，架构评审列出四个诉求：

1. 商品详情页九成访问来自未登录用户，看同一批 SKU，希望 CDN 缓存 60 秒，源站只做回源验证。
2. 客服后台的退款详情页包含会员手机号与退款金额，绝不允许进入任何共享缓存。
3. 登录态目前存在 `localStorage` 的 `token` 里，安全评审要求迁移到 Cookie。
4. 海外站点要在同一个商品 URL 上按浏览器语言返回中/英文案。

前两条是缓存头，第三条是 Cookie 属性，第四条是内容协商与 `Vary`，共同构成“同一个 URL 对不同人返回不同东西”这一最易出错的问题域。

## 核心概念

*Header*（消息头）是 HTTP 消息开头 `名字: 值` 形式的那几行，描述本次消息的元数据，不承载业务数据本体。浏览器、CDN、网关和框架都读它，所以影响面比业务代码更靠前。

*内容协商*（content negotiation）是客户端用 `Accept` 系列头声明偏好、服务端挑一个表示并声明结果的机制。被挑出来的字节叫*表示*（representation），由 `Content-Type` 与 `Content-Encoding` 说明。

*Cookie* 是服务端用 `Set-Cookie` 下发、浏览器保存、之后在同一站点请求的 `Cookie` 头里自动回传的键值对。<u>“自动回传”是 Cookie 的全部价值，也是它的全部风险来源。</u>

*HTTP 缓存*是浏览器或 CDN 保存一份响应副本、在有效期内直接复用。*ETag* 是某个表示版本的指纹，配合 `If-None-Match` 做验证，内容没变就返回 `304`，省掉响应体。

| 类别 | 方向 | 典型头 | 谁在读 | 常见误用 |
| --- | --- | --- | --- | --- |
| 表示 | 响应 | `Content-Type`、`Content-Encoding`、`Content-Language` | 浏览器、客户端 | 漏写 `charset=utf-8` |
| 协商 | 双向 | `Accept`、`Accept-Language`、`Accept-Encoding`、`Vary` | 服务端、CDN | 做了协商却不写 `Vary` |
| 状态 | 双向 | `Set-Cookie`、`Cookie`、`Authorization` | 浏览器、服务端 | 把会话 ID 放进 URL 参数 |
| 缓存 | 双向 | `Cache-Control`、`ETag`、`Last-Modified`、`Age` | 浏览器、CDN | 以为 `no-cache` 等于“不存储” |
| 追踪 | 请求 | `traceparent`、`X-Request-Id` | 网关、日志系统 | 用它传递“我已是管理员”这类信任信息 |

Cookie 的属性决定了它被谁读、被谁发：

| 属性 | 作用 | 缺失后果 | 建议 |
| --- | --- | --- | --- |
| `HttpOnly` | 禁止 JS 通过 `document.cookie` 读取 | 一次 XSS 即可批量导出登录态 | 承载登录态的 Cookie 必加 |
| `Secure` | 只在 HTTPS 连接上发送 | 明文 HTTP 或协议降级时会带上会话 | 生产环境一律开启 |
| `SameSite=Strict/Lax` | 限制跨站请求是否自动携带 | 第三方站点可借用户浏览器发起已登录请求 | 默认 `Lax`，高风险操作改 `Strict` |
| `Path`、`Domain` | 限定发送范围 | 范围过宽会发给无关子域 | 不写 `Domain`，`Path=/` 最省心 |
| `Max-Age`、`Expires` | 区分持久 Cookie 与会话 Cookie | 关浏览器即失效，用户反复登录 | 按业务定，登录态给明确过期 |

<u>`Set-Cookie` 与 `Cookie` 是两个不同的头</u>：前者只在响应里由服务端下发，后者只在请求里由浏览器带上，服务端不能“读取响应里的 `Set-Cookie`”。

## 工作原理

### 一次商品页请求的缓存路径

1. 浏览器发 `GET /api/products/sku-1001`，带 `Accept: application/json`、`Accept-Language: zh-CN,en;q=0.5`、`Accept-Encoding: gzip, br`。
2. 请求先到 CDN。副本仍在 `s-maxage` 内 → 直接返回，并带 `Age` 表示副本年龄，源站零请求。
3. 副本过期 → CDN 带旧 `ETag` 发 `If-None-Match` 回源验证。
4. 源站比对：内容没变返回 `304`（无响应体）；内容变了返回 `200` 加新 `ETag`。
5. CDN 按响应里的 `Vary` 判断这份副本能否复用于当前请求——`Vary: Accept-Encoding` 意味着 gzip 副本不能发给只接受 `br` 的客户端。
6. 浏览器收到后按 `max-age` 自己再存一份，下次连 CDN 都不问。

### 一次登录的 Cookie 路径

7. `POST /login` 校验通过，响应下发 `Set-Cookie: sid=abc123; Path=/; Max-Age=86400; Secure; HttpOnly; SameSite=Lax`。
8. 浏览器按 `Domain` 与 `Path` 存储，并把这条记进“JS 不可见”的存储区。
9. 之后同站请求自动附加 `Cookie: sid=abc123`，页面脚本读 `document.cookie` 读不到它。
10. 若有人从第三方站点提交表单，`SameSite=Lax` 让这个跨站 POST 不带 `sid`，服务端看到的是未登录请求。
11. 退出登录时下发同名 Cookie 且 `Max-Age=0`，浏览器立即删除。

存储与验证在网关处交汇：缓存决策在返回响应体的路上，Cookie 决策在请求带上来的路上。<u>所以网关配置错一次，会同时影响缓存和鉴权。</u>

## 架构与选型

### 登录态放在哪里

| 方案 | 适用 | 不适用 | 主要代价 |
| --- | --- | --- | --- |
| Cookie + `HttpOnly` + 服务端 Session | 同域 Web 应用、客服后台 | 跨域多前端、移动 App | 服务端要存会话，横向扩展需共享存储 |
| Cookie 里放签名令牌 | 无状态服务、多服务共享校验 | 需要即时吊销的场景 | 令牌难以即时作废，只能靠短过期 |
| `localStorage` + `Authorization` 头 | 跨域调用、第三方 API 客户端 | 任何含登录态的浏览器页面 | <u>XSS 可直接读走，且不随请求自动失效</u> |
| 内存变量 | 单页应用里的临时凭据 | 需要跨标签页共享 | 刷新即丢，体验差 |

### 缓存放在哪一层

| 位置 | 由谁控制 | 关键头 | 适合 | 不适合 |
| --- | --- | --- | --- | --- |
| 浏览器私有缓存 | 终端用户 | `max-age`、`private` | 头像、静态资源 | 一次性数据 |
| CDN 共享缓存 | 平台配置 | `s-maxage`、`public`、`Age` | 商品列表、详情、静态文件 | 含个人信息或登录态的响应 |
| 应用内缓存（如 Redis） | 应用代码 | 不涉及 | 高频查询、聚合结果 | 强一致要求的数据 |

### 内容协商用哪种形态

| 形态 | 例子 | 优点 | 风险 |
| --- | --- | --- | --- |
| 同 URL 协商 | `/products/sku-1001` 加 `Vary: Accept-Language` | URL 稳定，链接可复用 | `Vary` 维度越多缓存键越多，命中率骤降 |
| 独立路径 | `/zh-CN/products/sku-1001` | 缓存键天然分离，SEO 清晰 | 需要生成多套链接与跳转 |
| 客户端内切换 | 前端读语言包 | 服务端最省事 | 首屏闪烁，无法服务端渲染 SEO |

选型依据是“同一 URL 的变体数量”和“变体是否需要被 CDN 分别缓存”。只有压缩编码一维时，`Vary: Accept-Encoding` 很划算；一旦叠加语言、币种、会员等级，命中率会按乘法衰减，此时独立路径更稳。

## 最小示例

问题：给登录态 Cookie 和商品页缓存头做一次离线体检，不依赖浏览器，也不引入第三方库。

环境：Python 3.8 以上，只用标准库 `http.cookies`。输入是两条 `Set-Cookie` 与两条 `Cache-Control` 字符串，输出是逐条问题清单。

```python
"""审计 Set-Cookie 与 Cache-Control 是否符合晴空商城的安全基线。"""
import http.cookies  # 标准库自带的 Set-Cookie 语法解析器，可离线复现浏览器行为

def audit_cookie(raw_header):
    """把一条 Set-Cookie 拆成“谁能读取 / 何时发送”的判断。"""
    jar = http.cookies.SimpleCookie()
    jar.load(raw_header)                 # 语法错误不抛异常，只会留下空 jar
    if not jar:                          # 空 jar 说明这条头根本没解析出 cookie
        return ["解析失败：Set-Cookie 语法不合法"]
    findings = []
    for name, morsel in jar.items():
        if not morsel.get("httponly"):   # 属性缺失时返回空串，与 True 区分开
            findings.append(f"{name}: 缺 HttpOnly，JS 可读走登录态")
        if not morsel.get("secure"):     # Secure 缺失，明文 HTTP 也会发送
            findings.append(f"{name}: 缺 Secure，弱网降级时明文外泄")
        if not morsel.get("samesite"):   # SameSite 缺失，跨站表单会自动携带
            findings.append(f"{name}: 缺 SameSite，跨站请求被默认放行")
    if findings:
        return findings
    return ["通过：登录态不可被 JS 读取，且仅在 HTTPS 与同站请求中发送"]

def parse_cache_control(raw_header):
    """把 Cache-Control 拆成指令字典，逐条判断而不是凭印象。"""
    directives = {}
    for part in raw_header.split(","):               # 指令之间用逗号分隔
        key, _, value = part.strip().partition("=")  # 只有部分指令带值
        directives[key.lower()] = value or True      # 无值指令（no-store）记为 True
    return directives

if __name__ == "__main__":
    bad = "sid=abc123; Path=/; Max-Age=86400"        # 只设了路径和过期时间
    good = "sid=abc123; Path=/; Max-Age=86400; Secure; HttpOnly; SameSite=Lax"
    for label, header in (("旧写法", bad), ("基线写法", good)):
        print(f"[Cookie] {label}: {header}")
        for line in audit_cookie(header):
            print(f"  - {line}")
    for header in ("public, max-age=60, s-maxage=600, stale-while-revalidate=30",
                   "no-store"):
        print(f"[Cache-Control] {header} -> {parse_cache_control(header)}")
```

整体分三段：`jar.load()` 解析语法，`morsel.get()` 逐属性判空，字典承接 `Cache-Control` 指令。关键设计选择是**用标准库而不是手写正则**：`Set-Cookie` 的大小写、引号与空格都有兼容坑，正则容易误判。

运行与输出（Python 3.14 实测）：

```bash
$ python3 audit_session.py
[Cookie] 旧写法: sid=abc123; Path=/; Max-Age=86400
  - sid: 缺 HttpOnly，JS 可读走登录态
  - sid: 缺 Secure，弱网降级时明文外泄
  - sid: 缺 SameSite，跨站请求被默认放行
[Cookie] 基线写法: sid=abc123; Path=/; Max-Age=86400; Secure; HttpOnly; SameSite=Lax
  - 通过：登录态不可被 JS 读取，且仅在 HTTPS 与同站请求中发送
[Cache-Control] public, max-age=60, s-maxage=600, stale-while-revalidate=30 -> {'public': True, 'max-age': '60', 's-maxage': '600', 'stale-while-revalidate': '30'}
[Cache-Control] no-store -> {'no-store': True}
```

补齐缓存头之后，商品接口的预期报文如下（字段值为示意，`ETag` 由应用生成）：

```http
GET /api/products/sku-1001 HTTP/1.1
Host: shop.qingkong.example
Accept: application/json
Accept-Language: zh-CN,zh;q=0.9,en;q=0.5
Accept-Encoding: gzip, br
Cookie: sid=abc123

HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Content-Language: zh-CN
Content-Encoding: gzip
Vary: Accept, Accept-Language, Accept-Encoding
Cache-Control: public, max-age=60, s-maxage=600, stale-while-revalidate=30
ETag: "sku-1001-v7"
```

60 秒后 CDN 回来验证，若商品未改动：

```http
GET /api/products/sku-1001 HTTP/1.1
If-None-Match: "sku-1001-v7"

HTTP/1.1 304 Not Modified
ETag: "sku-1001-v7"
Cache-Control: public, max-age=60, s-maxage=600
```

304 没有响应体，但不是“没响应”：头部会刷新副本有效期。**回源验证把一次完整响应压缩到几百字节**，这是 `ETag` 在大促里最直接的价值。

## 动手实验

前置条件：已安装 `python3`（3.8 以上）和 `curl`；不需要网络与账号；把本课脚本存为 `/tmp/qk-lab/audit_session.py`。

1. 建实验目录并放一份静态数据：
   ```bash
   mkdir -p /tmp/qk-lab && cd /tmp/qk-lab
   printf '{"sku":"1001","price":199}\n' > sku-1001.json
   ```
2. 用标准库起一个只监听本机的静态服务：`python3 -m http.server 8765`。
3. 另开终端只看响应头：`curl -sI http://127.0.0.1:8765/sku-1001.json`。
4. 取出 `Last-Modified` 的值，带上 `If-Modified-Since` 再请求一次：
   ```bash
   curl -sI -H 'If-Modified-Since: <步骤 3 的 Last-Modified 值>' \
     http://127.0.0.1:8765/sku-1001.json
   ```
5. 带上 `Accept-Encoding` 再请求，观察是否出现 `Content-Encoding`：
   ```bash
   curl -sI -H 'Accept-Encoding: gzip, br' http://127.0.0.1:8765/sku-1001.json
   ```
6. 把步骤 3 的响应头抄成 `patched-headers.txt`，补上 `Cache-Control`、`ETag`、`Vary`，再用脚本的 `parse_cache_control` 打印结果。

预期结果：步骤 3 只有 `Content-Type`、`Content-Length`、`Last-Modified`（外加 `Server`、`Date`），**既没有 `Cache-Control` 也没有 `ETag`**；步骤 4 返回 `304 Not Modified` 且无响应体；步骤 5 仍不出现 `Content-Encoding`。`Date` 与 `Last-Modified` 的具体时间每次都会变。

验证方法：`304` 决定验证机制是否生效，`Content-Encoding` 决定压缩是否被协商，补齐版里能否说清 `max-age` 与 `s-maxage` 各是谁的预算。

清理方法：`Ctrl+C` 停止服务，然后 `rm -rf /tmp/qk-lab`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| CDN 命中率接近 0，源站被打满 | 响应缺 `Cache-Control`，或带了 `Set-Cookie` | `curl -sI` 看有无这两个头 | 接口加 `s-maxage`，并从响应急去掉 `Set-Cookie` |
| 不同用户看到彼此的数据 | 共享缓存缓存了含个人信息的响应 | 看该响应是否有 `private` 或 `no-store` | 对含 PII 的路径强制 `no-store` |
| 前端发版后用户仍是旧页面 | HTML 被长缓存，静态资源没带内容指纹 | 看 HTML 的 `max-age`，看 JS/CSS 文件名是否带 hash | HTML 用 `no-cache` 加 `ETag`，带 hash 的资源用长缓存 |
| 登录成功但下一跳又要求登录 | `Path` 或 `Domain` 与新页面不匹配，或 `Secure` 在 HTTP 下被拒 | DevTools → Application → Cookies 看 `Path`、`Domain`，看请求是否带 `Cookie` | 统一 `Path=/`，不写 `Domain`，在 HTTPS 环境验证 |
| 英文用户仍看到中文 | 做了协商却没写 `Vary`，缓存复用了错误副本 | 看响应有无 `Vary: Accept-Language` | 补 `Vary`，或改独立路径 |
| `SameSite=None` 的 Cookie 被丢弃 | 没有同时设置 `Secure` | DevTools 里该 Cookie 带黄色警告 | `SameSite=None` 必须配 `Secure` |

## 安全与生产注意事项

**<u>登录态 Cookie 漏写 `HttpOnly`，等于把会话密钥交给页面上任何一个第三方脚本。</u>** 后果是一次 XSS 就能批量导出在线用户的 `sid`，服务端无法区分真实用户与攻击者，只能全量强制下线，退款与支付链路同时中断。缓解：登录态 Cookie 一律 `HttpOnly` + `Secure` + `SameSite=Lax/Strict`；前端要用的昵称、租户等信息放响应体。

**<u>对含个人信息的响应漏写 `private` 或 `no-store`，会被 CDN 或企业出口代理跨用户复用。</u>** 退款详情、收货地址一旦进了共享缓存，下一个访问同一 URL 的人拿到的就是别人的内容；这类事故在访问日志里全是 `200`，只有缓存头审计能发现。缓解：把含 PII 的路径写进网关规则强制 `no-store`，并在 CI 里断言响应头。

**<u>`SameSite=None` 不配 `Secure` 会被现代浏览器直接丢弃。</u>** 后果是跨站支付回跳后登录态丢失，用户看到“请重新登录”而重复下单。缓解：只在确需跨站嵌入时用 `None` 并同时开 `Secure`，优先用 `__Host-` 前缀把约束固化进名字。

另两点是日常约束：Cookie 有约 4KB 上限，别塞整个 JWT；`Authorization` 与 `Cookie` 在日志里必须脱敏。

## 本课总结

- Cookie 的三个属性各挡一类攻击：`HttpOnly` 挡 XSS 读取，`Secure` 挡明文传输，`SameSite` 挡跨站自动携带。
- 判断一份缓存能否复用看三件事：`Cache-Control` 规定谁能存多久，`ETag` 与 `Last-Modified` 规定怎么验证，`Vary` 规定哪些请求可以共用副本。
- `max-age` 是浏览器预算，`s-maxage` 是 CDN 预算，`private` 把共享缓存整体排除在外，三者不是同义词。
- 内容协商的根问题是“一个 URL 多种表示”，不给 `Vary` 就会串味，变体一多就该换独立路径。

## 思考题

晴空商城要在同一 URL 上给中英文用户返回不同文案，产品要求“SEO 友好、CDN 命中率高、默认语言可回退”。你会选 `Vary: Accept-Language`，还是 `/zh-CN/`、`/en/` 独立路径？请给出至少三条判断依据，并说明这个选择对 CDN 缓存键和默认语言回退的影响。

参考思路：先量化变体数（语言 × 编码 × 币种），再看缓存键相乘后的命中率；SEO 上独立路径更稳，可单独索引也能做 hreflang，协商方式依赖爬虫带上 `Accept-Language`；回退上独立路径要显式处理根路径跳转；运维上独立路径多一套链接生成成本。只做中英双语且 CDN 支持按头分键时协商可行，叠加币种后独立路径更可控。

## 小测

1. 下列哪个属性阻止页面脚本读取登录态 Cookie？  
   A. `Secure`　B. `HttpOnly`　C. `SameSite=Strict`　D. `Path=/`
2. 响应带 `Cache-Control: no-cache`，意味着浏览器不得存储这份响应。对还是错？
3. 要让 CDN 缓存 10 分钟、浏览器只缓存 1 分钟，哪个响应头正确？  
   A. `Cache-Control: max-age=600`　B. `Cache-Control: s-maxage=600, max-age=60`　C. `Cache-Control: no-store`　D. `Cache-Control: private, max-age=600`
4. 做了 `Accept-Encoding` 协商之后，为什么通常必须写 `Vary: Accept-Encoding`？
5. 场景题：客服后台的退款详情页 `/agent/refunds/{id}`，响应含会员手机号与退款金额。请写出你会设置的至少三个响应头，并说明每个头在挡什么。

## 答案与解析

1. **B。**`HttpOnly` 的语义就是“JS 不可读”。A 的 `Secure` 只管传输通道；C 的 `SameSite` 管跨站请求是否自动发送；D 的 `Path` 只管发送的路径范围——三者都不影响 `document.cookie` 的可见性。
2. **错。**`no-cache` 允许存储，但每次使用前必须向源站验证；禁止存储的是 `no-store`。<u>把 `no-cache` 读成“不缓存”是本课最常见的误读。</u>
3. **B。**`s-maxage` 只约束共享缓存（CDN），`max-age` 约束私有缓存（浏览器）。A 让两层都存 10 分钟；C 谁都不存；D 的 `private` 禁止 CDN 存储，与题意矛盾。
4. 同一个 URL 会产出压缩与未压缩等多个表示。不带 `Vary` 时，缓存可能把压缩副本发给不支持压缩的客户端，也可能把大体积副本发给能接受压缩的客户端。`Vary` 让缓存键带上编码维度，代价是条目翻倍。
5. 参考组合：`Cache-Control: no-store`（含个人信息，禁止浏览器与出口代理落盘）；`Content-Type: application/json; charset=utf-8`（避免按错误编码解析手机号）；`Vary: Accept-Encoding`（压缩时不串味）。登录态另用 `HttpOnly` + `Secure` + `SameSite=Strict`。只写 `no-cache` 不够，它仍可能落盘。

### 动手实验参考

步骤 3 只有 `Server`、`Date`、`Content-Type`、`Content-Length`、`Last-Modified`，因为 `http.server` 是最小实现，既不生成 `Cache-Control` 也不发 `ETag`，正好复现“没有缓存头时只能靠 `Last-Modified` 试探”。步骤 4 的 `304` 说明验证生效但缺少显式新鲜期，所以每次都回源。步骤 5 没有 `Content-Encoding`，因为标准库服务不做压缩协商。补齐版合理写法：`public, max-age=60, s-maxage=600`、`ETag: "sku-1001-v7"`、`Vary: Accept-Encoding, Accept-Language`。

## 延伸阅读与下一课

- [MDN：HTTP 头部索引](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Headers)——按名称查任意头的语义与浏览器兼容性。
- [MDN：Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)——Cookie 属性的完整说明与 `__Host-`、`__Secure-` 前缀规则。
- [MDN：Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control)——各缓存指令的区别与组合建议。
- [RFC 9110：HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)——Header 语义、内容协商与条件请求的权威定义。
- [RFC 9111：HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)——缓存新鲜度、验证与 `Vary` 的规范行为。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[HTTP 请求、响应与状态码](03-http-request-response.md)。
- 下一课：[HTTPS、TLS 与证书](05-https-tls-and-certificates.md)。
