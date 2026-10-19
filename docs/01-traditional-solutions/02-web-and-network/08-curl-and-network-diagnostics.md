---
title: curl 与网络诊断
slug: curl-and-network-diagnostics
module: traditional-solutions
stage: operate-and-optimize
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - cors-csrf-and-browser-security
outcomes:
  - 用 curl 的分段耗时变量拆解一次请求的 DNS、TCP、TLS、TTFB 与传输时间
  - 依据退出码与详细输出区分 DNS、连接、TLS 与重定向故障
  - 编写一份从便宜到昂贵、每步都有证据的连通性排查顺序
last_reviewed: 2026-10-19
---

# curl 与网络诊断

## 为什么需要学习

客服从 14:00 开始陆续报告“退款提交超时”。退款服务监控显示自身 P95 只有 180ms，支付商状态页写着“一切正常”，运维回复“链路没问题”。三方都没说谎，但没人知道时间花在哪里。常见的应对是加机器、加超时、加重试，而重试又让少数退款被受理两次。

> **核心结论：网络问题不靠猜测定位，而靠把一次请求切成几段可测量的时间，再用证据逐层排除。**

`curl` 的价值就在这里：它只用一条命令，就能把“很慢”“连不上”“证书报错”变成可以对比、可以贴进工单、可以进自动化脚本的数字。

## 学习目标

完成本课后，你能够：

- 用 `-v`、`-i`、`-I`、`-o /dev/null` 分别取得握手过程、响应头、状态行和干净的测量数据。
- 用 `--write-out` 的五个时间变量相减，算出 DNS、TCP、TLS、等待和传输五段耗时，指出瓶颈段。
- 根据退出码 `6`、`7`、`28`、`35`、`60` 判断故障层级，并说出下一步的验证命令。
- 解释 `-L` 对请求方法、请求体和凭证的影响，说明为什么诊断时先不加 `-L`。
- 在私有 CA 场景下用 `--cacert` 建立信任，而不是用 `-k` 关闭校验。

## 前置知识

- 回看上一课：[CORS、CSRF 与浏览器安全](07-cors-csrf-and-browser-security.md)。
- 知道 HTTP 请求由方法、路径、请求头与可选请求体组成，响应由状态行、响应头与响应体组成。
- 知道域名先解析成 IP，再在 IP 与端口上建立 TCP 连接。
- 能在终端切换目录、编辑文件、用 `Ctrl+C` 结束前台进程。

## 业务场景

晴空商城的退款集成服务调用支付商的 `POST /v2/refunds`，客服工作台再调用内部退款 API。高峰期页面报“请求超时”，客服点重试，同一笔退款于是出现两条受理记录。会上有四种说法：客服说系统慢，开发说监控正常，运维说链路没问题，支付商说接口可用。

架构师需要把这些说法换成可验证的问题：

- 超时发生在哪一段——域名解析、TCP 建连排队、TLS 握手、支付商返回首字节，还是响应体下载？
- 为什么浏览器能打开支付商后台，而跳板机上的脚本报证书错误？
- 为什么给脚本加上 `-L` 之后，登录态就丢了？

本单元的定位在这里：把疑问变成跳板机上能跑的一条命令和一组数字，为后续反向代理与 CDN 排查提供起点。

## 核心概念

*curl* 是命令行 HTTP 客户端，它把一次请求的每个阶段暴露成可观测的输出，因此适合做“听诊器”而不是压测工具。

*耗时分解*指 `--write-out`（简写 `-w`）输出的一组时间变量。关键在于它们是**从请求开始计算的累计时间**，必须相减才是单段耗时。

*TTFB*（time to first byte）是从发出请求到收到响应第一个字节的时间，包含服务端排队、业务计算和网络往返。<u>它不是“服务端处理时间”。</u>

*退出码*是 curl 用数字表达的失败层级。4xx 和 5xx 在没有加 `-f` 时退出码仍为 0，所以 `$?` 只说明传输是否完成，不说明业务是否成功。

*重定向*是 3xx 加 `Location` 响应头；*跟随重定向*（`-L`）是客户端据此再发一次请求，因此主机、方法甚至凭证策略都可能改变。

*证书链*是从服务端证书逐级签名到受信任根证书的路径；*SNI*（Server Name Indication）是 TLS 握手中客户端声明的目标域名，同一 IP 托管多个站点时靠它选择证书。

