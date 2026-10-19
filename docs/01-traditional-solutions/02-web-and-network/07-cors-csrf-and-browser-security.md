---
title: CORS、CSRF 与浏览器安全
slug: cors-csrf-and-browser-security
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - json-xml-and-encoding
outcomes:
  - 用协议、主机、端口三要素判断两个 URL 是否同源，并说明跨源时浏览器限制了什么
  - 区分简单请求与预检请求，写出可用的 CORS 响应头并指出其中的危险配置
  - 解释 CSRF 的攻击前提，说明 SameSite 与 CSRF Token 分别在哪一步拦截攻击
last_reviewed: 2026-10-19
---

# CORS、CSRF 与浏览器安全

## 为什么需要学习

晴空商城的前端在 `shop.qingkong.example`，接口在 `api.qingkong.example`。联调时控制台报 `blocked by CORS policy`，后端加了一行 `Access-Control-Allow-Origin: *`，页面恢复正常，这行配置随后进了生产。

两周后安全评审发现：用户在商城登录后访问任何第三方页面，那个页面都能静默调用订单接口，读走收货地址和订单列表。根因是**同源策略本来挡得住这类读取，是通配符把它关掉了。**

同期还有一类工单：“用户说没点过退款，账户里却多了一笔退款申请”。这类请求在日志里完全合法：方法正确、Cookie 有效、参数齐全，因为它是用户自己的浏览器发出去的。

> **核心结论：** 浏览器安全依赖三套互相独立、不能互替的机制——同源策略限制“谁可以读”，CSRF 防御限制“谁可以代你写”，XSS 防护限制“谁能在你的页面里跑代码”。

## 学习目标

完成本课后，你能够：

- 用协议、主机、端口判断两个 URL 是否同源，并指出跨源时浏览器允许和禁止的行为。
- 判断请求是否触发预检，写出匹配它的 CORS 响应头，并识别会导致越权读取的配置。
- 复述 CSRF 的四个攻击前提，说明 `SameSite` 与 CSRF Token 各拦截在哪一步。
- 解释 XSS 为何让 CSRF Token 与同源策略同时失效，并给出缓解措施。

## 前置知识

- 回看上一课：[JSON、XML、CSV 与字符编码](06-json-xml-and-encoding.md)。
- 知道 HTTP 请求由方法、路径、头部和正文组成，响应由状态码和头部组成。
- 知道 Cookie 是浏览器按域名自动保存并自动携带的键值对。

## 业务场景

晴空商城的商城前端、客服后台和 API 分属三个子域：

| 角色 | 地址 | 说明 |
| --- | --- | --- |
| 商城前端 | `https://shop.qingkong.example` | 静态站，走 CDN |
| 客服后台 | `https://cs.qingkong.example` | 内部使用，调用 API |
| 业务 API | `https://api.qingkong.example` | 会话 Cookie 在 `qingkong.example` |
| 合作方组件 | `https://coupon.partner.example` | 嵌入的第三方优惠券脚本 |

三个子域共享父域 Cookie，“已登录”状态跨子域生效，但互相都不同源。本课要回答：写操作靠哪一层挡住伪造请求，读操作靠哪一层挡住别家网站偷看。

## 核心概念

*源*（origin）由协议、主机、端口三元组组成，三者完全相同才同源。`http://a.example` 与 `https://a.example` 不同源，`https://a.example` 与 `https://a.example:8443` 也不同源；路径不参与判断。

*同源策略*是浏览器实施的一组限制：一个源的文档默认不能读取另一个源的响应，不能读取对方 Cookie，也不能操作对方 DOM。它限制“读取”和“操作”，不限制“发出”——这是理解 CSRF 的关键。

*CORS*（跨源资源共享）是一套响应头协议，让服务端声明“哪些源可以读取我的响应”，是同源策略的**受控豁免**，不是关闭它。

*预检请求*是浏览器在发送“非简单请求”前自动发出的一次 `OPTIONS` 探测，询问服务端是否允许真正的方法与头部。

*简单请求*可绕过预检：方法为 `GET`、`HEAD`、`POST` 之一，只用白名单头部，`Content-Type` 限于 `application/x-www-form-urlencoded`、`multipart/form-data`、`text/plain`。