| 观察对象 | 命令开关 | 回答的问题 | 常见误读 |
| --- | --- | --- | --- |
| 状态行与响应头 | `-i`、`-I` | 返回了什么，是否要求跳转 | 只看正文正常就以为一切正常 |
| 握手与协商过程 | `-v` | 解析到哪个 IP、TLS 版本、证书属于谁 | 把 `*` 开头的诊断行当成错误 |
| 分段耗时 | `-w '%{time_…}'` | 时间花在哪一段 | 把累计值当成单段值 |
| 失败层级 | `echo $?` 退出码 | 失败发生在 DNS、连接、TLS 还是传输 | 用退出码判断业务是否成功 |
| 实际连接目标 | `--resolve`、`--connect-to` | 是否打到预期节点 | 以为只能改 hosts 文件 |

## 工作原理

一次 `curl` 请求按下面的顺序推进，每一段都留下对应的观测值：

1. 读取 URL、配置文件与代理环境变量，确定主机、端口和协议。
2. 解析域名得到 A/AAAA 记录，结束时间写入 `time_namelookup`。
3. 与目标 IP 和端口完成 TCP 三次握手，结束时间写入 `time_connect`，其中已经包含 DNS 时间。
4. 对 HTTPS 发起 TLS 握手：ClientHello（含 SNI 与 ALPN）→ 服务端返回证书链 → 客户端校验有效期、域名和签发链 → 协商密钥 → 双方 Finished，结束时间写入 `time_appconnect`。
5. 发送请求行、请求头和请求体，结束时间写入 `time_pretransfer`。
6. 等待响应首字节，结束时间写入 `time_starttransfer`，这一段就是 TTFB。
7. 读取响应体直至结束，`time_total` 收尾。
8. 若状态码是 3xx 且启用了 `-L`，读取 `Location` 后重发请求，`num_redirects` 加一。<u>301/302 会把 `POST` 改写成 `GET` 并丢弃请求体，跨主机重定向还会默认剥离 `Authorization` 头</u>，所以“加 `-L` 掉登录态”是设计行为。

五段耗时的算法是：DNS 取 `time_namelookup`，TCP 取 `time_connect` 减 `time_namelookup`，TLS 取 `time_appconnect` 减 `time_connect`，等待取 `time_starttransfer` 减 `time_appconnect`，传输取 `time_total` 减 `time_starttransfer`；五段之和应接近 `time_total`。

失败时 curl 停止推进并返回退出码：`6` 解析失败、`7` 连接失败、`28` 超时、`35` 握手失败、`60` 证书校验失败、`47` 重定向超限、`52` 空响应。记分层比记数字有用：`6` 看 DNS，`7` 看端口与防火墙，`35`/`60` 看证书与协议，`28` 看分段耗时。

## 架构与选型

诊断工具各有边界，选错的代价是拿到一堆无法解释的数据。

| 工具 | 适用场景 | 不适用场景 | 选它的依据 |
| --- | --- | --- | --- |
| `curl -w` | 端到端分段耗时、可脚本化、可进巡检 | 浏览器专属行为（CORS 预检、JS 渲染） | 需要可复现的数字证据 |
| `curl -v` | 解析结果、TLS 版本、证书主体与有效期、实际请求头 | 高频轮询，输出噪声大 | 需要确认“到底发了什么” |
| `openssl s_client` | 只测 TLS：证书链、SNI、协议版本、过期时间 | HTTP 层问题 | curl 报 `35`/`60` 但网络可达 |
| `dig` | DNS 记录、多台权威服务器结果是否一致 | 应用层超时 | 退出码是 `6` 或解析可疑 |
| `nc -vz` | 单端口连通性确认 | 需要 HTTP 语义 | 退出码是 `7`，先排除端口封锁 |
| `tcpdump` | 重传、RST、丢包、真实报文 | 常规排障；含敏感数据的流量 | 前几层正常却仍偶发失败 |
| 浏览器开发者工具 | 前端真实体验、CORS、缓存 | 服务间调用 | 问题只在浏览器里复现 |

选型顺序从便宜到昂贵：先 `-w` 定位到段，再 `-v` 看协商，再用 `dig`、`nc`、`openssl` 拆层，最后抓包。只有浏览器能复现的问题别用 curl 硬模拟，那会漏掉 CORS 与 Cookie 策略。

## 最小示例

要解决的问题：本地起一个“等 300ms 再 302 跳转”的服务，一条命令同时看清重定向行为和耗时分布。环境为 Python 3.9+ 与 curl 7.68+，只用回环地址，不需要外网。