*CSRF*（跨站请求伪造）是攻击者诱导已登录用户的浏览器，向目标站点发出状态变更请求，以受害者身份完成操作。

*SameSite* 是 Cookie 属性，控制跨站请求是否携带该 Cookie，取值为 `Strict`、`Lax`、`None`。

*CSRF Token* 是服务端签发、与会话绑定的随机值，由页面脚本显式放进请求，服务端逐次比对。

*XSS*（跨站脚本）是攻击者让恶意脚本在目标源内执行。脚本一旦在目标源里运行，自己就是“同源”，绕过方式极其直接。

*CSP*（内容安全策略）由响应头下发，限制页面只能加载和执行哪些来源的资源。

| 机制 | 实际防护对象 | 由谁执行 | 失效后的典型后果 |
| --- | --- | --- | --- |
| 同源策略 | 跨源读取响应与 Cookie、操作 DOM | 浏览器 | 任意站点读取用户数据 |
| CORS | 受控地放开同源限制 | 浏览器（依据响应头） | 白名单写宽 → 等同取消同源策略 |
| CSRF 防御 | 别的站点以用户身份发写请求 | 服务端 + 浏览器 | 静默退款、改密码、加地址 |
| XSS 防护 | 攻击者脚本在目标源内执行 | 输出编码 + CSP + 浏览器 | Cookie 被读、页面被接管 |

<u>CORS 不是 CSRF 防御手段</u>，<u>把 `Access-Control-Allow-Origin` 配严也不会让写接口变安全</u>。

## 工作原理

### 一次跨源请求要经过哪些判断

1. 页面脚本 `fetch` 到另一个源，浏览器先比较目标 URL 与当前文档的源。
2. 同源则直接放行，后续步骤全部跳过。
3. 不同源时判断是否属于简单请求：三条都符合才走“直接发送”分支，否则先发预检。
4. 预检是一条不带 Cookie、不带正文的 `OPTIONS`，附带 `Origin`、`Access-Control-Request-Method`、`Access-Control-Request-Headers`。
5. 服务端回以 `Allow-Origin` 等方法与头部白名单。浏览器比对来源、方法、自定义头部三条，全部满足才继续。
6. 预检通过后才发送真正的请求；若脚本显式要求携带凭据，此时才附加 Cookie。
7. 响应返回后浏览器再查 `Allow-Origin` 与 `Allow-Credentials`，通过才把响应体交给脚本，否则脚本只看到 `TypeError`。

<u>第 6 步和第 7 步必须分开记</u>：预检通过只代表“允许发”；在简单请求分支里，**请求会真实发出并可能产生副作用，浏览器只是不把响应交给脚本**。

| 响应头 | 作用 | 常见错误值 |
| --- | --- | --- |
| `Allow-Origin` | 声明允许读取的源 | `*`（配合凭据时无效）、回显任意 `Origin` |
| `Allow-Methods` | 预检中允许的方法 | 只写 `GET, POST`，漏掉 `PUT` |
| `Allow-Headers` | 预检中允许的请求头 | 漏掉自定义的 `X-CSRF-Token` |
| `Allow-Credentials` | 允许跨源携带 Cookie | 设为 `true` 却仍使用 `*` |
| `Access-Control-Max-Age` | 预检结果缓存秒数 | 过大导致策略变更迟迟不生效 |
| `Vary: Origin` | 缓存按 `Origin` 分别存储 | 漏写导致 CDN 把 A 源响应发给 B 源 |

### CSRF 的攻击链

1. 受害者在 `shop.qingkong.example` 登录，浏览器持有父域会话 Cookie。
2. 受害者访问攻击者页面，页面里有一个自动提交的表单，`action` 指向退款接口，方法 `POST`。
3. 表单提交属于简单请求，**不触发预检**；浏览器按域名规则自动附加 Cookie，请求带着合法会话发出。
4. 服务端看到方法、Cookie 和参数都合法，于是执行退款；响应是否交给攻击者页面，对结果毫无影响。

这条链需要四个前提：Cookie 能自动携带、参数可预测、服务端分不清来源、操作有副作用。防御就是逐个拆前提：`SameSite=Lax` 拆跨站携带，随机 Token 拆参数可预测，`Origin` 校验拆来源不可辨。<u>`Lax` 仍允许顶层导航的 `GET` 携带 Cookie</u>，把写操作做成 `GET` 会直接回到危险状态。

### XSS 为什么让前两道防线同时失效

脚本一旦在目标源页面里执行，读 `document.cookie`、读 CSRF Token、以受害者身份调用同源接口，全是同源操作，同源策略不介入。带 `HttpOnly` 的 Cookie 脚本读不到，但脚本仍可**代为发起请求**，让浏览器自动携带它。<u>所以 `HttpOnly` 降低的是“会话被偷走”的风险，不是“被冒用”的风险</u>。

## 架构与选型

| 场景 | 推荐方案 | 理由 | 不适用情形 |
| --- | --- | --- | --- |
| 前后端分离、必须跨子域 | 精确 CORS 白名单 | 保留同源策略，只放开必要接口 | 接口多、来源常变时维护成本高 |
| 前后端可同域部署 | 反向代理把 API 挂在 `/api` | 不需要 CORS，攻击面最小 | 已有 CDN 与灰度体系难改造 |
| 会话 Cookie + 写接口 | `SameSite=Lax` + CSRF Token | 两层独立机制，任一失效仍可拦住 | 必须真正跨站跳转、Cookie 必须跨站 |
| 纯令牌（`Authorization` 头） | 不加 CSRF Token，强化 XSS 防护 | 令牌不会自动携带 | 令牌存进可被脚本读取的位置 |
| 移动端或服务端调用 | 不实施 CORS | 不经过浏览器同源检查 | WebView 内嵌页面仍按浏览器处理 |
| 第三方组件嵌入 | 独立子域 + CSP 白名单 | 隔离来源，限制脚本访问范围 | 组件需读取宿主页面数据 |

选型依据是**先确认谁是信任边界**：调用方是浏览器脚本时，同源策略是唯一免费的隔离手段，任何放松都要逐条论证；调用方是服务端时，CORS 与其无关，边界落在身份认证与限流。写接口则用 `SameSite`、Token、`Origin` 三层校验，各挡一类情况。

## 最小示例

目标：用 Python 3 标准库起一个最小 CORS 端点，观察同一份响应头如何面对可信与恶意来源。环境 Python 3.8+，无第三方依赖。

```python
from http.server import BaseHTTPRequestHandler, HTTPServer

# 3. 白名单写死在服务端，不回显请求的 Origin
ALLOWED_ORIGIN = "https://shop.qingkong.example"

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        # 4. 预检：跨源非简单请求之前发出，不带 Cookie
        self.send_response(204)
        # 5. 只声明一个可信来源；带凭据时不能写 *
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        # 6. 列出允许的方法与自定义头，不用通配符
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
        # 7. 允许带 Cookie，上一行必须是具体来源
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Max-Age", "600")  # 8. 预检缓存 10 分钟
        self.end_headers()

    def do_POST(self):
        # 9. 读出正文，否则后续请求可能读到残留
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        # 10. 服务端不判断 Origin，拦截由浏览器完成
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # 11. 关闭默认访问日志，输出更干净

# 12. 只监听回环地址，不暴露到局域网
HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
```

保存为 `/tmp/cors_demo.py` 后启动，用 `curl` 扮演浏览器，以可信与恶意来源分别发起预检：

```bash
# 13. 可信来源：预检应当被允许
curl -i -s -X OPTIONS http://127.0.0.1:8000/refunds \
  -H "Origin: https://shop.qingkong.example" \
  -H "Access-Control-Request-Method: POST"

# 14. 恶意来源：对比响应头
curl -i -s -X OPTIONS http://127.0.0.1:8000/refunds \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: POST"
```

预期输出（两次完全相同，`Server` 与 `Date` 随环境变化）：

```text
HTTP/1.0 204 No Content
Server: BaseHTTP/0.6 Python/3.x
Date: <当前时间>
Access-Control-Allow-Origin: https://shop.qingkong.example
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
```

两条响应一模一样，这正是本例的核心：**服务端并没有“拒绝”恶意来源，它只是宣告了允许清单；真正拦截并丢弃响应的是浏览器**——绕过 CORS 只需不用浏览器。