先保存为 `slow_redirect.py`：

```python
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slow":
            time.sleep(0.30)                        # 模拟处理耗时，让 TTFB 可观测
            self.send_response(302)                 # 先返回重定向，暴露 -L 的差异
            self.send_header("Location", "/final")  # 相对路径，第二跳仍在同一服务内
            self.end_headers()                      # 302 没有响应体，必须显式结束头部
        elif self.path == "/final":
            body = json.dumps({"status": "paid", "order": "SK-1001"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))  # 让 curl 知道何时读完
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)                    # 便于确认地址是否打对

    def log_message(self, fmt, *args):
        pass  # 关掉访问日志，避免终端里的测量输出被干扰


ThreadingHTTPServer(("127.0.0.1", 8099), Handler).serve_forever()  # 只监听回环，不对外暴露
```

终端 A 运行 `python3 slow_redirect.py`，终端 B 执行：

```bash
curl -sS -o /dev/null \
  -w 'code=%{http_code} redirects=%{num_redirects} dns=%{time_namelookup}s tcp=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  http://127.0.0.1:8099/slow
```

预期输出（本机实测，量级一致）：

```text
code=302 redirects=0 dns=0.000124s tcp=0.000340s tls=0.000000s ttfb=0.306165s total=0.306197s
```

`-s` 关进度条，`-S` 保留错误，`-o /dev/null` 只留测量值。`dns` 与 `tcp` 都是亚毫秒级，解析与建连正常；`tls` 为 0 是因为明文 HTTP；`ttfb` 约 306ms 正好被 `sleep(0.30)` 吃掉，说明瓶颈在服务端；`total` 约等于 `ttfb`，没有传输成本。这就是一次完整的分层归因。

再加 `-L` 重跑：

```bash
curl -sS -L -o /dev/null -w 'code=%{http_code} redirects=%{num_redirects} total=%{time_total}s url=%{url_effective}\n' http://127.0.0.1:8099/slow
```

预期输出：

```text
code=200 redirects=1 total=0.306431s url=http://127.0.0.1:8099/final
```

两次总耗时几乎一样，因为第二跳不再等待；变的是 `code`、`redirects` 和 `url_effective`。这就是本课的习惯：**先不加 `-L` 看原始响应，再加 `-L` 看最终落点**，否则会把 302 之后那一跳算进接口耗时。

## 动手实验

前置条件：macOS 或 Linux 终端；`curl --version` 正常输出版本；`python3 --version` 为 3.9 以上；只需回环地址，不需要外网和真实凭据。

1. 把上一节的 `slow_redirect.py` 保存到临时目录，执行 `python3 slow_redirect.py`，保持前台运行。
2. 另开终端，运行不带 `-L` 的 `-w` 命令，记录 `code`、`redirects`、`ttfb`、`total`。
3. 加上 `-L` 重跑，对比 `redirects` 与 `url_effective` 的变化。预期 `redirects` 由 0 变 1，`url_effective` 指向 `/final`。
4. 用 `curl -sS -i http://127.0.0.1:8099/slow` 看原始响应。预期第一行是 `HTTP/1.1 302 Found`，响应头含 `Location: /final`，且没有响应体。
5. 故意打断一层：`curl -sS http://127.0.0.1:8098/slow; echo "exit=$?"`，预期报 `curl: (7) Failed to connect to 127.0.0.1 port 8098` 且 `exit=7`；再执行 `curl -sS http://no-such-host.invalid/; echo "exit=$?"`，预期 `exit=6`。
6. 可选加测 TLS 一层（需要 `openssl`）：用 `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 1 -nodes -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"` 生成自签证书，再用 `ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)` 配合 `load_cert_chain` 把服务改到 `8443`。预期 `curl https://127.0.0.1:8443/` 返回 `exit=60` 并提示 `self signed certificate`；加 `--cacert cert.pem` 且改用 `https://localhost:8443/` 后返回 200；地址换回 `127.0.0.1` 则报 `no alternative certificate subject name matches target ipv4 address`。

验证方法：按“工作原理”里的公式把五段耗时相减，五段之和应接近 `time_total`；每个非零退出码都要能对应到 DNS、连接、TLS、传输中的某一层，并说出下一步用哪个工具。