## 动手实验

### 前置条件

Python 3.8 或以上，`curl` 可用。不需要浏览器、账号或密钥。

### 步骤

1. 将上一节代码保存为 `/tmp/cors_demo.py`。
2. 执行 `python3 /tmp/cors_demo.py`，让服务保持前台运行。
3. 另开终端执行第 13 条命令。
4. 再执行第 14 条命令。
5. 追加一条不带 `Origin` 的预检：`curl -i -s -X OPTIONS http://127.0.0.1:8000/refunds`。
6. 若有浏览器，在控制台执行 `fetch("http://127.0.0.1:8000/refunds", {method: "POST"})`。

### 预期结果

步骤 3 与步骤 4 的响应头完全相同；步骤 5 也一样，说明服务端根本不关心来源；步骤 6 抛出 `TypeError: Failed to fetch`，即使服务端返回 `200`，脚本也读不到响应体。

### 验证方法

对比三次 `curl` 输出是否逐字节一致。若步骤 4 出现 `Allow-Origin: https://evil.example`，说明代码被改成回显 `Origin`，这是最该避免的写法。

### 清理方法

按 `Ctrl+C` 停止服务，再执行 `rm /tmp/cors_demo.py` 清理。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 预检返回 `204`，正式请求仍被拦 | 正式响应漏发 `Allow-Origin` | 用 `curl -i` 分别看两条响应头 | 两个响应下发同一组 CORS 头 |
| 报错说 `X-CSRF-Token` 不在允许列表 | `Allow-Headers` 未列自定义头 | 看浏览器报错点名的头部 | 补上该头部，拼写与前端一致 |
| 带 Cookie 的请求总是失败 | 用了 `*`，或前端未设 `credentials` | 看响应有无 `Allow-Credentials: true` | 改为具体来源，前端设 `include` |
| 间歇性报错，刷新后偶尔正常 | 缺 `Vary: Origin`，缓存串源 | 对比 CDN 日志的 `Origin` 与命中记录 | 加上 `Vary: Origin` 并按该头分键 |
| 接口限制了来源仍被伪造调用 | 把 CORS 当访问控制，攻击方用脚本直连 | 用 `curl` 不带 `Origin` 调写接口 | 增加认证、CSRF Token 与来源校验 |
| 改 `SameSite` 后登录态丢失 | `Strict` 下跨站跳转不再携带 Cookie | 从外部链接进首屏看是否已登录 | 用 `Lax`，或先落到同站中转页 |

## 安全与生产注意事项

**<u>“读取请求 Origin 并原样回显到 `Access-Control-Allow-Origin`”等价于关闭同源策略。</u>** 这类代码联调时最省事，上线后任何站点都能带着用户 Cookie 读取订单和支付信息，后果是数据泄露而非报错。缓解方式是白名单静态比对：允许的源写进配置，精确匹配后下发。

**<u>用 CORS 保护写接口是无效防御，因为简单请求不经过预检也会被执行。</u>** 表单式 `POST` 照发不误，服务端的退款、改密码已经完成。缓解方式是写接口同时启用 `SameSite=Lax`、CSRF Token 与 `Origin` 校验。

**<u>XSS 一旦发生，同源策略与 CSRF Token 同时失效，`HttpOnly` 只保住 Cookie 不被读取、保不住被冒用。</u>** 缓解方式是在输出点做上下文相关编码、用 CSP 限制脚本来源、对富文本做白名单清洗，并把会话 Cookie 标为 `Secure`、`HttpOnly`、`SameSite=Lax`。评审时要把这三层当独立控制项验证。

## 本课总结

- 同源由协议、主机、端口共同判定，限制的是读取与操作，不是请求的发出。
- CORS 是同源策略的受控豁免，拦截由浏览器执行，服务端只声明清单。
- 预检只发生在非简单请求上；简单请求会真实执行，不能用 CORS 保护写接口。
- CSRF 利用 Cookie 自动携带，靠 `SameSite`、随机 Token 和来源校验三者拆掉攻击前提。
- XSS 让攻击者取得目标源内的执行权，前两道防线因此同时失效。

## 思考题