清理方法：在运行服务的终端按 `Ctrl+C`，删除 `slow_redirect.py`（以及可选步骤产生的 `cert.pem`、`key.pem`），用 `lsof -i :8099` 确认没有残留进程。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| `curl: (6) Could not resolve host` | 域名拼错、DNS 配置错、容器内无解析器 | `dig +short 域名`、`getent hosts 域名` | 修 DNS；用 `--resolve 域名:443:IP` 跳过解析先验证链路 |
| `curl: (7) Failed to connect` | 端口未监听、安全组或防火墙拦截、服务已崩 | `nc -vz 主机 端口`、`ss -lntp` | 开放端口；确认监听地址不是仅 `127.0.0.1`；先恢复服务 |
| `curl: (60)` 证书错误但浏览器正常 | 自签或私有 CA、缺中间证书、信任库缺根证书 | `curl -v` 看 `SSL certificate verify`；`openssl s_client -connect 主机:443 -servername 域名 -showcerts` | 用 `--cacert` 指定内部根证书；服务端补中间证书；不要用 `-k` |
| `curl: (35)` 握手失败 | 协议版本不匹配、缺少 SNI、被中间设备重置 | 用 `--tlsv1.2`、`--http1.1` 分别复测 | 对齐协议版本；按域名而不是 IP 访问；请网络方确认设备策略 |
| `curl: (28)` 超时 | 无响应或整体过慢，未区分连接与传输 | 分别加 `--connect-timeout 3` 与 `--max-time 10` 复现 | 按 `-w` 分段定位：连接超时查网络，TTFB 高查服务端 |
| `curl: (52) Empty reply from server` | 后端崩溃、代理提前断开、端口被非 HTTP 服务占用 | `-v` 看是否收到状态行；查服务端日志 | 修复服务；确认端口与协议一致 |
| 返回 200 但内容是登录页或为空 | 打到错误环境、会话过期、跟随重定向丢了凭证 | `-i` 看 `Location` 与 `Set-Cookie` | 用 `-b` 带 Cookie；跨主机重定向时显式重放凭证 |
| 脚本 403 而浏览器正常 | WAF 或反爬按 UA、TLS 指纹、请求头拦截 | `-A` 模拟 UA；用 `-v` 对比实际发出的请求头 | 申请白名单、补齐必要请求头；不要绕过安全控制 |
| `time_total` 大但 `ttfb` 很小 | 响应体过大、未压缩、带宽受限 | `-w '%{size_download} %{speed_download}'` | 启用压缩、缩小分页、检查出口带宽 |

## 安全与生产注意事项

**<u>不要用 `-k` 或 `--insecure` 关闭证书校验来“先通一下”。</u>**它关掉了对抗中间人攻击的唯一防线，而这样的命令极容易被复制进脚本和 Runbook 长期存活，后果是令牌与退款数据被静默劫持。正确做法是私有 CA 场景用 `--cacert` 指向内部根证书，或把根证书装入系统信任库。

**<u>不要把带 `Authorization`、`Cookie` 或 `-u 用户:口令` 的 curl 命令贴进工单、聊天记录或提交进仓库。</u>**这些内容会落进 shell 历史、进程列表和日志采集，等同于凭据泄露。缓解方式是改用 `--config -` 从权限 600 的文件或标准输入读取，测试与生产账号分离，并立即轮换已暴露的令牌。

**<u>不要在写操作上无脑加 `--retry` 或循环重试。</u>**超时的退款请求再发一次，缺少幂等键就会变成重复退款。缓解方式是写请求必须携带幂等键，重试只用于可安全重放的查询。

抓包也有边界：`tcpdump` 会把 Cookie、令牌和报文正文落盘，属于敏感数据，须授权并限定过滤条件与保留期限。

## 本课总结

- **curl 把“慢”拆成 DNS、TCP、TLS、首字节和传输五段可比较的数字**，而不是一个笼统的总时长。
- `-w` 输出累计时间，必须相减才是单段耗时；`ttfb` 包含服务端处理，不等于服务端耗时。
- 退出码表达失败层级：`6` 查 DNS、`7` 查端口与防火墙、`28` 查分段耗时、`35` 和 `60` 查证书与协议版本。
- `-L` 会改写方法、丢弃请求体、跨主机剥离凭证，所以先用原始 3xx 判断链路再决定跟随。
- 排查顺序从便宜到昂贵：`-w` → `-v` → `dig`、`nc`、`openssl` → 抓包，每步都要留下证据。

## 思考题