晴空商城计划把客服后台迁到独立域名 `cs.qingkong-tools.com`，以便外包团队访问，但“同意退款”仍需携带 `qingkong.example` 的 Cookie。请分析哪些防御会失效，并说明 Cookie 作用域、`SameSite`、CORS 白名单和 Token 校验各需怎样调整，哪一项必须改架构才能解决。

参考思路：跨注册域共享 Cookie 本身就不该做，优先给后台独立身份体系。若必须共享，`SameSite=None` 需要 `Secure` 且会把 Cookie 暴露给更多跨站场景，白名单要新增来源但绝不能回显，Token 需绑定新的会话。真正的架构问题是“信任边界随域名一起外移”：外包浏览器不再可信，应改为后端代理或独立授权服务。

## 小测

1. 下列哪一组 URL 与 `https://api.qingkong.example/orders` 同源？  
   A. `https://api.qingkong.example:443/refunds`　B. `http://api.qingkong.example/orders`　C. `https://shop.qingkong.example/orders`　D. `https://api.qingkong.example.evil.example/orders`

2. 关于预检请求，下列说法正确的是？  
   A. 所有跨源请求都会先发预检　B. 预检本身会携带用户 Cookie　C. 预检通过即代表正式请求一定成功　D. 预检用 `OPTIONS` 询问方法和头部是否被允许

3. 把 `Access-Control-Allow-Origin` 设为 `*` 同时设置 `Access-Control-Allow-Credentials: true`，浏览器会怎样处理？

4. CSRF 的四个成立前提中，`SameSite=Lax` 主要拆掉哪一个？

5. 场景题：开发同学说“订单查询已配 CORS 白名单，不用加 CSRF Token；退款接口是同一套 CORS，同样安全”。这个判断对吗？请分别评价两个接口。

## 答案与解析

1. **A。**端口省略时 `https` 默认为 `443`，A 与目标同源。B 协议不同；C 主机不同（`shop` 与 `api`）；D 主机是 `api.qingkong.example.evil.example`，属于完全不同的域。本题考“看起来像不等于同源”。

2. **D。**预检就是一条 `OPTIONS` 探测，列出将要使用的方法和头部。A 错在只有非简单请求才预检；B 错在预检不携带凭据，否则等于提前泄露身份；C 错在预检只说明“允许发”，正式响应仍要再过一次来源检查。

3. 浏览器拒绝这次跨源请求。规范规定携带凭据时 `Allow-Origin` 必须是具体来源；`Allow-Headers` 与 `Allow-Methods` 在凭据模式下也不能用 `*`。表现是脚本收到网络错误而非清晰提示，常被误判为“浏览器 bug”。

4. 拆掉的是“跨站请求也会自动携带 Cookie”。`Lax` 对跨站的 `POST`、`PUT`、`DELETE` 及子资源请求不携带 Cookie，只允许顶层导航的 `GET` 携带。它不解决参数可预测与来源不可辨，仍需 Token 与 `Origin` 校验。

5. **不对，但要分开评价。**订单查询是读操作，CORS 白名单确实对症。退款是写操作，CORS 几乎无效：表单式 `POST` 属于简单请求，不经预检就会被执行，服务端看到的是一个完全合法的已登录请求。正确做法是加 `SameSite=Lax`、CSRF Token 和 `Origin` 校验。

### 动手实验参考

合理结果与“预期输出”一致：三次 `curl` 输出逐字节相同。改动 `ALLOWED_ORIGIN` 后响应头会随之变化，但这仍只是“声明”而非访问控制——可补一条不带 `Origin` 的调用，说明服务端照常返回 `200`。

## 延伸阅读与下一课

- [MDN：同源策略](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
- [MDN：跨源资源共享（CORS）](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN：`Set-Cookie` 与 `SameSite`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [OWASP：CSRF 防御速查表](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 6265：HTTP 状态管理机制](https://www.rfc-editor.org/rfc/rfc6265)
- 返回[本单元目录](00-overview.md)。
- 回看上一课：[JSON、XML、CSV 与字符编码](06-json-xml-and-encoding.md)。
- 下一课：[curl 与网络诊断](08-curl-and-network-diagnostics.md)。