客服在 14:00 到 15:00 报告退款超时，重试后偶发重复受理；退款服务 P95 只有 180ms，支付商状态页正常。请设计排查顺序：每步用什么命令、期望看到什么数据、何时才升级到抓包，以及如何避免排查动作本身造成重复退款。

参考思路：先用 `-w` 对支付商接口取样约 20 次，对比失败与成功样本的 `time_connect`、`time_starttransfer`，判断抖动在建连段还是等待段。建连不稳就用 `dig` 比对解析结果、`nc` 抽测端口，怀疑 DNS 轮询或某个出口节点；只有等待段偏高则转向支付商限流与自身连接池。用 `-v` 确认是否命中同一 IP 与证书，排除灰度节点。网络层指标全正常仍失败时才抓包，并限定目标 IP、端口与时长、脱敏保存。全程用同一幂等键重放或查单核对，绝不重复提交退款。

## 小测

1. `-w` 输出 `time_connect=0.23s`、`time_namelookup=0.02s`，TCP 建连耗时约为多少？
   A. 0.23s　B. 0.21s　C. 0.02s　D. 无法计算
2. 下列哪种情况 `$?` 为 0 但业务其实已经失败？
   A. 域名解析失败　B. 返回 500 且未加 `-f`　C. 连接被拒绝　D. 证书过期
3. 私有 CA 签发的内部服务，正确的调试方式是？
   A. 加 `-k`　B. 用 `--cacert` 指定内部根证书　C. 改用 HTTP 访问　D. 只要浏览器能打开就不用管
4. 为什么加了 `-L` 之后，`POST` 请求可能变成 `GET`？
   A. curl 的缺陷　B. 301/302 的语义与客户端转换约定　C. 服务端强制改写　D. 缺少 `--max-redirs`
5. 场景判断题：某接口浏览器能正常打开，服务器上用 curl 却报 `curl: (60) SSL certificate problem: unable to get local issuer certificate`。可以直接判定“服务端证书坏了”，要求对方重签吗？

## 答案与解析

1. **B。**`time_connect` 是累计值，减去 `time_namelookup` 才是 TCP 建连耗时。选 A 把累计值当单段值，是本课最常见的误读；选 C 混淆了 DNS 段与连接段。
2. **B。**不加 `-f` 时 curl 把 HTTP 错误视为“已成功传输”，退出码仍为 0。A、C、D 分别返回 `6`、`7`、`60`，<u>所以退出码只能判断传输是否完成</u>。
3. **B。**`--cacert` 只是增加一个受信任的根证书，有效期、域名与签发链校验照旧。A 关闭全部校验，等于放弃中间人防护；C 把敏感数据降级为明文；D 混淆了浏览器与 curl 各自的信任库。
4. **B。**301/302 的历史语义允许客户端把非 `GET` 请求改写为 `GET` 并丢弃请求体，curl 遵循这一约定；要保留方法和请求体应使用 307 或 308。A 误判为缺陷，D 只涉及重定向次数上限。
5. 不能直接下结论。该错误说明找不到能签发服务端证书的根证书，可能是服务端缺中间证书，也可能是本机信任库缺内部根证书。用 `openssl s_client -connect 主机:443 -servername 域名 -showcerts` 看证书链是否完整，再用 `--cacert` 指向内部根证书复测；只有补齐信任后仍报错才怀疑服务端配置。

动手实验参考：五段耗时相减之和接近 `time_total`，且每个非零退出码都能对应到 DNS、连接、TLS、传输中的一层，即达到目标。若加 `-L` 后 `total` 明显大于两跳单次之和，结论应指向连接复用或中间节点，而非服务端处理变慢。

## 延伸阅读与下一课

- curl 官方手册，含全部参数与 `--write-out` 变量说明：https://curl.se/docs/manpage.html
- MDN 重定向指南，301/302 与 307/308 的语义差异：https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Guides/Redirections
- MDN 传输层安全（TLS）概览：https://developer.mozilla.org/zh-CN/docs/Web/Security/Transport_Layer_Security
- RFC 8446，TLS 1.3 协议标准：https://www.rfc-editor.org/rfc/rfc8446
- RFC 9110，HTTP 语义与状态码定义：https://www.rfc-editor.org/rfc/rfc9110

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[CORS、CSRF 与浏览器安全](07-cors-csrf-and-browser-security.md)。
- 下一课：[反向代理、负载均衡与 CDN](09-reverse-proxy-load-balancer-cdn.md)。
